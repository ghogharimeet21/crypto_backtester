from __future__ import annotations

from enum import Enum

from commons.utils import seconds_to_hms


class BaseModel:
    """Base class for all models: generic to_dict / eq / hash / repr / str."""

    # subclasses list int-field names here that should render as HH:MM:SS
    _time_fields: set[str] = set()

    def to_dict(self) -> dict:
        def convert(value):
            if isinstance(value, BaseModel):
                return value.to_dict()
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value

        return {k: convert(v) for k, v in self.__dict__.items()}

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

    def __hash__(self):
        return hash((self.__class__,) + tuple(self.__dict__.values()))

    def __repr__(self):
        values = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"{self.__class__.__name__}({values})"

    def _format_field(self, key: str, value):
        if isinstance(value, Enum):
            return value.value
        if key in self._time_fields and isinstance(value, int):
            return seconds_to_hms(value)
        return value

    def __str__(self):
        parts = []
        for key, value in self.__dict__.items():
            if isinstance(value, BaseModel):
                for sub_key, sub_value in value.__dict__.items():
                    parts.append(f"{sub_key}={value._format_field(sub_key, sub_value)}")
            else:
                parts.append(f"{key}={self._format_field(key, value)}")
        return ", ".join(parts)


class Underlying(BaseModel):
    """A tradable symbol, e.g. Underlying('BTCUSDT', 'Binance')."""

    def __init__(self, symbol: str, exchange: str):
        self.symbol = symbol
        self.exchange = exchange


class Quote(BaseModel):
    """OHLCV snapshot for a symbol at a point in time."""

    _time_fields = {"time"}

    def __init__(
        self,
        date: int,
        time: int,
        underlying: Underlying,
        _open: float,
        _high: float,
        _low: float,
        _close: float,
        _volume: float,
    ):
        self.date = date
        self.time = time
        self.underlying = underlying

        self._open = _open
        self._high = _high
        self._low = _low
        self._close = _close
        self._volume = _volume