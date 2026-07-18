from logging import getLogger
from datetime import datetime, timedelta, timezone
from typing import List

logger = getLogger(__name__)


def make_date_obj(date, date_format="%Y%m%d") -> datetime:
    return datetime.strptime(str(date), date_format)


def date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(str(date_str), "%Y%m%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def split_datetime(ms: int):
    dt = datetime.fromtimestamp(
        ms / 1000, tz=timezone.utc
    )  # ← correct UTC, not deprecated

    date_int = int(dt.strftime("%Y%m%d"))
    seconds = dt.hour * 3600 + dt.minute * 60 + dt.second

    return date_int, seconds


def shift_date(date: str | int, shift: int, date_format: str = "%Y%m%d") -> int:
    return int(
        (datetime.strptime(str(date), date_format) + timedelta(days=shift)).strftime(
            date_format
        )
    )


def hms_to_seconds(time_str: str) -> int:
    hours, minutes, seconds = map(int, time_str.split(":"))
    if hours > 23:
        raise ValueError(
            f"in {time_str} hour={hours} is not valid please enter less then 24"
        )
    if minutes > 59:
        raise ValueError(
            f"in {time_str} minute={minutes} is not valid please enter less then 60"
        )
    if seconds > 59:
        raise ValueError(
            f"in {time_str} seconds={seconds} is not valid please enter less then 60"
        )
    return (hours * 3600) + minutes * 60 + seconds


def seconds_to_hms(seconds: int) -> str:
    if seconds > 86399:
        raise ValueError(f"{seconds} is not valid please enter less then 86399")
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_atm(spot, strike_gap):
    return round(spot / strike_gap) * strike_gap


def get_date_span(
    start_date: int, end_date: int, date_format: str = "%Y%m%d"
) -> List[int]:

    start = make_date_obj(start_date, date_format)
    end = make_date_obj(end_date, date_format)

    dates: List[int] = []

    while start <= end:
        dates.append(int(start.strftime("%Y%m%d")))
        start += timedelta(days=1)

    return dates