from datetime import datetime, timedelta
from typing import List


def get_date_span(start_date: int, end_date: int, date_format: str = "%Y%m%d") -> List[int]:

    start = datetime.strptime(str(start_date), date_format)
    end = datetime.strptime(str(end_date), date_format)

    dates: List[int] = []

    while start <= end:
        dates.append(int(start.strftime("%Y%m%d")))
        start += timedelta(days=1)

    return dates
