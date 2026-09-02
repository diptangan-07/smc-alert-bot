import os
import requests
import pandas as pd
import yfinance as yf
from flask import Flask

app = Flask(__name__)

# ENV OR DIRECT FALLBACK
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7963364955:AAEz0z--r6Y0L2kI7f4yT53S51pGfQoP6uM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8893050202")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        res = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Response: {res.status_code} -> {res.text}")
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

    if df_5m.empty or df_1d.empty or len(df_5m) < 15:
        print(f"Data empty for {symbol}")
        return

    prev = df_5m.iloc[-2]
    curr = df_5m.iloc[-1]
    pdh = df_1d['High'].iloc[-2]
    pdl = df_1d['Low'].iloc[-2]
    avg_vol = df_5m['Volume'].rolling(20).mean().iloc[-1]

    # STRATEGY 1: PDH/PDL Liquidity Sweep
    if prev['High'] > pdh and prev['Close'] < pdh:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDH SWEEP]</b>\nSymbol: {symbol}\nBuyside Liquidity Swept above PDH ({pdh:.2f})!\nCandle closed inside range.\n<b>Bias: BEARISH / SELL</b>")
    elif prev['Low'] < pdl and prev['Close'] > pdl:
        send_telegram(f"🚨 <b>[SMC STRATEGY 1 - PDL SWEEP]</b>\nSymbol: {symbol}\nSellside Liquidity Swept below PDL ({pdl:.2f})!\nCandle closed inside range.\n<b>Bias: BULLISH / BUY</b>")

    # STRATEGY 2: CHoCH
    recent_lh = df_5m['High'].iloc[-12:-2].max()
    recent_hl = df_5m['Low'].iloc[-12:-2].min()
    if prev['Close'] > recent_lh:
        send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BULLISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bearish L-H Broken with Body Close!")
    elif prev['Close'] < recent_hl:
        send_telegram(f"⚡ <b>[SMC STRATEGY 2 - BEARISH CHoCH]</b>\nSymbol: {symbol}\nPrevious Bullish H-L Broken with Body Close!")

    # STRATEGY 3: BOS
    prev_hh = df_5m['High'].iloc[-7:-2].max()
    prev_ll = df_5m['Low'].iloc[-7:-2].min()
    if prev['Close'] > prev_hh:
        send_telegram(f"📈 <b>[SMC STRATEGY 3 - BULLISH BOS]</b>\nSymbol: {symbol}\nContinuation: New HH Broken with Body Close!")
    elif prev['Close'] < prev_ll:
        send_telegram(f"📉 <b>[SMC STRATEGY 3 - BEARISH BOS]</b>\nSymbol: {symbol}\nContinuation: New LL Broken with Body Close!")

    # STRATEGY 4: Low Volume Breakout
    if prev['Volume'] < avg_vol:
        if prev['Close'] > pdh:
            send_telegram(f"📊 <b>[SMC STRATEGY 4 - PDH BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout above PDH. Waiting for BOS.")
        elif prev['Close'] < pdl:
            send_telegram(f"📊 <b>[SMC STRATEGY 4 - PDL BREAKOUT]</b>\nSymbol: {symbol}\nLow Volume Breakout below PDL. Waiting for BOS.")

    # STRATEGY 5: EQH / EQL Sweep
    eqh_level = df_5m['High'].iloc[-15:-3].max()
    eql_level = df_5m['Low'].iloc[-15:-3].min()
    if abs(prev['High'] - eqh_level) / eqh_level < 0.0003 and prev['Close'] < eqh_level:
        send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQH SWEEP]</b>\nSymbol: {symbol}\nEqual Highs Liquidity Swept and Returned Inside!")
    elif abs(prev['Low'] - eql_level) / eql_level < 0.0003 and prev['Close'] > eql_level:
        send_telegram(f"🎯 <b>[SMC STRATEGY 5 - EQL SWEEP]</b>\nSymbol: {symbol}\nEqual Lows Liquidity Swept and Returned Inside!")

    # STRATEGY 6: High Volume Breakout Failure / Fakeout
    if prev['Volume'] > (avg_vol * 1.3):
        if prev['Close'] < pdl and curr['Close'] > pdl:
            send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nPDL Breakout Failed! Price Returned Inside PDL Range.")
        elif prev['Close'] > pdh and curr['Close'] < pdh:
            send_telegram(f"⚠️ <b>[SMC STRATEGY 6 - FAKEOUT RE-ENTRY]</b>\nSymbol: {symbol}\nPDH Breakout Failed! Price Returned Inside PDH Range.")

    # STRATEGY 7: HTF CRT (1H & 4H SEPARATE NOTIFICATIONS)
    if not df_1h.empty and len(df_1h) >= 5:
        # 1H CRT Check
        prev_1h_high = df_1h['High'].iloc[-2]
        prev_1h_low = df_1h['Low'].iloc[-2]
        if prev['High'] > prev_1h_high and prev['Close'] < prev_1h_high:
            send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT HIGH SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H High ({prev_1h_high:.2f}) & Closed Inside Range!")
        elif prev['Low'] < prev_1h_low and prev['Close'] > prev_1h_low:
            send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 1H CRT LOW SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 1H Low ({prev_1h_low:.2f}) & Closed Inside Range!")

        # 4H CRT Check
        df_4h = df_1h.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        if len(df_4h) >= 2:
            prev_4h_high = df_4h['High'].iloc[-2]
            prev_4h_low = df_4h['Low'].iloc[-2]
            if prev['High'] > prev_4h_high and prev['Close'] < prev_4h_high:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 4H CRT HIGH SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 4H High ({prev_4h_high:.2f}) & Closed Inside Range!")
            elif prev['Low'] < prev_4h_low and prev['Close'] > prev_4h_low:
                send_telegram(f"⏳ <b>[SMC STRATEGY 7 - 4H CRT LOW SWEEP]</b>\nSymbol: {symbol}\n5M Candle Swept 4H Low ({prev_4h_low:.2f}) & Closed Inside Range!")

@app.route('/')
def home():
    return "SMC Engine Running", 200

@app.route('/run')
def run():
    send_telegram("🔄 <b>Manual Trigger Fired: Scanning Market Now...</b>")
    analyze_symbol("GC=F")
    analyze_symbol("BTC-USD")
    return "Scan Complete", 200

if __name__ == "__main__":
    send_telegram("✅ <b>Diptangan SMC Bot Engine Online & Ready!</b>")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
