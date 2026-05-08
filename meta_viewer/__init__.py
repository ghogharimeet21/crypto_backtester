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


def _summarise_indicators(symbol: str) -> dict:
    tf_map = meta_data.indicators.get(symbol, {})
    out = {}
    for tf, ind_map in sorted(tf_map.items()):
        out[str(tf)] = {}
        for ind_name, dates_map in sorted(ind_map.items()):
            total = sum(len(t) for t in dates_map.values())
            out[str(tf)][ind_name] = {
                "dates": len(dates_map),
                "total_values": total,
                "by_date": {str(d): len(t) for d, t in sorted(dates_map.items())},
            }
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
        | set(meta_data.indicators.keys())
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
    name   = request.args.get("name",   "")

    if not symbol or date is None or tf is None or not name:
        return jsonify({"error": "symbol, date, tf and name are required"}), 400

    times_map = (
        meta_data.indicators
        .get(symbol, {}).get(tf, {}).get(name, {}).get(date, {})
    )

    rows = [{"time": seconds_to_hms(t), "value": v} for t, v in sorted(times_map.items())]
    values = [r["value"] for r in rows]

    return jsonify({
        "symbol": symbol, "date": date, "tf": tf, "name": name,
        "count": len(rows),
        "stats": {"min": min(values) if values else 0, "max": max(values) if values else 0},
        "rows": rows,
    })