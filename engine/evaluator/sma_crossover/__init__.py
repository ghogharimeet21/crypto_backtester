from typing import List, Optional

from logging import getLogger

from data import meta_data
from data.indicators.enums import SOURCE
from oms.enums import ExitReason, OrderSide
from oms.models import Trade, BacktestResult
from .models import SmaCrossoverStrategy
from commons.utils import seconds_to_hms

logger = getLogger(__name__)


def execute(strategy: SmaCrossoverStrategy) -> BacktestResult:
    """
    SMA Crossover backtest.

    Rules
    -----
    - Fast SMA crosses above slow SMA  -> BUY
    - Fast SMA crosses below slow SMA   -> SELL/EXIT
    - Only one open trade at a time
    - Stoploss/target are checked using candle high/low
    - If both target and stoploss hit in same candle, stoploss is assumed first
      (conservative backtest)
    """

    symbol = strategy.symbol
    tf = strategy.timeframe

    meta_data.meta_utils.fill_relevant_quotes(
        symbol, strategy.start_date, strategy.end_date, strategy.timeframe
    )

    logger.info(f"Computing SMA_{strategy.fast_period} on {symbol} tf={tf}...")
    meta_data.indicators.compute_sma(
        symbol,
        tf,
        strategy.fast_period,
        strategy.start_date,
        strategy.end_date,
    )

    logger.info(f"Computing SMA_{strategy.slow_period} on {symbol} tf={tf}...")
    meta_data.indicators.compute_sma(
        symbol,
        tf,
        strategy.slow_period,
        strategy.start_date,
        strategy.end_date,
    )

    quotes = meta_data.meta_utils.get_quotes_series(
        symbol,
        strategy.start_date,
        strategy.end_date,
        tf,
    )

    if not quotes:
        logger.warning("No quotes returned — check symbol, date range, and timeframe.")
        return BacktestResult([])

    trades: List[Trade] = []
    open_trade: Optional[Trade] = None

    prev_fast: Optional[float] = None
    prev_slow: Optional[float] = None

    def build_trade(
        entry_date: int,
        entry_time: int,
        entry_price: float,
        side: OrderSide,
    ) -> Trade:
        return Trade(
            entry_date=entry_date,
            entry_time=entry_time,
            entry_price=entry_price,
            order_side=side,
            quantity=1,
            target=strategy.target,
            stop_loss=strategy.stop_loss,
        )

    for quote in quotes:
        date, time = quote.date, quote.time

        fast = meta_data.indicators.get_sma(
            symbol, tf, SOURCE.CLOSE, strategy.fast_period, date, time
        )
        slow = meta_data.indicators.get_sma(
            symbol, tf, SOURCE.CLOSE, strategy.slow_period, date, time
        )

        # Warmup bars
        if fast is None or slow is None or prev_fast is None or prev_slow is None:
            prev_fast, prev_slow = fast, slow
            continue

        crossed_above = (prev_fast <= prev_slow) and (fast > slow)
        crossed_below = (prev_fast >= prev_slow) and (fast < slow)

        closed_this_bar = False

        # ---------------------------------------------------------------------
        # 1) Manage existing open position first
        # ---------------------------------------------------------------------
        if open_trade is not None:
            if open_trade.order_side == OrderSide.BUY:
                stoploss_hit = (
                    open_trade.stop_loss_price is not None
                    and quote._low <= open_trade.stop_loss_price
                )
                target_hit = (
                    open_trade.target_price is not None
                    and quote._high >= open_trade.target_price
                )

                if stoploss_hit and target_hit:
                    # Conservative assumption: stoploss first
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.stop_loss_price,
                        exit_reason=ExitReason.STOPLOSS,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif stoploss_hit:
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.stop_loss_price,
                        exit_reason=ExitReason.STOPLOSS,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif target_hit:
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.target_price,
                        exit_reason=ExitReason.TARGET,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif crossed_below:
                    # Opposite signal: exit long at candle close
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=quote._close,
                        exit_reason=ExitReason.SIGNAL,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

            else:
                # SHORT position
                stoploss_hit = (
                    open_trade.stop_loss_price is not None
                    and quote._high >= open_trade.stop_loss_price
                )
                target_hit = (
                    open_trade.target_price is not None
                    and quote._low <= open_trade.target_price
                )

                if stoploss_hit and target_hit:
                    # Conservative assumption: stoploss first
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.stop_loss_price,
                        exit_reason=ExitReason.STOPLOSS,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif stoploss_hit:
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.stop_loss_price,
                        exit_reason=ExitReason.STOPLOSS,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif target_hit:
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=open_trade.target_price,
                        exit_reason=ExitReason.TARGET,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

                elif crossed_above:
                    # Opposite signal: exit short at candle close
                    open_trade.close(
                        exit_date=date,
                        exit_time=time,
                        exit_price=quote._close,
                        exit_reason=ExitReason.SIGNAL,
                    )
                    trades.append(open_trade)
                    open_trade = None
                    closed_this_bar = True

        # ---------------------------------------------------------------------
        # 2) If flat now, look for a new entry
        #    Do not open a new trade on the same bar where one was closed.
        # ---------------------------------------------------------------------
        if open_trade is None and not closed_this_bar:
            if crossed_above:
                open_trade = build_trade(
                    entry_date=date,
                    entry_time=time,
                    entry_price=quote._close,
                    side=OrderSide.BUY,
                )
                logger.info(
                    f"BUY  {symbol} @ {quote._close:.2f} "
                    f"date={date} time={seconds_to_hms(time)} "
                    f"fast={fast:.2f} slow={slow:.2f}"
                )

            elif crossed_below and strategy.allow_short:
                open_trade = build_trade(
                    entry_date=date,
                    entry_time=time,
                    entry_price=quote._close,
                    side=OrderSide.SELL,
                )
                logger.info(
                    f"SELL {symbol} @ {quote._close:.2f} "
                    f"date={date} time={seconds_to_hms(time)} "
                    f"fast={fast:.2f} slow={slow:.2f}"
                )

        prev_fast, prev_slow = fast, slow

    # -------------------------------------------------------------------------
    # 3) Force close any remaining open position at end of backtest
    # -------------------------------------------------------------------------
    if open_trade is not None:
        last_quote = quotes[-1]
        open_trade.close(
            exit_date=last_quote.date,
            exit_time=last_quote.time,
            exit_price=last_quote._close,
            exit_reason=ExitReason.EOD,
        )
        trades.append(open_trade)

        logger.info(
            f"Forced EOD close for {symbol} "
            f"entry_date={open_trade.entry_date} "
            f"entry_time={seconds_to_hms(open_trade.entry_time)} "
            f"exit_price={last_quote._close:.2f}"
        )

    result = BacktestResult(trades)

    logger.info(
        f"Backtest complete — trades={result.total_trades} "
        f"win_rate={result.win_rate}% "
        f"total_pnl={result.total_pnl:.2f}"
    )

    return result