from typing import Optional
from data.utils import seconds_to_hms





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