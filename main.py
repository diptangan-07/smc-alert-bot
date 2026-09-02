import os
import time
import requests
import pandas as pd
from tvdatafeed import TvDatafeed, Interval
from flask import Flask

app = Flask(__name__)

# TELEGRAM CONFIG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Send Error: {e}")

# TradingView Live Feed Engine (No Lag)
tv = TvDatafeed()

def analyze_smc_live(symbol="XAUUSD", exchange="OANDA"):
    try:
        # Fetch 5m, 1h, and Daily candles directly from TradingView
        df_5m = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_5_minute, n_bars=100)
        df_1h = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=50)
        df_1d = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=5)

        if df_5m is None or df_5m.empty:
            return

        # PDH & PDL Calculation
        pdh = df_1d['high'].iloc[-2]
        pdl = df_1d['low'].iloc[-2]

        curr = df_5m.iloc[-1]   # Running Candle
        prev = df_5m.iloc[-2]   # Just Closed Candle
        avg_vol = df_5m['volume'].rolling(20).mean().iloc[-1]

        # ------------------- 1ST STRATEGY: LIQUIDITY SWEEP -------------------
        # Buyside Liquidity Sweep (PDH Sweep -> Close Inside -> SELL Setup)
        if prev['high'] > pdh and prev['close'] < pdh:
            send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDH SWEEP]</b>\nSymbol: {symbol}\nBuyside Liquidity Swept! Wick hunt above PDH ({pdh}) but body closed inside.\n<b>Bias: BEARISH / SELL</b>")
        
        # Sellside Liquidity Sweep (PDL Sweep -> Close Inside -> BUY Setup)
        if prev['low'] < pdl and prev['close'] > pdl:
            send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDL SWEEP]</b>\nSymbol: {symbol}\nSellside Liquidity Swept! Wick hunt below PDL ({pdl}) but body closed inside.\n<b>Bias: BULLISH / BUY</b>")

        # ------------------- 2ND STRATEGY: CHoCH -------------------
        recent_lh = df_5m['high'].iloc[-10:-2].max()
        recent_hl = df_5m['low'].iloc[-10:-2].min()

        if prev['close'] > recent_lh:
            send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BULLISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bearish L-H Broken with Body Close!\n<b>Trend Shift: Bearish to Bullish</b>")
        elif prev['close'] < recent_hl:
            send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BEARISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bullish H-L Broken with Body Close!\n<b>Trend Shift: Bullish to Bearish</b>")

        # ------------------- 3RD STRATEGY: BOS -------------------
        prev_hh = df_5m['high'].iloc[-6:-2].max()
        prev_ll = df_5m['low'].iloc[-6:-2].min()

        if prev['close'] > prev_hh:
            send_telegram(f"📈 <b>[SMC STRATEGY 3 - BULLISH BOS]</b>\nSymbol: {symbol}\nNew High-High Broken with Body Close. Continuation Upward.")
        elif prev['close'] < prev_ll:
            send_telegram(f"📉 <b>[SMC STRATEGY 3 - BEARISH BOS]</b>\nSymbol: {symbol}\nNew Low-Low Broken with Body Close. Continuation Downward.")

        # ------------------- 4TH STRATEGY: BREAKOUT & BOS -------------------
        if prev['volume'] < avg_vol:
            if prev['close'] > pdh:
                send_telegram(f"📊 <b>[SMC STRATEGY 4 - PDH BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout above PDH. Waiting for BOS Confirmation.")
            elif prev['close'] < pdl:
                send_telegram(f"📊 <b>[SMC STRATEGY 4 - PDL BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout below PDL. Waiting for BOS Confirmation.")

        # ------------------- 5TH STRATEGY: EQH / EQL SWEEP -------------------
        eqh_level = df_5m['high'].iloc[-15:-3].max()
        eql_level = df_5m['low'].iloc[-15:-3].min()

        if abs(prev['high'] - eqh_level) / eqh_level < 0.0003 and prev['close'] < eqh_level:
            send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQH SWEEP]</b>\nSymbol: {symbol}\nEqual Highs Liquidity Swept! Reversing Back Inside.")
        if abs(prev['low'] - eql_level) / eql_level < 0.0003 and prev['close'] > eql_level:
            send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQL SWEEP]</b>\nSymbol: {symbol}\nEqual Lows Liquidity Swept! Reversing Back Inside.")

        # ------------------- 6TH STRATEGY: BREAKOUT FAILURE (FAKEOUT) -------------------
        if prev['volume'] > (avg_vol * 1.4):
            if prev['close'] < pdl and curr['close'] > pdl:
                send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nHigh Volume PDL Breakout Failed! Price Returned Inside Range.")
            elif prev['close'] > pdh and curr['close'] < pdh:
                send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nHigh Volume PDH Breakout Failed! Price Returned Inside Range.")

        # ------------------- 7TH STRATEGY: HTF CRT (1H / 4H SWEEP via 5M) -------------------
        if df_1h is not None and len(df_1h) >= 2:
            prev_1h_high = df_1h['high'].iloc[-2]
            prev_1h_low = df_1h['low'].iloc[-2]

            if prev['high'] > prev_1h_high and prev['close'] < prev_1h_high:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT HIGH SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H High Liquidity and Returned Inside.")
            elif prev['low'] < prev_1h_low and prev['close'] > prev_1h_low:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT LOW SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H Low Liquidity and Returned Inside.")

    except Exception as e:
        print(f"Analysis Error: {e}")

@app.route('/')
def home():
    return "Diptangan Live SMC Engine Running", 200

@app.route('/run')
def run():
    analyze_smc_live("XAUUSD", "OANDA")
    analyze_smc_live("BTCUSD", "BITSTAMP")
    return "OK", 200

if __name__ == "__main__":
    send_telegram("✅ <b>Diptangan SMC Live TradingView Engine Reloaded & Active!</b>")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
