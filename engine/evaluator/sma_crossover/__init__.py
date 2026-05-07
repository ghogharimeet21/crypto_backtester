from .models import SmaCrossoverStrategy
from data.local import meta_data
import logging
from typing import List, Dict, Optional
from data.utils import seconds_to_hms

logger = logging.getLogger(__name__)


# =============================================================================
# Result models
# =============================================================================


class Trade:
    """A single completed round-trip trade."""

    def __init__(self, entry_date: int, entry_time: int, entry_price: float):
        self.entry_date = entry_date
        self.entry_time = entry_time
        self.entry_price = entry_price

        self.exit_date: Optional[int] = None
        self.exit_time: Optional[int] = None
        self.exit_price: Optional[float] = None
        self.pnl: Optional[float] = None  # absolute price difference
        self.pnl_pct: Optional[float] = None  # percentage return

    def close(self, exit_date: int, exit_time: int, exit_price: float):
        self.exit_date = exit_date
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.pnl = exit_price - self.entry_price
        self.pnl_pct = (self.pnl / self.entry_price) * 100

    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date,
            "entry_time": seconds_to_hms(self.entry_time),
            "entry_price": self.entry_price,
            "exit_date": self.exit_date,
            "exit_time": seconds_to_hms(self.exit_time),
            "exit_price": self.exit_price,
            "pnl": round(self.pnl, 4) if self.pnl is not None else None,
            "pnl_pct": round(self.pnl_pct, 4) if self.pnl_pct is not None else None,
        }


class BacktestResult:
    """Aggregated result returned to the caller."""

    def __init__(self, trades: List[Trade]):
        self.trades = trades
        closed = [t for t in trades if t.pnl is not None]

        self.total_trades = len(closed)
        self.winning_trades = sum(1 for t in closed if t.pnl > 0)
        self.losing_trades = sum(1 for t in closed if t.pnl <= 0)
        self.total_pnl = sum(t.pnl for t in closed)
        self.total_pnl_pct = sum(t.pnl_pct for t in closed)
        self.win_rate = (
            round(self.winning_trades / self.total_trades * 100, 2)
            if self.total_trades
            else 0.0
        )

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": self.win_rate,
            "total_pnl": round(self.total_pnl, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
            "trades": [t.to_dict() for t in self.trades],
        }


# =============================================================================
# Strategy execution
# =============================================================================


def execute(strategy: SmaCrossoverStrategy) -> BacktestResult:
    """
    SMA Crossover backtest.

    Logic
    -----
    - At every bar, read the fast SMA and slow SMA values.
    - If fast crosses ABOVE slow and we have no open position → BUY (go long).
    - If fast crosses BELOW slow and we have an open position → SELL (close long).

    The strategy only holds one position at a time (no pyramiding).

    Data flow
    ---------
    1. meta_data.compute_sma  — loads / resamples quotes, then writes indicator
                                 values into meta_data.indicators in one pass.
    2. meta_data.get_quotes_series — returns the ordered list of Quote objects
                                      we iterate bar by bar.
    3. meta_data.get_indicator — O(1) dict lookup per bar to read each SMA value.
    """

    symbol = strategy.symbol
    tf = strategy.timeframe
    fast_name = f"SMA_{strategy.fast_period}"
    slow_name = f"SMA_{strategy.slow_period}"

    # ------------------------------------------------------------------
    # Step 1: Compute both SMAs across the full date range.
    #         This also handles data loading / resampling internally via
    #         validate_relevant_quotes, so we don't need to call load_data
    #         or resample_quotes manually.
    # ------------------------------------------------------------------
    logger.info(f"Computing {fast_name} on {symbol} tf={tf}...")
    meta_data.compute_sma(
        symbol, tf, strategy.fast_period, strategy.start_date, strategy.end_date
    )

    logger.info(f"Computing {slow_name} on {symbol} tf={tf}...")
    meta_data.compute_sma(
        symbol, tf, strategy.slow_period, strategy.start_date, strategy.end_date
    )

    # ------------------------------------------------------------------
    # Step 2: Get the full ordered series of candles for the date range.
    # ------------------------------------------------------------------
    quotes = meta_data.get_quotes_series(
        symbol, strategy.start_date, strategy.end_date, tf
    )

    if not quotes:
        logger.warning("No quotes returned — check symbol, date range, and timeframe.")
        return BacktestResult([])

    # ------------------------------------------------------------------
    # Step 3: Walk bar by bar.
    # ------------------------------------------------------------------
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None

    prev_fast: Optional[float] = None
    prev_slow: Optional[float] = None

    for quote in quotes:
        date, time = quote.date, quote.time

        # Read pre-computed indicator values for this exact bar.
        # Returns None for the first (period - 1) bars where the SMA
        # window isn't full yet — we skip those bars.
        fast = meta_data.get_indicator(symbol, tf, fast_name, date, time)
        slow = meta_data.get_indicator(symbol, tf, slow_name, date, time)

        if fast is None or slow is None or prev_fast is None or prev_slow is None:
            # Not enough history yet to detect a crossover
            prev_fast, prev_slow = fast, slow
            continue

        # --- Crossover detection ---
        crossed_above = (prev_fast <= prev_slow) and (fast > slow)
        crossed_below = (prev_fast >= prev_slow) and (fast < slow)

        # BUY signal — fast SMA crossed above slow SMA
        if crossed_above and open_trade is None:
            open_trade = Trade(
                entry_date=date,
                entry_time=time,
                entry_price=quote._close,  # fill at close of signal bar
            )
            logger.info(
                f"BUY  {symbol} @ {quote._close:.2f}  "
                f"date={date} time={time}  "
                f"fast={fast:.2f} slow={slow:.2f}"
            )

        # SELL signal — fast SMA crossed below slow SMA
        elif crossed_below and open_trade is not None:
            open_trade.close(
                exit_date=date,
                exit_time=time,
                exit_price=quote._close,
            )
            logger.info(
                f"SELL {symbol} @ {quote._close:.2f}  "
                f"date={date} time={time}  "
                f"pnl={open_trade.pnl:.2f} ({open_trade.pnl_pct:.2f}%)"
            )
            trades.append(open_trade)
            open_trade = None

        prev_fast, prev_slow = fast, slow

    # If still in a position at end of range, record it as open (no forced close)
    if open_trade is not None:
        logger.info(
            f"Strategy ended with an open position entered at "
            f"date={open_trade.entry_date} time={open_trade.entry_time} "
            f"price={open_trade.entry_price:.2f}"
        )
        trades.append(open_trade)

    result = BacktestResult(trades)
    logger.info(
        f"Backtest complete — trades={result.total_trades} "
        f"win_rate={result.win_rate}% "
        f"total_pnl={result.total_pnl:.2f}"
    )
    return result
