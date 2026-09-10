import os
import time
import requests
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs")
CHAT_ID = os.getenv("CHAT_ID", "7476331970")

SYMBOLS = {
    "NIFTY50": "^NSEI",
    "SENSEX": "^BSESN",
    "BTCUSD": "BTC-USD",
    "GOLD": "PAXG-USD", # Updated to PAXG-USD
    "ETHUSD": "ETH-USD",
    "XRPUSD": "XRP-USD",
    "EURUSD": "EURUSD=X",
    "JPYUSD": "JPY=X",
    "GBPUSD": "GBPUSD=X"
}

# State tracking to avoid spamming alerts for the same candle
last_processed_candle = {}

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def fetch_data(symbol, interval, period):
    try:
        df = yf.download(tickers=symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching {symbol} ({interval}): {e}")
        return None

def analyze_symbol(name, symbol):
    df_5m = fetch_data(symbol, "5m", "5d")
    df_1d = fetch_data(symbol, "1d", "10d")
    df_1h = fetch_data(symbol, "1h", "10d")
    df_4h = fetch_data(symbol, "1h", "1mo") 

    if df_5m is None or df_1d is None or len(df_5m) < 15 or len(df_1d) < 2:
        return

    # Ensure duplicate candle check using closed 5M candle timestamp
    latest_candle_time = df_5m.index[-2]
    if last_processed_candle.get(name) == latest_candle_time:
        return

    # Closed 5m Candle (-2 represents last fully closed candle)
    c_open = df_5m['Open'].iloc[-2]
    c_high = df_5m['High'].iloc[-2]
    c_low = df_5m['Low'].iloc[-2]
    c_close = df_5m['Close'].iloc[-2]
    c_volume = df_5m['Volume'].iloc[-2]
    avg_vol = df_5m['Volume'].tail(20).mean()

    # Previous Day Levels (Daily)
    pdh = df_1d['High'].iloc[-2]
    pdl = df_1d['Low'].iloc[-2]

    # --- Strategy 1: Previous Day Liquidity Sweep & Re-entry ---
    if c_high > pdh and c_close < pdh:
        send_alert(f"🚨 **Strategy 1 Alert [{name}]**\n⚡ **PDH Liquidity Sweep!**\nHigh: `{c_high:.2f}` | PDH: `{pdh:.2f}`\nBody closed inside the range (`{c_close:.2f}`).")
        last_processed_candle[name] = latest_candle_time

    elif c_low < pdl and c_close > pdl:
        send_alert(f"🚨 **Strategy 1 Alert [{name}]**\n⚡ **PDL Liquidity Sweep!**\nLow: `{c_low:.2f}` | PDL: `{pdl:.2f}`\nBody closed inside the range (`{c_close:.2f}`).")
        last_processed_candle[name] = latest_candle_time

    # --- Strategy 2: CHoCH (Change of Character) ---
    recent_high = df_5m['High'].iloc[-12:-2].max()
    recent_low = df_5m['Low'].iloc[-12:-2].min()
    if df_5m['Close'].iloc[-3] < recent_high and c_close > recent_high:
        send_alert(f"🚨 **Strategy 2 Alert [{name}]**\n📈 **Bullish CHoCH Confirmed!**\nBroke previous structural high (`{recent_high:.2f}`) with candle close (`{c_close:.2f}`).")
        last_processed_candle[name] = latest_candle_time

    # --- Strategy 3: BOS (Break of Structure) ---
    prev_high = df_5m['High'].iloc[-7:-2].max()
    if c_close > prev_high and df_5m['Close'].iloc[-3] <= prev_high:
        send_alert(f"🚨 **Strategy 3 Alert [{name}]**\n🚀 **Bullish BOS Alert!**\nPrice closed (`{c_close:.2f}`) above structure high (`{prev_high:.2f}`).")
        last_processed_candle[name] = latest_candle_time

    # --- Strategy 4 & 6: Breakout with Volume Logic ---
    if c_close > pdh:
        if c_volume < avg_vol:
            send_alert(f"🚨 **Strategy 4 Alert [{name}]**\n⚠️ **PDH Breakout with LOW Volume!**\nClose: `{c_close:.2f}` | PDH: `{pdh:.2f}`")
        elif c_volume > (avg_vol * 1.5):
            send_alert(f"🚨 **Strategy 6 Alert [{name}]**\n🔥 **PDH Breakout with STRONG Volume!**\nClose: `{c_close:.2f}` | Volume: `{c_volume}`")
        last_processed_candle[name] = latest_candle_time

    # --- Strategy 5: Equal Highs / Lows (EQH/EQL) Sweep ---
    if df_1h is not None and len(df_1h) >= 5:
        h1 = df_1h['High'].iloc[-2]
        h2 = df_1h['High'].iloc[-3]
        if abs(h1 - h2) / h1 < 0.0008 and c_high > max(h1, h2) and c_close < max(h1, h2):
            send_alert(f"🚨 **Strategy 5 Alert [{name}]**\n🎯 **1H/4H EQH Liquidity Sweep Detected on 5M!**")
            last_processed_candle[name] = latest_candle_time

    # --- Strategy 7: CRT (Candle Range Theory) 1H & 4H Sweep ---
    if df_1h is not None and len(df_1h) >= 3:
        p_1h_high = df_1h['High'].iloc[-2]
        p_1h_low = df_1h['Low'].iloc[-2]
        if (c_high > p_1h_high and c_close < p_1h_high) or (c_low < p_1h_low and c_close > p_1h_low):
            send_alert(f"🚨 **Strategy 7 Alert [{name}]**\n⏳ **1H CRT Liquidity Swept by 5M Candle!**")
            last_processed_candle[name] = latest_candle_time

def main():
    print("Bot is running with updated strategy logic...")
    while True:
        for name, symbol in SYMBOLS.items():
            try:
                analyze_symbol(name, symbol)
            except Exception as e:
                print(f"Error running logic for {name}: {e}")
        time.sleep(60) # Checks every 1 minute

if __name__ == "__main__":
    main()
