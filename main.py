import os
import time
import requests
import yfinance as yf
import google.generativeai as genai

# Configure Gemini AI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Telegram Configs
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

ASSETS = {
    "Gold": "GC=F",
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
    "Nifty 50": "^NSEI",
    "Sensex": "^BSESN"
}

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Credentials Missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_market_data(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="5m")
        if df.empty or len(df) < 10:
            return None
        recent_candles = df.tail(15).to_string()
        return recent_candles
    except Exception as e:
        print(f"Fetch Error for {ticker}: {e}")
        return None

def analyze_smc(name, candles):
    prompt = f"""
    You are an advanced Smart Money Concepts (SMC) AI Trading Engine monitoring 5-minute (5m) charts for {name}.
    Analyze the following 5m OHLCV candle data carefully:
    {candles}

    Your strict strategy rules to detect (both Uptrend -> Downtrend AND Downtrend -> Uptrend):

    STRATEGY 1: LIQUIDITY SWEEP (PDH/PDL Sweep and Re-entry)
    - Bullish: Price sweeps Previous Day Low (PDL) or previous swing low with a wick/candle, but body closes INSIDE the previous range/structure. If price initially closed outside but the next candle returns inside the range, trigger alert.
    - Bearish: Price sweeps Previous Day High (PDH) or previous swing high with a wick/candle, but body closes INSIDE the range.

    STRATEGY 2: CHoCH (Change of Character)
    - Bullish: After sweeping liquidity in a downtrend and returning inside range, price breaks the previous Lower High (L-H) with a strong candle BODY CLOSING above it.
    - Bearish: After sweeping liquidity in an uptrend, price breaks the previous Higher Low (H-L) with a strong candle BODY CLOSING below it.

    STRATEGY 3: BOS (Break of Structure - Post CHoCH Confirmation)
    - Bullish: After CHoCH occurs, market forms new Higher-High (H-H) and Higher-Low (H-L). When a new candle breaks the previous H-H with a BODY CLOSING above it, trigger BOS alert.
    - Bearish: After CHoCH, market forms Lower-Low (L-L) and Lower-High (L-H). When a new candle breaks the previous L-L with a BODY CLOSING below it, trigger BOS alert.

    STRATEGY 4: TRUE BREAKOUT & CONTINUATION
    - Bullish: Price breaks out of PDH with minimum volume expansion and stays above range without returning inside. If market forms new L-H/H-L structure and breaks previous H-H (BOS), trigger alert.
    - Bearish: Price breaks out of PDL with minimum volume expansion and stays below range. If market forms L-H structure and breaks previous L-L (BOS), trigger alert.

    STRATEGY 5: ALL CONTINUOUS BOS ALERTS (5m Timeframe)
    - Send an alert for EVERY SINGLE valid BOS occurrence on the 5m chart for all tracked assets (Gold, BTC, ETH, Nifty 50, Sensex) whenever a candle body breaks previous swing high/low structure.

    STRATEGY 6: EQUAL HIGH / EQUAL LOW LIQUIDITY SWEEP
    - Trigger alert when Equal Highs (EQH) or Equal Lows (EQL) liquidity pool is swept and rejected back.

    IF ANY of the above conditions are met on the latest 5m candle, reply STRICTLY in this English notification format:

    🚨 *[SMC 5M ALERT - {name}]*
    • *SIGNAL:* [BUY / SELL]
    • *STRATEGY:* [Exact Strategy triggered: Liquidity Sweep / CHoCH / BOS / Breakout / EQH-EQL Sweep]
    • *TIMEFRAME:* 5M
    • *REASON:* [Short English explanation of candle body closing and structure break]

    IF NO CLEAR SETUP MATCHES, reply strictly with: NO_SIGNAL
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "NO_SIGNAL" not in text:
            return text
        return None
    except Exception as e:
        print(f"Gemini Analysis Error: {e}")
        return None

def main():
    send_telegram("🚀 *DIPTANGAN SMC ENGINE v3.0 ACTIVE*\nMonitoring 5m Charts for Sweep, CHoCH, BOS & Breakouts...")
    while True:
        for name, ticker in ASSETS.items():
            candles = get_market_data(ticker)
            if candles is not None:
                alert = analyze_smc(name, candles)
                if alert:
                    send_telegram(alert)
            time.sleep(3)
        time.sleep(300) # Scan every 5 mins

if __name__ == "__main__":
    main()
        
