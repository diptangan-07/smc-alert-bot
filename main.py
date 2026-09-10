import os
import time
import requests
import ccxt
import pandas as pd
import numpy as np

# ==========================================
# CONFIGURATION & USER CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs"
TELEGRAM_CHAT_ID = "7476331970"

# Asset Symbols (CCXT / Binance Format)
SYMBOLS = [
    'PAXG/USDT', # Gold (PAXG)
    'BTC/USDT',  # BTC
    'ETH/USDT',  # ETH
    'GBP/USDT',  # GBPUSD Proxy
    'EUR/USDT',  # EURUSD Proxy
]

# Track state to avoid repeated duplicate notifications
notified_events = set()

# Initialize CCXT Exchange
exchange = ccxt.binance({
    'enableRateLimit': True,
})

def send_telegram_msg(message):
    """Telegram Group/Chat e message pathanor function"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Failed to send Telegram message: {res.text}")
    except Exception as e:
        print(f"Telegram API Error: {e}")

def fetch_ohlcv(symbol, timeframe, limit=100):
    """OHLCV data anar function"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol} ({timeframe}): {e}")
        return None

def analyze_symbol(symbol):
    print(f"Analyzing {symbol}...")
    
    # Data Fetching
    df_5m = fetch_ohlcv(symbol, '5m', 100)
    df_1h = fetch_ohlcv(symbol, '1h', 100)
    df_4h = fetch_ohlcv(symbol, '4h', 100)
    df_1d = fetch_ohlcv(symbol, '1d', 10)
    
    if df_5m is None or df_1h is None or df_4h is None or df_1d is None:
        return

    # Previous Day High / Low
    pdh = df_1d.iloc[-2]['high']
    pdl = df_1d.iloc[-2]['low']
    
    # Latest completed 5m candle
    curr_5m = df_5m.iloc[-1]
    prev_5m = df_5m.iloc[-2]
    
    curr_close = curr_5m['close']
    curr_high = curr_5m['high']
    curr_low = curr_5m['low']
    curr_volume = curr_5m['volume']
    avg_vol_5m = df_5m['volume'].tail(20).mean()

    # -----------------------------------------------------------
    # STRATEGY 1: PDH / PDL Liquidity Sweep / Re-entry
    # -----------------------------------------------------------
    # High sweep but body closed inside range
    if curr_high > pdh and curr_close < pdh and curr_close > pdl:
        event_key = f"{symbol}_STRAT1_PDH_SWEEP_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDH Liquidity Sweep Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrevious Day High ({pdh}) was swept by wick, but price closed inside the daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # Low sweep but body closed inside range
    if curr_low < pdl and curr_close > pdl and curr_close < pdh:
        event_key = f"{symbol}_STRAT1_PDL_SWEEP_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDL Liquidity Sweep Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrevious Day Low ({pdl}) was swept by wick, but price closed inside the daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # Price broke out/closed outside PDH/PDL and re-entered range
    if prev_5m['close'] > pdh and curr_close < pdh:
        event_key = f"{symbol}_STRAT1_PDH_REENTRY_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDH Range Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nPrice closed above PDH previously and has now returned back inside the daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if prev_5m['close'] < pdl and curr_close > pdl:
        event_key = f"{symbol}_STRAT1_PDL_REENTRY_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 1] PDL Range Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nPrice closed below PDL previously and has now returned back inside the daily range!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 2: CHoCH (Change of Character)
    # -----------------------------------------------------------
    recent_high = df_5m['high'].tail(15).max()
    recent_low = df_5m['low'].tail(15).min()

    # Bearish to Bullish CHoCH
    if prev_5m['close'] <= recent_high and curr_close > recent_high:
        event_key = f"{symbol}_STRAT2_BULL_CHOCH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 2] Bullish CHoCH Detected!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nMarket broke recent LH structure with body closing above key level ({recent_high}). Trend shifting Bearish ➡️ Bullish!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # Bullish to Bearish CHoCH
    if prev_5m['close'] >= recent_low and curr_close < recent_low:
        event_key = f"{symbol}_STRAT2_BEAR_CHOCH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 2] Bearish CHoCH Detected!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nMarket broke recent HL structure with body closing below key level ({recent_low}). Trend shifting Bullish ➡️ Bearish!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 3: BOS (Break of Structure)
    # -----------------------------------------------------------
    prev_hh = df_5m['high'].iloc[-10:-2].max()
    prev_ll = df_5m['low'].iloc[-10:-2].min()

    if curr_close > prev_hh:
        event_key = f"{symbol}_STRAT3_BULL_BOS_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 3] Bullish BOS Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrice broke previous Higher-High ({prev_hh}) with strong body close. Bullish trend continuation confirmed!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_close < prev_ll:
        event_key = f"{symbol}_STRAT3_BEAR_BOS_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 3] Bearish BOS Alert!</b>\n\nAsset: <b>{symbol}</b>\nTimeframe: 5m\nPrice broke previous Lower-Low ({prev_ll}) with strong body close. Bearish trend continuation confirmed!"
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 4: Low Volume Breakout & Trend Continuation
    # -----------------------------------------------------------
    if curr_close > pdh and curr_volume < avg_vol_5m and prev_5m['close'] <= pdh:
        event_key = f"{symbol}_STRAT4_LOWVOL_PDH_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 4] Low Volume PDH Breakout!</b>\n\nAsset: <b>{symbol}</b>\nPrice broke out above PDH with minimal volume. Watch closely for trend continuation or fakeout."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_close < pdl and curr_volume < avg_vol_5m and prev_5m['close'] >= pdl:
        event_key = f"{symbol}_STRAT4_LOWVOL_PDL_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 4] Low Volume PDL Breakdown!</b>\n\nAsset: <b>{symbol}</b>\nPrice broke down below PDL with minimal volume. Watch closely for trend continuation or fakeout."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 5: Equal High (EQH) / Equal Low (EQL) Liquidity
    # -----------------------------------------------------------
    # Check 1H EQH/EQL
    highs_1h = df_1h['high'].tail(30).values
    lows_1h = df_1h['low'].tail(30).values
    
    for i in range(len(highs_1h) - 5):
        for j in range(i + 3, len(highs_1h)):
            if abs(highs_1h[i] - highs_1h[j]) / highs_1h[i] < 0.0008: # Near equal high
                eqh_val = max(highs_1h[i], highs_1h[j])
                if curr_high > eqh_val and curr_close < eqh_val:
                    event_key = f"{symbol}_STRAT5_EQH_{curr_5m['timestamp']}"
                    if event_key not in notified_events:
                        msg = f"🚨 <b>[STRATEGY 5] Equal Highs (EQH) Liquidity Swept!</b>\n\nAsset: <b>{symbol}</b>\nEqual Highs level ({eqh_val}) swept on 5m execution!"
                        send_telegram_msg(msg)
                        notified_events.add(event_key)

            if abs(lows_1h[i] - lows_1h[j]) / lows_1h[i] < 0.0008: # Near equal low
                eql_val = min(lows_1h[i], lows_1h[j])
                if curr_low < eql_val and curr_close > eql_val:
                    event_key = f"{symbol}_STRAT5_EQL_{curr_5m['timestamp']}"
                    if event_key not in notified_events:
                        msg = f"🚨 <b>[STRATEGY 5] Equal Lows (EQL) Liquidity Swept!</b>\n\nAsset: <b>{symbol}</b>\nEqual Lows level ({eql_val}) swept on 5m execution!"
                        send_telegram_msg(msg)
                        notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 6: High Volume Breakout Re-Entry
    # -----------------------------------------------------------
    if curr_volume > (avg_vol_5m * 1.8):
        if prev_5m['close'] > pdh and curr_close < pdh:
            event_key = f"{symbol}_STRAT6_HV_PDH_REENTRY_{curr_5m['timestamp']}"
            if event_key not in notified_events:
                msg = f"🚨 <b>[STRATEGY 6] High Volume PDH Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nStrong volume breakout above PDH failed! Price has returned back inside the daily range!"
                send_telegram_msg(msg)
                notified_events.add(event_key)

        if prev_5m['close'] < pdl and curr_close > pdl:
            event_key = f"{symbol}_STRAT6_HV_PDL_REENTRY_{curr_5m['timestamp']}"
            if event_key not in notified_events:
                msg = f"🚨 <b>[STRATEGY 6] High Volume PDL Re-Entry Alert!</b>\n\nAsset: <b>{symbol}</b>\nStrong volume breakdown below PDL failed! Price has returned back inside the daily range!"
                send_telegram_msg(msg)
                notified_events.add(event_key)

    # -----------------------------------------------------------
    # STRATEGY 7: CRT (Candle Range Theory - 1H & 4H Sweeps)
    # -----------------------------------------------------------
    # 1H CRT
    prev_1h_high = df_1h.iloc[-2]['high']
    prev_1h_low = df_1h.iloc[-2]['low']

    if curr_high > prev_1h_high and curr_close < prev_1h_high:
        event_key = f"{symbol}_STRAT7_1H_HIGH_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 1H High Swept!</b>\n\nAsset: <b>{symbol}</b>\n5m candle swept Previous 1H High ({prev_1h_high}) and re-entered the range."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_low < prev_1h_low and curr_close > prev_1h_low:
        event_key = f"{symbol}_STRAT7_1H_LOW_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 1H Low Swept!</b>\n\nAsset: <b>{symbol}</b>\n5m candle swept Previous 1H Low ({prev_1h_low}) and re-entered the range."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    # 4H CRT
    prev_4h_high = df_4h.iloc[-2]['high']
    prev_4h_low = df_4h.iloc[-2]['low']

    if curr_high > prev_4h_high and curr_close < prev_4h_high:
        event_key = f"{symbol}_STRAT7_4H_HIGH_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 4H High Swept!</b>\n\nAsset: <b>{symbol}</b>\n5m candle swept Previous 4H High ({prev_4h_high}) and re-entered the range."
            send_telegram_msg(msg)
            notified_events.add(event_key)

    if curr_low < prev_4h_low and curr_close > prev_4h_low:
        event_key = f"{symbol}_STRAT7_4H_LOW_CRT_{curr_5m['timestamp']}"
        if event_key not in notified_events:
            msg = f"🚨 <b>[STRATEGY 7] CRT Alert: 4H Low Swept!</b>\n\nAsset: <b>{symbol}</b>\n5m candle swept Previous 4H Low ({prev_4h_low}) and re-entered the range."
            send_telegram_msg(msg)
            notified_events.add(event_key)

def main():
    send_telegram_msg("🤖 <b>Trading Bot Started Successfully on Render!</b>\nMonitoring assets: PAXG/USDT, BTC, ETH, GBP, EUR.")
    print("Bot started...")
    
    while True:
        try:
            for symbol in SYMBOLS:
                analyze_symbol(symbol)
                time.sleep(1) # Prevent rate limiting
        except Exception as e:
            print(f"Error in main loop: {e}")
        
        # Check every 1 minute
        time.sleep(60)

if __name__ == "__main__":
    main()
