# data/indicators.py

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
import logging

if TYPE_CHECKING:
    from data.local import MetaData

from data.models import Quote
from data.utils import shift_date

logger = logging.getLogger(__name__)


def _quote_in_range(date: int, start_date: int, end_date: int) -> bool:
    return start_date <= date <= end_date


class Indicator:
    def __init__(self, meta: "MetaData"):
        self._meta = meta

        # single-value:  symbol -> tf -> period -> date -> time -> float
        self.sma:  Dict[str, Dict[int, Dict[int, Dict[int, Dict[int, float]]]]] = {}
        self.ema:  Dict[str, Dict[int, Dict[int, Dict[int, Dict[int, float]]]]] = {}
        self.rsi:  Dict[str, Dict[int, Dict[int, Dict[int, Dict[int, float]]]]] = {}
        self.atr:  Dict[str, Dict[int, Dict[int, Dict[int, Dict[int, float]]]]] = {}

        # multi-value:   symbol -> tf -> params(tuple) -> date -> time -> Dict[str, float]
        self.macd:  Dict[str, Dict[int, Dict[Tuple, Dict[int, Dict[int, Dict[str, float]]]]]] = {}
        self.bb:    Dict[str, Dict[int, Dict[Tuple, Dict[int, Dict[int, Dict[str, float]]]]]] = {}
        self.stoch: Dict[str, Dict[int, Dict[Tuple, Dict[int, Dict[int, Dict[str, float]]]]]] = {}

    # =========================================================================
    # Internal storage helpers
    # =========================================================================

    def _set(self, store: dict, symbol: str, tf: int, key, date: int, time: int, value):
        """key is period (int) for single-value, tuple for multi-value."""
        store \
            .setdefault(symbol, {}) \
            .setdefault(tf, {}) \
            .setdefault(key, {}) \
            .setdefault(date, {})[time] = value

    def _get(self, store: dict, symbol: str, tf: int, key, date: int, time: int):
        return (
            store
            .get(symbol, {})
            .get(tf, {})
            .get(key, {})
            .get(date, {})
            .get(time)
        )

    # =========================================================================
    # Private setters  (called only from compute_* methods)
    # =========================================================================

    def _set_sma(self, symbol, tf, period, date, time, value: float):
        self._set(self.sma, symbol, tf, period, date, time, value)

    def _set_ema(self, symbol, tf, period, date, time, value: float):
        self._set(self.ema, symbol, tf, period, date, time, value)

    def _set_rsi(self, symbol, tf, period, date, time, value: float):
        self._set(self.rsi, symbol, tf, period, date, time, value)

    def _set_atr(self, symbol, tf, period, date, time, value: float):
        self._set(self.atr, symbol, tf, period, date, time, value)

    def _set_macd(self, symbol, tf, fast, slow, signal, date, time,
                  *, line: float, sig: float, hist: float):
        self._set(self.macd, symbol, tf, (fast, slow, signal), date, time,
                  {"line": line, "signal": sig, "hist": hist})

    def _set_bb(self, symbol, tf, period, std_dev, date, time,
                *, upper: float, mid: float, lower: float):
        self._set(self.bb, symbol, tf, (period, std_dev), date, time,
                  {"upper": upper, "mid": mid, "lower": lower})

    def _set_stoch(self, symbol, tf, k_period, d_period, date, time,
                   *, k: float, d: float):
        self._set(self.stoch, symbol, tf, (k_period, d_period), date, time,
                  {"k": k, "d": d})

    # =========================================================================
    # Public getters  (called from strategy code)
    # =========================================================================

    def get_sma(self, symbol: str, tf: int, period: int,
                date: int, time: int) -> Optional[float]:
        return self._get(self.sma, symbol, tf, period, date, time)

    def get_ema(self, symbol: str, tf: int, period: int,
                date: int, time: int) -> Optional[float]:
        return self._get(self.ema, symbol, tf, period, date, time)

    def get_rsi(self, symbol: str, tf: int, period: int,
                date: int, time: int) -> Optional[float]:
        return self._get(self.rsi, symbol, tf, period, date, time)

    def get_atr(self, symbol: str, tf: int, period: int,
                date: int, time: int) -> Optional[float]:
        return self._get(self.atr, symbol, tf, period, date, time)

    def get_macd(self, symbol: str, tf: int, fast: int, slow: int, signal: int,
                 date: int, time: int) -> Optional[Dict[str, float]]:
        return self._get(self.macd, symbol, tf, (fast, slow, signal), date, time)

    def get_bb(self, symbol: str, tf: int, period: int, std_dev: float,
               date: int, time: int) -> Optional[Dict[str, float]]:
        return self._get(self.bb, symbol, tf, (period, std_dev), date, time)

    def get_stoch(self, symbol: str, tf: int, k_period: int, d_period: int,
                  date: int, time: int) -> Optional[Dict[str, float]]:
        return self._get(self.stoch, symbol, tf, (k_period, d_period), date, time)

    # =========================================================================
    # Internal quote fetcher
    # =========================================================================

    @staticmethod
    def _extended_start(start_date: int, timeframe: int, min_prior_bars: int) -> int:
        """
        Shift start_date back far enough to load ~min_prior_bars candles at `timeframe`
        (24/7 crypto clock — uses 86400 s per day).
        """
        if min_prior_bars <= 0:
            return start_date
        bars_per_day = max(1, 86400 // timeframe)
        calendar_days = min_prior_bars // bars_per_day + 5
        return shift_date(start_date, -calendar_days)

    def _get_quotes(
        self,
        symbol: str,
        tf: int,
        start_date: int,
        end_date: int,
        *,
        warmup_bars: int = 0,
    ) -> List[Quote]:
        """Ensure data is ready then return quotes (optionally extended backward for warmup)."""
        ext = self._extended_start(start_date, tf, warmup_bars)
        self._meta.fill_relevant_quotes(symbol, ext, end_date, tf)
        return self._meta.get_quotes_series(symbol, ext, end_date, tf)

    # =========================================================================
    # Compute methods
    # =========================================================================

    def compute_sma(self, symbol: str, tf: int, period: int,
                    start_date: int, end_date: int):
        """
        Simple Moving Average — rolling sum / period.
        Warmup bars (i < period-1) are skipped — get_sma returns None for them.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=period
        )

        if not quotes:
            logger.warning(f"SMA_{period}: no quotes found for {symbol} tf={tf}")
            return

        rolling_sum = 0.0
        for i, q in enumerate(quotes):
            rolling_sum += q._close
            if i >= period:
                rolling_sum -= quotes[i - period]._close
            if i >= period - 1 and _quote_in_range(q.date, start_date, end_date):
                self._set_sma(symbol, tf, period, q.date, q.time,
                              rolling_sum / period)

    def compute_ema(self, symbol: str, tf: int, period: int,
                    start_date: int, end_date: int):
        """
        Exponential Moving Average.
        EMA = close * k + prev_ema * (1 - k)   k = 2 / (period + 1)
        Seed = SMA of first `period` closes.
        Warmup bars are skipped — get_ema returns None for them.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=period
        )

        if not quotes:
            logger.warning(f"EMA_{period}: no quotes found for {symbol} tf={tf}")
            return

        if len(quotes) < period:
            # still compute what we can once warmup is satisfied in future calls
            logger.warning(
                f"EMA_{period}: only {len(quotes)} candles — "
                f"need at least {period} to seed. No values stored."
            )
            return

        k   = 2.0 / (period + 1)
        ema = sum(q._close for q in quotes[:period]) / period

        q0 = quotes[period - 1]
        if _quote_in_range(q0.date, start_date, end_date):
            self._set_ema(symbol, tf, period, q0.date, q0.time, ema)

        for q in quotes[period:]:
            ema = q._close * k + ema * (1 - k)
            if _quote_in_range(q.date, start_date, end_date):
                self._set_ema(symbol, tf, period, q.date, q.time, ema)

    def compute_rsi(self, symbol: str, tf: int, period: int,
                    start_date: int, end_date: int):
        """
        RSI — Wilder's smoothing.
        Needs period+1 bars minimum to produce the first value.
        Warmup bars are skipped — get_rsi returns None for them.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=period + 1
        )

        if not quotes:
            logger.warning(f"RSI_{period}: no quotes found for {symbol} tf={tf}")
            return

        if len(quotes) < period + 1:
            logger.warning(
                f"RSI_{period}: only {len(quotes)} candles — "
                f"need at least {period + 1}. No values stored."
            )
            return

        changes = [
            quotes[i]._close - quotes[i - 1]._close
            for i in range(1, len(quotes))
        ]

        avg_gain = sum(max(c, 0)      for c in changes[:period]) / period
        avg_loss = sum(abs(min(c, 0)) for c in changes[:period]) / period

        def _rsi(ag, al):
            return 100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))

        # first valid RSI at index `period`
        q_r = quotes[period]
        if _quote_in_range(q_r.date, start_date, end_date):
            self._set_rsi(symbol, tf, period,
                          q_r.date, q_r.time,
                          _rsi(avg_gain, avg_loss))

        for i in range(period, len(changes)):
            avg_gain = (avg_gain * (period - 1) + max(changes[i], 0))      / period
            avg_loss = (avg_loss * (period - 1) + abs(min(changes[i], 0))) / period
            qn = quotes[i + 1]
            if _quote_in_range(qn.date, start_date, end_date):
                self._set_rsi(symbol, tf, period,
                              qn.date, qn.time,
                              _rsi(avg_gain, avg_loss))

    def compute_macd(self, symbol: str, tf: int,
                     fast: int, slow: int, signal: int,
                     start_date: int, end_date: int):
        """
        MACD line  = EMA(fast) - EMA(slow)
        Signal     = EMA(MACD line, signal period)
        Histogram  = MACD line - Signal
        Stored as  → {"line": float, "signal": float, "hist": float}
        Warmup bars (fewer than slow+signal candles) are skipped.
        """
        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=slow + signal
        )
        closes = [q._close for q in quotes]

        if not closes:
            logger.warning(f"MACD ({fast},{slow},{signal}): no quotes found for {symbol} tf={tf}")
            return

        if len(closes) < slow + signal:
            logger.warning(
                f"MACD ({fast},{slow},{signal}): only {len(closes)} candles — "
                f"need at least {slow + signal}. No values stored."
            )
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
            if (
                ml is not None
                and sv is not None
                and _quote_in_range(q.date, start_date, end_date)
            ):
                self._set_macd(symbol, tf, fast, slow, signal,
                               q.date, q.time,
                               line=ml, sig=sv, hist=ml - sv)

    def compute_bb(self, symbol: str, tf: int,
                   period: int, std_dev: float,
                   start_date: int, end_date: int):
        """
        Bollinger Bands.
        mid   = SMA(period)
        std   = population std of rolling window (ddof=0, matches TradingView)
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        Stored as → {"upper": float, "mid": float, "lower": float}
        Warmup bars are skipped.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=period
        )
        closes = [q._close for q in quotes]

        if not closes:
            logger.warning(f"BB ({period},{std_dev}): no quotes found for {symbol} tf={tf}")
            return

        if len(closes) < period:
            logger.warning(
                f"BB ({period},{std_dev}): only {len(closes)} candles — "
                f"need at least {period}. No values stored."
            )
            return

        for i in range(period - 1, len(closes)):
            qi = quotes[i]
            if not _quote_in_range(qi.date, start_date, end_date):
                continue
            window   = closes[i - period + 1: i + 1]
            mid      = sum(window) / period
            variance = sum((v - mid) ** 2 for v in window) / period
            band     = std_dev * (variance ** 0.5)
            self._set_bb(symbol, tf, period, std_dev,
                         qi.date, qi.time,
                         upper=mid + band, mid=mid, lower=mid - band)

    def compute_atr(self, symbol: str, tf: int, period: int,
                    start_date: int, end_date: int):
        """
        Average True Range — Wilder's smoothing.
        TR   = max(high-low, |high-prev_close|, |low-prev_close|)
        Seed = plain average of first `period` TRs.
        ATR  = (prev_atr * (period-1) + TR) / period
        Warmup bars are skipped.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=period + 1
        )

        if not quotes:
            logger.warning(f"ATR_{period}: no quotes found for {symbol} tf={tf}")
            return

        if len(quotes) < period + 1:
            logger.warning(
                f"ATR_{period}: only {len(quotes)} candles — "
                f"need at least {period + 1}. No values stored."
            )
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
        if _quote_in_range(seed_q.date, start_date, end_date):
            self._set_atr(symbol, tf, period, seed_q.date, seed_q.time, atr)

        for q, tr in tr_pairs[period:]:
            atr = (atr * (period - 1) + tr) / period
            if _quote_in_range(q.date, start_date, end_date):
                self._set_atr(symbol, tf, period, q.date, q.time, atr)

    def compute_stoch(self, symbol: str, tf: int,
                      k_period: int, d_period: int,
                      start_date: int, end_date: int):
        """
        Stochastic Oscillator.
        %K = (close - lowest_low) / (highest_high - lowest_low) * 100
        %D = SMA(%K, d_period)
        Stored as → {"k": float, "d": float}
        %D warmup bars (fewer than d_period %K values) are skipped.
        """
        if k_period <= 0 or d_period <= 0:
            raise ValueError("periods must be positive")

        quotes = self._get_quotes(
            symbol, tf, start_date, end_date, warmup_bars=k_period + d_period
        )

        if not quotes:
            logger.warning(f"STOCH ({k_period},{d_period}): no quotes found for {symbol} tf={tf}")
            return

        if len(quotes) < k_period:
            logger.warning(
                f"STOCH ({k_period},{d_period}): only {len(quotes)} candles — "
                f"need at least {k_period}. No values stored."
            )
            return

        k_values: List[tuple] = []

        for i in range(k_period - 1, len(quotes)):
            window       = quotes[i - k_period + 1: i + 1]
            highest_high = max(q._high for q in window)
            lowest_low   = min(q._low  for q in window)
            denom        = highest_high - lowest_low
            k            = 0.0 if denom == 0 else (quotes[i]._close - lowest_low) / denom * 100
            k_values.append((quotes[i], k))

        for i in range(len(k_values)):
            q, k = k_values[i]
            if i >= d_period - 1 and _quote_in_range(q.date, start_date, end_date):
                d = sum(v for _, v in k_values[i - d_period + 1: i + 1]) / d_period
                self._set_stoch(symbol, tf, k_period, d_period,
                                q.date, q.time, k=k, d=d)