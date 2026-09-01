import time
import requests
import yfinance as yf
from google import genai

# Configs
GEMINI_API_KEY = "AQ.Ab8RN6L3eQ2UYi6doKNGt84aoxqVfZaVsNI7LD_KwNyKz7ZX6A"
TELEGRAM_BOT_TOKEN = "8893050202:AAHrl0kzyt5Bjptbuoy9ae2c9SwF0KAOsmE"
TELEGRAM_CHAT_ID = "7476331970"

# Gemini Client Init
client = genai.Client(api_key=GEMINI_API_KEY)

# Assets Mapping (Gold, Silver, Crypto, Nifty, Sensex)
ASSETS = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "NIFTY50": "^NSEI",
    "SENSEX": "^BSESN"
}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

def get_market_data(ticker):
    try:
        data = yf.download(tickers=ticker, period="1d", interval="5m", progress=False)
        if data.empty:
            return []
        candles = []
        for index, row in data.tail(20).iterrows():
            candles.append({
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close'])
            })
        return candles
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return []

def analyze_smc(name, candles):
    prompt = f"""
    You are an expert SMC trader. Analyze the following last 5-minute candles for {name}:
    {candles}

    Check for:
    1. Liquidity Sweep (PDH/PDL or Equal Highs/Lows)
    2. CHoCH
    3. BOS
    4. True Breakout

    If a strong setup is found right now, respond in this format:
    SIGNAL: [BUY/SELL]
    STRATEGY: [Strategy Name]
    REASON: [Short 1-sentence reason]

    If NO clear setup, reply ONLY: NO_SIGNAL
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI Error on {name}:", e)
        return "NO_SIGNAL"

print("🚀 DIPTANGAN Multi-Asset SMC Terminal Engine Started...")
send_telegram("🚀 Multi-Asset SMC AI Bot Live! Tracking Gold, Silver, BTC, ETH, Nifty & Sensex.")

processed_candles = {}

while True:
    for name, ticker in ASSETS.items():
        try:
            candles = get_market_data(ticker)
            if not candles:
                continue
                
            last_close = candles[-1]['close']
            
            # Prevent double alerts on same candle close
            if processed_candles.get(name) != last_close:
                ai_result = analyze_smc(name, candles)
                if "NO_SIGNAL" not in ai_result:
                    msg = f"🔥 [SMC ALERT - {name} 5M]\n\n{ai_result}"
                    send_telegram(msg)
                    print(f"Alert Sent for {name}:", ai_result)
                processed_candles[name] = last_close
                
        except Exception as e:
            print(f"Error checking {name}:", e)
            
    time.sleep(60) # Scan every 1 minute
    
