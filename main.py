import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs"
TELEGRAM_CHAT_ID = "7476331970"

# Asset Tickers
SYMBOLS = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN"
}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Telegram Error: {e}")
        return False

def analyze_smc(symbol_name, ticker):
    try:
        # Fetching Timeframes Data
        df_5m = yf.download(ticker, period="5d", interval="5m", progress=False)
        df_1d = yf.download(ticker, period="1mo", interval="1d", progress=False)
        df_1h = yf.download(ticker, period="7d", interval="1h", progress=False)

        if df_5m.empty or df_1d.empty or len(df_5m) < 5:
            return

        # Flatten Column Headers if MultiIndex
        if isinstance(df_5m.columns, pd.MultiIndex):
            df_5m.columns = df_5m.columns.get_level_values(0)
        if isinstance(df_1d.columns, pd.MultiIndex):
            df_1d.columns = df_1d.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        # Key Levels
        pdh = float(df_1d['High'].iloc[-2])
        pdl = float(df_1d['Low'].iloc[-2])

        curr = df_5m.iloc[-1]
        prev = df_5m.iloc[-2]

        c_close, c_high, c_low = float(curr['Close']), float(curr['High']), float(curr['Low'])
        p_close, p_high, p_low = float(prev['Close']), float(prev['High']), float(prev['Low'])
        c_vol = float(curr['Volume']) if 'Volume' in curr else 0
        avg_vol = float(df_5m['Volume'].iloc[-10:].mean()) if 'Volume' in df_5m else 1

        # STRATEGY 1: PDH/PDL Sweep & Range Re-entry (5m Body)
        if c_high > pdh and c_close < pdh:
            send_telegram_alert(f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n🔥 *PDH Liquidity Sweep & Re-entry!*\n• TF: 5M\n• Level: PDH ({pdh:.2f})\n• High Swept: {c_high:.2f}\n• 5M Close Inside: {c_close:.2f}\n• Bias: BEARISH 📉")
        elif c_low < pdl and c_close > pdl:
            send_telegram_alert(f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n🔥 *PDL Liquidity Sweep & Re-entry!*\n• TF: 5M\n• Level: PDL ({pdl:.2f})\n• Low Swept: {c_low:.2f}\n• 5M Close Inside: {c_close:.2f}\n• Bias: BULLISH 📈")

        # STRATEGY 2: CHoCH Shift
        if p_close < pdl and c_close > p_high:
            send_telegram_alert(f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n⚡ *Bullish CHoCH Confirmed!*\n• TF: 5M\n• Prev Bearish Trend LH Broken ({p_high:.2f})\n• Body Close Confirmed\n• Bias: BULLISH 📈")
        elif p_close > pdh and c_close < p_low:
            send_telegram_alert(f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n⚡ *Bearish CHoCH Confirmed!*\n• TF: 5M\n• Prev Bullish Trend HL Broken ({p_low:.2f})\n• Body Close Confirmed\n• Bias: BEARISH 📉")

        # STRATEGY 3: BOS Continuation
        if c_close > p_high and p_close > pdh:
            send_telegram_alert(f"🚨 *[STRATEGY 3 ALERT] - {symbol_name}*\n\n🚀 *Bullish BOS (Break of Structure)!*\n• TF: 5M\n• HH/HL Structure Intact\n• Current Close: {c_close:.2f}\n• Bias: BULLISH 📈")

        # STRATEGY 4: Low Volume Breakout Continuation
        if c_close < pdl and c_vol < avg_vol:
            send_telegram_alert(f"🚨 *[STRATEGY 4 ALERT] - {symbol_name}*\n\n⚠️ *PDL Breakout with Low Volume!*\n• TF: 5M\n• Level: PDL ({pdl:.2f})\n• Continuating Downtrend\n• Bias: BEARISH 📉")

        # STRATEGY 5: EQH / EQL Sweeps
        recent_highs = df_5m['High'].iloc[-10:-1]
        recent_lows = df_5m['Low'].iloc[-10:-1]
        if abs(recent_highs.max() - p_high) < (p_high * 0.0005) and c_high > p_high and c_close < p_high:
            send_telegram_alert(f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n🎯 *Equal Highs (EQH) Liquidity Swept!*\n• TF: 5M\n• EQH Level Swept & Re-entered\n• Bias: BEARISH 📉")
        elif abs(recent_lows.min() - p_low) < (p_low * 0.0005) and c_low < p_low and c_close > p_low:
            send_telegram_alert(f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n🎯 *Equal Lows (EQL) Liquidity Swept!*\n• TF: 5M\n• EQL Level Swept & Re-entered\n• Bias: BULLISH 📈")

        # STRATEGY 6: High Volume Breakout Fakeout Re-entry
        if p_close < pdl and c_close > pdl and c_vol > avg_vol:
            send_telegram_alert(f"🚨 *[STRATEGY 6 ALERT] - {symbol_name}*\n\n💥 *High Volume Fakeout - Re-entered Range!*\n• TF: 5M\n• Level: PDL ({pdl:.2f})\n• Strong Volume Invalidation\n• Bias: BULLISH 📈")

        # STRATEGY 7: 1H / 4H CRT Sweeps via 5M Candle
        h1_high = float(df_1h['High'].iloc[-2])
        h1_low = float(df_1h['Low'].iloc[-2])
        if c_high > h1_high and c_close < h1_high:
            send_telegram_alert(f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n⏰ *1H CRT High Swept by 5M Candle!*\n• 1H High: {h1_high:.2f}\n• 5M Closed Back Inside Range: {c_close:.2f}\n• Bias: BEARISH 📉")
        elif c_low < h1_low and c_close > h1_low:
            send_telegram_alert(f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n⏰ *1H CRT Low Swept by 5M Candle!*\n• 1H Low: {h1_low:.2f}\n• 5M Closed Back Inside Range: {c_close:.2f}\n• Bias: BULLISH 📈")

    except Exception as e:
        print(f"Error on {symbol_name}: {e}")

@app.route('/')
def home():
    return "TRADE WITH_____ICT-DIPTANGAN Live Scanning Engine Active!"

@app.route('/run')
def run_scan():
    for name, ticker in SYMBOLS.items():
        analyze_smc(name, ticker)
    return jsonify({"status": "success", "message": "Scanned GOLD, SILVER, BTC, ETH, NIFTY 50, SENSEX"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
