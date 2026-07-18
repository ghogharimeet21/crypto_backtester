from data.models import Quote, Underlying
from commons.utils import hms_to_seconds, get_date_span, shift_date
from logging import getLogger
import pandas as pd
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from data import MetaData

logger = getLogger(__name__)


class MetaUtils:
    def __init__(self, meta: "MetaData"):
        self._meta = meta

    def insert_quote(self, quote: Quote, timeframe: int = 60):

        date, time, symbol = quote.date, quote.time, quote.underlying.symbol
        if symbol not in self._meta.quotes:
            self._meta.quotes[symbol] = {}
        if timeframe not in self._meta.quotes[symbol]:
            self._meta.quotes[symbol][timeframe] = {}
        if date not in self._meta.quotes[symbol][timeframe]:
            self._meta.quotes[symbol][timeframe][date] = {}
        if time not in self._meta.quotes[symbol][timeframe][date]:
            self._meta.quotes[symbol][timeframe][date][time] = quote

    def get_quote(
        self, symbol: str, date: int, time: int | str, timeframe: int = 60
    ) -> Quote | None:
        if isinstance(time, str):
            time = hms_to_seconds(time)
        return (
            self._meta.quotes.get(symbol, {}).get(timeframe, {}).get(date, {}).get(time)
        )

    def get_quotes_series(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = 60
    ) -> List[Quote]:
        quotes: List[Quote] = []
        for date in get_date_span(start_date, end_date):
            day_quotes = (
                self._meta.quotes.get(symbol, {}).get(timeframe, {}).get(date, {})
            )
            for time in sorted(day_quotes.keys()):
                quotes.append(day_quotes[time])
        return quotes

    def get_not_available_dates(
        self, start_date: int, end_date: int, symbol: str, timeframe: int
    ) -> List[int]:
        """
        Returns every date in [start_date, end_date] that isn't already
        cached for symbol/timeframe. If nothing is cached at all, that
        correctly means the entire span is missing.
        """
        available = self._meta.quotes.get(symbol, {}).get(timeframe, {}).keys()
        return [d for d in get_date_span(start_date, end_date) if d not in available]

    def fill_relevant_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int
    ):
        if timeframe == 60:
            missing = self.get_not_available_dates(
                start_date, end_date, symbol, 60
            )
            if missing:
                self._meta.data_loader.spot_feed.load_data(
                    symbol,
                    shift_date(min(missing), -5),
                    shift_date(max(missing), 5),
                )
        else:
            # resample_quotes already ensures the required 1-min base data
            # is loaded before resampling, so no separate load call needed
            # here.
            self.resample_quotes(symbol, start_date, end_date, timeframe)

    def get_best_base(self, symbol: str, target_tf: int, date: int) -> int | None:
        # Defaults to [60] when nothing is loaded yet for this symbol,
        # assuming 1-min is always the native/base granularity.
        # Only tfs that actually have data for this specific date qualify —
        # a tf can be populated for other dates of this symbol while being
        # empty on `date`, which would otherwise pick a base with nothing
        # to resample from.
        available_tfs = [
            t
            for t, dates in self._meta.quotes.get(symbol, {}).items()
            if date in dates
        ] or [60]
        valid = [t for t in available_tfs if target_tf % t == 0]
        return max(valid) if valid else None

    def resample_day(self, symbol: str, date: int, base_tf: int, target_tf: int):
        """
        Buckets base_tf quotes into target_tf candles aligned to fixed time
        boundaries (t // target_tf * target_tf), not by raw count. This
        keeps buckets aligned to the standard exchange candle grid even
        when the base data has gaps, and ensures no bucket (including a
        partial one, first or last) is silently dropped.
        """

        base_data = self._meta.quotes.get(symbol, {}).get(base_tf, {}).get(date)
        if not base_data:
            logger.warning(
                f"resample_day: no data symbol={symbol}, base_tf={base_tf}, date={date} — skipping"
            )
            return

        times = sorted(base_data.keys())
        ratio = target_tf // base_tf

        buckets: dict = {}
        for t in times:
            bucket_open_time = (t // target_tf) * target_tf
            if bucket_open_time not in buckets:
                buckets[bucket_open_time] = []
            buckets[bucket_open_time].append(base_data[t])

        for bucket_open_time in sorted(buckets.keys()):
            bucket = buckets[bucket_open_time]

            if len(bucket) < ratio:
                logger.warning(
                    f"resample_day: partial bucket ({len(bucket)}/{ratio}) "
                    f"symbol={symbol}, date={date}, target_tf={target_tf}, "
                    f"bucket_open_time={bucket_open_time} — flushing anyway"
                )

            underlying = Underlying(symbol, "BINANCE")
            self.insert_quote(
                Quote(
                    date,
                    bucket_open_time,
                    underlying,
                    bucket[0]._open,
                    max(q._high for q in bucket),
                    min(q._low for q in bucket),
                    bucket[-1]._close,
                    sum(q._volume for q in bucket),
                ),
                timeframe=target_tf,
            )

    def resample_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = None
    ):
        if timeframe is None:
            raise ValueError("timeframe is required for resampling")
        if timeframe <= 0:
            raise ValueError("timeframe must be positive")

        date_span = get_date_span(start_date, end_date)
        missing = self.get_not_available_dates(start_date, end_date, symbol, 60)
        if missing:
            logger.info(f"Fetching missing 1-min data: symbol={symbol}")
            self._meta.data_loader.spot_feed.load_data(
                symbol,
                shift_date(min(missing), -5),
                shift_date(max(missing), 5),
            )

        for date in date_span:
            if date in self._meta.quotes.get(symbol, {}).get(timeframe, {}):
                continue
            base_tf = self.get_best_base(symbol, timeframe, date)
            if base_tf is None:
                raise ValueError("No valid base timeframe found")
            self.resample_day(symbol, date, base_tf, timeframe)



    def _build_quote_df(
        self,
        symbol: str,
        timeframe: int,
        start_date: int,
        end_date: int,
    ) -> pd.DataFrame:
        """
        Pulls all quotes for symbol/timeframe across the date span into a
        single DataFrame, sorted by (date, time).
        """

        self.fill_relevant_quotes(
            symbol, start_date, end_date, timeframe
        )

        date_span = get_date_span(start_date, end_date)

        df_list: List[dict] = []

        for date in date_span:
            try:
                times = sorted(self._meta.quotes[symbol][timeframe][date].keys())
            except KeyError:
                continue

            for time in times:
                quote = self.get_quote(symbol, date, time, timeframe)
                row = quote.to_dict()
                row["date"] = date
                row["time"] = time
                df_list.append(row)

        df = pd.DataFrame(df_list)

        if not df.empty:
            df = df.sort_values(["date", "time"]).reset_index(drop=True)

        return df