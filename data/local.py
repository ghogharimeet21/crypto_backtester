# data/local.py
from typing import Dict, List
from datetime import datetime
from data.models import Quote
from data.models import OptionQuote
from data.enums import OptionType
from data.indicators import Indicator
from data.utils import shift_date, date_to_ms, split_datetime, hms_to_seconds
import logging
import requests
import os
from pandas import read_csv, DataFrame
from engine.evaluator.utils import get_date_span

logger = logging.getLogger(__name__)

BINANCE_HISTORICAL_URL = "https://api.binance.com/api/v3/klines"
DERIBIT_BASE_URL = "https://www.deribit.com/api/v2/public"


# =============================================================================
# Deribit instrument name helpers
# =============================================================================


def _parse_deribit_expiry(expiry_str: str) -> int:
    """'27JUN26' -> 20260627"""
    return int(datetime.strptime(expiry_str, "%d%b%y").strftime("%Y%m%d"))


def _parse_deribit_instrument(name: str) -> tuple[str, int, float, OptionType]:
    """'BTC-27JUN26-50000-C' -> ('BTC', 20260627, 50000.0, 'CE')"""
    parts = name.split("-")
    underlying = parts[0]
    expiry = _parse_deribit_expiry(parts[1])
    strike = float(parts[2])
    option_type: OptionType = OptionType.CE if parts[3] == "C" else OptionType.PE
    return underlying, expiry, strike, option_type


def _build_deribit_instrument_name(
    underlying: str, expiry: int, strike: float, option_type: OptionType
) -> str:
    """('BTC', 20260627, 50000.0, 'CE') -> 'BTC-27JUN26-50000-C'"""
    dt = datetime.strptime(str(expiry), "%Y%m%d")
    exp_str = dt.strftime("%d%b%y").upper()  # 27JUN26
    strike_str = str(int(strike)) if strike == int(strike) else str(strike)
    opt_char = "C" if option_type == OptionType.CE else "P"
    return f"{underlying}-{exp_str}-{strike_str}-{opt_char}"


class MetaData:
    def __init__(self):
        # ── Spot ─────────────────────────────────────────────────────────────
        # symbol -> timeframe -> date -> time -> Quote
        self.quotes: Dict[str, Dict[int, Dict[int, Dict[int, Quote]]]] = {}

        # symbol -> timeframe -> set[date]
        self.available_dates: Dict[str, Dict[int, set]] = {}

        # ── Options ───────────────────────────────────────────────────────────
        # underlying -> expiry -> strike -> option_type -> timeframe -> date -> time -> OptionQuote
        self.option_quotes: Dict[
            str,
            Dict[
                int,
                Dict[float, Dict[str, Dict[int, Dict[int, Dict[int, OptionQuote]]]]],
            ],
        ] = {}

        # instrument_name -> timeframe -> set[date]
        self.option_available_dates: Dict[str, Dict[int, set]] = {}

        # underlying -> expiry -> strike -> option_type -> instrument_name
        self.instrument_registry: Dict[str, Dict[int, Dict[float, Dict[str, str]]]] = {}

        self.indicators: Indicator = Indicator(self)

    # =========================================================================
    # Spot — Data Loading
    # =========================================================================

    def load_default_data(self, csv: bool = True):
        CSV_PATH = "btcusdt_jan2026.csv"

        if csv:
            if os.path.exists(CSV_PATH):
                logger.info("Loading BTCUSDT Jan 2026 from local CSV...")
                df = read_csv(CSV_PATH)
                for _, row in df.iterrows():
                    d = int(row["date_int"])
                    t = int(float(row["time_seconds"]))
                    self.insert_quote(
                        Quote(
                            d,
                            t,
                            "BTCUSDT",
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                        ),
                    )
            else:
                logger.info("Fetching BTCUSDT Jan 2026 from Binance...")
                load_df = read_csv("default_load.csv")
                for i in range(len(load_df)):
                    load = load_df.iloc[i]
                    self.load_data(
                        str(load["symbol"]),
                        int(load["start_date"]),
                        int(load["end_date"]),
                    )

                rows = []
                for date, times in self.quotes.get("BTCUSDT", {}).get(60, {}).items():
                    for time_sec, q in times.items():
                        rows.append(
                            {
                                "date_int": date,
                                "time_seconds": time_sec,
                                "open": q._open,
                                "high": q._high,
                                "low": q._low,
                                "close": q._close,
                                "volume": q._volume,
                            }
                        )
                DataFrame(rows).to_csv(CSV_PATH, index=False)
                logger.info(f"Saved {len(rows):,} candles to {CSV_PATH}")

            logger.info("Done.")
        else:
            logger.info("Fetching BTCUSDT Jan 2026 from Binance...")
            self.load_data("BTCUSDT", "20260101", "20260201")

    def load_data(self, symbol: str, start_date, end_date, interval: str = "1m"):
        start_ts = date_to_ms(start_date)
        end_ts = date_to_ms(end_date)
        logger.info(
            f"Starting spot load: symbol={symbol}, start={start_date}, end={end_date}"
        )

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
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                raise RuntimeError(f"Binance API error for symbol={symbol}: {data}")
            if not data:
                break

            for row in data:
                utc = row[0]
                if utc >= end_ts:
                    logger.info(f"Spot load complete: symbol={symbol}")
                    return
                date_int, time_seconds = split_datetime(utc)
                self.insert_quote(
                    Quote(
                        date_int,
                        time_seconds,
                        symbol,
                        float(row[1]),
                        float(row[2]),
                        float(row[3]),
                        float(row[4]),
                        float(row[5]),
                    )
                )

            current_start = data[-1][0] + 1

        logger.info(
            f"Spot load complete: symbol={symbol}, start={start_date}, end={end_date}"
        )

    # =========================================================================
    # Spot — Quote Storage
    # =========================================================================

    def insert_quote(self, quote: Quote, timeframe: int = 60):
        date, time, symbol = quote.date, quote.time, quote.symbol

        if symbol not in self.quotes:
            self.quotes[symbol] = {}
        if timeframe not in self.quotes[symbol]:
            self.quotes[symbol][timeframe] = {}
        if date not in self.quotes[symbol][timeframe]:
            self.quotes[symbol][timeframe][date] = {}
        if time not in self.quotes[symbol][timeframe][date]:
            self.quotes[symbol][timeframe][date][time] = quote

        if symbol not in self.available_dates:
            self.available_dates[symbol] = {}
        if timeframe not in self.available_dates[symbol]:
            self.available_dates[symbol][timeframe] = set()
        self.available_dates[symbol][timeframe].add(date)

    def get_quote(
        self, symbol: str, date: int, time: int | str, timeframe: int = 60
    ) -> Quote | None:
        if isinstance(time, str):
            time = hms_to_seconds(time)
        return self.quotes.get(symbol, {}).get(timeframe, {}).get(date, {}).get(time)

    def get_quotes_series(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = 60
    ) -> List[Quote]:
        quotes: List[Quote] = []
        for date in get_date_span(start_date, end_date):
            day_quotes = self.quotes.get(symbol, {}).get(timeframe, {}).get(date, {})
            for time in sorted(day_quotes.keys()):
                quotes.append(day_quotes[time])
        return quotes

    # =========================================================================
    # Spot — Availability / Fill
    # =========================================================================

    def get_not_available_dates(
        self, date_span: List[int], symbol: str, timeframe: int
    ) -> List[int]:
        available = self.available_dates.get(symbol, {}).get(timeframe, set())
        return [d for d in date_span if d not in available]

    def fill_relevant_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int
    ):
        if timeframe == 60:
            missing = self.get_not_available_dates(
                get_date_span(start_date, end_date), symbol, 60
            )
            if missing:
                self.load_data(
                    symbol, shift_date(min(missing), -2), shift_date(max(missing), 1)
                )
        else:
            self.resample_quotes(symbol, start_date, end_date, timeframe)

    # =========================================================================
    # Spot — Resampling
    # =========================================================================

    def get_best_base(self, symbol: str, target_tf: int) -> int | None:
        available_tfs = list(self.quotes.get(symbol, {}).keys()) or [60]
        valid = [t for t in available_tfs if target_tf % t == 0]
        return max(valid) if valid else None

    def resample_day(self, symbol: str, date: int, base_tf: int, target_tf: int):
        base_data = self.quotes.get(symbol, {}).get(base_tf, {}).get(date)
        if not base_data:
            logger.warning(
                f"resample_day: no data symbol={symbol}, base_tf={base_tf}, date={date} — skipping"
            )
            return

        times = sorted(base_data.keys())
        bucket: List[Quote] = []
        bucket_open_time: int = None
        ratio = target_tf // base_tf

        for t in times:
            if not bucket:
                bucket_open_time = t
            bucket.append(base_data[t])

            if len(bucket) == ratio:
                self.insert_quote(
                    Quote(
                        date,
                        bucket_open_time,
                        symbol,
                        bucket[0]._open,
                        max(q._high for q in bucket),
                        min(q._low for q in bucket),
                        bucket[-1]._close,
                        sum(q._volume for q in bucket),
                    ),
                    timeframe=target_tf,
                )
                bucket.clear()
                bucket_open_time = None

        if bucket:
            logger.warning(
                f"resample_day: partial bucket ({len(bucket)}/{ratio}) "
                f"symbol={symbol}, date={date}, target_tf={target_tf} — flushing"
            )
            self.insert_quote(
                Quote(
                    date,
                    bucket_open_time,
                    symbol,
                    bucket[0]._open,
                    max(q._high for q in bucket),
                    min(q._low for q in bucket),
                    bucket[-1]._close,
                    sum(q._volume for q in bucket),
                ),
                timeframe=target_tf,
            )

    def resample_quotes(
        self, symbol: str, start_date: int, end_date: int, timeframe: int = None
    ):
        if timeframe is None:
            raise ValueError("timeframe is required for resampling")
        if timeframe <= 0:
            raise ValueError("timeframe must be positive")

        date_span = get_date_span(start_date, end_date)
        missing = self.get_not_available_dates(date_span, symbol, 60)
        if missing:
            logger.info(f"Fetching missing 1-min data: symbol={symbol}")
            self.load_data(symbol, min(missing), shift_date(max(missing), 1))

        base_tf = self.get_best_base(symbol, timeframe)
        if base_tf is None:
            raise ValueError("No valid base timeframe found")

        for date in date_span:
            if date in self.quotes.get(symbol, {}).get(timeframe, {}):
                continue
            self.resample_day(symbol, date, base_tf, timeframe)

    # =========================================================================
    # Options — Instrument Registry
    # =========================================================================

    def load_option_instruments(self, underlying: str, expired: bool = False):
        """
        Fetch all active (or expired) option instruments from Deribit for a
        given underlying (e.g. 'BTC', 'ETH') and populate instrument_registry.
        """
        params = {
            "currency": underlying,
            "kind": "option",
            "expired": str(expired).lower(),
        }
        response = requests.get(f"{DERIBIT_BASE_URL}/get_instruments", params=params)
        response.raise_for_status()
        result = response.json().get("result", [])

        count = 0
        for instrument in result:
            name = instrument["instrument_name"]
            try:
                u, expiry, strike, option_type = _parse_deribit_instrument(name)
            except Exception:
                logger.warning(
                    f"load_option_instruments: could not parse '{name}' — skipping"
                )
                continue

            if u not in self.instrument_registry:
                self.instrument_registry[u] = {}
            if expiry not in self.instrument_registry[u]:
                self.instrument_registry[u][expiry] = {}
            if strike not in self.instrument_registry[u][expiry]:
                self.instrument_registry[u][expiry][strike] = {}

            self.instrument_registry[u][expiry][strike][option_type] = name
            count += 1

        logger.info(
            f"load_option_instruments: loaded {count} instruments for {underlying} (expired={expired})"
        )

    def get_instrument_name(
        self, underlying: str, expiry: int, strike: float, option_type: OptionType
    ) -> str:
        """
        Return the Deribit instrument name for a given contract.
        Falls back to building it from parts if not in registry.
        """
        name = (
            self.instrument_registry.get(underlying, {})
            .get(expiry, {})
            .get(strike, {})
            .get(option_type)
        )
        if name is None:
            name = _build_deribit_instrument_name(
                underlying, expiry, strike, option_type
            )
            logger.warning(
                f"get_instrument_name: '{name}' not in registry — using constructed name"
            )
        return name

    # =========================================================================
    # Options — Data Loading
    # =========================================================================

    def load_option_data(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        start_date: int,
        end_date: int,
        timeframe: int = 60,
    ):
        """
        Load OHLCV + OI + IV candles for a specific option contract from Deribit
        and insert into option_quotes.
        Deribit resolution mapping: 60 -> '1', 300 -> '5', 900 -> '15', etc. (seconds)
        """
        instrument_name = self.get_instrument_name(
            underlying, expiry, strike, option_type
        )

        # Deribit uses resolution in minutes for chart data
        resolution_map = {
            60: "1",
            300: "5",
            900: "15",
            1800: "30",
            3600: "60",
            86400: "1D",
        }
        resolution = resolution_map.get(timeframe)
        if resolution is None:
            raise ValueError(
                f"Unsupported timeframe for Deribit: {timeframe}. Supported: {list(resolution_map.keys())}"
            )

        start_ts = date_to_ms(start_date)
        end_ts = date_to_ms(end_date)

        logger.info(
            f"Loading option data: {instrument_name}, start={start_date}, end={end_date}, tf={timeframe}s"
        )

        params = {
            "instrument_name": instrument_name,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "resolution": resolution,
        }
        response = requests.get(
            f"{DERIBIT_BASE_URL}/get_tradingview_chart_data", params=params
        )
        response.raise_for_status()
        result = response.json().get("result", {})

        if result.get("status") == "no_data":
            logger.warning(f"load_option_data: no data returned for {instrument_name}")
            return

        ticks = result.get("ticks", [])
        opens = result.get("open", [])
        highs = result.get("high", [])
        lows = result.get("low", [])
        closes = result.get("close", [])
        volumes = result.get("volume", [])
        # Deribit provides these at candle level
        ivs = result.get("iv", [None] * len(ticks))
        ois = result.get("open_interest", [0.0] * len(ticks))

        for i, utc_ms in enumerate(ticks):
            if utc_ms >= end_ts:
                break
            date_int, time_seconds = split_datetime(utc_ms)
            self.insert_option_quote(
                OptionQuote(
                    date=date_int,
                    time=time_seconds,
                    symbol=instrument_name,
                    _open=float(opens[i]),
                    _high=float(highs[i]),
                    _low=float(lows[i]),
                    _close=float(closes[i]),
                    _volume=float(volumes[i]),
                    strike=strike,
                    expiry=expiry,
                    option_type=option_type,
                    oi=float(ois[i]),
                    iv=float(ivs[i]) if ivs[i] is not None else None,
                ),
                timeframe=timeframe,
            )

        logger.info(f"Option load complete: {instrument_name}, {len(ticks)} candles")

    # =========================================================================
    # Options — Quote Storage
    # =========================================================================

    def insert_option_quote(self, quote: OptionQuote, timeframe: int = 60):
        underlying = quote.symbol.split("-")[0]  # 'BTC' from 'BTC-27JUN26-50000-C'
        expiry = quote.expiry
        strike = quote.strike
        option_type = quote.option_type
        date = quote.date
        time = quote.time

        if underlying not in self.option_quotes:
            self.option_quotes[underlying] = {}
        if expiry not in self.option_quotes[underlying]:
            self.option_quotes[underlying][expiry] = {}
        if strike not in self.option_quotes[underlying][expiry]:
            self.option_quotes[underlying][expiry][strike] = {}
        if option_type not in self.option_quotes[underlying][expiry][strike]:
            self.option_quotes[underlying][expiry][strike][option_type] = {}
        if timeframe not in self.option_quotes[underlying][expiry][strike][option_type]:
            self.option_quotes[underlying][expiry][strike][option_type][timeframe] = {}
        if date not in self.option_quotes[underlying][expiry][strike][option_type][timeframe]:
            self.option_quotes[underlying][expiry][strike][option_type][timeframe][date] = {}
        if time not in self.option_quotes[underlying][expiry][strike][option_type][timeframe][date]:
            self.option_quotes[underlying][expiry][strike][option_type][timeframe][date][time] = quote

        # availability tracking — keyed by instrument name for easy lookup
        instrument_name = quote.symbol
        if instrument_name not in self.option_available_dates:
            self.option_available_dates[instrument_name] = {}
        if timeframe not in self.option_available_dates[instrument_name]:
            self.option_available_dates[instrument_name][timeframe] = set()
        self.option_available_dates[instrument_name][timeframe].add(date)

    def get_option_quote(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        date: int,
        time: int | str,
        timeframe: int = 60,
    ) -> OptionQuote | None:
        if isinstance(time, str):
            time = hms_to_seconds(time)
        return (
            self.option_quotes.get(underlying, {})
            .get(expiry, {})
            .get(strike, {})
            .get(option_type, {})
            .get(timeframe, {})
            .get(date, {})
            .get(time)
        )

    def get_option_quotes_series(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        start_date: int,
        end_date: int,
        timeframe: int = 60,
    ) -> List[OptionQuote]:
        quotes: List[OptionQuote] = []
        tf_data = (
            self.option_quotes.get(underlying, {})
            .get(expiry, {})
            .get(strike, {})
            .get(option_type, {})
            .get(timeframe, {})
        )
        for date in get_date_span(start_date, end_date):
            day_quotes = tf_data.get(date, {})
            for time in sorted(day_quotes.keys()):
                quotes.append(day_quotes[time])
        return quotes

    # =========================================================================
    # Options — Availability / Fill
    # =========================================================================

    def get_option_not_available_dates(
        self, date_span: List[int], instrument_name: str, timeframe: int
    ) -> List[int]:
        available = self.option_available_dates.get(instrument_name, {}).get(
            timeframe, set()
        )
        return [d for d in date_span if d not in available]

    def fill_relevant_option_quotes(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        start_date: int,
        end_date: int,
        timeframe: int = 60,
    ):
        instrument_name = self.get_instrument_name(
            underlying, expiry, strike, option_type
        )
        date_span = get_date_span(start_date, end_date)
        missing = self.get_option_not_available_dates(
            date_span, instrument_name, timeframe
        )

        if not missing:
            return

        if timeframe == 60:
            self.load_option_data(
                underlying,
                expiry,
                strike,
                option_type,
                shift_date(min(missing), -1),
                shift_date(max(missing), 1),
                timeframe=60,
            )
        else:
            # load base 1-min first, then resample up
            self.fill_relevant_option_quotes(
                underlying,
                expiry,
                strike,
                option_type,
                start_date,
                end_date,
                timeframe=60,
            )
            self.resample_option_quotes(
                underlying, expiry, strike, option_type, start_date, end_date, timeframe
            )

    # =========================================================================
    # Options — Resampling
    # =========================================================================

    def get_option_best_base(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        target_tf: int,
    ) -> int | None:
        available_tfs = list(
            self.option_quotes.get(underlying, {})
            .get(expiry, {})
            .get(strike, {})
            .get(option_type, {})
            .keys()
        ) or [60]
        valid = [t for t in available_tfs if target_tf % t == 0]
        return max(valid) if valid else None

    def resample_option_day(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        date: int,
        base_tf: int,
        target_tf: int,
    ):
        base_data = (
            self.option_quotes.get(underlying, {})
            .get(expiry, {})
            .get(strike, {})
            .get(option_type, {})
            .get(base_tf, {})
            .get(date)
        )
        if not base_data:
            logger.warning(
                f"resample_option_day: no data underlying={underlying}, expiry={expiry}, "
                f"strike={strike}, type={option_type}, base_tf={base_tf}, date={date} — skipping"
            )
            return

        times = sorted(base_data.keys())
        bucket: List[OptionQuote] = []
        bucket_open_time: int = None
        ratio = target_tf // base_tf

        for t in times:
            if not bucket:
                bucket_open_time = t
            bucket.append(base_data[t])

            if len(bucket) == ratio:
                self.insert_option_quote(
                    OptionQuote(
                        date=date,
                        time=bucket_open_time,
                        symbol=bucket[0].symbol,
                        _open=bucket[0]._open,
                        _high=max(q._high for q in bucket),
                        _low=min(q._low for q in bucket),
                        _close=bucket[-1]._close,
                        _volume=sum(q._volume for q in bucket),
                        strike=strike,
                        expiry=expiry,
                        option_type=option_type,
                        oi=bucket[-1].oi,  # last value in bucket, not sum
                        iv=bucket[-1].iv,  # last value in bucket
                    ),
                    timeframe=target_tf,
                )
                bucket.clear()
                bucket_open_time = None

        if bucket:
            logger.warning(
                f"resample_option_day: partial bucket ({len(bucket)}/{ratio}) "
                f"underlying={underlying}, date={date}, target_tf={target_tf} — flushing"
            )
            self.insert_option_quote(
                OptionQuote(
                    date=date,
                    time=bucket_open_time,
                    symbol=bucket[0].symbol,
                    _open=bucket[0]._open,
                    _high=max(q._high for q in bucket),
                    _low=min(q._low for q in bucket),
                    _close=bucket[-1]._close,
                    _volume=sum(q._volume for q in bucket),
                    strike=strike,
                    expiry=expiry,
                    option_type=option_type,
                    oi=bucket[-1].oi,
                    iv=bucket[-1].iv,
                ),
                timeframe=target_tf,
            )

    def resample_option_quotes(
        self,
        underlying: str,
        expiry: int,
        strike: float,
        option_type: OptionType,
        start_date: int,
        end_date: int,
        timeframe: int,
    ):
        if timeframe <= 0:
            raise ValueError("timeframe must be positive")

        base_tf = self.get_option_best_base(
            underlying, expiry, strike, option_type, timeframe
        )
        if base_tf is None:
            raise ValueError(
                f"No valid base timeframe found for {underlying} {expiry} {strike} {option_type}"
            )

        instrument_name = self.get_instrument_name(
            underlying, expiry, strike, option_type
        )
        for date in get_date_span(start_date, end_date):
            already = (
                self.option_quotes.get(underlying, {})
                .get(expiry, {})
                .get(strike, {})
                .get(option_type, {})
                .get(timeframe, {})
            )
            if date in already:
                continue
            self.resample_option_day(
                underlying, expiry, strike, option_type, date, base_tf, timeframe
            )

    # =========================================================================
    # Options — Chain Snapshot
    # =========================================================================

    def get_option_chain(self, underlying: str, expiry: int) -> List[dict]:
        """
        Fetch a live option chain snapshot from Deribit for a given underlying + expiry.
        Returns a list of dicts with strike, option_type, iv, oi, mark_price, bid, ask.
        """
        params = {"currency": underlying, "kind": "option"}
        response = requests.get(
            f"{DERIBIT_BASE_URL}/get_book_summary_by_currency", params=params
        )
        response.raise_for_status()
        result = response.json().get("result", [])

        chain = []
        for item in result:
            name = item.get("instrument_name", "")
            try:
                u, exp, strike, option_type = _parse_deribit_instrument(name)
            except Exception:
                continue

            if u != underlying or exp != expiry:
                continue

            chain.append(
                {
                    "instrument_name": name,
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": exp,
                    "mark_price": item.get("mark_price"),
                    "iv": item.get("mark_iv"),
                    "bid": item.get("bid_price"),
                    "ask": item.get("ask_price"),
                    "oi": item.get("open_interest"),
                    "volume": item.get("volume"),
                }
            )

        chain.sort(key=lambda x: (x["strike"], x["option_type"]))
        logger.info(
            f"get_option_chain: {len(chain)} contracts for {underlying} expiry={expiry}"
        )
        return chain


meta_data = MetaData()
