from data.utils import seconds_to_hms


class Quote:
    def __init__(
        self,
        date: int,
        time: int,
        symbol: str,
        _open: float,
        _high: float,
        _low: float,
        _close: float,
        _volume: float,
    ):
        (
            self.date,
            self.time,
            self.symbol,
            self._open,
            self._high,
            self._low,
            self._close,
            self._volume,
        ) = (date, time, symbol, _open, _high, _low, _close, _volume,)

    def __str__(self):
        time_str = seconds_to_hms(self.time) if self.time is not None else None
        return (
            f"symbol={self.symbol}, date={self.date}, time={time_str}, "
            f"open={self._open}, high={self._high}, low={self._low}, close={self._close}"
        )
