import os
import time
import threading
import requests
import yfinance as yf
import google.generativeai as genai
from flask import Flask

# Flask Server for Render Port Binding
app = Flask(__name__)

@app.route('/')
def home():
    return "ICT-RAJ SMC ENGINE IS RUNNING LIVE 24/7!"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_market_data(ticker, timeframe="5m", period="2d"):
    try:
        df = yf.download(ticker, period=period, interval=timeframe)
        if df.empty or len(df) < 5:
            return None
        return df.tail(10).to_string()
    except Exception as e:
        return None

def analyze_smc(name, data_5m, data_1h, data_4h):
    prompt = f"""
    You are an expert Smart Money Concepts (SMC) AI Trading Engine analyzing market structure for {name}.
    Both Bullish (Downtrend to Uptrend) and Bearish (Uptrend to Downtrend) scenarios apply to all rules.

    [5M CANDLES]:
    {data_5m}

    [1H CANDLES]:
    {data_1h}

    [4H CANDLES]:
    {data_4h}

    Strictly check for the following 7 Strategies:

    STRATEGY 1: PDH/PDL LIQUIDITY SWEEP & RE-ENTRY (5M)
    - Wick sweeps Previous Day High (PDH) or Previous Day Low (PDL) and body closes INSIDE the range.
    - OR price closes outside PDH/PDL initially, but a subsequent candle returns INSIDE the range. Send alert ONLY when price is safely inside the range.

    STRATEGY 2: CHoCH - CHANGE OF CHARACTER (5M)
    - Triggered AFTER Strategy 1 (Sweep + Return inside range).
    - Bullish: Candle BODY CLOSES above the previous Lower High (L-H).
    - Bearish: Candle BODY CLOSES below the previous Higher Low (H-L).

    STRATEGY 3: POST-CHoCH BOS (5M)
    - Triggered AFTER CHoCH is formed.
    - Bullish: Price forms new H-H/H-L, then candle BODY CLOSES above the previous Higher High (H-H).
    - Bearish: Price forms new L-L/L-H, then candle BODY CLOSES below the previous Lower Low (L-L).

    STRATEGY 4: BREAKOUT WITH MINIMUM VOLUME & CONTINUATION BOS (5M)
    - Price breaks out of PDH/PDL with minimum volume and DOES NOT return inside range.
    - Market continues structure (forms L-H/H-L and breaks previous L-L/H-H via BOS). Trigger breakout & continuation alert.

    STRATEGY 5: EQUAL HIGH (EQH) & EQUAL LOW (EQL) SWEEP (5M)
    - Trigger alert when Equal Highs or Equal Lows liquidity pool is swept and rejected back.

    STRATEGY 6: BREAKOUT FAILURE / FAILED CONTINUATION RE-ENTRY (5M)
    - Market strongly breaks PDH/PDL with high volume and starts forming BOS outside.
    - BUT THEN IT FAILS and price re-enters back INSIDE the PDH/PDL range. Send immediate failure alert upon re-entry.

    STRATEGY 7: CANDLE RANGE THEORY (CRT - 1H, 4H & 5M SWEEP)
    - 1H CRT: 1-hour candle sweeps previous 1h high/low (or closes outside) and returns INSIDE the previous 1h range.
    - 4H CRT: 4-hour candle sweeps previous 4h high/low (or closes outside) and returns INSIDE the previous 4h range.
    - (Note: If price stays outside and continues trend without returning, DO NOT alert).
    - SPECIAL 5M SWEEP OF HTF: If ANY current 5m candle sweeps the high or low liquidity of the previous 1H or 4H candle, trigger an instant alert for 1H/4H Liquidity Sweep on 5M.

    If any strategy triggers on the latest candles, reply strictly in this English format:

    🚨 *[SMC ALERT - {name}]*
    • *STRATEGY:* [Exact Strategy Name e.g. Strategy 1 / Strategy 2 CHoCH / CRT 1H]
    • *SIGNAL:* [BUY / SELL]
    • *TIMEFRAME:* [5M / 1H / 4H]
    • *DETAILS:* [Short 1-sentence English explanation of candle body closing and structure]

    IF NO CLEAR SETUP MATCHES, reply strictly with: NO_SIGNAL
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "NO_SIGNAL" not in text:
            return text
        return None
    except Exception as e:
        return None

def bot_loop():
    send_telegram("🚀 *DIPTANGAN SMC ENGINE v3.0 LIVE*\nAll 7 SMC Strategies Loaded & Actively Monitoring...")
    while True:
        for name, ticker in ASSETS.items():
            d5m = get_market_data(ticker, "5m", "2d")
            d1h = get_market_data(ticker, "1h", "5d")
            d4h = get_market_data(ticker, "4h", "10d")
            
            if d5m and d1h and d4h:
                alert = analyze_smc(name, d5m, d1h, d4h)
                if alert:
                    send_telegram(alert)
            time.sleep(2)
        time.sleep(300)

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
