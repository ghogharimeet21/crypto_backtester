from typing import List
from engine.evaluator.utils import get_date_span


class TrendConfluenceStrategy:

    def __init__(self, request_json: dict):
        symbols = request_json["symbols"]
        if not isinstance(symbols, list) or not symbols:
            raise ValueError("symbols must be a non-empty list of strings")
        self.symbols: List[str] = [str(s) for s in symbols]

        self.timeframe: int = int(request_json["timeframe"])
        self.start_date: int = int(request_json["start_date"])
        self.end_date: int = int(request_json["end_date"])

        self.trend_period: int = int(request_json.get("trend_period", 200))
        self.rsi_period: int = int(request_json.get("rsi_period", 14))
        self.rsi_pullback_long: float = float(request_json.get("rsi_pullback_long", 45))
        self.rsi_pullback_short: float = float(request_json.get("rsi_pullback_short", 55))
        self.bb_period: int = int(request_json.get("bb_period", 20))
        self.bb_std: float = float(request_json.get("bb_std", 2.0))

        self.target: float = float(request_json["target"])
        self.stop_loss: float = float(request_json["stop_loss"])
        self.allow_short: bool = bool(request_json.get("allow_short", True))

        if self.timeframe <= 0:
            raise ValueError("timeframe must be positive")
        if self.trend_period <= 0 or self.rsi_period <= 0 or self.bb_period <= 0:
            raise ValueError("indicator periods must be positive")
        if self.rsi_pullback_long >= self.rsi_pullback_short:
            raise ValueError("rsi_pullback_long must be less than rsi_pullback_short")

        # Pre-build the full list of dates the strategy will run over
        self.date_span: List[int] = get_date_span(self.start_date, self.end_date)
