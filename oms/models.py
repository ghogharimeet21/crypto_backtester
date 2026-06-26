from typing import Optional, List
from data.utils import seconds_to_hms
from oms.enums import OrderSide, TradeStatus, ExitReason


class Trade:
    """Represents a single trade."""

    def __init__(
        self,
        entry_date: int,
        entry_time: int,
        entry_price: float,
        order_side: OrderSide,
        quantity: int = 1,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
    ):
        # Entry
        self.entry_date = entry_date
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.order_side = order_side

        # Position
        self.quantity = quantity

        # Risk Management
        self.stop_loss = stop_loss
        self.target = target
        self.target_price = (
            self.entry_price + self.target
            if self.order_side == OrderSide.BUY
            else self.entry_price - target
        )
        self.stop_loss_price = (
            self.entry_price - self.stop_loss
            if self.order_side == OrderSide.BUY
            else self.entry_price + stop_loss
        )

        # Status
        self.trade_status = TradeStatus.OPEN

        # Exit
        self.exit_date: Optional[int] = None
        self.exit_time: Optional[int] = None
        self.exit_price: Optional[float] = None
        self.exit_reason: Optional[ExitReason] = None

        # Metrics
        self.pnl: Optional[float] = None
        self.pnl_pct: Optional[float] = None
        self.holding_seconds: Optional[int] = None

    def close(
        self,
        exit_date: int,
        exit_time: int,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> None:
        self.exit_date = exit_date
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason

        if self.order_side == OrderSide.BUY:
            price_diff = exit_price - self.entry_price
        else:
            price_diff = self.entry_price - exit_price

        self.pnl = price_diff * self.quantity
        self.pnl_pct = (price_diff / self.entry_price) * 100

        self.holding_seconds = exit_time - self.entry_time

        self.trade_status = TradeStatus.CLOSED

    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date,
            "entry_time": seconds_to_hms(self.entry_time),
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "order_side": self.order_side.name,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "exit_date": self.exit_date,
            "exit_time": (
                seconds_to_hms(self.exit_time) if self.exit_time is not None else None
            ),
            "exit_price": self.exit_price,
            "exit_reason": (self.exit_reason.name if self.exit_reason else None),
            "pnl": round(self.pnl, 2) if self.pnl is not None else None,
            "pnl_pct": round(self.pnl_pct, 2) if self.pnl_pct is not None else None,
            "holding_seconds": self.holding_seconds,
            "is_open": self.trade_status == TradeStatus.OPEN,
        }


class BacktestResult:
    """Aggregated backtest statistics."""

    def __init__(self, trades: List[Trade]):
        self.trades = trades

        closed = [trade for trade in trades if trade.trade_status == TradeStatus.CLOSED]

        self.total_trades = len(closed)

        self.winning_trades = sum(
            1 for trade in closed if trade.pnl is not None and trade.pnl > 0
        )

        self.losing_trades = sum(
            1 for trade in closed if trade.pnl is not None and trade.pnl < 0
        )

        self.breakeven_trades = sum(1 for trade in closed if trade.pnl == 0)

        self.total_pnl = sum(trade.pnl or 0 for trade in closed)

        self.total_pnl_pct = sum(trade.pnl_pct or 0 for trade in closed)

        self.win_rate = (
            round(
                self.winning_trades / self.total_trades * 100,
                2,
            )
            if self.total_trades
            else 0.0
        )

        winning_pnls = [
            trade.pnl for trade in closed if trade.pnl is not None and trade.pnl > 0
        ]

        losing_pnls = [
            trade.pnl for trade in closed if trade.pnl is not None and trade.pnl < 0
        ]

        self.avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0.0

        self.avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0.0

        self.largest_win = max(winning_pnls) if winning_pnls else 0.0

        self.largest_loss = min(losing_pnls) if losing_pnls else 0.0

        gross_profit = sum(winning_pnls)
        gross_loss = abs(sum(losing_pnls))

        self.profit_factor = (
            round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")
        )

        self.target_hits = sum(
            1 for trade in closed if trade.exit_reason == ExitReason.TARGET
        )

        self.stoploss_hits = sum(
            1 for trade in closed if trade.exit_reason == ExitReason.STOPLOSS
        )

        holding_times = [
            trade.holding_seconds
            for trade in closed
            if trade.holding_seconds is not None
        ]

        self.average_holding_seconds = (
            sum(holding_times) / len(holding_times) if holding_times else 0
        )

        # Equity Curve
        self.equity_curve = []

        running_pnl = 0

        for trade in closed:
            running_pnl += trade.pnl or 0
            self.equity_curve.append(round(running_pnl, 2))

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate_pct": self.win_rate,
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "profit_factor": self.profit_factor,
            "target_hits": self.target_hits,
            "stoploss_hits": self.stoploss_hits,
            "average_holding_seconds": round(
                self.average_holding_seconds,
                2,
            ),
            "equity_curve": self.equity_curve,
            "trades": [trade.to_dict() for trade in self.trades],
        }
