# data/local.py
from typing import Dict, List
from data.models import Quote
from data.indicators import Indicator
from data.utils import shift_date, date_to_ms, split_datetime, hms_to_seconds
import logging
import requests
import os
from pandas import read_csv, DataFrame
from engine.evaluator.utils import get_date_span

logger = logging.getLogger(__name__)

BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"


class MetaData:
    def __init__(self):
        # symbol -> date -> time -> quote
        self.base_quotes: Dict[str, Dict[int, Dict[int, Quote]]] = {}

        # symbol -> timeframe -> set_of_dates
        self.available_dates: Dict[str, Dict[int, set]] = {}

        # symbol -> timeframe -> date -> time -> quote
        self.resampled_quotes: Dict[str, Dict[int, Dict[int, Dict[int, Quote]]]] = {}

        # symbol -> [time_frame]
        self.resampled_info: Dict[str, set] = {}

        # Indicator gets a back-reference to self so it can fetch quotes on its own
        self.indicators: Indicator = Indicator(self)

    # =========================================================================
    # Data Loading
    # =========================================================================

    def load_default_data(self, csv: bool = True):
        CSV_PATH = "btcusdt_jan2026.csv"

        if csv:
            if os.path.exists(CSV_PATH):
                logger.info("Loading BTCUSDT Jan 2026 from local CSV...")
                df = read_csv(CSV_PATH)
                for _, row in df.iterrows():
                    d = int(row["date_int"])
                    t = int(row["time_seconds"])
                    self.insert_quote(
                        Quote(
                            d,
                            t,
                            "BTCUSDT",
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                        ),
                    )
            else:
                logger.info("Fetching BTCUSDT Jan 2026 from Binance...")
                self.load_data("BTCUSDT", "20260101", "20260201")
                rows = []
                for date, times in self.base_quotes.get("BTCUSDT", {}).items():
                    for time_sec, q in times.items():
                        rows.append(
                            {
                                "date_int": date,
                                "time_seconds": time_sec,
                                "open": q._open,
                                "high": q._high,
                                "low": q._low,
                                "close": q._close,
                                "volume": q._volume,
                            }
                        )
                DataFrame(rows).to_csv(CSV_PATH, index=False)
                logger.info(f"Saved {len(rows):,} candles to {CSV_PATH}")

            logger.info("Done.")
        else:
            logger.info("Fetching BTCUSDT Jan 2026 from Binance...")
            self.load_data("BTCUSDT", "20260101", "20260201")

    def load_data(self, symbol: str, start_date, end_date, interval="1m"):
        """Fetch 1-minute candles from Binance and insert them into base_quotes.

        end_date is exclusive — data up to but not including that date is loaded.
        Paginates automatically in chunks of 1 000 candles until end_date is reached.
        Accepts start_date / end_date as int (20260101) or str ("20260101").
        """
        start_ts = date_to_ms(start_date)
        end_ts = date_to_ms(end_date)

        logger.info(
            f"Starting data load: symbol={symbol}, start_date={start_date}, end_date={end_date}"
        )

        current_start = start_ts

        while current_start < end_ts:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_ts,
                "limit": 1000,
            }

            response = requests.get(BINANCE_HISTORICAL_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                raise RuntimeError(f"Binance API error for symbol={symbol}: {data}")

            if not data:
                break

            for row in data:
                utc = row[0]

                if utc >= end_ts:
                    logger.info(
                        f"Data load complete: symbol={symbol}, start_date={start_date}, end_date={end_date}"
                    )
                    return

                date_int, time_seconds = split_datetime(utc)

                self.insert_quote(
                    Quote(
                        date_int,
                        time_seconds,
                        symbol,
                        float(row[1]),
                        float(row[2]),
                        float(row[3]),
                        float(row[4]),
                        float(row[5]),
                    ),
                )

            current_start = data[-1][0] + 1

        logger.info(
            f"Data load complete: symbol={symbol}, start_date={start_date}, end_date={end_date}"
        )

    # =========================================================================
    # Quote Storage (insert / get)
    # =========================================================================

    def insert_quote(self, quote: Quote, timeframe: int = None):
        date, time, symbol = quote.date, quote.time, quote.symbol

        if (not timeframe) or timeframe == 60:
            if symbol not in self.base_quotes:
                self.base_quotes[symbol] = {}
                if symbol not in self.available_dates:
                    self.available_dates[symbol] = {}
                if 60 not in self.available_dates[symbol]:
                    self.available_dates[symbol][60] = set()
            if date not in self.base_quotes[symbol]:
                self.base_quotes[symbol][date] = {}
                if 60 not in self.available_dates[symbol]:
                    self.available_dates[symbol][60] = set()
                self.available_dates[symbol][60].add(date)
            if time not in self.base_quotes[symbol][date]:
                self.base_quotes[symbol][date][time] = quote

        else:
            if symbol not in self.resampled_quotes:
                self.resampled_quotes[symbol] = {}
                if symbol not in self.available_dates:
                    self.available_dates[symbol] = {}
            if timeframe not in self.resampled_quotes[symbol]:
                self.resampled_quotes[symbol][timeframe] = {}
                self.available_dates[symbol][timeframe] = set()
            if date not in self.resampled_quotes[symbol][timeframe]:
                self.resampled_quotes[symbol][timeframe][date] = {}
                self.available_dates[symbol][timeframe].add(date)
            if time not in self.resampled_quotes[symbol][timeframe][date]:
                self.resampled_quotes[symbol][timeframe][date][time] = quote

            if symbol not in self.resampled_info:
                self.resampled_info[symbol] = set()
            self.resampled_info[symbol].add(timeframe)

    def get_quote(
        self, symbol: str, date: int, time: int | str, timeframe: int = None
    ) -> Quote | None:
        if isinstance(time, str):
            time = hms_to_seconds(time)
        if not timeframe or timeframe == 60:
            return self.base_quotes.get(symbol, {}).get(date, {}).get(time)
        else:
            return (
                self.resampled_quotes.get(symbol, {})
                .get(timeframe, {})
                .get(date, {})
                .get(time)
            )

    def get_quotes_series(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = None
    ) -> List[Quote]:
        date_span = get_date_span(start_date, end_date)
        quotes: List[Quote] = []

        for date in date_span:
            if (not timeframe) or timeframe == 60:
                day_quotes = self.base_quotes.get(symbol, {}).get(date, {})
            else:
                day_quotes = (
                    self.resampled_quotes.get(symbol, {})
                    .get(timeframe, {})
                    .get(date, {})
                )

            for time in sorted(day_quotes.keys()):
                quotes.append(day_quotes[time])

        return quotes

    # =========================================================================
    # Availability Checks
    # =========================================================================

    def get_not_available_dates(
        self, date_span: List[int], symbol: str, timeframe: int
    ) -> List[int]:
        available = self.available_dates.get(symbol, {}).get(timeframe, set())
        return [date for date in date_span if date not in available]

    def validate_relevant_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int
    ):
        if timeframe == 60:
            date_span = get_date_span(start_date, end_date)
            missing_dates = self.get_not_available_dates(date_span, symbol, 60)
            if missing_dates:
                self.load_data(
                    symbol, min(missing_dates), shift_date(max(missing_dates), 1)
                )
        else:
            self.resample_quotes(symbol, start_date, end_date, timeframe)

    # =========================================================================
    # Resampling
    # =========================================================================

    def get_best_base(self, symbol: str, target_tf: int):
        """Return the largest available timeframe that evenly divides target_tf."""
        candidates = [60]

        if symbol in self.resampled_quotes:
            candidates += list(self.resampled_quotes[symbol].keys())

        valid = [t for t in candidates if target_tf % t == 0]

        if not valid:
            return None

        return max(valid)

    def resample_day(self, symbol: str, date: int, base_tf: int, target_tf: int):
        """Aggregate base_tf candles for a single day into target_tf candles."""
        if base_tf == 60:
            if symbol not in self.base_quotes or date not in self.base_quotes[symbol]:
                logger.warning(
                    f"resample_day: no 1-min data for symbol={symbol}, date={date} — skipping"
                )
                return
            base_data = self.base_quotes[symbol][date]
        else:
            if (
                symbol not in self.resampled_quotes
                or base_tf not in self.resampled_quotes[symbol]
                or date not in self.resampled_quotes[symbol][base_tf]
            ):
                logger.warning(
                    f"resample_day: no base data for symbol={symbol}, base_tf={base_tf}, date={date} — skipping"
                )
                return
            base_data = self.resampled_quotes[symbol][base_tf][date]

        times = sorted(base_data.keys())
        bucket: List[Quote] = []
        bucket_open_time: int = None
        ratio = target_tf // base_tf

        for t in times:
            if len(bucket) == 0:
                bucket_open_time = t
            bucket.append(base_data[t])

            if len(bucket) == ratio:
                self.insert_quote(
                    Quote(
                        date,
                        bucket_open_time,
                        symbol,
                        bucket[0]._open,
                        max(q._high for q in bucket),
                        min(q._low for q in bucket),
                        bucket[-1]._close,
                        sum(q._volume for q in bucket),
                    ),
                    timeframe=target_tf,
                )
                bucket.clear()
                bucket_open_time = None

        if bucket:
            logger.warning(
                f"resample_day: partial bucket ({len(bucket)} of {ratio} candles) "
                f"at end of day — symbol={symbol}, date={date}, target_tf={target_tf}. "
                f"Flushing as a partial candle."
            )
            self.insert_quote(
                Quote(
                    date,
                    bucket_open_time,
                    symbol,
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

        not_available_dates = self.get_not_available_dates(date_span, symbol, 60)
        if not_available_dates:
            start = min(not_available_dates)
            end = max(not_available_dates)
            logger.info(
                f"Fetching missing 1-min data: symbol={symbol}, start={start}, end={end}"
            )
            self.load_data(symbol, start, shift_date(end, 1))

        base_tf = self.get_best_base(symbol, timeframe)
        if base_tf is None:
            raise ValueError("No valid base timeframe found")

        for date in date_span:
            if (
                timeframe in self.resampled_quotes.get(symbol, {})
                and date in self.resampled_quotes[symbol][timeframe]
            ):
                continue

            self.resample_day(symbol, date, base_tf, timeframe)


meta_data = MetaData()
