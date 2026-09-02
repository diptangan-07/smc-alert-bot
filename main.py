import os
import time
import requests
import pandas as pd
import yfinance as yf
from flask import Flask, render_template

app = Flask(__name__)

# TELEGRAM BOT CONFIGURATION
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def fetch_data(symbol, period="5d", interval="5m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

def analyze_smc_strategies(symbol="GC=F"): # Gold Spot (XAUUSD)
    df_5m = fetch_data(symbol, period="5d", interval="5m")
    df_1h = fetch_data(symbol, period="7d", interval="1h")
    df_4h = fetch_data(symbol, period="14d", interval="1h") # Resampled to 4H

    if df_5m.empty or len(df_5m) < 10:
        return

    # Calculate PDH & PDL from 1D view
    df_1d = fetch_data(symbol, period="5d", interval="1d")
    if len(df_1d) < 2:
        return
    pdh = df_1d['High'].iloc[-2]
    pdl = df_1d['Low'].iloc[-2]

    latest = df_5m.iloc[-1]
    prev = df_5m.iloc[-2]
    avg_volume = df_5m['Volume'].rolling(20).mean().iloc[-1]

    # --- STRATEGY 1: PDH / PDL Liquidity Sweep into Range ---
    # Bullish Sweep (PDL Sweep & return inside)
    if prev['Low'] < pdl and latest['Close'] > pdl:
        send_telegram(f"🚨 <b>[SMC Strategy 1 - PDL SWEEP]</b>\nSymbol: {symbol}\nPDL Swept! Price returned inside the range.\nBias: Bullish Reversal Alert")
    # Bearish Sweep (PDH Sweep & return inside)
    elif prev['High'] > pdh and latest['Close'] < pdh:
        send_telegram(f"🚨 <b>[SMC Strategy 1 - PDH SWEEP]</b>\nSymbol: {symbol}\nPDH Swept! Price returned inside the range.\nBias: Bearish Reversal Alert")

    # --- STRATEGY 2: CHoCH (Change of Character) ---
    recent_high = df_5m['High'].iloc[-10:-2].max()
    recent_low = df_5m['Low'].iloc[-10:-2].min()
    if prev['Close'] < recent_high and latest['Close'] > recent_high:
        send_telegram(f"⚡ <b>[SMC Strategy 2 - CHoCH CONFIRMED]</b>\nSymbol: {symbol}\nTrend Shift: Bearish to Bullish! Previous L-H Broken with Body Close.")
    elif prev['Close'] > recent_low and latest['Close'] < recent_low:
        send_telegram(f"⚡ <b>[SMC Strategy 2 - CHoCH CONFIRMED]</b>\nSymbol: {symbol}\nTrend Shift: Bullish to Bearish! Previous H-L Broken with Body Close.")

    # --- STRATEGY 3: BOS (Break of Structure) ---
    higher_high = df_5m['High'].iloc[-5:-1].max()
    lower_low = df_5m['Low'].iloc[-5:-1].min()
    if latest['Close'] > higher_high:
        send_telegram(f"📈 <b>[SMC Strategy 3 - BULLISH BOS]</b>\nSymbol: {symbol}\nContinuation: Bullish BOS confirmed! New High Breakout.")
    elif latest['Close'] < lower_low:
        send_telegram(f"📉 <b>[SMC Strategy 3 - BEARISH BOS]</b>\nSymbol: {symbol}\nContinuation: Bearish BOS confirmed! New Low Breakout.")

    # --- STRATEGY 4: Low Volume Breakout Continuation & BOS ---
    if latest['Volume'] < avg_volume:
        if latest['Close'] < pdl and prev['Close'] >= pdl:
            send_telegram(f"📊 <b>[SMC Strategy 4 - PDL BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout below PDL. Downtrend Continuation BOS pending.")
        elif latest['Close'] > pdh and prev['Close'] <= pdh:
            send_telegram(f"📊 <b>[SMC Strategy 4 - PDH BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout above PDH. Uptrend Continuation BOS pending.")

    # --- STRATEGY 5: Equal High (EQH) & Equal Low (EQL) Sweep ---
    last_lows = df_5m['Low'].iloc[-15:-2]
    last_highs = df_5m['High'].iloc[-15:-2]
    for l in last_lows:
        if abs(l - prev['Low']) / l < 0.0005 and latest['Close'] > l: # EQH/EQL Tolerance
            send_telegram(f"🎯 <b>[SMC Strategy 5 - EQL SWEEP]</b>\nSymbol: {symbol}\nEqual Lows Liquidity Swept and Price Claimed Back.")
            break
    for h in last_highs:
        if abs(h - prev['High']) / h < 0.0005 and latest['Close'] < h:
            send_telegram(f"🎯 <b>[SMC Strategy 5 - EQH SWEEP]</b>\nSymbol: {symbol}\nEqual Highs Liquidity Swept and Price Claimed Back.")
            break

    # --- STRATEGY 6: High Volume Breakout Failure (Fakeout Return) ---
    if latest['Volume'] > (avg_volume * 1.5):
        if prev['Close'] < pdl and latest['Close'] > pdl:
            send_telegram(f"⚠️ <b>[SMC Strategy 6 - BREAKOUT FAILURE]</b>\nSymbol: {symbol}\nHigh Volume Breakout Failed! Price Re-entered PDL Range.")
        elif prev['Close'] > pdh and latest['Close'] < pdh:
            send_telegram(f"⚠️ <b>[SMC Strategy 6 - BREAKOUT FAILURE]</b>\nSymbol: {symbol}\nHigh Volume Breakout Failed! Price Re-entered PDH Range.")

    # --- STRATEGY 7: CRT (Candle Range Theory 1H / 4H HTF Sweep via 5M) ---
    if not df_1h.empty and len(df_1h) >= 2:
        prev_1h_high = df_1h['High'].iloc[-2]
        prev_1h_low = df_1h['Low'].iloc[-2]
        if prev['Low'] < prev_1h_low and latest['Close'] > prev_1h_low:
            send_telegram(f"⏳ <b>[SMC Strategy 7 - 1H CRT SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H HTF Liquidity Low and Re-entered.")
        elif prev['High'] > prev_1h_high and latest['Close'] < prev_1h_high:
            send_telegram(f"⏳ <b>[SMC Strategy 7 - 1H CRT SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H HTF Liquidity High and Re-entered.")

@app.route('/')
def home():
    return "Diptangan SMC Intelligence Engine is Running 24/7!"

@app.route('/run')
def run_bot():
    analyze_smc_strategies()
    return "Analysis Triggered", 200

if __name__ == "__main__":
    send_telegram("🚀 <b>Diptangan SMC AI Engine Started Successfully!</b>")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
