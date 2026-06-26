from enum import Enum




class TimeFrameType(Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    YEAR = "YEAR"



class OptionType(Enum):
    CE = "CE"
    PE = "PE"