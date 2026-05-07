from typing import List
from engine.evaluator.utils import get_date_span
from data.utils import hms_to_seconds


class SmaCrossoverStrategy:
    """
    Config object built from the POST request body.

    Expected JSON:
    {
        "symbol":       "BTCUSDT",
        "timeframe":    300,          # seconds — 300 = 5-min candles
        "fast_period":  10,           # fast SMA lookback
        "slow_period":  20,           # slow SMA lookback
        "start_date":   20260101,
        "end_date":     20260131
    }
    """

    def __init__(self, request_json: dict):
        self.symbol: str = request_json["symbol"]
        self.timeframe: int = int(request_json["timeframe"])
        self.fast_period: int = int(request_json["fast_period"])
        self.slow_period: int = int(request_json["slow_period"])
        self.start_date: int = int(request_json["start_date"])
        self.end_date: int = int(request_json["end_date"])

        # Pre-build the full list of dates the strategy will run over
        self.date_span: List[int] = get_date_span(self.start_date, self.end_date)

        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        if self.timeframe <= 0:
            raise ValueError("timeframe must be positive")
