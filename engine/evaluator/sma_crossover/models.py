from typing import List
from engine.evaluator.utils import get_date_span


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
        self.start_date: int = int(request_json["start_date"])
        self.end_date: int = int(request_json["end_date"])

        periods = request_json.get("periods")
        if periods is None:
            if "fast_period" in request_json and "slow_period" in request_json:
                periods = [
                    int(request_json["fast_period"]),
                    int(request_json["slow_period"]),
                ]
            else:
                raise ValueError(
                    "Provide either 'periods': [fast, slow] or "
                    "'fast_period' and 'slow_period'"
                )
        if not isinstance(periods, list) or len(periods) != 2:
            raise ValueError("periods must be a list of exactly two integers")
        self.periods: List[int] = [int(periods[0]), int(periods[1])]

        # Pre-build the full list of dates the strategy will run over
        self.date_span: List[int] = get_date_span(self.start_date, self.end_date)

        sorted_p = sorted(self.periods)
        self.fast_period = int(sorted_p[0])
        self.slow_period = int(sorted_p[1])

        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        if self.fast_period <= 0 or self.slow_period <= 0:
            raise ValueError("periods must be positive")
        if self.timeframe <= 0:
            raise ValueError("timeframe must be positive")
