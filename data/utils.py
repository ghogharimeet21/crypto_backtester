import logging
from datetime import datetime, timedelta
from typing import List


BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"


logger = logging.getLogger(__name__)


def date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(str(date_str), "%Y%m%d")
    return int(dt.timestamp() * 1000)


def split_datetime(ms: int):
    dt = datetime.fromtimestamp(ms / 1000)

    date_int = int(dt.strftime("%Y%m%d"))
    seconds = dt.hour * 3600 + dt.minute * 60 + dt.second

    return date_int, seconds


def shift_date(date: str | int, shift: int) -> int:
    return int(
        (datetime.strptime(str(date), "%Y%m%d") + timedelta(days=shift)).strftime(
            "%Y%m%d"
        )
    )


def generate_date_range(start, end, date_format: str = "%Y%m%d") -> List[int]:
    """
    enter start_date and end_date in format of '%y%m%d' in integers
    you will get a list of integers of that dates in that start and end date range
    """
    dates = []
    start_date = datetime.strptime(str(start), date_format)
    end_date = datetime.strptime(str(end), date_format)
    if start_date > end_date:
        raise ValueError(f"{start_date.strftime(date_format)} is greter then {end_date.strftime(date_format)} please enter valid dates")
    while start_date <= end_date:
        dates.append(int(start_date.strftime(date_format)))
        start_date += timedelta(days=1)
    return dates



def hms_to_seconds(time_str: str) -> int:
    hours, minutes, seconds = map(int, time_str.split(':'))
    if hours > 24:
        raise ValueError(f"in {time_str} hour={hours} is not valid please enter less then 24")
    if minutes > 59:
        raise ValueError(f"in {time_str} minute={minutes} is not valid please enter less then 60")
    if seconds > 59:
        raise ValueError(f"in {time_str} seconds={seconds} is not valid please enter less then 60")
    return (hours * 3600) + minutes * 60 + seconds


def seconds_to_hms(seconds: int) -> str:
    if seconds > 86399:
        raise ValueError(f"{seconds} is not valid please enter less then 86399")
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"