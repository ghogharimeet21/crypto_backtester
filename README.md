# 📈 Crypto Backtester

A modular, event-driven backtesting engine for cryptocurrency trading strategies. Built with Python + Flask, it ingests 1-minute OHLCV candles from Binance (or local CSV), resamples them to any timeframe, computes technical indicators, and runs bar-by-bar strategy simulations — all accessible via a REST API with a built-in live inspector UI.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Server](#running-the-server)
- [API Reference](#api-reference)
  - [Engine Routes](#engine-routes)
  - [Meta Viewer Routes](#meta-viewer-routes)
- [Data Layer](#data-layer)
  - [Data Loading](#data-loading)
  - [Resampling](#resampling)
- [Indicators](#indicators)
- [Order Management System (OMS)](#order-management-system-oms)
- [Strategies](#strategies)
  - [SMA Crossover](#sma-crossover)
  - [Adding a New Strategy](#adding-a-new-strategy)
- [Meta Viewer (Live Inspector)](#meta-viewer-live-inspector)
- [Configuration & Environment](#configuration--environment)
- [Running the Jupyter Notebook](#running-the-jupyter-notebook)
- [Contributing](#contributing)

---

## Features

- **Live & CSV data ingestion** — fetches 1-minute candles from the Binance public API or loads from a local CSV cache; auto-paginates large date ranges.
- **Flexible timeframe resampling** — aggregates 1-minute base candles into any N-minute timeframe on demand (5m, 15m, 1h, 4h, etc.).
- **Pre-computed indicator engine** — compute indicators once, look them up in O(1) per bar: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic Oscillator.
- **Bar-by-bar strategy runner** — clean, deterministic simulation loop that prevents look-ahead bias.
- **REST API** — Flask-powered endpoints to trigger backtests and inspect in-memory state.
- **Meta Viewer** — browser-based live inspector showing in-memory quote trees, resampled candles, and indicator values in real time.
- **OMS (Order Management System)** — trade lifecycle models: open/close trades with PnL, win rate, and summary statistics.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Flask App (app.py)                   │
│              port 5002  │  CORS enabled                     │
└────────────────┬────────────────────┬───────────────────────┘
                 │                    │
         /engine/*              /meta/*
                 │                    │
    ┌────────────▼────────┐  ┌────────▼──────────┐
    │   Engine Blueprint  │  │  Meta Viewer BP   │
    │  (engine/routes.py) │  │ (meta_viewer/)    │
    └────────────┬────────┘  └───────────────────┘
                 │
    ┌────────────▼──────────────────────────────┐
    │         Strategy Evaluators               │
    │   engine/evaluator/sma_crossover/         │
    └────────────┬──────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────┐
    │          MetaData Store (data/local.py)   │
    │  base_quotes  │  resampled_quotes         │
    │  available_dates  │  indicators           │
    └────┬──────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────┐
    │         Indicator Engine                  │
    │              (data/indicators.py)         │
    │  SMA · EMA · RSI · MACD · BB · ATR · STOCH│
    └───────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────┐
    │         OMS (oms/)                        │
    │  Trade · BacktestResult · TradeStatus     │
    └───────────────────────────────────────────┘
```

---

## Project Structure

```
crypto_backtester/
│
├── app.py                          # Flask app entry point
├── requirements.txt                # Python dependencies
├── btcusdt_jan2026.csv             # Pre-cached 1-min BTCUSDT candles (Jan 2026)
├── default_load.csv                # Default data used on startup
├── symbols.json                    # Reference list of supported Binance symbols
├── test.py                         # Manual test script
├── test.ipynb                      # Jupyter notebook for ad-hoc exploration
│
├── data/                           # Data layer
│   ├── enums.py                    # TimeFrameType enum
│   ├── models.py                   # Quote data model (OHLCV)
│   ├── utils.py                    # Date/time helpers (ms ↔ int, HH:MM:SS ↔ seconds)
│   ├── indicators.py               # Self-contained indicator computation & storage
│   └── local.py                    # MetaData store — load, insert, resample, validate
│
├── engine/                         # Strategy execution layer
│   ├── __init__.py
│   ├── routes.py                   # Flask blueprint — /engine/* endpoints
│   └── evaluator/
│       ├── __init__.py
│       ├── utils.py                # Date span helpers
│       └── sma_crossover/
│           ├── __init__.py         # SMA crossover strategy executor
│           └── models.py           # SmaCrossoverStrategy config model
│
├── oms/                            # Order Management System
│   ├── enums.py                    # TradeStatus enum (OPEN / CLOSE)
│   └── models.py                   # Trade and BacktestResult models
│
└── meta_viewer/                    # Live in-memory inspector
    ├── __init__.py                 # Flask blueprint — /meta/* routes
    └── templates/
        └── meta_viewer.html        # Browser-based tree view UI
```

---

## Prerequisites

- Python 3.11+
- pip
- Internet access (for live Binance data fetching — only needed if no CSV cache exists)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/ghogharimeet21/crypto_backtester.git
cd crypto_backtester

# 2. (Recommended) Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the Server

```bash
python app.py
```

The server starts on **http://localhost:5002** with debug mode enabled.

On startup, it automatically loads 1-minute BTCUSDT candles for January 2026 from the local CSV (`btcusdt_jan2026.csv`). If the CSV is not found it fetches the data from the Binance API and saves it for future runs.

---

## API Reference

### Engine Routes

#### `GET /engine/health`

Health check.

**Response:**
```json
{
  "status": "success",
  "message": "Engine is running"
}
```

---

#### `POST /engine/sma_crossover`

Run an SMA crossover backtest.

**Request body:**
```json
{
  "symbol":       "BTCUSDT",
  "timeframe":    300,
  "periods":      [10, 20],
  "start_date":   20260101,
  "end_date":     20260131
}
```

| Field | Type | Description |
|---|---|---|
| `symbol` | string | Binance trading pair, e.g. `"BTCUSDT"` |
| `timeframe` | int | Candle duration in **seconds** (e.g. `300` = 5-minute) |
| `periods` | int[2] | `[fast_period, slow_period]` — order doesn't matter, smaller is treated as fast |
| `start_date` | int | Inclusive start date as `YYYYMMDD` |
| `end_date` | int | Inclusive end date as `YYYYMMDD` |

**Response:**
```json
{
  "status": "success",
  "execution_time_sec": 0.412,
  "result": {
    "total_trades": 14,
    "winning_trades": 8,
    "losing_trades": 6,
    "win_rate_pct": 57.14,
    "total_pnl": 1234.56,
    "total_pnl_pct": 12.34,
    "trades": [
      {
        "entry_date": 20260101,
        "entry_time": "02:15:00",
        "entry_price": 94500.0,
        "exit_date": 20260103,
        "exit_time": "09:30:00",
        "exit_price": 96200.0,
        "pnl": 1700.0,
        "pnl_pct": 1.7989,
        "is_open": false
      }
    ]
  }
}
```

**Error response:**
```json
{
  "status": "failed",
  "err": "fast_period must be less than slow_period"
}
```

---

### Meta Viewer Routes

#### `GET /meta/`

Opens the live browser-based inspector UI.

#### `GET /meta/snapshot`

Returns a full JSON tree of everything currently held in memory — candle counts per symbol/date/timeframe and indicator value counts. Polled automatically every 2 seconds by the UI.

#### `GET /meta/quotes?symbol=BTCUSDT&date=20260101&tf=300`

Returns all OHLCV candles for a single symbol, date, and timeframe.

| Param | Required | Description |
|---|---|---|
| `symbol` | ✅ | e.g. `BTCUSDT` |
| `date` | ✅ | `YYYYMMDD` integer |
| `tf` | ❌ | Timeframe in seconds, default `60` (1-minute) |

#### `GET /meta/indicator_values?symbol=BTCUSDT&date=20260101&tf=300&name=sma`

Returns all computed indicator values for a symbol/date/timeframe/indicator combination.

| Param | Required | Description |
|---|---|---|
| `symbol` | ✅ | e.g. `BTCUSDT` |
| `date` | ✅ | `YYYYMMDD` integer |
| `tf` | ✅ | Timeframe in seconds |
| `name` | ✅ | Indicator name, e.g. `sma`, `ema`, `rsi` |

---

## Data Layer

### Data Loading

The `MetaData` class (`data/local.py`) is a singleton (`meta_data`) shared across the entire application. It holds all OHLCV data in memory using a nested dict structure:

```
base_quotes:      symbol → date → time_seconds → Quote
resampled_quotes: symbol → timeframe → date → time_seconds → Quote
available_dates:  symbol → timeframe → set(dates)
```

Quotes are keyed by:
- **date** — integer in `YYYYMMDD` format (e.g. `20260101`)
- **time** — seconds since midnight (e.g. `9000` = `02:30:00`)

Data is fetched from Binance's public `/api/v3/klines` endpoint, auto-paginating in 1,000-candle chunks. The default load covers **BTCUSDT 1-minute candles for January 2026**.

To load data for a different symbol or date range programmatically:
```python
from data.local import meta_data
meta_data.load_data("ETHUSDT", "20260101", "20260201")
```

### Resampling

Any timeframe that is an even multiple of 60 seconds can be computed on demand. Resampling aggregates base 1-minute candles into the target timeframe candles:

- **Open** = first bar's open
- **High** = max of all highs in window
- **Low** = min of all lows in window
- **Close** = last bar's close
- **Volume** = sum of all volumes in window

The engine automatically selects the largest already-computed base that evenly divides the target (e.g. to build 1h candles, it will use 5-min candles if they already exist rather than re-aggregating from 1-minute).

---

## Indicators

All indicators are implemented from scratch (no TA-Lib dependency) in `data/indicators.py` and use the same nested dict storage pattern:

```
Single-value:  symbol → tf → period  → date → time → float
Multi-value:   symbol → tf → (params) → date → time → dict
```

| Indicator | Method | Returns | Notes |
|---|---|---|---|
| **SMA** | `compute_sma(symbol, tf, period, start, end)` | `float` | Rolling sum / period |
| **EMA** | `compute_ema(symbol, tf, period, start, end)` | `float` | Seeded from SMA; k = 2/(period+1) |
| **RSI** | `compute_rsi(symbol, tf, period, start, end)` | `float` | Wilder's smoothing |
| **MACD** | `compute_macd(symbol, tf, fast, slow, signal, start, end)` | `{line, signal, hist}` | Standard MACD |
| **Bollinger Bands** | `compute_bb(symbol, tf, period, std_dev, start, end)` | `{upper, mid, lower}` | Population std (ddof=0, matches TradingView) |
| **ATR** | `compute_atr(symbol, tf, period, start, end)` | `float` | Wilder's smoothing; TR = max(H-L, |H-PC|, |L-PC|) |
| **Stochastic** | `compute_stoch(symbol, tf, k_period, d_period, start, end)` | `{k, d}` | %K with SMA-based %D |

All getters return `None` during warmup periods — strategy code must always null-check.

**Example usage:**
```python
from data.local import meta_data

# Compute
meta_data.indicators.compute_ema("BTCUSDT", 300, 20, 20260101, 20260131)

# Read at a specific bar
ema = meta_data.indicators.get_ema("BTCUSDT", 300, 20, 20260115, 34200)
# → e.g. 95430.12 or None (warmup)
```

---

## Order Management System (OMS)

### `Trade` (`oms/models.py`)

Represents a single long trade (entry → exit).

| Attribute | Type | Description |
|---|---|---|
| `entry_date` | int | Entry date (`YYYYMMDD`) |
| `entry_time` | int | Entry time in seconds since midnight |
| `entry_price` | float | Fill price on entry |
| `exit_date` | int | Exit date (`YYYYMMDD`), or `None` if still open |
| `exit_time` | int | Exit time in seconds, or `None` |
| `exit_price` | float | Fill price on exit, or `None` |
| `pnl` | float | Absolute P&L (`exit_price - entry_price`) |
| `pnl_pct` | float | Percentage return |
| `trade_status` | TradeStatus | `OPEN` or `CLOSE` |

### `BacktestResult` (`oms/models.py`)

Aggregates a list of trades into summary statistics.

| Field | Description |
|---|---|
| `total_trades` | Number of closed trades |
| `winning_trades` | Trades with `pnl > 0` |
| `losing_trades` | Trades with `pnl ≤ 0` |
| `win_rate` | `winning / total * 100` |
| `total_pnl` | Sum of all P&L |
| `total_pnl_pct` | Sum of all percentage returns |

---

## Strategies

### SMA Crossover

**Location:** `engine/evaluator/sma_crossover/`

**Logic:**
1. Compute fast SMA and slow SMA across the full date range.
2. Walk bar by bar through the candle series.
3. **BUY** (open long) when the fast SMA crosses **above** the slow SMA and no position is open.
4. **SELL** (close long) when the fast SMA crosses **below** the slow SMA.
5. Only one position held at a time — no pyramiding.
6. If still in a position at the end of the range, the trade is recorded as open (no forced close).

**Validation:**
- `fast_period` must be strictly less than `slow_period`.
- Exactly 2 periods must be provided; order doesn't matter (smaller is auto-assigned as fast).
- `timeframe` must be a positive integer (seconds).

### Adding a New Strategy

1. Create a new folder under `engine/evaluator/`, e.g. `engine/evaluator/rsi_mean_reversion/`.
2. Add a `models.py` with a config class that validates request params.
3. Add an `__init__.py` with an `execute(strategy) -> BacktestResult` function following the same data-flow pattern:
   - Compute indicators via `meta_data.indicators.compute_*`.
   - Iterate over `meta_data.get_quotes_series(...)`.
   - Lookup indicator values with `meta_data.indicators.get_*`.
   - Build `Trade` objects; return `BacktestResult(trades)`.
4. Register a new route in `engine/routes.py`.

---

## Meta Viewer (Live Inspector)

Navigate to **http://localhost:5002/meta/** after starting the server.

The viewer polls `/meta/snapshot` every 2 seconds and renders a collapsible tree showing:

- **Base quotes** — per-symbol, per-date candle counts (1-minute base data)
- **Resampled quotes** — per-symbol, per-timeframe, per-date candle counts
- **Indicators** — per-symbol, per-timeframe, per-indicator name/params, per-date value counts

The lazy-load endpoints (`/meta/quotes`, `/meta/indicator_values`) let you drill down to see actual OHLCV rows or indicator time-series for a specific symbol/date/tf combination.

---

## Configuration & Environment

| Setting | Location | Default | Description |
|---|---|---|---|
| Server host | `app.py` | `0.0.0.0` | Bind address |
| Server port | `app.py` | `5002` | HTTP port |
| Default CSV | `data/local.py` | `btcusdt_jan2026.csv` | Pre-cached candle data |
| Binance API URL | `data/local.py` | `https://api.binance.com/api/v3/klines` | Public klines endpoint |
| Candle fetch limit | `data/local.py` | `1000` per request | Binance pagination chunk size |

No API key is required — only Binance's public endpoints are used.

---

## Running the Jupyter Notebook

```bash
jupyter notebook test.ipynb
```

Use the notebook for ad-hoc exploration: loading data, computing indicators manually, and inspecting the `MetaData` store interactively.

---

## Contributing

1. Fork the repository and create a feature branch.
2. Follow the existing module pattern — keep data, engine, and OMS layers separate.
3. All indicator compute methods must guard against warmup bars (return `None`, not 0).
4. Strategy code must null-check every indicator value before using it.
5. Submit a pull request with a clear description of what the strategy or feature does.
