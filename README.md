# crypto_backtester

A Python/Flask backtesting engine for crypto trading strategies, built around an in-memory OHLCV quote store, a TA-Lib-powered indicator layer, and a pluggable strategy evaluator system. It pulls historical klines directly from Binance's public API, computes indicators on demand, walks the resulting series bar-by-bar to simulate entries/exits, and returns a full trade log with aggregate performance stats as JSON.

> ⚠️ This project is for research, learning, and portfolio demonstration purposes. It does not place real trades and comes with no guarantee of profitability. See [Known Gaps & Caveats](#known-gaps--caveats) before relying on any strategy result.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Architecture Deep Dive](#architecture-deep-dive)
  - [Data Layer (`data/`)](#data-layer-data)
  - [Indicators (`data/indicators/`)](#indicators-dataindicators)
  - [Engine & Strategies (`engine/`)](#engine--strategies-engine)
  - [Order Management (`oms/`)](#order-management-oms)
- [API Reference](#api-reference)
- [Getting Started](#getting-started)
- [Running with Docker](#running-with-docker)
- [Known Gaps & Caveats](#known-gaps--caveats)

---

## How It Works

At a high level, a single backtest request flows through four stages:

1. **Fetch** — On startup (and on-demand per request), 1-minute OHLCV candles are pulled from Binance's `/api/v3/klines` endpoint and cached in memory, keyed by `symbol -> timeframe -> date -> time`.
2. **Resample** — If a strategy asks for a timeframe other than 1 minute (e.g. 5-min, 1-hour candles), the engine buckets the cached 1-minute candles into the target timeframe on the fly, aligned to fixed exchange-style time boundaries.
3. **Compute indicators** — SMA, EMA, RSI, and rolling VWAP are computed over the resampled series using TA-Lib (and NumPy for VWAP, since TA-Lib has no native VWAP function), then cached the same way quotes are.
4. **Evaluate** — A strategy-specific evaluator walks the quote series bar-by-bar, checks entry/exit rules against the indicator values, manages one open position at a time (or one per symbol for multi-leg strategies), and produces a list of closed `Trade` objects plus aggregate stats (win rate, profit factor, equity curve, etc.).

Everything runs synchronously inside a single Flask process — there's no database and no persistence layer; all cached quotes/indicators live in one shared in-process `MetaData` object for the lifetime of the server.

---

## Project Structure

```
crypto_backtester/
├── app.py                          # Flask entrypoint — boots the app, preloads BTCUSD data, registers routes
├── requirements.txt                 # Pinned dependencies (Flask, pandas, numpy, ta-lib, requests, ...)
├── Dockerfile                       # Slim Python 3.12 image, dependencies installed via uv
├── compose.yml                      # Docker Compose service definition (port 5003, bind-mounted source)
│
├── commons/
│   └── utils.py                     # Shared date/time helpers: date<->ms conversion, HH:MM:SS <-> seconds,
│                                     # date span generation, ATM strike rounding
│
├── data/
│   ├── __init__.py                  # MetaData — the app-wide in-memory store (quotes + indicators + loaders)
│   ├── models.py                    # BaseModel, Underlying, Quote (OHLCV snapshot)
│   ├── utils.py                     # MetaUtils — quote insertion/retrieval, resampling, DataFrame building
│   ├── enums.py                     # TimeFrameType enum
│   │
│   ├── feed/
│   │   ├── __init__.py              # MetaDataLoader — wraps the exchange feed(s)
│   │   └── spot/binance/__init__.py # Binance — fetches historical klines via REST, paginated by time window
│   │
│   └── indicators/
│       ├── __init__.py              # Indicator — compute_sma/ema/rsi/vwap + get_* accessors, TA-Lib backed
│       ├── models.py                 # SmaSetting, EmaSetting, IndicatorSettings config objects
│       ├── enums.py                  # SOURCE enum (OPEN/HIGH/LOW/CLOSE)
│       └── utils.py                  # Parses indicator settings out of incoming strategy JSON
│
├── engine/
│   ├── routes.py                    # Flask Blueprint — /engine/health, /engine/sma_crossover, /engine/trend_confluence
│   ├── runtime.py                   # (currently unused / placeholder)
│   │
│   └── evaluator/
│       ├── utils.py                  # Re-exports get_date_span for strategy config objects
│       │
│       ├── sma_crossover/
│       │   ├── __init__.py           # execute() — fast/slow SMA crossover strategy loop
│       │   └── models.py             # SmaCrossoverStrategy — parses/validates the request payload
│       │
│       ├── trend_confluence/
│       │   ├── __init__.py           # execute() — multi-symbol EMA trend + RSI pullback + BB confluence strategy
│       │   └── models.py             # TrendConfluenceStrategy — parses/validates the request payload
│       │
│       └── test_sets/
│           ├── __init__.py           # Ad-hoc manual test harness (not a real strategy)
│           └── models.py             # (empty — placeholder)
│
└── oms/
    ├── enums.py                      # TradeStatus, OrderSide, ExitReason enums
    └── models.py                     # Trade (single position lifecycle) and BacktestResult (aggregate stats)
```

---

## Architecture Deep Dive

### Data Layer (`data/`)

The heart of the app is `MetaData` (instantiated once as the module-level singleton `meta_data` in `data/__init__.py`). It holds:

- **`quotes`** — a nested dict `symbol -> timeframe (seconds) -> date (YYYYMMDD int) -> time (seconds-since-midnight int) -> Quote`. This shape avoids a database entirely while still supporting fast point lookups and ordered series extraction.
- **`indicators`** — an `Indicator` instance (see below) that mirrors the same nested-dict caching pattern per indicator type.
- **`data_loader`** — a `MetaDataLoader` wrapping the Binance spot feed.
- **`meta_utils`** — a `MetaUtils` instance with the actual logic for inserting quotes, fetching missing date ranges, and resampling.

Key behaviors in `MetaUtils`:

- **`fill_relevant_quotes`** — the main "make sure I have the data I need" entrypoint. For 1-min timeframe requests it fetches only the missing dates from Binance (with a 5-day buffer on each side for indicator warmup). For any other timeframe it delegates to resampling.
- **`resample_day` / `resample_quotes`** — buckets a base timeframe (usually 1-min) into a coarser target timeframe, aligning bucket boundaries to `(time // target_tf) * target_tf` so candles line up the way an exchange chart would, even across data gaps.
- **`get_best_base`** — picks the finest already-cached timeframe that evenly divides into the requested target timeframe, so repeated resampling doesn't always re-derive from 1-min data if a coarser cache already exists for that date.
- **`_build_quote_df`** — converts the cached dict structure into a sorted pandas DataFrame, which is what gets fed into TA-Lib for indicator computation.

The Binance feed (`data/feed/spot/binance/__init__.py`) hits `GET https://api.binance.com/api/v3/klines` in a paginated loop (1000 candles per request, matching Binance's API limit), converting each row into a `Quote` and inserting it via `meta_utils.insert_quote`.

### Indicators (`data/indicators/`)

The `Indicator` class computes and caches four indicators, all following the same pattern:

| Indicator | Method | Backing | Notes |
|---|---|---|---|
| SMA | `compute_sma` / `get_sma` | `talib.SMA` | Warmup bars stored as `None` |
| EMA | `compute_ema` / `get_ema` | `talib.EMA` | Warmup bars stored as `None` |
| RSI | `compute_rsi` / `get_rsi` | `talib.RSI` | 0–100 range, warmup bars as `None` |
| VWAP | `compute_vwap` / `get_vwap` | Manual NumPy cumulative-sum | Rolling (not session-anchored), since TA-Lib has no VWAP function |

Each `compute_*` method pulls a DataFrame via `MetaUtils._build_quote_df`, runs the TA-Lib (or NumPy) calculation, and writes results into a cache dict shaped `symbol -> timeframe -> source -> period -> date -> time -> value`, mirroring the quote cache. Each `get_*` is a safe nested lookup that logs and returns `None` on a cache miss rather than raising.

`data/indicators/utils.py` also has helpers (`get_sma_setting`, `get_ema_setting`, `get_indicator_settings`) for parsing indicator configuration blocks out of incoming strategy JSON, for strategies that want configurable indicator settings beyond fixed periods.

### Engine & Strategies (`engine/`)

`engine/routes.py` defines a Flask Blueprint (`engine_bp`, mounted at `/engine`) with one route per strategy, plus a health check. Each strategy route:

1. Parses `request.json` into a `*Strategy` config object (validating required fields, raising `ValueError` on bad input).
2. Calls that strategy's `execute()` function.
3. Wraps the result in a JSON response with `status`, `execution_time_sec`, and the serialized `BacktestResult`.
4. On any exception, logs the full traceback and returns `{"status": "failed", "err": ...}` with a 400.

**`sma_crossover`** — the simplest strategy. Computes a fast and slow SMA, and on each bar:
- Enters **long** when fast SMA crosses above slow SMA.
- Enters **short** when fast SMA crosses below slow SMA (only if `allow_short` is set).
- Exits on the opposite crossover, or when target/stop-loss (fixed points from entry) is hit against the candle's high/low.
- If both target and stop-loss are touched on the same candle, stop-loss is assumed to have hit first (a conservative backtesting convention).
- Only one position open at a time; any position still open at the end of the date range is force-closed at the last available price (`ExitReason.EOD`).

**`trend_confluence`** — a more involved, multi-symbol strategy requiring three signals to agree before entering:
1. **Regime filter** — price above/below a slow EMA (default period 200) sets the only direction that leg is allowed to trade.
2. **Pullback trigger** — RSI dipping to/below (long) or rallying to/above (short) a threshold and then recovering — a "buy the dip within an established trend" entry, not a standalone reversal signal.
3. **Volatility gate** — price must be on the trade side of the Bollinger Band midline, confirming the pullback actually recovered.

Each symbol in the request's `symbols` list is tracked as an independent leg with its own open position, and all legs' candles are merged into one chronologically-sorted stream so bars are evaluated in true time order across symbols. All closed trades across every leg are merged into a single `BacktestResult`.

**`test_sets`** — not a real strategy; a scratch harness (`execute()`) used for manually poking at indicator computation during development. Not wired to a meaningful route response.

### Order Management (`oms/`)

- **`Trade`** — represents one position's full lifecycle: entry price/time/side, derived `stop_loss_price`/`target_price` (computed from points-from-entry at construction time), and a `close()` method that records the exit and computes `pnl`, `pnl_pct`, and `holding_seconds` (calculated via absolute timestamps rather than raw time-of-day subtraction, so trades held across midnight — normal on a 24/7 spot market — don't produce negative durations).
- **`BacktestResult`** — aggregates a list of `Trade`s into summary statistics: total/winning/losing/breakeven trade counts, win rate, total PnL (absolute and %), average win/loss, largest win/loss, profit factor, target/stop-loss hit counts, average holding time, and a cumulative equity curve. Both classes expose `to_dict()` for clean JSON serialization.

---

## API Reference

Base URL: `http://localhost:5003/engine`

### `GET /health`
Simple liveness check.
```json
{ "status": "success", "message": "Engine is running" }
```

### `POST /sma_crossover`
Runs the SMA crossover backtest.

**Request body:**
```json
{
  "symbol": "BTCUSDT",
  "timeframe": 300,
  "fast_period": 10,
  "slow_period": 20,
  "start_date": 20260101,
  "end_date": 20260131,
  "target": 500,
  "stop_loss": 200,
  "allow_short": false
}
```
- `timeframe` is in **seconds** (e.g. `300` = 5-minute candles).
- `fast_period`/`slow_period` can also be passed as `"periods": [10, 20]`.
- `target`/`stop_loss` are absolute **points** away from entry price, not percentages.

**Response:** `{ "status": "success", "execution_time_sec": ..., "result": { ...BacktestResult.to_dict() } }`

### `POST /trend_confluence`
Runs the multi-symbol trend/pullback/volatility confluence backtest.

**Request body:**
```json
{
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframe": 3600,
  "start_date": 20260101,
  "end_date": 20260131,
  "trend_period": 200,
  "rsi_period": 14,
  "rsi_pullback_long": 45,
  "rsi_pullback_short": 55,
  "bb_period": 20,
  "bb_std": 2.0,
  "target": 500,
  "stop_loss": 200,
  "allow_short": true
}
```
All indicator-period fields are optional and fall back to the defaults shown above.

> **Note:** this route currently calls `meta_data.indicators.compute_bb` / `get_bb` for the Bollinger Band gate, but no Bollinger Band computation exists yet in `data/indicators/`. See [Known Gaps](#known-gaps--caveats) — this endpoint will raise until that indicator is implemented.

---

## Getting Started

**Requirements:** Python 3.12, and [TA-Lib's C library](https://ta-lib.org/) installed on your system before `pip install ta-lib` will succeed.

```bash
git clone https://github.com/ghogharimeet21/crypto_backtester.git
cd crypto_backtester

pip install -r requirements.txt

python app.py
```

The server starts on `http://0.0.0.0:5003` in debug mode. On boot, `app.py` preloads one month of `BTCUSD` 1-minute data (see the hardcoded call in `app.py`) before the routes are registered — for a real symbol, note Binance list this pair as `BTCUSDT`.

Test it's alive:
```bash
curl http://localhost:5003/engine/health
```

Run a backtest:
```bash
curl -X POST http://localhost:5003/engine/sma_crossover \
  -H "Content-Type: application/json" \
  -d '{
        "symbol": "BTCUSDT",
        "timeframe": 300,
        "fast_period": 10,
        "slow_period": 20,
        "start_date": 20260101,
        "end_date": 20260107,
        "target": 500,
        "stop_loss": 200
      }'
```

---

## Running with Docker

```bash
docker compose up --build
```

This builds a slim Python 3.12 image (dependencies installed via [`uv`](https://github.com/astral-sh/uv) for speed), exposes port `5003`, and bind-mounts the project directory into the container so local edits are picked up without a rebuild. Timezone is set to `Asia/Kolkata` in the compose environment.

---

## Known Gaps & Caveats

This is an actively evolving personal/portfolio project. A few things worth knowing before extending or demoing it:

- **`trend_confluence` references an unimplemented Bollinger Band indicator.** `compute_bb`/`get_bb` are called in `engine/evaluator/trend_confluence/__init__.py` but not defined anywhere in `data/indicators/`. The endpoint will fail until this is added (following the same `compute_*`/`get_*` + nested-cache pattern as SMA/EMA/RSI).
- **No persistence layer.** All quotes and indicators live in a single in-process dict for the lifetime of the server; restarting the app clears the cache and re-fetches from Binance as needed.
- **Single shared `MetaData` instance.** Concurrent requests for the same symbol/timeframe share the same cache, which is efficient but means this isn't currently isolated per-request/per-user — fine for a demo/single-user backtesting tool, not yet safe as a multi-tenant service.
- **`engine/runtime.py` and `test_sets/models.py` are empty placeholders**, and `test_sets/__init__.py` is a manual scratch harness rather than a real strategy — none of these are wired into meaningful behavior yet.
- **Fixed points, not percentages, for target/stop-loss**, and only one position per symbol at a time — position sizing, leverage, and fees are not modeled.
- **This is a backtester, not a live trading system.** It does not place orders on any exchange; it only simulates strategy performance against historical Binance data.
