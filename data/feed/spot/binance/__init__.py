from logging import getLogger
import requests

from data.models import Quote, Underlying
from commons.utils import date_to_ms, split_datetime

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data import MetaData


logger = getLogger(__name__)

BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"


class Binance:
    def __init__(self, meta: "MetaData"):
        self._meta = meta

    def load_data(
        self,
        symbol: str,
        start_date: int,
        end_date: int,
        interval: str = "1m",
    ):
        start_ts = date_to_ms(start_date)
        end_ts = date_to_ms(end_date)

        logger.info(
            f"Starting Binance load: symbol={symbol}, start={start_date}, end={end_date}"
        )

        quotes: list[Quote] = []

        current_start = start_ts

        while current_start < end_ts:
            response = requests.get(
                BINANCE_HISTORICAL_URL,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_ts,
                    "limit": 1000,
                },
            )
            response.raise_for_status()

            data = response.json()

            if isinstance(data, dict):
                raise RuntimeError(f"Binance API error for symbol={symbol}: {data}")

            if not data:
                break

            for row in data:
                utc = row[0]

                if utc >= end_ts:
                    logger.info(f"Binance load complete: symbol={symbol}")
                    return quotes

                date_int, time_seconds = split_datetime(utc)

                underlying = Underlying(symbol, "BINANCE")

                self._meta.meta_utils.insert_quote(
                    Quote(
                        date=date_int,
                        time=time_seconds,
                        underlying=underlying,
                        _open=float(row[1]),
                        _high=float(row[2]),
                        _low=float(row[3]),
                        _close=float(row[4]),
                        _volume=float(row[5]),
                    )
                )

            current_start = data[-1][0] + 1

        logger.info(
            f"Binance load complete: symbol={symbol}, start={start_date}, end={end_date}"
        )
