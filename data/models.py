from data.utils import seconds_to_hms


class Quote:
    def __init__(
        self,
        _open: float,
        _high: float,
        _low: float,
        _close: float,
        _volume: float,
        date: int = None,
        time: int = None,
    ):
        (
            self._open,
            self._high,
            self._low,
            self._close,
            self._volume,
            self.date,
            self.time,
        ) = (_open, _high, _low, _close, _volume, date, time)

    def __str__(self):
        time_str = seconds_to_hms(self.time) if self.time is not None else None
        return f"date={self.date}, time={time_str}, open={self._open}, high={self._high}, low={self._low}, close={self._close}"
