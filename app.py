"""
app.py – Confluence Snapshot micro-service
──────────────────────────────────────────
Pulls the latest OHLCV from Binance, calculates RSI & ATR with
pandas-ta, and returns a compact JSON snapshot suitable for a GPT
“action” (OpenAPI) endpoint.

Local dev:
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

Render deployment:
    Start command →  gunicorn app:app
"""

import os
import math
from flask import Flask, request, jsonify, abort

import ccxt
import pandas as pd
import pandas_ta as ta


# ───────────────────────────────────────────────────────────────
#  Exchange init (public endpoints only)
# ───────────────────────────────────────────────────────────────
ex = ccxt.binance({"enableRateLimit": True})

app = Flask(__name__)


@app.route("/")
def index():
    """Simple health-check route."""
    return "Confluence Snapshot is up and running!", 200


@app.route("/snapshot", methods=["GET", "POST", "OPTIONS"])
def snapshot():
    """
    Accepts EITHER a GET query string or a POST JSON body.

    • GET  /snapshot?pair=BTCUSDT&interval=1h[&lookback=14]
    • POST /snapshot   {"pair": "BTCUSDT", "interval": "1h", "lookback": 14}

    Returns:
        {
          "price": 66540.12,
          "rsi": 58.23,
          "atr": 643.77,
          "swingHigh": 67021.0,
          "swingLow": 65432.0,
          "bos": 67021.0,
          "orderBlock": "66086-67340"
        }
    """
    # CORS pre-flight
    if request.method == "OPTIONS":
        return "", 204

    # ── Parse input ────────────────────────────────────────────
    if request.method == "GET":
        pair     = request.args.get("pair")
        tf       = request.args.get("interval") or request.args.get("timeframe")
        lookback = int(request.args.get("lookback", 14))
    else:  # POST
        data     = request.get_json(force=True, silent=True) or {}
        pair     = data.get("pair")
        tf       = data.get("interval") or data.get("timeframe")
        lookback = int(data.get("lookback", 14))

    if not pair or not tf:
        abort(400, description="`pair` and `interval` are required")

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

    # Placeholder smart-money fields
    bos = swing_high                                  # basic “break of structure”
    ob_low, ob_high = round(swing_low * 1.01, 2), round(swing_low * 1.03, 2)

    raw = dict(
        price      = round(float(df["c"].iloc[-1]), 2),
        rsi        = round(float(rsi_val), 2),
        atr        = round(float(atr_val), 2),
        swingHigh  = round(float(swing_high), 2),
        swingLow   = round(float(swing_low), 2),
        bos        = round(float(bos), 2),
        orderBlock = f"{ob_low}-{ob_high}",
    )

    # ── Clean NaN / Inf so JSON is always valid ───────────────
    clean = {
        k: (None
            if v is None or (isinstance(v, float) and not math.isfinite(v))
            else v)
        for k, v in raw.items()
    }

    return jsonify(clean)


# ── Entrypoint for local dev ───────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Render injects PORT
    app.run(host="0.0.0.0", port=port, debug=True)
