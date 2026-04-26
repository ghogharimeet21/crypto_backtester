from typing import Dict, List
from data.models import Quote
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

    ############################################################################################################
    # Data Loading

    def load_default_data(self, csv: bool = True):
        CSV_PATH = "btcusdt_jan2026.csv"

        if csv:
            if os.path.exists(CSV_PATH):
                logger.info("Loading BTCUSDT Jan 2026 from local CSV...")
                df = read_csv(CSV_PATH)
                for _, row in df.iterrows():
                    meta_data.insert_quote(
                        int(row["date_int"]),
                        int(row["time_seconds"]),
                        "BTCUSDT",
                        Quote(
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                        ),
                    )
            else:
                logger.info("Fetching BTCUSDT Jan 2026 from Binance...")
                meta_data.load_data("BTCUSDT", "20260101", "20260201")
                # flatten meta_data into CSV so next startup loads from disk
                rows = []
                for date, times in meta_data.base_quotes.get("BTCUSDT", {}).items():
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
            meta_data.load_data("BTCUSDT", "20260101", "20260201")

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

    # Data Loading
    ############################################################################################################

    ############################################################################################################
    # meta_data ops

    def insert_quote(
        self, date: int, time: int, symbol: str, quote: Quote, timeframe: int = None
    ):
        quote.date = date
        quote.time = time

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

    # meta_data ops
    ############################################################################################################

    ############################################################################################################
    # meta_data resampling

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # resampling utils

    def get_best_base(self, symbol: str, target_tf: int):
        candidates = [60]

        if symbol in self.resampled_quotes:
            candidates += list(self.resampled_quotes[symbol].keys())

        valid = [t for t in candidates if target_tf % t == 0]

        if not valid:
            return None

        return max(valid)

    def resample_day(self, symbol: str, date: int, base_tf: int, target_tf: int):
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

        for i, t in enumerate(times):
            if len(bucket) == 0:
                bucket_open_time = t  # capture the opening time of this candle
            bucket.append(base_data[t])

            if len(bucket) == ratio:
                o = bucket[0]._open
                h = max(q._high for q in bucket)
                l = min(q._low for q in bucket)
                c = bucket[-1]._close
                v = sum(q._volume for q in bucket)

                self.insert_quote(
                    date,
                    bucket_open_time,  # opening time of candle (not closing)
                    symbol,
                    Quote(o, h, l, c, v),
                    timeframe=target_tf,
                )

                bucket.clear()
                bucket_open_time = None

    def get_not_available_dates(
        self, date_span: List[int], symbol: str, timeframe: int
    ) -> List[int]:
        available = self.available_dates.get(symbol, {}).get(timeframe, set())
        return [date for date in date_span if date not in available]

    # resampling utils
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def resample_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = None
    ):
        date_span = get_date_span(start_date, end_date)

        not_available_dates = self.get_not_available_dates(date_span, symbol, 60)

        if not_available_dates:
            start = min(not_available_dates)
            end = max(not_available_dates)
            logger.info(
                f"1min data is loading for symbol={symbol}, start_date={start}, end_date={end}"
            )
            self.load_data(symbol, start, end)

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

    # meta_data resampling
    ############################################################################################################


meta_data = MetaData()
