from __future__ import annotations
from datetime import timedelta
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from logging import getLogger
from commons.utils import get_date_span, make_date_obj, shift_date
from data.models import Quote
from data.indicators.utils import quote_in_range
from data.indicators.enums import SOURCE, BAND

import talib
import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from data import MetaData


logger = getLogger(__name__)


class Indicator:
    def __init__(self, meta: "MetaData"):
        self._meta = meta

        # symbol -> timeframe -> source -> period -> date -> time -> value
        self.sma: Dict[
            str, Dict[int, Dict[SOURCE, Dict[int, Dict[int, Dict[int, float]]]]]
        ] = {}
        self.ema: Dict[
            str, Dict[int, Dict[SOURCE, Dict[int, Dict[int, Dict[int, float]]]]]
        ] = {}
        self.rsi: Dict[
            str, Dict[int, Dict[SOURCE, Dict[int, Dict[int, Dict[int, float]]]]]
        ] = {}
        self.vwap: Dict[
            str, Dict[int, Dict[SOURCE, Dict[int, Dict[int, Dict[int, float]]]]]
        ] = {}

        # symbol -> timeframe -> period -> std -> date -> time -> {upper, mid, lower}
        self.bb: Dict[
            str,
            Dict[
                int,
                Dict[
                    int, Dict[float, Dict[int, Dict[int, Dict[BAND, Optional[float]]]]]
                ],
            ],
        ] = {}


    def compute_sma(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        start_date: int,
        end_date: int,
        source: SOURCE = SOURCE.CLOSE,
    ):
        """
        Simple Moving Average via talib.SMA on `source`.
        Warmup bars (i < period-1) are stored as None.
        """

        if period <= 0:
            raise ValueError("period must be positive")

        df = self._meta.meta_utils._build_quote_df(symbol, timeframe, start_date, end_date)

        if df.empty:
            return

        source_col = f"_{source.value.lower()}"

        sma_values = talib.SMA(df[source_col].to_numpy(dtype="float64"), timeperiod=period)

        if symbol not in self.sma:
            self.sma[symbol] = {}
        if timeframe not in self.sma[symbol]:
            self.sma[symbol][timeframe] = {}
        if source not in self.sma[symbol][timeframe]:
            self.sma[symbol][timeframe][source] = {}
        if period not in self.sma[symbol][timeframe][source]:
            self.sma[symbol][timeframe][source][period] = {}

        target = self.sma[symbol][timeframe][source][period]

        for row, value in zip(df.itertuples(index=False), sma_values):
            row_date = row.date
            row_time = row.time

            if pd.isna(value):
                value = None

            if row_date not in target:
                target[row_date] = {}

            target[row_date][row_time] = value

    def get_sma(
        self,
        symbol: str,
        timeframe: int,
        source: SOURCE,
        period: int,
        date: int,
        time: int,
    ) -> Optional[float]:
        try:
            return self.sma[symbol][timeframe][source][period][date][time]
        except Exception as e:
            logger.error(str(e))

    def compute_ema(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        start_date: int,
        end_date: int,
        source: SOURCE = SOURCE.CLOSE,
    ):
        """
        Exponential Moving Average via talib.EMA on `source`.
        Warmup bars are stored as None.
        """

        if period <= 0:
            raise ValueError("period must be positive")

        df = self._meta.meta_utils._build_quote_df(symbol, timeframe, start_date, end_date)

        if df.empty:
            return

        source_col = f"_{source.value.lower()}"

        ema_values = talib.EMA(df[source_col].to_numpy(dtype="float64"), timeperiod=period)

        if symbol not in self.ema:
            self.ema[symbol] = {}
        if timeframe not in self.ema[symbol]:
            self.ema[symbol][timeframe] = {}
        if source not in self.ema[symbol][timeframe]:
            self.ema[symbol][timeframe][source] = {}
        if period not in self.ema[symbol][timeframe][source]:
            self.ema[symbol][timeframe][source][period] = {}

        target = self.ema[symbol][timeframe][source][period]

        for row, value in zip(df.itertuples(index=False), ema_values):
            row_date = row.date
            row_time = row.time

            if pd.isna(value):
                value = None

            if row_date not in target:
                target[row_date] = {}

            target[row_date][row_time] = value

    def get_ema(
        self,
        symbol: str,
        timeframe: int,
        source: SOURCE,
        period: int,
        date: int,
        time: int,
    ) -> Optional[float]:
        try:
            return self.ema[symbol][timeframe][source][period][date][time]
        except Exception as e:
            logger.error(str(e))

    def compute_rsi(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        start_date: int,
        end_date: int,
        source: SOURCE = SOURCE.CLOSE,
    ):
        """
        Relative Strength Index via talib.RSI on `source`.
        Warmup bars are stored as None. Values range 0-100.
        """

        if period <= 0:
            raise ValueError("period must be positive")

        df = self._meta.meta_utils._build_quote_df(symbol, timeframe, start_date, end_date)

        if df.empty:
            return

        source_col = f"_{source.value.lower()}"

        rsi_values = talib.RSI(df[source_col].to_numpy(dtype="float64"), timeperiod=period)

        if symbol not in self.rsi:
            self.rsi[symbol] = {}
        if timeframe not in self.rsi[symbol]:
            self.rsi[symbol][timeframe] = {}
        if source not in self.rsi[symbol][timeframe]:
            self.rsi[symbol][timeframe][source] = {}
        if period not in self.rsi[symbol][timeframe][source]:
            self.rsi[symbol][timeframe][source][period] = {}

        target = self.rsi[symbol][timeframe][source][period]

        for row, value in zip(df.itertuples(index=False), rsi_values):
            row_date = row.date
            row_time = row.time

            if pd.isna(value):
                value = None

            if row_date not in target:
                target[row_date] = {}

            target[row_date][row_time] = value

    def get_rsi(
        self,
        symbol: str,
        timeframe: int,
        source: SOURCE,
        period: int,
        date: int,
        time: int,
    ) -> Optional[float]:
        try:
            return self.rsi[symbol][timeframe][source][period][date][time]
        except Exception as e:
            logger.error(str(e))

    def compute_vwap(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        start_date: int,
        end_date: int,
        source: SOURCE = SOURCE.CLOSE,
    ):
        """
        Rolling Volume Weighted Average Price (TradingView-style "Moving VWAP"):
        rolling_sum(source * volume, period) / rolling_sum(volume, period).

        Not anchored/reset per day — continuous rolling window across the
        full date span, same as SMA/EMA/RSI. talib has no native VWAP
        function, so this is computed manually via numpy cumulative sums.
        Warmup bars (i < period-1) are stored as None.
        """

        if period <= 0:
            raise ValueError("period must be positive")

        df = self._meta.meta_utils._build_quote_df(symbol, timeframe, start_date, end_date)

        if df.empty:
            return

        source_col = f"_{source.value.lower()}"

        price = df[source_col].to_numpy(dtype="float64")
        volume = df["_volume"].to_numpy(dtype="float64")

        pv = price * volume

        # Rolling sums via cumulative sum difference — O(n), avoids a
        # manual Python loop over every window.
        cum_pv = np.cumsum(pv)
        cum_vol = np.cumsum(volume)

        vwap_values = np.full(len(df), np.nan, dtype="float64")

        for i in range(period - 1, len(df)):
            if i == period - 1:
                window_pv = cum_pv[i]
                window_vol = cum_vol[i]
            else:
                window_pv = cum_pv[i] - cum_pv[i - period]
                window_vol = cum_vol[i] - cum_vol[i - period]

            if window_vol != 0:
                vwap_values[i] = window_pv / window_vol

        if symbol not in self.vwap:
            self.vwap[symbol] = {}
        if timeframe not in self.vwap[symbol]:
            self.vwap[symbol][timeframe] = {}
        if source not in self.vwap[symbol][timeframe]:
            self.vwap[symbol][timeframe][source] = {}
        if period not in self.vwap[symbol][timeframe][source]:
            self.vwap[symbol][timeframe][source][period] = {}

        target = self.vwap[symbol][timeframe][source][period]

        for row, value in zip(df.itertuples(index=False), vwap_values):
            row_date = row.date
            row_time = row.time

            if pd.isna(value):
                value = None

            if row_date not in target:
                target[row_date] = {}

            target[row_date][row_time] = value

    def get_vwap(
        self,
        symbol: str,
        timeframe: int,
        source: SOURCE,
        period: int,
        date: int,
        time: int,
    ) -> Optional[float]:
        try:
            return self.vwap[symbol][timeframe][source][period][date][time]
        except Exception as e:
            logger.error(str(e))


    def compute_bb(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        std: float,
        start_date: int,
        end_date: int,
        source: SOURCE = SOURCE.CLOSE,
    ):
        """
        Bollinger Bands via talib.BBANDS on `source`.

        Stores {BAND.UPPER: ..., BAND.MID: ..., BAND.LOWER: ...} per
        (date, time) — enum keys, same convention as SOURCE, instead of
        raw "upper"/"mid"/"lower" strings.
        Warmup bars (i < period-1) are stored as None for all three keys.
        matype is left at talib's default (SMA basis), matching how every
        other indicator here defers to talib's own defaults rather than
        re-implementing them.
        """

        if period <= 0:
            raise ValueError("period must be positive")
        if std <= 0:
            raise ValueError("std must be positive")

        df = self._meta.meta_utils._build_quote_df(
            symbol, timeframe, start_date, end_date
        )

        if df.empty:
            return

        source_col = f"_{source.value.lower()}"

        upper, mid, lower = talib.BBANDS(
            df[source_col].to_numpy(dtype="float64"),
            timeperiod=period,
            nbdevup=std,
            nbdevdn=std,
        )

        if symbol not in self.bb:
            self.bb[symbol] = {}
        if timeframe not in self.bb[symbol]:
            self.bb[symbol][timeframe] = {}
        if period not in self.bb[symbol][timeframe]:
            self.bb[symbol][timeframe][period] = {}
        if std not in self.bb[symbol][timeframe][period]:
            self.bb[symbol][timeframe][period][std] = {}

        target = self.bb[symbol][timeframe][period][std]

        for row, u, m, l in zip(df.itertuples(index=False), upper, mid, lower):
            row_date = row.date
            row_time = row.time

            value = {
                BAND.UPPER: None if pd.isna(u) else u,
                BAND.MID: None if pd.isna(m) else m,
                BAND.LOWER: None if pd.isna(l) else l,
            }

            if row_date not in target:
                target[row_date] = {}

            target[row_date][row_time] = value

    def get_bb(
        self,
        symbol: str,
        timeframe: int,
        period: int,
        std: float,
        date: int,
        time: int,
    ) -> Optional[Dict[BAND, Optional[float]]]:
        try:
            return self.bb[symbol][timeframe][period][std][date][time]
        except Exception as e:
            logger.error(str(e))