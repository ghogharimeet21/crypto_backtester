




from data.storage import meta_data
import requests
import logging
from data.utils import date_to_ms

BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"


logger = logging.getLogger(__name__)


def load_data(self, symbol: str, start_date: int, end_date: int, interval="1m"):
    start_ts = date_to_ms(start_date)
    end_ts = date_to_ms(end_date)

    current_start = start_ts

    while current_start < end_ts:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ts,
            "limit": 1000,
        }

        response = requests.get(BINANCE_HISTORICAL_URL, params=params)
        data = response.json()

        if not data:
            break

        for row in data:
            utc = row[0]

            # safety check (very important)
            if utc >= end_ts:
                return

            date_int, time_seconds = split_datetime(utc)

            _open = float(row[1])
            _high = float(row[2])
            _low = float(row[3])
            _close = float(row[4])
            _volume = float(row[5])

            meta_data.insert_quote(
                date_int,
                time_seconds,
                symbol,
                Quote(_open, _high, _low, _close, _volume),
            )

            # print(Quote(_open, _high, _low, _close, _volume))

        # move cursor forward (key step)
        current_start = data[-1][0] + 1

    logger.info(
        f"Data loaded for symbol={symbol}, start_date={start_date}, end_date={end_date}"
    )