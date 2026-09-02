import os
import requests
import pandas as pd
import yfinance as yf
from flask import Flask

app = Flask(__name__)

# TELEGRAM CONFIG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8893050202:AAHr10kzyt5Bjptbuoy9ae2c9SwF0KAOsmE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7476331970")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        res = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Status: {res.status_code} -> {res.text}")
    except Exception as e:
        print(f"Telegram Exception: {e}")

def get_clean_data(symbol, period, interval):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"Fetch Exception ({symbol}): {e}")
        return pd.DataFrame()

def analyze_symbol(symbol):
    df_5m = get_clean_data(symbol, period="5d", interval="5m")
    df_1h = get_clean_data(symbol, period="7d", interval="1h")
    df_1d = get_clean_data(symbol, period="5d", interval="1d")

    if df_5m.empty or df_1d.empty or len(df_5m) < 20:
        return

    prev = df_5m.iloc[-2]
    curr = df_5m.iloc[-1]
    pdh = df_1d['High'].iloc[-2]
    pdl = df_1d['Low'].iloc[-2]
    avg_vol = df_5m['Volume'].rolling(20).mean().iloc[-1]

    # ----------------------------------------------------
    # STRATEGY 1: PDH / PDL Liquidity Sweep & Range Re-entry
    # ----------------------------------------------------
    # Case A: Direct Wick Sweep (Wick outside, body closed inside)
    if prev['High'] > pdh and prev['Close'] < pdh:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDH SWEEP]</b>\nSymbol: {symbol}\nBuyside Liquidity Swept above PDH ({pdh:.2f}) and closed inside range!\n<b>Bias: BEARISH</b>")
    elif prev['Low'] < pdl and prev['Close'] > pdl:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDL SWEEP]</b>\nSymbol: {symbol}\nSellside Liquidity Swept below PDL ({pdl:.2f}) and closed inside range!\n<b>Bias: BULLISH</b>")
    
    # Case B: Closed outside earlier, but now re-entered back inside range
    if prev['Close'] > pdh and curr['Close'] < pdh:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDH RANGE RE-ENTRY]</b>\nSymbol: {symbol}\nPrice returned back inside PDH Range ({pdh:.2f}) after sweep!\n<b>Bias: BEARISH</b>")
    elif prev['Close'] < pdl and curr['Close'] > pdl:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDL RANGE RE-ENTRY]</b>\nSymbol: {symbol}\nPrice returned back inside PDL Range ({pdl:.2f}) after sweep!\n<b>Bias: BULLISH</b>")

    # ----------------------------------------------------
    # STRATEGY 2: CHoCH (Change of Character with Body Close)
    # ----------------------------------------------------
    recent_lh = df_5m['High'].iloc[-15:-2].max()
    recent_hl = df_5m['Low'].iloc[-15:-2].min()
    if curr['Close'] > recent_lh and prev['Close'] <= recent_lh:
        send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BULLISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bearish Lower High ({recent_lh:.2f}) broken with body close!\n<b>Trend shift: BEARISH -> BULLISH</b>")
    elif curr['Close'] < recent_hl and prev['Close'] >= recent_hl:
        send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BEARISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bullish Higher Low ({recent_hl:.2f}) broken with body close!\n<b>Trend shift: BULLISH -> BEARISH</b>")

    # ----------------------------------------------------
    # STRATEGY 3: BOS (Break of Structure in New Trend)
    # ----------------------------------------------------
    prev_hh = df_5m['High'].iloc[-8:-2].max()
    prev_ll = df_5m['Low'].iloc[-8:-2].min()
    if curr['Close'] > prev_hh and prev['Close'] <= prev_hh:
        send_telegram(f"📈 <b>[SMC STRATEGY 3 - BULLISH BOS]</b>\nSymbol: {symbol}\nContinuation: New Higher High broken with body close!")
    elif curr['Close'] < prev_ll and prev['Close'] <= prev_ll:
        send_telegram(f"📉 <b>[SMC STRATEGY 3 - BEARISH BOS]</b>\nSymbol: {symbol}\nContinuation: New Lower Low broken with body close!")

    # ----------------------------------------------------
    # STRATEGY 4: Low Volume Breakout + Continuation BOS
    # ----------------------------------------------------
    if curr['Volume'] < avg_vol:
        if curr['Close'] > pdh:
            send_telegram(f"📊 <b>[SMC STRATEGY 4 - LOW VOL PDH BREAKOUT]</b>\nSymbol: {symbol}\nBreakout above PDH with Low Volume. Watching for continuation.")
        elif curr['Close'] < pdl:
            send_telegram(f"📊 <b>[SMC STRATEGY 4 - LOW VOL PDL BREAKOUT]</b>\nSymbol: {symbol}\nBreakout below PDL with Low Volume. Watching for continuation.")

    # Continuation BOS after Low Vol Breakout
    if curr['Close'] < pdl and curr['Close'] < prev_ll:
        send_telegram(f"📉 <b>[SMC STRATEGY 4 - BREAKOUT BOS CONTINUATION]</b>\nSymbol: {symbol}\nPDL Breakout Trend Continued: LL Broken!")

    # ----------------------------------------------------
    # STRATEGY 5: Equal Highs (EQH) & Equal Lows (EQL) Sweep
    # ----------------------------------------------------
    eqh_level = df_5m['High'].iloc[-15:-3].max()
    eql_level = df_5m['Low'].iloc[-15:-3].min()
    if abs(prev['High'] - eqh_level) / eqh_level < 0.0003 and curr['Close'] < eqh_level:
        send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQH SWEEP]</b>\nSymbol: {symbol}\nEqual Highs Liquidity Swept and Price Returned Inside!")
    elif abs(prev['Low'] - eql_level) / eql_level < 0.0003 and curr['Close'] > eql_level:
        send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQL SWEEP]</b>\nSymbol: {symbol}\nEqual Lows Liquidity Swept and Price Returned Inside!")

    # ----------------------------------------------------
    # STRATEGY 6: Strong High Volume Breakout Failure / Fakeout Re-entry
    # ----------------------------------------------------
    if prev['Close'] < pdl and curr['Close'] > pdl:
        send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nStrong Breakout Failed! Price Returned Back Inside PDL Range.")
    elif prev['Close'] > pdh and curr['Close'] < pdh:
        send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nStrong Breakout Failed! Price Returned Back Inside PDH Range.")

    # ----------------------------------------------------
    # STRATEGY 7: HTF CRT (1H & 4H Sweeps via 5M Candle)
    # ----------------------------------------------------
    if not df_1h.empty and len(df_1h) >= 5:
        # 1H CRT Check
        prev_1h_high = df_1h['High'].iloc[-2]
        prev_1h_low = df_1h['Low'].iloc[-2]
        
        if curr['High'] > prev_1h_high and curr['Close'] < prev_1h_high:
            send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT HIGH SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H High ({prev_1h_high:.2f}) & Closed Inside Range!")
        elif curr['Low'] < prev_1h_low and curr['Close'] > prev_1h_low:
            send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT LOW SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H Low ({prev_1h_low:.2f}) & Closed Inside Range!")

        # 4H CRT Check
        df_4h = df_1h.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        if len(df_4h) >= 2:
            prev_4h_high = df_4h['High'].iloc[-2]
            prev_4h_low = df_4h['Low'].iloc[-2]
            
            if curr['High'] > prev_4h_high and curr['Close'] < prev_4h_high:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 4H CRT HIGH SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 4H High ({prev_4h_high:.2f}) & Closed Inside Range!")
            elif curr['Low'] < prev_4h_low and curr['Close'] > prev_4h_low:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 4H CRT LOW SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 4H Low ({prev_4h_low:.2f}) & Closed Inside Range!")

@app.route('/')
def home():
    return "SMC Engine Running", 200

@app.route('/run')
def run():
    analyze_symbol("GC=F")
    analyze_symbol("BTC-USD")
    return "Scan Complete", 200

if __name__ == "__main__":
    send_telegram("✅ <b>Diptangan SMC AI Bot Engine Connected Successfully!</b>")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
