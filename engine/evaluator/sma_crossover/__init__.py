from oms.models import Trade, BacktestResult
from .models import SmaCrossoverStrategy
from data.local import meta_data
import logging
from typing import List, Optional
from data.utils import seconds_to_hms

logger = logging.getLogger(__name__)


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
    1. meta_data.indicators.compute_sma — loads / resamples quotes, then writes
                                           indicator values into meta_data.indicators.
    2. meta_data.get_quotes_series       — returns the ordered list of Quote objects
                                           we iterate bar by bar.
    3. meta_data.indicators.get_sma      — O(1) dict lookup per bar to read each SMA.
    """

    symbol = strategy.symbol
    tf     = strategy.timeframe

    # ------------------------------------------------------------------
    # Step 1: Compute both SMAs across the full date range.
    #         validate_relevant_quotes is called internally — no need to
    #         call load_data or resample_quotes manually.
    # ------------------------------------------------------------------
    logger.info(f"Computing SMA_{strategy.fast_period} on {symbol} tf={tf}...")
    meta_data.indicators.compute_sma(
        symbol, tf, strategy.fast_period, strategy.start_date, strategy.end_date
    )

    logger.info(f"Computing SMA_{strategy.slow_period} on {symbol} tf={tf}...")
    meta_data.indicators.compute_sma(
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
    trades: List[Trade]     = []
    open_trade: Optional[Trade] = None

    prev_fast: Optional[float] = None
    prev_slow: Optional[float] = None

    for quote in quotes:
        date, time = quote.date, quote.time

        # Read pre-computed indicator values for this exact bar.
        # period is now required — both fast and slow go through the same get_sma.
        # Returns None for warmup bars — we skip those.
        fast = meta_data.indicators.get_sma(symbol, tf, strategy.fast_period, date, time)
        slow = meta_data.indicators.get_sma(symbol, tf, strategy.slow_period, date, time)

        if fast is None or slow is None or prev_fast is None or prev_slow is None:
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
                entry_price=quote._close,
            )
            logger.info(
                f"BUY  {symbol} @ {quote._close:.2f}  "
                f"date={date} time={seconds_to_hms(time)}  "
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
                f"date={date} time={seconds_to_hms(time)}  "
                f"pnl={open_trade.pnl:.2f} ({open_trade.pnl_pct:.2f}%)"
            )
            trades.append(open_trade)
            open_trade = None

        prev_fast, prev_slow = fast, slow

    # If still in a position at end of range, record it as open (no forced close)
    if open_trade is not None:
        logger.info(
            f"Strategy ended with an open position entered at "
            f"date={open_trade.entry_date} time={seconds_to_hms(open_trade.entry_time)} "
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