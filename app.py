"""
app.py – Confluence Snapshot micro-service  (v4)
Adds exchange-switching to dodge the Binance 451 ban.
────────────────────────────────────────────────────────────────
"""

import os
import math
from flask import Flask, request, jsonify, abort
import ccxt
import pandas as pd
import pandas_ta as ta


# ───────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────
def get_exchange(exchange_id: str = "binanceus") -> ccxt.Exchange:
    """
    Build a ccxt exchange instance.

    Defaults to 'binanceus' so it works from U-S IPs.
    Any ccxt-supported id (kucoin, bybit, okx, …) is accepted.
    """
    if not hasattr(ccxt, exchange_id):
        abort(400, description=f"Unsupported exchange '{exchange_id}'")
    return getattr(ccxt, exchange_id)({
        "enableRateLimit": True,
    })


def finite_or_none(x: float | None):
    return None if (x is None or (isinstance(x, float) and not math.isfinite(x))) else x


# ───────────────────────────────────────────────────────────────
# Flask
# ───────────────────────────────────────────────────────────────
app = Flask(__name__)
DEFAULT_LOOKBACK  = int(os.getenv("LOOKBACK", 14))
DEFAULT_EXCHANGE  = os.getenv("EXCHANGE", "binanceus")   # dodge 451 by default
DEFAULT_INTERVAL  = os.getenv("INTERVAL", "1h")
DEFAULT_PAIR      = os.getenv("PAIR", "BTC/USDT")


@app.route("/")
def index():
    return "Confluence Snapshot is live 🚀", 200


@app.route("/snapshot", methods=["GET", "POST", "OPTIONS"])
def snapshot():
    if request.method == "OPTIONS":          # CORS pre-flight
        return "", 204

    if request.method == "GET":
        params   = request.args
    else:                                    # POST
        params   = request.get_json(force=True, silent=True) or {}

    pair      = params.get("pair",      DEFAULT_PAIR)
    tf        = params.get("interval") or params.get("timeframe") or DEFAULT_INTERVAL
    lookback  = int(params.get("lookback",  DEFAULT_LOOKBACK))
    exch_id   = params.get("exchange",  DEFAULT_EXCHANGE).lower()

    if not pair or not tf:
        abort(400, description="`pair` and `interval` are required")

    ex = get_exchange(exch_id)

    # ── Fetch candles ──────────────────────────────────────────
    try:
        candles = ex.fetch_ohlcv(pair, tf, limit=max(lookback * 5, 200))
    except Exception as err:
        return jsonify({"error": str(err)}), 400

    df = pd.DataFrame(candles, columns=["ts", "o", "h", "l", "c", "v"])

    # ── Indicators ─────────────────────────────────────────────
    rsi_val = ta.rsi(df["c"], length=lookback).iloc[-1]
    atr_val = ta.atr(df["h"], df["l"], df["c"], length=lookback).iloc[-1]

    swing_high = df["h"].max()
    swing_low  = df["l"].min()

    bos = swing_high                                     # placeholder “break of structure”
    ob_low, ob_high = round(swing_low * 1.01, 2), round(swing_low * 1.03, 2)

    payload = {
        "exchange":   exch_id,
        "pair":       pair,
        "interval":   tf,
        "price":      round(float(df['c'].iloc[-1]), 2),
        "rsi":        round(float(rsi_val), 2),
        "atr":        round(float(atr_val), 2),
        "swingHigh":  round(float(swing_high), 2),
        "swingLow":   round(float(swing_low), 2),
        "bos":        round(float(bos), 2),
        "orderBlock": f"{ob_low}-{ob_high}",
    }

    # clean NaN / Inf
    payload = {k: finite_or_none(v) for k, v in payload.items()}

    return jsonify(payload)


# ── Local dev entrypoint ───────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
