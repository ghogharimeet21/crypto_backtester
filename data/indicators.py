# data/indicators.py
#
# Indicator owns its own storage AND its own compute logic.
# It holds a back-reference to MetaData so it can fetch quotes
# via self._meta — without MetaData knowing anything about indicators.
#
# Usage:
#   meta_data.indicators.compute_rsi("BTCUSDT", 300, 14, 20260101, 20260131)
#   meta_data.indicators.get_rsi("BTCUSDT", 300, date, time)
#   meta_data.indicators.get_macd("BTCUSDT", 300, date, time)  # → {"line", "signal", "hist"}
#   meta_data.indicators.get_bb("BTCUSDT",  300, date, time)   # → {"upper", "mid", "lower"}

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Optional
import logging

if TYPE_CHECKING:
    from data.local import MetaData   # import only for type hints — avoids circular import

logger = logging.getLogger(__name__)


class Indicator:
    """
    Self-contained indicator engine.

    Storage shape for every attribute:
        symbol -> timeframe -> date -> time -> value

    Single-value  (sma, ema, rsi, atr)  →  value is float
    Multi-value   (macd, bb, stoch)     →  value is plain dict
    """

    def __init__(self, meta: "MetaData"):
        # back-reference to MetaData — used by compute_* to fetch quotes
        self._meta = meta

        # ── storage ───────────────────────────────────────────────────────────
        # single-value:  symbol -> timeframe -> date -> time -> float
        self.sma:  Dict[str, Dict[int, Dict[int, Dict[int, float]]]] = {}
        self.ema:  Dict[str, Dict[int, Dict[int, Dict[int, float]]]] = {}
        self.rsi:  Dict[str, Dict[int, Dict[int, Dict[int, float]]]] = {}
        self.atr:  Dict[str, Dict[int, Dict[int, Dict[int, float]]]] = {}

        # multi-value:   symbol -> timeframe -> date -> time -> dict
        self.macd:  Dict[str, Dict[int, Dict[int, Dict[int, Dict[str, float]]]]] = {}
        self.bb:    Dict[str, Dict[int, Dict[int, Dict[int, Dict[str, float]]]]] = {}
        self.stoch: Dict[str, Dict[int, Dict[int, Dict[int, Dict[str, float]]]]] = {}

    # =========================================================================
    # Internal storage helpers
    # =========================================================================

    def _set(self, store: dict, symbol: str, tf: int, date: int, time: int, value):
        store \
            .setdefault(symbol, {}) \
            .setdefault(tf, {}) \
            .setdefault(date, {})[time] = value

    def _get(self, store: dict, symbol: str, tf: int, date: int, time: int):
        return store.get(symbol, {}).get(tf, {}).get(date, {}).get(time)

    # =========================================================================
    # Setters  (private — called only from compute_* methods below)
    # =========================================================================

    def _set_sma(self, symbol, tf, date, time, value: float):
        self._set(self.sma, symbol, tf, date, time, value)

    def _set_ema(self, symbol, tf, date, time, value: float):
        self._set(self.ema, symbol, tf, date, time, value)

    def _set_rsi(self, symbol, tf, date, time, value: float):
        self._set(self.rsi, symbol, tf, date, time, value)

    def _set_atr(self, symbol, tf, date, time, value: float):
        self._set(self.atr, symbol, tf, date, time, value)

    def _set_macd(self, symbol, tf, date, time, *, line: float, signal: float, hist: float):
        self._set(self.macd, symbol, tf, date, time,
                  {"line": line, "signal": signal, "hist": hist})

    def _set_bb(self, symbol, tf, date, time, *, upper: float, mid: float, lower: float):
        self._set(self.bb, symbol, tf, date, time,
                  {"upper": upper, "mid": mid, "lower": lower})

    def _set_stoch(self, symbol, tf, date, time, *, k: float, d: float):
        self._set(self.stoch, symbol, tf, date, time, {"k": k, "d": d})

    # =========================================================================
    # Getters  (public — called from strategy code)
    # =========================================================================

    def get_sma(self, symbol: str, tf: int, date: int, time: int) -> Optional[float]:
        return self._get(self.sma, symbol, tf, date, time)

    def get_ema(self, symbol: str, tf: int, date: int, time: int) -> Optional[float]:
        return self._get(self.ema, symbol, tf, date, time)

    def get_rsi(self, symbol: str, tf: int, date: int, time: int) -> Optional[float]:
        return self._get(self.rsi, symbol, tf, date, time)

    def get_atr(self, symbol: str, tf: int, date: int, time: int) -> Optional[float]:
        return self._get(self.atr, symbol, tf, date, time)

    def get_macd(self, symbol: str, tf: int, date: int, time: int) -> Optional[dict]:
        return self._get(self.macd, symbol, tf, date, time)

    def get_bb(self, symbol: str, tf: int, date: int, time: int) -> Optional[dict]:
        return self._get(self.bb, symbol, tf, date, time)

    def get_stoch(self, symbol: str, tf: int, date: int, time: int) -> Optional[dict]:
        return self._get(self.stoch, symbol, tf, date, time)

    # =========================================================================
    # Internal quote fetcher — bridges to MetaData
    # =========================================================================

    def _get_quotes(self, symbol: str, timeframe: int,
                    start_date: int, end_date: int):
        """Ensure data is ready then return the quote series — all via self._meta."""
        self._meta.validate_relevant_quotes(symbol, start_date, end_date, timeframe)
        return self._meta.get_quotes_series(symbol, start_date, end_date, timeframe)

    # =========================================================================
    # Compute methods  (public — called from strategy code)
    # =========================================================================

    def compute_sma(self, symbol: str, timeframe: int, period: int,
                    start_date: int, end_date: int):
        """
        Simple Moving Average — rolling sum / period.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)

        if len(quotes) < period:
            logger.warning(f"SMA_{period}: not enough candles (have={len(quotes)}, need={period})")
            return

        rolling_sum = 0.0
        for i, q in enumerate(quotes):
            rolling_sum += q._close
            if i >= period:
                rolling_sum -= quotes[i - period]._close
            if i >= period - 1:
                self._set_sma(symbol, timeframe, q.date, q.time, rolling_sum / period)

    def compute_ema(self, symbol: str, timeframe: int, period: int,
                    start_date: int, end_date: int):
        """
        Exponential Moving Average.
        Formula : EMA = close * k + prev_ema * (1 - k)   k = 2 / (period + 1)
        Seed    : plain SMA of first `period` closes.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)

        if len(quotes) < period:
            logger.warning(f"EMA_{period}: not enough candles (have={len(quotes)}, need={period})")
            return

        k   = 2.0 / (period + 1)
        ema = sum(q._close for q in quotes[:period]) / period  # seed with SMA

        self._set_ema(symbol, timeframe, quotes[period - 1].date, quotes[period - 1].time, ema)

        for q in quotes[period:]:
            ema = q._close * k + ema * (1 - k)
            self._set_ema(symbol, timeframe, q.date, q.time, ema)

    def compute_rsi(self, symbol: str, timeframe: int, period: int,
                    start_date: int, end_date: int):
        """
        Relative Strength Index — Wilder's smoothing.
          1. Bar-by-bar price change.
          2. Seed avg_gain / avg_loss as plain average over first `period` changes.
          3. Wilder: avg = (prev * (period-1) + current) / period
          4. RSI = 100 - 100 / (1 + avg_gain / avg_loss)
             avg_loss == 0  →  RSI = 100 (pure uptrend).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)

        if len(quotes) < period + 1:
            logger.warning(f"RSI_{period}: not enough candles (have={len(quotes)}, need={period + 1})")
            return

        changes = [quotes[i]._close - quotes[i - 1]._close for i in range(1, len(quotes))]

        avg_gain = sum(max(c, 0)      for c in changes[:period]) / period
        avg_loss = sum(abs(min(c, 0)) for c in changes[:period]) / period

        def _rsi(ag, al):
            return 100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))

        self._set_rsi(symbol, timeframe, quotes[period].date, quotes[period].time, _rsi(avg_gain, avg_loss))

        for i in range(period, len(changes)):
            avg_gain = (avg_gain * (period - 1) + max(changes[i], 0))      / period
            avg_loss = (avg_loss * (period - 1) + abs(min(changes[i], 0))) / period
            self._set_rsi(symbol, timeframe, quotes[i + 1].date, quotes[i + 1].time, _rsi(avg_gain, avg_loss))

    def compute_macd(self, symbol: str, timeframe: int,
                     fast: int, slow: int, signal: int,
                     start_date: int, end_date: int):
        """
        MACD line  = EMA(fast) - EMA(slow)
        Signal     = EMA(MACD line, signal period)
        Histogram  = MACD line - Signal
        Stored as  : {"line": float, "signal": float, "hist": float}
        """
        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)
        closes = [q._close for q in quotes]

        if len(closes) < slow + signal:
            logger.warning(f"MACD_{fast}_{slow}_{signal}: not enough candles")
            return

        def _ema_series(values: list, p: int) -> list:
            out = [None] * (p - 1)
            k   = 2.0 / (p + 1)
            ema = sum(values[:p]) / p
            out.append(ema)
            for v in values[p:]:
                ema = v * k + ema * (1 - k)
                out.append(ema)
            return out

        fast_ema  = _ema_series(closes, fast)
        slow_ema  = _ema_series(closes, slow)
        macd_line = [
            (f - s) if (f is not None and s is not None) else None
            for f, s in zip(fast_ema, slow_ema)
        ]

        valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
        if len(valid) < signal:
            return

        k         = 2.0 / (signal + 1)
        sig_ema   = sum(v for _, v in valid[:signal]) / signal
        start_idx = valid[signal - 1][0]

        sig_values            = [None] * len(macd_line)
        sig_values[start_idx] = sig_ema

        for i, v in valid[signal:]:
            sig_ema       = v * k + sig_ema * (1 - k)
            sig_values[i] = sig_ema

        for i, q in enumerate(quotes):
            ml = macd_line[i]
            sv = sig_values[i]
            if ml is not None and sv is not None:
                self._set_macd(symbol, timeframe, q.date, q.time,
                               line=ml, signal=sv, hist=ml - sv)

    def compute_bb(self, symbol: str, timeframe: int,
                   period: int, std_dev: float,
                   start_date: int, end_date: int):
        """
        Bollinger Bands.
          mid   = SMA(period)
          std   = population std of rolling window  (ddof=0 — matches TradingView)
          upper = mid + std_dev * std
          lower = mid - std_dev * std
        Stored as : {"upper": float, "mid": float, "lower": float}
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)
        closes = [q._close for q in quotes]

        if len(closes) < period:
            logger.warning(f"BB_{period}: not enough candles (have={len(closes)}, need={period})")
            return

        for i in range(period - 1, len(closes)):
            window   = closes[i - period + 1: i + 1]
            mid      = sum(window) / period
            variance = sum((v - mid) ** 2 for v in window) / period
            band     = std_dev * (variance ** 0.5)
            self._set_bb(symbol, timeframe, quotes[i].date, quotes[i].time,
                         upper=mid + band, mid=mid, lower=mid - band)

    def compute_atr(self, symbol: str, timeframe: int, period: int,
                    start_date: int, end_date: int):
        """
        Average True Range — Wilder's smoothing.
          TR   = max(high-low, |high-prev_close|, |low-prev_close|)
          Seed = plain average of first `period` TRs.
          ATR  = (prev_atr * (period-1) + TR) / period
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)

        if len(quotes) < period + 1:
            logger.warning(f"ATR_{period}: not enough candles (have={len(quotes)}, need={period + 1})")
            return

        tr_pairs: List[tuple] = []
        for i in range(1, len(quotes)):
            q, prev = quotes[i], quotes[i - 1]
            tr = max(
                q._high - q._low,
                abs(q._high - prev._close),
                abs(q._low  - prev._close),
            )
            tr_pairs.append((q, tr))

        atr    = sum(v for _, v in tr_pairs[:period]) / period
        seed_q = tr_pairs[period - 1][0]
        self._set_atr(symbol, timeframe, seed_q.date, seed_q.time, atr)

        for q, tr in tr_pairs[period:]:
            atr = (atr * (period - 1) + tr) / period
            self._set_atr(symbol, timeframe, q.date, q.time, atr)

    def compute_stoch(self, symbol: str, timeframe: int,
                      k_period: int, d_period: int,
                      start_date: int, end_date: int):
        """
        Stochastic Oscillator.
          %K = (close - lowest_low) / (highest_high - lowest_low) * 100
          %D = SMA(%K, d_period)
        Stored as : {"k": float, "d": float}
        """
        if k_period <= 0 or d_period <= 0:
            raise ValueError("periods must be positive")

        quotes = self._get_quotes(symbol, timeframe, start_date, end_date)

        if len(quotes) < k_period:
            logger.warning(f"STOCH: not enough candles (have={len(quotes)}, need={k_period})")
            return

        k_values: List[float] = []

        for i in range(k_period - 1, len(quotes)):
            window       = quotes[i - k_period + 1: i + 1]
            highest_high = max(q._high for q in window)
            lowest_low   = min(q._low  for q in window)
            denom        = highest_high - lowest_low
            k            = 0.0 if denom == 0 else (quotes[i]._close - lowest_low) / denom * 100
            k_values.append((quotes[i], k))

        # %D = SMA of %K over d_period
        for i in range(len(k_values)):
            q, k = k_values[i]
            if i >= d_period - 1:
                d = sum(v for _, v in k_values[i - d_period + 1: i + 1]) / d_period
                self._set_stoch(symbol, timeframe, q.date, q.time, k=k, d=d)