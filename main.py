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

# Symbols mapped to Yahoo Finance Tickers
SYMBOLS = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN"
}

# Cache to prevent duplicate alert spamming
# Format: { "SYMBOL_STRATEGY": last_alert_timestamp }
ALERT_CACHE = {}

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
    """ Prevents sending duplicate alerts for the exact same 5M candle """
    key = f"{symbol}_{strategy_id}"
    last_time = ALERT_CACHE.get(key)
    if last_time == candle_time:
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

def analyze_smc(symbol_name, ticker):
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

        # Key Levels
        pdh = float(df_1d['High'].iloc[-2])
        pdl = float(df_1d['Low'].iloc[-2])

        # Completed 5M Candle (Index -2 is the last fully closed 5m candle)
        prev = df_5m.iloc[-2]
        prev2 = df_5m.iloc[-3]
        candle_time = str(df_5m.index[-2])
        
        p_close, p_high, p_low = float(prev['Close']), float(prev['High']), float(prev['Low'])
        p2_close = float(prev2['Close'])
        p_vol = float(prev['Volume']) if 'Volume' in prev else 0
        avg_vol = float(df_5m['Volume'].iloc[-15:].mean()) if 'Volume' in df_5m else 1

        sw_highs, sw_lows = get_swing_points(df_5m.iloc[:-1])
        last_swing_high = sw_highs[-1] if sw_highs else float(df_5m['High'].iloc[-10:-2].max())
        last_swing_low = sw_lows[-1] if sw_lows else float(df_5m['Low'].iloc[-10:-2].min())

        # ==================== STRATEGY 1: PDH/PDL SWEEP & RE-ENTRY ====================
        # PDL Re-entry (Wick Sweep OR Body Break & Return to Range)
        if (p_low < pdl and p_close > pdl) or (p2_close < pdl and p_close > pdl):
            if should_send_alert(symbol_name, "S1_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n"
                    f"🔥 *PDL Liquidity Swept & Price Re-entered Range!*\n"
                    f"• Timeframe: 5M\n"
                    f"• Level: PDL ({pdl:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # PDH Re-entry (Wick Sweep OR Body Break & Return to Range)
        if (p_high > pdh and p_close < pdh) or (p2_close > pdh and p_close < pdh):
            if should_send_alert(symbol_name, "S1_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 1 ALERT] - {symbol_name}*\n\n"
                    f"🔥 *PDH Liquidity Swept & Price Re-entered Range!*\n"
                    f"• Timeframe: 5M\n"
                    f"• Level: PDH ({pdh:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 2: CHoCH (TREND REVERSAL) ====================
        # Bearish to Bullish CHoCH
        if p2_close < last_swing_low and p_close > last_swing_high:
            if should_send_alert(symbol_name, "S2_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n"
                    f"⚡ *Bullish CHoCH Confirmed!*\n"
                    f"• Timeframe: 5M\n"
                    f"• Trend Shift: Bearish to Bullish\n"
                    f"• Broken L-H Level: {last_swing_high:.2f}\n"
                    f"• 5M Body Close Confirmed: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # Bullish to Bearish CHoCH
        if p2_close > last_swing_high and p_close < last_swing_low:
            if should_send_alert(symbol_name, "S2_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 2 ALERT] - {symbol_name}*\n\n"
                    f"⚡ *Bearish CHoCH Confirmed!*\n"
                    f"• Timeframe: 5M\n"
                    f"• Trend Shift: Bullish to Bearish\n"
                    f"• Broken H-L Level: {last_swing_low:.2f}\n"
                    f"• 5M Body Close Confirmed: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 3: BOS (TREND CONTINUATION) ====================
        # Bullish BOS
        if p2_close <= last_swing_high and p_close > last_swing_high:
            if should_send_alert(symbol_name, "S3_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 3 ALERT] - {symbol_name}*\n\n"
                    f"🚀 *Bullish BOS Confirmed!*\n"
                    f"• Timeframe: 5M\n"
                    f"• New H-H Level Broken: {last_swing_high:.2f}\n"
                    f"• 5M Body Close Confirmed: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # Bearish BOS
        if p2_close >= last_swing_low and p_close < last_swing_low:
            if should_send_alert(symbol_name, "S3_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 3 ALERT] - {symbol_name}*\n\n"
                    f"🚀 *Bearish BOS Confirmed!*\n"
                    f"• Timeframe: 5M\n"
                    f"• New L-L Level Broken: {last_swing_low:.2f}\n"
                    f"• 5M Body Close Confirmed: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 4: LOW VOLUME BREAKOUT & CONTINUATION ====================
        if p_close < pdl and p_vol < avg_vol and p2_close >= pdl:
            if should_send_alert(symbol_name, "S4_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 4 ALERT] - {symbol_name}*\n\n"
                    f"⚠️ *PDL Breakout with Low Volume!*\n"
                    f"• Level Broken: PDL ({pdl:.2f})\n"
                    f"• New Bearish Trend Active\n"
                    f"• Market Bias: BEARISH 📉"
                )
        elif p_close > pdh and p_vol < avg_vol and p2_close <= pdh:
            if should_send_alert(symbol_name, "S4_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 4 ALERT] - {symbol_name}*\n\n"
                    f"⚠️ *PDH Breakout with Low Volume!*\n"
                    f"• Level Broken: PDH ({pdh:.2f})\n"
                    f"• New Uptrend Active\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # ==================== STRATEGY 5: HTF (1H / 4H) EQH & EQL SWEEPS ====================
        h1_sw_highs, h1_sw_lows = get_swing_points(df_1h.iloc[:-1], window=2)
        
        if h1_sw_highs:
            htf_eqh = h1_sw_highs[-1]
            if p_high > htf_eqh and p_close < htf_eqh:
                if should_send_alert(symbol_name, "S5_EQH", candle_time):
                    send_telegram_alert(
                        f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n"
                        f"🎯 *HTF Equal Highs (EQH) Liquidity Swept by 5M Candle!*\n"
                        f"• HTF EQH Level: {htf_eqh:.2f}\n"
                        f"• 5M Close Back Inside: {p_close:.2f}\n"
                        f"• Market Bias: BEARISH 📉"
                    )

        if h1_sw_lows:
            htf_eql = h1_sw_lows[-1]
            if p_low < htf_eql and p_close > htf_eql:
                if should_send_alert(symbol_name, "S5_EQL", candle_time):
                    send_telegram_alert(
                        f"🚨 *[STRATEGY 5 ALERT] - {symbol_name}*\n\n"
                        f"🎯 *HTF Equal Lows (EQL) Liquidity Swept by 5M Candle!*\n"
                        f"• HTF EQL Level: {htf_eql:.2f}\n"
                        f"• 5M Close Back Inside: {p_close:.2f}\n"
                        f"• Market Bias: BULLISH 📈"
                    )

        # ==================== STRATEGY 6: HIGH VOLUME FAKEOUT RANGE RE-ENTRY ====================
        if p2_close < pdl and p_close > pdl and p_vol > avg_vol:
            if should_send_alert(symbol_name, "S6_BULL", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 6 ALERT] - {symbol_name}*\n\n"
                    f"💥 *High Volume Breakout Failed - Price Re-entered Range!*\n"
                    f"• Swept Level: PDL ({pdl:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )
        elif p2_close > pdh and p_close < pdh and p_vol > avg_vol:
            if should_send_alert(symbol_name, "S6_BEAR", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 6 ALERT] - {symbol_name}*\n\n"
                    f"💥 *High Volume Breakout Failed - Price Re-entered Range!*\n"
                    f"• Swept Level: PDH ({pdh:.2f})\n"
                    f"• 5M Candle Close: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )

        # ==================== STRATEGY 7: 1H & 4H CRT SWEEPS (BY 5M CANDLE) ====================
        h1_high, h1_low = float(df_1h['High'].iloc[-2]), float(df_1h['Low'].iloc[-2])
        h4_high, h4_low = float(df_4h_res['High'].iloc[-2]), float(df_4h_res['Low'].iloc[-2])

        # 1H CRT Sweeps
        if p_high > h1_high and p_close < h1_high:
            if should_send_alert(symbol_name, "S7_1H_HIGH", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *1H CRT High Swept by 5M Candle!*\n"
                    f"• 1H High Level: {h1_high:.2f}\n"
                    f"• 5M Close Back Inside: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )
        elif p_low < h1_low and p_close > h1_low:
            if should_send_alert(symbol_name, "S7_1H_LOW", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *1H CRT Low Swept by 5M Candle!*\n"
                    f"• 1H Low Level: {h1_low:.2f}\n"
                    f"• 5M Close Back Inside: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

        # 4H CRT Sweeps
        if p_high > h4_high and p_close < h4_high:
            if should_send_alert(symbol_name, "S7_4H_HIGH", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *4H CRT High Swept by 5M Candle!*\n"
                    f"• 4H High Level: {h4_high:.2f}\n"
                    f"• 5M Close Back Inside: {p_close:.2f}\n"
                    f"• Market Bias: BEARISH 📉"
                )
        elif p_low < h4_low and p_close > h4_low:
            if should_send_alert(symbol_name, "S7_4H_LOW", candle_time):
                send_telegram_alert(
                    f"🚨 *[STRATEGY 7 ALERT] - {symbol_name}*\n\n"
                    f"⏰ *4H CRT Low Swept by 5M Candle!*\n"
                    f"• 4H Low Level: {h4_low:.2f}\n"
                    f"• 5M Close Back Inside: {p_close:.2f}\n"
                    f"• Market Bias: BULLISH 📈"
                )

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
