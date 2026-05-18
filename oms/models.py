from typing import Optional, List
from data.utils import seconds_to_hms
from oms.enums import TradeStatus




class Trade:
    """A single completed round-trip trade."""

    def __init__(self, entry_date: int, entry_time: int, entry_price: float):
        self.entry_date = entry_date
        self.entry_time = entry_time
        self.entry_price = entry_price

        self.trade_status: TradeStatus = TradeStatus.OPEN

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
        if self.entry_price:
            self.pnl_pct = (self.pnl / self.entry_price) * 100
        else:
            self.pnl_pct = 0.0

        self.trade_status = TradeStatus.CLOSE

    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date,
            "entry_time": seconds_to_hms(self.entry_time),
            "entry_price": self.entry_price,
            "exit_date": self.exit_date,
            "exit_time": seconds_to_hms(self.exit_time) if self.exit_time is not None else None,
            "exit_price": self.exit_price,
            "pnl": round(self.pnl, 4) if self.pnl is not None else None,
            "pnl_pct": round(self.pnl_pct, 4) if self.pnl_pct is not None else None,
            "is_open": self.exit_time is None,
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