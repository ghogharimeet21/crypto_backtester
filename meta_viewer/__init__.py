"""
meta_viewer — live inspector for the in-memory MetaData store.

Routes
------
GET /meta/                                              → visual tree UI
GET /meta/snapshot                                      → full tree summary (polled every 2 s)
GET /meta/quotes?symbol=&date=&tf=                      → OHLCV rows for one day  (lazy)
GET /meta/indicator_values?symbol=&date=&tf=&name=      → indicator rows for one day (lazy)
"""

import os
from flask import Blueprint, jsonify, render_template, request
from data.local import meta_data
from data.utils import seconds_to_hms

meta_bp = Blueprint(
    "meta",
    __name__,
    url_prefix="/meta",
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot helpers  (summary counts only — no raw data)
# ─────────────────────────────────────────────────────────────────────────────

def _summarise_base(symbol: str) -> dict:
    dates_map = meta_data.base_quotes.get(symbol, {})
    return {str(date): len(times) for date, times in sorted(dates_map.items())}


def _summarise_resampled(symbol: str) -> dict:
    tf_map = meta_data.resampled_quotes.get(symbol, {})
    out = {}
    for tf, dates_map in sorted(tf_map.items()):
        out[str(tf)] = {str(date): len(times) for date, times in sorted(dates_map.items())}
    return out


def _indicator_symbol_set() -> set:
    ind = meta_data.indicators
    keys: set = set()
    for store in (ind.sma, ind.ema, ind.rsi, ind.atr, ind.macd, ind.bb, ind.stoch):
        keys |= set(store.keys())
    return keys


def _param_key_to_suffix(param_key) -> str:
    if isinstance(param_key, tuple):
        return "_".join(str(x) for x in param_key)
    return str(param_key)


def _parse_indicator_series(name: str):
    """
    Decode tree keys like sma_20, bb_20_2.0, macd_12_26_9 → (kind, lookup_key).
    lookup_key is int for scalar series or tuple for multi-param series.
    """
    if "_" not in name:
        return None, None
    kind, rest = name.split("_", 1)
    kind = kind.lower()
    if kind in ("sma", "ema", "rsi", "atr"):
        try:
            return kind, int(rest)
        except ValueError:
            return None, None
    if kind == "bb":
        segs = rest.split("_")
        if len(segs) >= 2:
            try:
                return kind, (int(segs[0]), float(segs[1]))
            except ValueError:
                return None, None
    if kind == "macd":
        segs = rest.split("_")
        if len(segs) >= 3:
            try:
                return kind, (int(segs[0]), int(segs[1]), int(segs[2]))
            except ValueError:
                return None, None
    if kind == "stoch":
        segs = rest.split("_")
        if len(segs) >= 2:
            try:
                return kind, (int(segs[0]), int(segs[1]))
            except ValueError:
                return None, None
    return None, None


def _summarise_indicators(symbol: str) -> dict:
    """
    Shape matches meta_viewer.html: indicators[tf][name] = summary,
    with names like sma_20 so /indicator_values?name=sma_20 works.
    """
    ind = meta_data.indicators
    out: dict = {}

    def add_branch(tf: int, series_name: str, by_date: dict):
        tf_s = str(tf)
        bucket = out.setdefault(tf_s, {})
        n = sum(len(times) for times in by_date.values())
        bucket[series_name] = {
            "dates": len(by_date),
            "total_values": n,
            "by_date": {str(d): len(t) for d, t in sorted(by_date.items())},
        }

    for label, store in (
        ("sma", ind.sma),
        ("ema", ind.ema),
        ("rsi", ind.rsi),
        ("atr", ind.atr),
    ):
        for tf, by_period in store.get(symbol, {}).items():
            for period_key, by_date in by_period.items():
                add_branch(tf, f"{label}_{_param_key_to_suffix(period_key)}", by_date)

    for label, store in (("macd", ind.macd), ("bb", ind.bb), ("stoch", ind.stoch)):
        for tf, by_params in store.get(symbol, {}).items():
            for param_key, by_date in by_params.items():
                add_branch(tf, f"{label}_{_param_key_to_suffix(param_key)}", by_date)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@meta_bp.route("/")
def viewer():
    return render_template("meta_viewer.html")


@meta_bp.route("/snapshot")
def snapshot():
    symbols = sorted(
        set(meta_data.base_quotes.keys())
        | set(meta_data.resampled_quotes.keys())
        | _indicator_symbol_set()
    )

    payload = {}
    for sym in symbols:
        base = _summarise_base(sym)
        res  = _summarise_resampled(sym)
        inds = _summarise_indicators(sym)

        payload[sym] = {
            "base": {
                "dates":         len(base),
                "total_candles": sum(base.values()),
                "by_date":       base,
            },
            "resampled": {
                tf: {
                    "dates":         len(d),
                    "total_candles": sum(d.values()),
                    "by_date":       d,
                }
                for tf, d in res.items()
            },
            "indicators": inds,
        }

    return jsonify({"symbols": payload})


@meta_bp.route("/quotes")
def quotes():
    symbol = request.args.get("symbol", "")
    date   = request.args.get("date",   type=int)
    tf     = request.args.get("tf",     type=int, default=60)

    if not symbol or date is None:
        return jsonify({"error": "symbol and date are required"}), 400

    if tf == 60:
        times_map = meta_data.base_quotes.get(symbol, {}).get(date, {})
    else:
        times_map = meta_data.resampled_quotes.get(symbol, {}).get(tf, {}).get(date, {})

    rows = []
    for t in sorted(times_map.keys()):
        q = times_map[t]
        rows.append({
            "time":   seconds_to_hms(t),
            "open":   q._open,
            "high":   q._high,
            "low":    q._low,
            "close":  q._close,
            "volume": round(q._volume, 6),
        })

    volumes = [r["volume"] for r in rows]
    closes  = [r["close"]  for r in rows]

    return jsonify({
        "symbol": symbol, "date": date, "tf": tf, "count": len(rows),
        "stats": {
            "max_volume": max(volumes) if volumes else 0,
            "min_close":  min(closes)  if closes  else 0,
            "max_close":  max(closes)  if closes  else 0,
        },
        "rows": rows,
    })


@meta_bp.route("/indicator_values")
def indicator_values():
    symbol = request.args.get("symbol", "")
    date   = request.args.get("date",   type=int)
    tf     = request.args.get("tf",     type=int)
    kind   = request.args.get("kind", "")
    period = request.args.get("period", type=int)
    name   = request.args.get("name",   "")

    if not symbol or date is None or tf is None:
        return jsonify({"error": "symbol, date, and tf are required"}), 400

    if kind and period is not None:
        series_kind, lookup = kind.lower(), period
    elif name:
        series_kind, lookup = _parse_indicator_series(name)
    else:
        series_kind, lookup = None, None

    if not series_kind or lookup is None:
        return (
            jsonify(
                {
                    "error": "Provide name=sma_20 (or bb_20_2.0, macd_12_26_9) "
                    "or kind=sma&period=20"
                }
            ),
            400,
        )

    ind = meta_data.indicators
    if series_kind == "sma":
        times_map = ind.sma.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "ema":
        times_map = ind.ema.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "rsi":
        times_map = ind.rsi.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "atr":
        times_map = ind.atr.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "macd":
        times_map = ind.macd.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "bb":
        times_map = ind.bb.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    elif series_kind == "stoch":
        times_map = ind.stoch.get(symbol, {}).get(tf, {}).get(lookup, {}).get(date, {})
    else:
        return jsonify({"error": f"unsupported series {series_kind!r}"}), 400

    rows = []
    nums: list = []
    for t, v in sorted(times_map.items()):
        if isinstance(v, dict):
            rows.append({"time": seconds_to_hms(t), "value": v})
            nums.extend(x for x in v.values() if isinstance(x, (int, float)))
        else:
            rows.append({"time": seconds_to_hms(t), "value": v})
            if isinstance(v, (int, float)):
                nums.append(v)

    return jsonify({
        "symbol": symbol, "date": date, "tf": tf, "name": name or f"{series_kind}_{lookup}",
        "count": len(rows),
        "stats": {"min": min(nums) if nums else 0, "max": max(nums) if nums else 0},
        "rows": rows,
    })