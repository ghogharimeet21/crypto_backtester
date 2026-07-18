from enum import Enum


class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(Enum):
    TARGET = "TARGET"
    STOPLOSS = "STOPLOSS"
    SIGNAL = "SIGNAL"
    TIME_EXIT = "TIME_EXIT"
    EOD = "EOD"
    MANUAL = "MANUAL"
