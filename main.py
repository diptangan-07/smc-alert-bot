import os
import time
import requests
import pandas as pd
import yfinance as yf

# Retrieve tokens from Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs")
CHAT_ID = os.getenv("CHAT_ID", "7476331970")

# All requested assets (GOLD set to PAXG-USD)
SYMBOLS = {
    "NIFTY50": "^NSEI",
    "SENSEX": "^BSESN",
    "BTCUSD": "BTC-USD",
    "GOLD (PAXG)": "PAXG-USD",
    "ETHUSD": "ETH-USD",
    "XRPUSD": "XRP-USD",
    "EURUSD": "EURUSD=X",
    "JPYUSD": "JPY=X",
    "GBPUSD": "GBPUSD=X"
}

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send alert: {e}")

def fetch_data(symbol, interval, period):
    try:
        # Custom session to prevent Yahoo Finance blocking on cloud servers like Render
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"Error fetching {symbol} ({interval}): {e}")
        return None

def analyze_market(name, symbol):
    # Fetch 5m, 1d, 1h data
    df_5m = fetch_data(symbol, "5m", "5d")
    df_1d = fetch_data(symbol, "1d", "1mo")
    df_1h = fetch_data(symbol, "1h", "10d")

    if df_5m is None or df_1d is None or len(df_5m) < 10 or len(df_1d) < 2:
        return

    # Daily Levels (Previous Day High & Low)
    p_high = df_1d['High'].iloc[-2]
    p_low = df_1d['Low'].iloc[-2]

    # Current 5m Candle Values
    c_close = df_5m['Close'].iloc[-1]
    c_high = df_5m['High'].iloc[-1]
    c_low = df_5m['Low'].iloc[-1]
    p_close = df_5m['Close'].iloc[-2]
    p_volume = df_5m['Volume'].iloc[-1] if 'Volume' in df_5m.columns else 0
    avg_volume = df_5m['Volume'].tail(20).mean() if 'Volume' in df_5m.columns else 1

    # --- Strategy 1: PDH/PDL Liquidity Sweep & Re-entry ---
    if (c_high > p_high and c_close < p_high) or (c_low < p_low and c_close > p_low):
        send_alert(f"🚨 **Strategy 1 Alert [{name}]**: Liquidity sweep detected! Wick swept PDH/PDL but 5m body closed inside range.")

    # --- Strategy 2: CHoCH (Change of Character) ---
    recent_high = df_5m['High'].tail(10).iloc[:-1].max()
    recent_low = df_5m['Low'].tail(10).iloc[:-1].min()
    if p_close < recent_high and c_close > recent_high:
        send_alert(f"🚨 **Strategy 2 Alert [{name}]**: CHoCH detected! Price broke previous swing high/low with body closing.")

    # --- Strategy 3: BOS (Break of Structure in Trend) ---
    higher_high = df_5m['High'].tail(5).iloc[:-1].max()
    if c_close > higher_high:
        send_alert(f"🚨 **Strategy 3 Alert [{name}]**: BOS confirmed! Continuation of new trend with candle body closing.")

    # --- Strategy 4: Breakout & Trend Continuation ---
    if c_close > p_high and p_volume < avg_volume:
        send_alert(f"🚨 **Strategy 4 Alert [{name}]**: PDH/PDL Breakout detected with low volume. Watching for trend/BOS.")

    # --- Strategy 5: Equal Highs / Equal Lows (EQH/EQL) Sweep (1H / 4H) ---
    if df_1h is not None and len(df_1h) >= 5:
        h1 = df_1h['High'].iloc[-2]
        h2 = df_1h['High'].iloc[-3]
        if abs(h1 - h2) / h1 < 0.001 and c_high > max(h1, h2):
            send_alert(f"🚨 **Strategy 5 Alert [{name}]**: 1H/4H EQH/EQL Liquidity Swept by 5m candle!")

    # --- Strategy 6: High Volume Breakout & Re-entry Range Alert ---
    if c_close < p_high and p_close > p_high and p_volume > (avg_volume * 1.3):
        send_alert(f"🚨 **Strategy 6 Alert [{name}]**: High volume breakout re-entered inside PDH/PDL range!")

    # --- Strategy 7: CRT (Candle Range Theory) 1H & 4H Sweep via 5M Candle ---
    if df_1h is not None and len(df_1h) >= 2:
        h1_high = df_1h['High'].iloc[-2]
        h1_low = df_1h['Low'].iloc[-2]
        if (c_high > h1_high and c_close < h1_high) or (c_low < h1_low and c_close > h1_low):
            send_alert(f"🚨 **Strategy 7 Alert [{name}]**: CRT 1H/4H Candle Liquidity Sweep detected on 5m candle!")

def main():
    print("Trading Bot Started Monitoring All Assets...")
    send_alert("🤖 **Trading Bot Connected & Active on Render!** Monitoring NIFTY, SENSEX, Crypto & Forex...")
    
    while True:
        for name, symbol in SYMBOLS.items():
            try:
                analyze_market(name, symbol)
            except Exception as e:
                print(f"Error executing logic for {name}: {e}")
        time.sleep(300) # Check every 5 minutes

if __name__ == "__main__":
    main()
