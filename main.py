import os
import time
import threading
from flask import Flask
import requests
import ccxt
import pandas as pd
import numpy as np

# ==========================================
# DUMMY WEB SERVER FOR RENDER
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "SMC Alert Bot Running..."

@app.route('/run')
def trigger_run():
    threading.Thread(target=run_analysis_once).start()
    return "OK"

# ==========================================
# CONFIGURATION & USER CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs"
TELEGRAM_CHAT_ID = "7476331970"

SYMBOLS = [
    'PAXG/USDT', # Gold
    'BTC/USDT',  # Bitcoin
    'ETH/USDT',  # Ethereum
    'GBP/USDT',  # GBPUSD
    'EUR/USDT',  # EURUSD
]

notified_events = set()

exchange = ccxt.binance({
    'enableRateLimit': True,
})

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram API Error: {e}")

def fetch_ohlcv(symbol, timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol} ({timeframe}): {e}")
        return None

def analyze_symbol(symbol):
    df_5m = fetch_ohlcv(symbol, '5m', 100)
    df_1h = fetch_ohlcv(symbol, '1h', 100)
    df_4h = fetch_ohlcv(symbol, '4h', 100)
    df_1d = fetch_ohlcv(symbol, '1d', 10)
    
    if df_5m is None or df_1h is None or df_4h is None or df_1d is None:
        return

    pdh = df_1d.iloc[-2]['high']
    pdl = df_1d.iloc[-2]['low']
    
    curr_5m = df_5m.iloc[-1]
    prev_5m = df_5m.iloc[-2]
    
    curr_close = curr_5m['close']
    curr_high = curr_5m['high']
    curr_low = curr_5m['low']
    curr_volume = curr_5m['volume']
    avg_vol_5m = df_5m['volume'].tail(20).mean()

    # 1st Strategy: PDH / PDL Liquidity Sweep & Re-entry
    if curr_high > pdh and curr_close < pdh and curr_close > pdl:
        event_key = f"{symbol}_STRAT1_PDH_SWEEP_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDH Liquidity Sweep Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrevious Day High ({pdh}) swept by wick, closed inside daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_low < pdl and curr_close > pdl and curr_close < pdh:
        event_key = f"{symbol}_STRAT1_PDL_SWEEP_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDL Liquidity Sweep Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrevious Day Low ({pdl}) swept by wick, closed inside daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if prev_5m['close'] > pdh and curr_close < pdh:
        event_key = f"{symbol}_STRAT1_PDH_REENTRY_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDH Range Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nPrice returned back inside daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if prev_5m['close'] < pdl and curr_close > pdl:
        event_key = f"{symbol}_STRAT1_PDL_REENTRY_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDL Range Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nPrice returned back inside daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # 2nd Strategy: CHoCH
    recent_high = df_5m['high'].tail(15).max()
    recent_low = df_5m['low'].tail(15).min()

    if prev_5m['close'] <= recent_high and curr_close > recent_high:
        event_key = f"{symbol}_STRAT2_BULL_CHOCH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 2] Bullish CHoCH Detected!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nBroke LH with body close above {recent_high}."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if prev_5m['close'] >= recent_low and curr_close < recent_low:
        event_key = f"{symbol}_STRAT2_BEAR_CHOCH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 2] Bearish CHoCH Detected!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nBroke HL with body close below {recent_low}."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # 3rd Strategy: BOS
    prev_hh = df_5m['high'].iloc[-10:-2].max()
    prev_ll = df_5m['low'].iloc[-10:-2].min()

    if curr_close > prev_hh:
        event_key = f"{symbol}_STRAT3_BULL_BOS_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 3] Bullish BOS Alert!</b>\n\nAsset: <b>{symbol}</b>\nBroke Higher-High ({prev_hh}). Bullish continuation!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_close < prev_ll:
        event_key = f"{symbol}_STRAT3_BEAR_BOS_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 3] Bearish BOS Alert!</b>\n\nAsset: <b>{symbol}</b>\nBroke Lower-Low ({prev_ll}). Bearish continuation!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # 4th Strategy: Low Volume Breakout
    if curr_close > pdh and curr_volume < avg_vol_5m and prev_5m['close'] <= pdh:
        event_key = f"{symbol}_STRAT4_LOWVOL_PDH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 4] Low Volume PDH Breakout!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_close < pdl and curr_volume < avg_vol_5m and prev_5m['close'] >= pdl:
        event_key = f"{symbol}_STRAT4_LOWVOL_PDL_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 4] Low Volume PDL Breakdown!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # 5th Strategy: Equal Highs & Lows
    highs_1h = df_1h['high'].tail(30).values
    lows_1h = df_1h['low'].tail(30).values
    
    for i in range(len(highs_1h) - 5):
        for j in range(i + 3, len(highs_1h)):
            if abs(highs_1h[i] - highs_1h[j]) / highs_1h[i] < 0.0008:
                eqh_val = max(highs_1h[i], highs_1h[j])
                if curr_high > eqh_val and curr_close < eqh_val:
                    event_key = f"{symbol}_STRAT5_EQH_{curr_5m['timestamp']}"
                    if event_key not in notified_events:
                        msg = f"🚨 <b>[STRATEGY 5] Equal Highs Swept!</b>\n\nAsset: <b>{symbol}</b>"
                        send_telegram_msg(msg)
                        notified_events.add(event_key)

            if abs(lows_1h[i] - lows_1h[j]) / lows_1h[i] < 0.0008:
                eql_val = min(lows_1h[i], lows_1h[j])
                if curr_low < eql_val and curr_close > eql_val:
                    event_key = f"{symbol}_STRAT5_EQL_{curr_5m['timestamp']}"
                    if event_key not in notified_events:
                        msg = f"🚨 <b>[STRATEGY 5] Equal Lows Swept!</b>\n\nAsset: <b>{symbol}</b>"
                        send_telegram_msg(msg)
                        notified_events.add(event_key)

    # 6th Strategy: High Volume Re-entry
    if curr_volume > (avg_vol_5m * 1.8):
        if prev_5m['close'] > pdh and curr_close < pdh:
            event_key = f"{symbol}_STRAT6_HV_PDH_REENTRY_{curr_5m['timestamp']}"
            if event_key not in notified_events:
                msg = f"🚨 <b>[STRATEGY 6] High Volume PDH Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>"
                send_telegram_msg(msg)
                notified_events.add(event_key)

        if prev_5m['close'] < pdl and curr_close > pdl:
            event_key = f"{symbol}_STRAT6_HV_PDL_REENTRY_{curr_5m['timestamp']}"
            if event_key not in notified_events:
                msg = f"🚨 <b>[STRATEGY 6] High Volume PDL Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>"
                send_telegram_msg(msg)
                notified_events.add(event_key)

    # 7th Strategy: CRT (1H & 4H Sweeps)
    prev_1h_high = df_1h.iloc[-2]['high']
    prev_1h_low = df_1h.iloc[-2]['low']

    if curr_high > prev_1h_high and curr_close < prev_1h_high:
        event_key = f"{symbol}_STRAT7_1H_HIGH_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 1H High Swept!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_low < prev_1h_low and curr_close > prev_1h_low:
        event_key = f"{symbol}_STRAT7_1H_LOW_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 1H Low Swept!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    prev_4h_high = df_4h.iloc[-2]['high']
    prev_4h_low = df_4h.iloc[-2]['low']

    if curr_high > prev_4h_high and curr_close < prev_4h_high:
        event_key = f"{symbol}_STRAT7_4H_HIGH_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 4H High Swept!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_low < prev_4h_low and curr_close > prev_4h_low:
        event_key = f"{symbol}_STRAT7_4H_LOW_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 4H Low Swept!</b>\n\nAsset: <b>{symbol}</b>"
            send_telegram_msg(msg)
            notified_events.add(event_key)

def run_analysis_once():
    for symbol in SYMBOLS:
        analyze_symbol(symbol)
        time.sleep(1)

def bot_loop():
    while True:
        try:
            run_analysis_once()
        except Exception as e:
            print(f"Error in main loop: {e}")
        time.sleep(60)

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot_loop()
