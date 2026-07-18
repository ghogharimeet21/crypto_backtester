from typing import Dict, List, Optional, Tuple

from logging import getLogger

from data import meta_data
from data.indicators.enums import SOURCE
from commons.utils import seconds_to_hms
from data.models import Quote
from oms.enums import ExitReason, OrderSide
from oms.models import Trade, BacktestResult
from .models import TrendConfluenceStrategy

logger = getLogger(__name__)


def execute(strategy: TrendConfluenceStrategy) -> BacktestResult:
    """
    Trend + Pullback + Volatility confluence backtest — multi-symbol, multi-leg.

    Entry logic (all three must agree):
      1) Regime filter    -> price above/below EMA(trend_period, slow — e.g. 200)
                              sets the only direction this leg is allowed to trade
      2) Pullback trigger -> RSI dips to/below rsi_pullback_long then recovers
                              (long), or rallies to/above rsi_pullback_short then
                              falls back (short). This is "buy the dip in an
                              established uptrend" — a shallow, trend-following
                              pullback entry, not a full oversold/overbought
                              reversal signal. A reversal signal would fight a
                              trend filter (a signal meaning "the down move is
                              ending" cannot also require "price is still above
                              its own trend average" — the two point in opposite
                              time-order).
      3) Volatility gate  -> price must be on the trade side of the Bollinger
                              mid-band, confirming the pullback has actually
                              recovered rather than continuing to bleed.

    Multi-leg:
      Each symbol in strategy.symbols is tracked independently with its own
      open position, so e.g. BTCUSDT and ETHUSDT can both be open at once.
      All trades across all symbols are merged into one BacktestResult.

    Risk management:
      Fixed target/stop_loss in points from entry, checked against candle
      high/low. If both are hit on the same candle, stop-loss is assumed
      first (conservative backtest) — same convention as sma_crossover.
    """

    tf = strategy.timeframe
    start_date, end_date = strategy.start_date, strategy.end_date

    all_trades: List[Trade] = []
    open_trades: Dict[str, Optional[Trade]] = {s: None for s in strategy.symbols}

    quotes_by_symbol: Dict[str, list] = {}

    for symbol in strategy.symbols:
        logger.info(f"Computing indicators for {symbol} tf={tf}...")
        meta_data.indicators.compute_ema(
            symbol, tf, strategy.trend_period, start_date, end_date
        )
        meta_data.indicators.compute_rsi(
            symbol, tf, strategy.rsi_period, start_date, end_date
        )
        meta_data.indicators.compute_bb(
            symbol, tf, strategy.bb_period, strategy.bb_std, start_date, end_date
        )

        quotes = meta_data.meta_utils.get_quotes_series(
            symbol, start_date, end_date, tf
        )
        quotes_by_symbol[symbol] = quotes

        if not quotes:
            logger.warning(f"No quotes for {symbol} — skipping this leg.")

    # Merge every symbol's quotes into one time-ordered stream so each bar is
    # evaluated in true chronological order across all legs.
    merged: List[Tuple[int, int, str]] = []
    for symbol, quotes in quotes_by_symbol.items():
        for q in quotes:
            merged.append((q.date, q.time, symbol))
    merged.sort(key=lambda x: (x[0], x[1]))

    prev_rsi: Dict[str, Optional[float]] = {s: None for s in strategy.symbols}

    def build_trade(entry_date, entry_time, entry_price, side) -> Trade:
        return Trade(
            entry_date=entry_date,
            entry_time=entry_time,
            entry_price=entry_price,
            order_side=side,
            quantity=1,
            target=strategy.target,
            stop_loss=strategy.stop_loss,
        )

    for date, time, symbol in merged:
        quote = meta_data.meta_utils.get_quote(symbol, date, time, tf)
        if quote is None:
            continue

        ema = meta_data.indicators.get_ema(symbol, tf, SOURCE.CLOSE, strategy.trend_period, date, time)
        rsi = meta_data.indicators.get_rsi(symbol, tf, SOURCE.CLOSE, strategy.rsi_period, date, time)
        bb = meta_data.indicators.get_bb(
            symbol, tf, strategy.bb_period, strategy.bb_std, date, time
        )

        open_trade = open_trades[symbol]
        closed_this_bar = False

        # -------------------------------------------------------------
        # 1) Manage existing open position for this symbol first
        # -------------------------------------------------------------
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
            else:
                stoploss_hit = (
                    open_trade.stop_loss_price is not None
                    and quote._high >= open_trade.stop_loss_price
                )
                target_hit = (
                    open_trade.target_price is not None
                    and quote._low <= open_trade.target_price
                )

            if stoploss_hit:
                # Conservative assumption: stoploss first if both hit same bar
                open_trade.close(
                    exit_date=date, exit_time=time,
                    exit_price=open_trade.stop_loss_price,
                    exit_reason=ExitReason.STOPLOSS,
                )
                all_trades.append(open_trade)
                open_trades[symbol] = None
                closed_this_bar = True
            elif target_hit:
                open_trade.close(
                    exit_date=date, exit_time=time,
                    exit_price=open_trade.target_price,
                    exit_reason=ExitReason.TARGET,
                )
                all_trades.append(open_trade)
                open_trades[symbol] = None
                closed_this_bar = True

        # -------------------------------------------------------------
        # 2) If flat now, check the three-indicator entry gate
        # -------------------------------------------------------------
        if (
            open_trades[symbol] is None
            and not closed_this_bar
            and ema is not None
            and rsi is not None
            and bb is not None
            and prev_rsi[symbol] is not None
        ):
            trend_up = quote._close > ema
            trend_down = quote._close < ema

            pullback_recovered_up = prev_rsi[symbol] <= strategy.rsi_pullback_long < rsi
            pullback_recovered_down = prev_rsi[symbol] >= strategy.rsi_pullback_short > rsi

            vol_confirms_long = quote._close > bb["mid"]
            vol_confirms_short = quote._close < bb["mid"]

            long_signal = trend_up and pullback_recovered_up and vol_confirms_long
            short_signal = (
                strategy.allow_short
                and trend_down
                and pullback_recovered_down
                and vol_confirms_short
            )

            if long_signal:
                open_trades[symbol] = build_trade(date, time, quote._close, OrderSide.BUY)
                logger.info(
                    f"BUY  {symbol} @ {quote._close:.4f} date={date} "
                    f"time={seconds_to_hms(time)} ema={ema:.4f} rsi={rsi:.1f}"
                )
            elif short_signal:
                open_trades[symbol] = build_trade(date, time, quote._close, OrderSide.SELL)
                logger.info(
                    f"SELL {symbol} @ {quote._close:.4f} date={date} "
                    f"time={seconds_to_hms(time)} ema={ema:.4f} rsi={rsi:.1f}"
                )

        if rsi is not None:
            prev_rsi[symbol] = rsi

    # -------------------------------------------------------------------
    # 3) Force close any remaining open positions at end of backtest
    # -------------------------------------------------------------------
    for symbol, open_trade in open_trades.items():
        if open_trade is not None and quotes_by_symbol.get(symbol):
            last_quote: Quote = quotes_by_symbol[symbol][-1]
            open_trade.close(
                exit_date=last_quote.date,
                exit_time=last_quote.time,
                exit_price=last_quote._close,
                exit_reason=ExitReason.EOD,
            )
            all_trades.append(open_trade)
            logger.info(f"Forced EOD close for {symbol}")

    result = BacktestResult(all_trades)

    logger.info(
        f"Backtest complete — legs={strategy.symbols} trades={result.total_trades} "
        f"win_rate={result.win_rate}% total_pnl={result.total_pnl:.2f}"
    )

    return result