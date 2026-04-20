from typing import Dict, Optional
import logging

import numpy as np
import pandas as pd
import requests

from data.models import Quote
from data.utils import date_to_ms, load_data, shift_date, split_datetime

logger = logging.getLogger(__name__)

BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"


class MetaData:
    def __init__(self):
        # symbol -> date -> time -> quote
        self.base_quotes: Dict[str, Dict[int, Dict[int, Quote]]] = {}
        # symbol -> timeframe -> date -> time -> quote
        self.resampled_quotes: Dict[str, Dict[int, Dict[int, Dict[int, Quote]]]] = {}
        # symbol -> {timeframe, ...}
        self.resampled_info: Dict[str, set] = {}

        # Per-symbol base DataFrame cache (invalidated on new base inserts)
        self._df_cache: Dict[str, Optional[pd.DataFrame]] = {}

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------


def load_data(self, symbol: str, start_date: int, end_date: int, interval="1m"):
    start_ts = date_to_ms(start_date)
    end_ts = date_to_ms(end_date)

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

            # print(Quote(_open, _high, _low, _close, _volume))

        # move cursor forward (key step)
        current_start = data[-1][0] + 1

    logger.info(
        f"Data loaded for symbol={symbol}, start_date={start_date}, end_date={end_date}"
    )

    def insert_quote(
        self,
        date: int,
        time: int,
        symbol: str,
        quote: Quote,
        timeframe: int = None,
    ):
        """Store a single quote.  timeframe=None or 60 → base (1-min) store."""
        if (not timeframe) or timeframe == 60:
            self.base_quotes.setdefault(symbol, {}).setdefault(date, {})[time] = quote
            self._df_cache[symbol] = None  # invalidate flat-df cache
        else:
            (
                self.resampled_quotes.setdefault(symbol, {})
                .setdefault(timeframe, {})
                .setdefault(date, {})[time]
            ) = quote
            self.resampled_info.setdefault(symbol, set()).add(timeframe)

    # ------------------------------------------------------------------
    # Unified getter
    # ------------------------------------------------------------------

    def get_quote(
        self,
        symbol: str,
        date: int,
        time: int,
        timeframe: int = 60,
    ) -> Optional[Quote]:
        """Retrieve a single OHLCV bar regardless of timeframe.

        Parameters
        ----------
        symbol    : e.g. "BTCUSDT"
        date      : YYYYMMDD int
        time      : seconds since midnight for the bar's open time
        timeframe : bar width in seconds  (default 60 = 1-min base data)

        Returns None if the bar doesn't exist.
        """
        if timeframe == 60:
            return self.base_quotes.get(symbol, {}).get(date, {}).get(time)
        return (
            self.resampled_quotes.get(symbol, {})
            .get(timeframe, {})
            .get(date, {})
            .get(time)
        )

    # ------------------------------------------------------------------
    # Internal: flat DataFrame builders
    # ------------------------------------------------------------------

    def _build_df_from_base(self, symbol: str) -> pd.DataFrame:
        """Flatten base_quotes[symbol] into a sorted DataFrame (cached)."""
        if self._df_cache.get(symbol) is not None:
            return self._df_cache[symbol]

        date_data = self.base_quotes[symbol]
        n = sum(len(v) for v in date_data.values())

        dates = np.empty(n, dtype=np.int32)
        times = np.empty(n, dtype=np.int32)
        opens = np.empty(n, dtype=np.float64)
        highs = np.empty(n, dtype=np.float64)
        lows = np.empty(n, dtype=np.float64)
        closes = np.empty(n, dtype=np.float64)
        volumes = np.empty(n, dtype=np.float64)

        idx = 0
        for date, time_dict in date_data.items():
            for time, q in time_dict.items():
                dates[idx] = date
                times[idx] = time
                opens[idx] = q._open
                highs[idx] = q._high
                lows[idx] = q._low
                closes[idx] = q._close
                volumes[idx] = q._volume
                idx += 1

        df = pd.DataFrame(
            {
                "date": dates,
                "time": times,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        df.sort_values(["date", "time"], inplace=True, ignore_index=True)

        self._df_cache[symbol] = df
        return df

    def _build_df_from_resampled(self, symbol: str, source_tf: int) -> pd.DataFrame:
        """Flatten resampled_quotes[symbol][source_tf] into a sorted DataFrame.

        No cache needed — resampled data is already small.
        """
        tf_data = self.resampled_quotes[symbol][source_tf]
        n = sum(len(v) for v in tf_data.values())

        dates = np.empty(n, dtype=np.int32)
        times = np.empty(n, dtype=np.int32)
        opens = np.empty(n, dtype=np.float64)
        highs = np.empty(n, dtype=np.float64)
        lows = np.empty(n, dtype=np.float64)
        closes = np.empty(n, dtype=np.float64)
        volumes = np.empty(n, dtype=np.float64)

        idx = 0
        for date, time_dict in tf_data.items():
            for time, q in time_dict.items():
                dates[idx] = date
                times[idx] = time
                opens[idx] = q._open
                highs[idx] = q._high
                lows[idx] = q._low
                closes[idx] = q._close
                volumes[idx] = q._volume
                idx += 1

        df = pd.DataFrame(
            {
                "date": dates,
                "time": times,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        df.sort_values(["date", "time"], inplace=True, ignore_index=True)
        return df

    # ------------------------------------------------------------------
    # Smart source selection
    # ------------------------------------------------------------------

    def _best_source_tf(self, symbol: str, target_tf: int) -> Optional[int]:
        """Return the largest already-resampled timeframe that:
          - is smaller than *target_tf*, AND
          - divides evenly into *target_tf*   (target_tf % source == 0)

        Using an evenly-divisible source guarantees that no source bar
        can straddle a target-bucket boundary, so OHLCV aggregation stays
        100% correct.

        Returns None if no such timeframe exists (fall back to 1-min base).

        Example
        -------
        target=600 (10 min), existing resampled={120, 300}
          300 % 600 == 0  →  candidates = [120, 300]  →  returns 300
          (2× fewer rows than base; 300 is chosen over 120 because it's larger)
        """
        existing = self.resampled_info.get(symbol, set())
        candidates = [tf for tf in existing if tf < target_tf and target_tf % tf == 0]
        return max(candidates) if candidates else None

    # ------------------------------------------------------------------
    # Resample
    # ------------------------------------------------------------------

    def resample_quotes(
        self,
        symbol: str,
        start_date: int,
        end_date: int,
        timeframe: int,
    ) -> None:
        """Resample OHLCV data for *symbol* into *timeframe*-second bars.

        Source selection (fastest first):
          1. Largest existing resampled tf that divides evenly into target
          2. 1-min base data  (fallback)

        Parameters
        ----------
        symbol     : e.g. "BTCUSDT"
        start_date : YYYYMMDD int  (inclusive)
        end_date   : YYYYMMDD int  (inclusive)
        timeframe  : target bar width in seconds  (e.g. 300 = 5 min, 3600 = 1 h)
        """
        if timeframe <= 60:
            raise ValueError("timeframe must be > 60 s (base resolution is 1 min)")

        # ── 1. Ensure base data exists ────────────────────────────────
        if symbol not in self.base_quotes:
            logger.info(f"No base data for {symbol}; loading from API …")
            load_data(symbol, shift_date(start_date, -1), end_date)

        if symbol not in self.base_quotes:
            logger.warning(f"Still no data for {symbol} after load — aborting.")
            return

        # ── 2. Pick the best source timeframe ────────────────────────
        source_tf = self._best_source_tf(symbol, timeframe)

        if source_tf:
            logger.info(
                f"Smart source: using {source_tf}s resampled data "
                f"instead of 1-min base  →  ~{timeframe // source_tf}× fewer rows"
            )
            df = self._build_df_from_resampled(symbol, source_tf)
        else:
            logger.info(f"Source: 1-min base data")
            df = self._build_df_from_base(symbol)

        # ── 3. Filter to requested date range ─────────────────────────
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        df = df.loc[mask].copy()

        if df.empty:
            logger.warning(f"No source bars for {symbol} in [{start_date}, {end_date}]")
            return

        # ── 4. Bucket assignment ───────────────────────────────────────
        #    bucket = floor(time / timeframe) * timeframe
        df["bucket"] = (df["time"] // timeframe) * timeframe

        # ── 5. Vectorised OHLCV aggregation ───────────────────────────
        agg = (
            df.groupby(["date", "bucket"], sort=False)
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .reset_index()
        )

        # ── 6. Write into self.resampled_quotes ───────────────────────
        sym_tf = self.resampled_quotes.setdefault(symbol, {}).setdefault(timeframe, {})

        for row in agg.itertuples(index=False):  # itertuples ≈ 10× faster than iterrows
            date = int(row.date)
            bucket = int(row.bucket)
            sym_tf.setdefault(date, {})[bucket] = Quote(
                row.open, row.high, row.low, row.close, row.volume
            )

        self.resampled_info.setdefault(symbol, set()).add(timeframe)

        logger.info(
            f"Resampled {len(agg)} bars  symbol={symbol}  "
            f"tf={timeframe}s  source={source_tf or 60}s  "
            f"range=[{start_date}, {end_date}]"
        )


meta_data = MetaData()
