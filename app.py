"""
app.py – Confluence Snapshot micro-service
Pulls the latest OHLCV data from Binance, calculates RSI & ATR
with pandas-ta, and returns a compact JSON snapshot.

Local dev:
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python3 app.py

Render deployment:
    Start command →  gunicorn app:app
"""

import os
from flask import Flask, request, jsonify
import ccxt
import pandas as pd
import pandas_ta as ta

# ───────────────────────────────────────────────────────────────
#  Exchange init (public endpoints only)
# ───────────────────────────────────────────────────────────────
ex = ccxt.binance({"enableRateLimit": True})

app = Flask(__name__)


@app.route("/snapshot", methods=["POST"])
def snapshot() -> jsonify:
    """
    Body:
        { "pair": "BTC/USDT", "timeframe": "1h" }

    Returns JSON with price, RSI, ATR, swing highs/lows, basic BOS
    and a placeholder order-block range.
    """
    data = request.get_json(silent=True) or {}
    pair = data.get("pair", "BTC/USDT")
    tf   = data.get("timeframe", "1h")

    try:
        candles = ex.fetch_ohlcv(pair, tf, limit=200)
    except Exception as err:
        return jsonify({"error": str(err)}), 400

    df = pd.DataFrame(candles, columns=["ts", "o", "h", "l", "c", "v"])

    # Indicators
    rsi = ta.rsi(df["c"], length=14).iloc[-1]
    atr = ta.atr(df["h"], df["l"], df["c"], length=14).iloc[-1]

    swing_high = df["h"].max()
    swing_low  = df["l"].min()

    # Placeholder smart-money values
    bos = swing_high
    ob_low, ob_high = round(swing_low * 1.01), round(swing_low * 1.03)

    return jsonify(
        price      = round(float(df["c"].iloc[-1]), 2),
        rsi        = round(float(rsi), 2),
        atr        = round(float(atr), 2),
        swingHigh  = round(float(swing_high), 2),
        swingLow   = round(float(swing_low), 2),
        bos        = round(float(bos), 2),
        orderBlock = f"{ob_low}-{ob_high}"
    )


if __name__ == "__main__":
    # Render injects PORT; fallback to 8000 locally
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
