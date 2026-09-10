import os
import time
import requests
import pandas as pd

# Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs")
CHAT_ID = os.getenv("CHAT_ID", "7476331970")

SYMBOLS = {
    "BTCUSD": "crypto/binance/btcusdt",
    "ETHUSD": "crypto/binance/ethusdt",
    "XRPUSD": "crypto/binance/xrpusdt",
    "EURUSD": "forex/oanda/eur_usd",
    "GBPUSD": "forex/oanda/gbp_usd",
    "JPYUSD": "forex/oanda/usd_jpy"
}

def send_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_market_data(symbol_path):
    # Free Market Data API fallback
    try:
        url = f"https://api.stooq.com/q/l/?s={symbol_path}&f=sdohcv&h&e=csv"
        df = pd.read_csv(url)
        if not df.empty and 'Close' in df.columns:
            return df
    except Exception as e:
        print(f"Data fetch error for {symbol_path}: {e}")
    return None

def process_strategies(name, df):
    if df is None or len(df) < 5:
        return

    close = df['Close'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    
    prev_high = df['High'].iloc[-2]
    prev_low = df['Low'].iloc[-2]

    # Strategy 1 & 7: Liquidity Sweep
    if high > prev_high and close < prev_high:
        send_alert(f"🚨 **Strategy 1 & 7 Alert [{name}]**: High Liquidity Sweep! Price closed back inside previous range.")
    elif low < prev_low and close > prev_low:
        send_alert(f"🚨 **Strategy 1 & 7 Alert [{name}]**: Low Liquidity Sweep! Price closed back inside previous range.")

    # Strategy 2: CHoCH
    recent_high = df['High'].tail(5).max()
    if close > recent_high:
        send_alert(f"🚨 **Strategy 2 Alert [{name}]**: CHoCH detected! Structure broken to upside.")

    # Strategy 3: BOS
    if close > prev_high:
        send_alert(f"🚨 **Strategy 3 Alert [{name}]**: BOS (Break of Structure) confirmed!")

    # Strategy 5: Equal High/Low Sweep
    if abs(df['High'].iloc[-2] - df['High'].iloc[-3]) / df['High'].iloc[-2] < 0.001:
        if high > df['High'].iloc[-2]:
            send_alert(f"🚨 **Strategy 5 Alert [{name}]**: Equal High Liquidity Swept!")

def main():
    print("Bot startup successful. Monitoring started...")
    send_alert("🤖 **Trading Bot active & running on Render!**")
    
    while True:
        for name, path in SYMBOLS.items():
            try:
                df = get_market_data(path)
                process_strategies(name, df)
            except Exception as e:
                print(f"Error processing {name}: {e}")
        
        # 3 minute interval
        time.sleep(180)

if __name__ == "__main__":
    main()
