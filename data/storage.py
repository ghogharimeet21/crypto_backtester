from typing import Dict
from data.models import Quote
from data.utils import shift_date, date_to_ms, split_datetime, hms_to_seconds
import logging
import requests

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

    def load_data(self, symbol: str, start_date: int, end_date: int, interval="1m"):
        start_ts = date_to_ms(start_date)
        end_ts = date_to_ms(end_date)

        logger.info(
            f"start Data Loading for symbol = {symbol} start_date = {start_date} end_date = {end_date}"
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
            data = response.json()

            if not data:
                break

            for row in data:
                utc = row[0]

                # safety check (very important)
                if utc >= end_ts:
                    logger.info(
                        f"Data loaded for symbol={symbol}, start_date={start_date}, end_date={end_date}"
                    )
                    return

                date_int, time_seconds = split_datetime(utc)

                _open = float(row[1])
                _high = float(row[2])
                _low = float(row[3])
                _close = float(row[4])
                _volume = float(row[5])

                self.insert_quote(
                    date_int,
                    time_seconds,
                    symbol,
                    Quote(_open, _high, _low, _close, _volume),
                )

            # move cursor forward (key step)
            current_start = data[-1][0] + 1

        logger.info(
            f"Data loaded for symbol={symbol}, start_date={start_date}, end_date={end_date}"
        )

    def insert_quote(
        self, date: int, time: int, symbol: str, quote: Quote, timeframe: int = None
    ):

        if (not timeframe) or timeframe == 60:
            if symbol not in self.base_quotes:
                self.base_quotes[symbol] = {}
                self.available_dates[symbol] = {}
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

    def resample_quotes(self, symbol: str, start_date: int, end_date: int, timeframe: int):

        if symbol not in self.base_quotes:
            self.load_data(symbol, shift_date(start_date, -1), shift_date(end_date, 1))

        if symbol not in self.resampled_quotes:
            self.resampled_quotes[symbol] = {}
        if timeframe not in self.resampled_quotes[symbol]:
            self.resampled_quotes[symbol][timeframe] = {}
        if symbol not in self.available_dates:
            self.available_dates[symbol] = {}
        if timeframe not in self.available_dates[symbol]:
            self.available_dates[symbol][timeframe] = set()
        if symbol not in self.resampled_info:
            self.resampled_info[symbol] = set()
        self.resampled_info[symbol].add(timeframe)

        sym_data = self.base_quotes[symbol]
        already_done = self.available_dates[symbol][timeframe]

        def needs_resampling(date: int) -> bool:
            return date not in already_done

        for date, day_data in sym_data.items():
            if date < start_date or date > end_date:
                continue
            if not day_data:
                continue
            if not needs_resampling(date):
                continue

            all_times = sorted(day_data)
            resampled_day = {}
            bucket_time = -1
            o = h = l = c = v = 0.0

            for t in all_times:
                q = day_data[t]
                b = (t // timeframe) * timeframe

                if b != bucket_time:
                    if bucket_time != -1:
                        resampled_day[bucket_time] = Quote(_open=o, _high=h, _low=l, _close=c, _volume=v)
                    bucket_time = b
                    o, h, l, c, v = q._open, q._high, q._low, q._close, q._volume
                else:
                    if q._high > h: h = q._high
                    if q._low < l:  l = q._low
                    c = q._close
                    v += q._volume

            if bucket_time != -1:
                resampled_day[bucket_time] = Quote(_open=o, _high=h, _low=l, _close=c, _volume=v)

            self.resampled_quotes[symbol][timeframe][date] = resampled_day
            already_done.add(date)

meta_data = MetaData()
