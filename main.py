import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import pytz
from flask import Flask, jsonify

app = Flask(__name__)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs"
TELEGRAM_CHAT_ID = "7476331970"

# Symbols (Silver and ETH removed as requested)
SYMBOLS = {
    "GOLD": "GC=F",
    "BTCUSD": "BTC-USD",
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN"
}

ALERT_CACHE = {}

def is_indian_market_open():
    """ Check if Indian Stock Market (NSE/BSE) is currently open """
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    
    # Weekend Check (Saturday = 5, Sunday = 6)
    if now.weekday() >= 5:
        return False
        
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= now <= market_end

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

def should_send_alert(symbol, strategy_id, candle_time):
    """ Prevents repeat alerts for the exact same 5-minute candle """
    key = f"{symbol}_{strategy_id}"
    if ALERT_CACHE.get(key) == candle_time:
        return False
    ALERT_CACHE[key] = candle_time
    return True

def get_swing_points(df, window=2):
    highs = df['High']
    lows = df['Low']
    swing_highs, swing_lows = [], []
    
    for i in range(window, len(df) - window):
        if all(highs.iloc[i] > highs.iloc[i-j] for j in range(1, window+1)) and \
           all(highs.iloc[i] > highs.iloc[i+j] for j in range(1, window+1)):
            swing_highs.append(highs.iloc[i])
            
        if all(lows.iloc[i] < lows.iloc[i-j] for j in range(1, window+1)) and \
           all(lows.iloc[i] < lows.iloc[i+j] for j in range(1, window+1)):
            swing_lows.append(lows.iloc[i])
            
    return swing_highs, swing_lows

def find_eqh_eql(df, tolerance=0.001):
    sw_highs, sw_lows = get_swing_points(df, window=2)
    eqh_levels, eql_levels = [], []

    for i in range(len(sw_highs)-1):
        for j in range(i+1, len(sw_highs)):
            if abs(sw_highs[i] - sw_highs[j]) / sw_highs[i] <= tolerance:
                eqh_levels.append(max(sw_highs[i], sw_highs[j]))

    for i in range(len(sw_lows)-1):
        for j in range(i+1, len(sw_lows)):
            if abs(sw_lows[i] - sw_lows[j]) / sw_lows[i] <= tolerance:
                eql_levels.append(min(sw_lows[i], sw_lows[j]))

    return eqh_levels, eql_levels

def analyze_smc(symbol_name, ticker):
    # Stop scanning Indian indices outside market hours
    if symbol_name in ["NIFTY 50", "SENSEX"] and not is_indian_market_open():
        return

    try:
        df_5m = yf.download(ticker, period="5d", interval="5m", progress=False)
        df_1d = yf.download(ticker, period="1mo", interval="1d", progress=False)
        df_1h = yf.download(ticker, period="7d", interval="1h", progress=False)
        df_4h = yf.download(ticker, period="14d", interval="1h", progress=False)

        if df_5m.empty or df_1d.empty or len(df_5m) < 20:
            return

        for df in [df_5m, df_1d, df_1h, df_4h]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        df_4h_res = df_4h.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()

        pdh = float(df_1d['High'].iloc[-2])
        pdl = float(df_1d['Low'].iloc[-2])

        prev = df_5m.iloc[-2]
        prev2 = df_5m.iloc[-3]
        candle_time = str(df_5m.index[-2])
        
        p_close, p_high, p_low = float(prev['Close']), float(prev['High']), float(prev['Low'])
        p2_close, p2_high, p2_low = float(prev2['Close']), float(prev2['High']), float(prev2['Low'])
        p_vol = float(prev['Volume']) if 'Volume' in prev else 0
        avg_vol = float(df_5m['Volume'].iloc[-15:].mean()) if 'Volume' in df_5m else 1

        sw_highs, sw_lows = get_swing_points(df_5m.iloc[:-1])
        last_swing_high = sw_highs[-1] if sw_highs else float(df_5m['High'].iloc[-10:-2].max())
        last_swing_low = sw_lows[-1] if sw_lows else float(df_5m['Low'].iloc[-10:-2].min())

        # ==================== STRATEGY 1: PDH/PDL LIQUIDITY SWEEP & RE-ENTRY ====================
        # Case A: Wick sweep or candle closed outside then re-entered range on 5m
        if (p_low < pdl and p_close > pdl) or (p2_close < pdl and p_close > pdl):
            if should_send_alert(symbol_name, "S1_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n"
                    f"🔥 *PDL Liquidity Swept & Price Re-entered Range!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Swept Level: PDL ({pdl:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        if (p_high > pdh and p_close < pdh) or (p2_close > pdh and p_close < pdh):
            if should_send_alert(symbol_name, "S1_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n"
                    f"🔥 *PDH Liquidity Swept & Price Re-entered Range!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Swept Level: PDH ({pdh:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 2: CHoCH (CHANGE OF CHARACTER) ====================
        if p2_close < last_swing_low and p_close > last_swing_high:
            if should_send_alert(symbol_name, "S2_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n"
                    f"⚡ *Bullish CHoCH Confirmed!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Structure: Bearish L-H Broken ({last_swing_high:.2f})\n"
                    f"• Body Closed Above: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        if p2_close > last_swing_high and p_close < last_swing_low:
            if should_send_alert(symbol_name, "S2_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n"
                    f"⚡ *Bearish CHoCH Confirmed!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Structure: Bullish H-L Broken ({last_swing_low:.2f})\n"
                    f"• Body Closed Below: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 3: BOS (BREAK OF STRUCTURE) ====================
        if p2_close <= last_swing_high and p_close > last_swing_high:
            if should_send_alert(symbol_name, "S3_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 3 ALERT] - {symbol_name}*\n\n"
                    f"🚀 *Bullish BOS Confirmed!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Previous High Broken: {last_swing_high:.2f}\n"
                    f"• Body Closed Above: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        if p2_close >= last_swing_low and p_close < last_swing_low:
            if should_send_alert(symbol_name, "S3_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 3 ALERT] - {symbol_name}*\n\n"
                    f"🚀 *Bearish BOS Confirmed!*\n"
                    f"• Timeframe: 5M Candle\n"
                    f"• Previous Low Broken: {last_swing_low:.2f}\n"
                    f"• Body Closed Below: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 4: LOW VOLUME BREAKOUT & TREND BOS ====================
        if p_close < pdl and p_vol < avg_vol and p_close < last_swing_low:
            if should_send_alert(symbol_name, "S4_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 4 ALERT] - {symbol_name}*\n\n"
                    f"⚠️ *PDL Low Volume Breakout & Trend Continuation (BOS)!*\n"
                    f"• Level Broken: PDL ({pdl:.2f})\n"
                    f"• New L-L Formed: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH CONTINUATION 📉"
                )
        elif p_close > pdh and p_vol < avg_vol and p_close > last_swing_high:
            if should_send_alert(symbol_name, "S4_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 4 ALERT] - {symbol_name}*\n\n"
                    f"⚠️ *PDH Low Volume Breakout & Trend Continuation (BOS)!*\n"
                    f"• Level Broken: PDH ({pdh:.2f})\n"
                    f"• New H-H Formed: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH CONTINUATION 📈"
                )

        # ==================== STRATEGY 5: HTF EQUAL HIGHS / EQUAL LOWS ====================
        h1_eqh, h1_eql = find_eqh_eql(df_1h.iloc[:-1])
        h4_eqh, h4_eql = find_eqh_eql(df_4h_res.iloc[:-1])

        all_eqh = list(set(h1_eqh + h4_eqh))
        all_eql = list(set(h1_eql + h4_eql))

        for eqh in all_eqh:
            if p_high > eqh and p_close < eqh:
                if should_send_alert(symbol_name, "S5_EQH", candle_time):
                    send_telegram_alert(
                        f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n"
                        f"🎯 *HTF Equal Highs (EQH) Liquidity Swept by 5M Candle!*\n"
                        f"• HTF EQH Level: {eqh:.2f}\n"
                        f"• 5M Close Back Inside: {p_close:.2f}\n"
                        f"• Market Bias: BEARISH 📉"
                    )

        for eql in all_eql:
            if p_low < eql and p_close > eql:
                if should_send_alert(symbol_name, "S5_EQL", candle_time):
                    send_telegram_alert(
                        f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n"
                        f"🎯 *HTF Equal Lows (EQL) Liquidity Swept by 5M Candle!*\n"
                        f"• HTF EQL Level: {eql:.2f}\n"
                        f"• 5M Close Back Inside: {p_close:.2f}\n"
                        f"• Market Bias: BULLISH 📈"
                    )

        # ==================== STRATEGY 6: HIGH VOLUME BREAKOUT FAILED & RE-ENTRY ====================
        if p2_close < pdl and p_close > pdl and p_vol > avg_vol:
            if should_send_alert(symbol_name, "S6_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 6 ALERT] - {symbol_name}*\n\n"
                    f"💥 *High Volume Breakdown Failed - Price Re-entered PDL Range!*\n"
                    f"• Swept Level: PDL ({pdl:.2f})\n"
                    f"• 5M Candle Close Inside: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )
        elif p2_close > pdh and p_close < pdh and p_vol > avg_vol:
            if should_send_alert(symbol_name, "S6_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 6 ALERT] - {symbol_name}*\n\n"
                    f"💥 *High Volume Breakout Failed - Price Re-entered PDH Range!*\n"
                    f"• Swept Level: PDH ({pdh:.2f})\n"
                    f"• 5M Candle Close Inside: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 7: CRT (1H & 4H SWEEP BY 5M CANDLE) ====================
        h1_high, h1_low = float(df_1h['High'].iloc[-2]), float(df_1h['Low'].iloc[-2])
        h4_high, h4_low = float(df_4h_res['High'].iloc[-2]), float(df_4h_res['Low'].iloc[-2])

        # 1-Hour CRT
        if (p_high > h1_high and p_close < h1_high) or (p2_high > h1_high and p2_close > h1_high and p_close < h1_high):
            if should_send_alert(symbol_name, "S7_1H_HIGH", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *1H CRT High Swept by 5M Candle!*\n"
                    f"• 1H High Level: {h1_high:.2f}\n"
                    f"• 5M Close Back Inside Range: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )
        elif (p_low < h1_low and p_close > h1_low) or (p2_low < h1_low and p2_close < h1_low and p_close > h1_low):
            if should_send_alert(symbol_name, "S7_1H_LOW", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *1H CRT Low Swept by 5M Candle!*\n"
                    f"• 1H Low Level: {h1_low:.2f}\n"
                    f"• 5M Close Back Inside Range: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # 4-Hour CRT
        if (p_high > h4_high and p_close < h4_high) or (p2_high > h4_high and p2_close > h4_high and p_close < h4_high):
            if should_send_alert(symbol_name, "S7_4H_HIGH", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *4H CRT High Swept by 5M Candle!*\n"
                    f"• 4H High Level: {h4_high:.2f}\n"
                    f"• 5M Close Back Inside Range: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )
        elif (p_low < h4_low and p_close > h4_low) or (p2_low < h4_low and p2_close < h4_low and p_close > h4_low):
            if should_send_alert(symbol_name, "S7_4H_LOW", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *4H CRT Low Swept by 5M Candle!*\n"
                    f"• 4H Low Level: {h4_low:.2f}\n"
                    f"• 5M Close Back Inside Range: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

    except Exception as e:
        print(f"Error on {symbol_name}: {e}")

@app.route('/')
def home():
    return "TRADE WITH_____ICT-DIPTANGAN Live Engine Active!"

@app.route('/run')
def run_scan():
    for name, ticker in SYMBOLS.items():
        analyze_smc(name, ticker)
    return jsonify({"status": "success", "message": "Scanned GOLD, BTC, NIFTY 50, SENSEX"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
