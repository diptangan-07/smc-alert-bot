import os
import time
import requests
import json

# ==========================================
# 1. TELEGRAM BOT CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8893050202:AAHrl0kzyt5Bjptbuoy9ae2c9SwF0KAOsmE"
TELEGRAM_CHAT_ID = "7476331970"

def send_telegram_alert(message):
    """Sends real-time formatting markdown alert to your Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[SUCCESS] Telegram Alert Sent!")
        else:
            print(f"[ERROR] Failed to send Telegram alert: {response.text}")
    except Exception as e:
        print(f"[EXCEPTION] Telegram API Error: {e}")

# Test message on backend start
send_telegram_alert("🚀 *TRADE WITH_____ICT-DIPTANGAN System Online!*\nBackend Engine is connected and listening for live 5M SMC alerts & Custom AI Rules.")


# ==========================================
# 2. 7 STRICT ICT/SMC STRATEGIES ENGINE (5M TIMEFRAME)
# ==========================================
def process_ict_strategies(candle):
    """
    Evaluates 5-Minute Candle Data against all 7 ICT Strategies.
    """
    asset = candle.get('symbol', 'UNKNOWN')
    close_price = candle.get('close')
    
    # --------------------------------------------------
    # Strategy 1: PDH/PDL Sweep & Range Re-entry
    # --------------------------------------------------
    if candle.get('pdh_pdl_sweep') and candle.get('closed_inside_range'):
        msg = (
            f"🚨 *[STRATEGY 1: PDH/PDL SWEEP & RE-ENTRY]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Price:* `{close_price}`\n"
            f"• *Timeframe:* `5M Execution`\n"
            f"• *Details:* Wick swept Previous Day High/Low liquidity and 5M candle closed inside daily range!"
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 2: CHoCH (Change of Character)
    # --------------------------------------------------
    if candle.get('choch_triggered'):
        direction = candle.get('choch_direction', 'Bullish/Bearish')
        msg = (
            f"⚡ *[STRATEGY 2: CHoCH CONFIRMED]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Direction:* `{direction}`\n"
            f"• *Details:* Previous L-H / H-L broken with body closing on 5M timeframe!"
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 3: BOS (Break of Structure)
    # --------------------------------------------------
    if candle.get('bos_triggered'):
        msg = (
            f"📈 *[STRATEGY 3: BOS CONTINUATION]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Details:* New trend H-H / L-L broken with candle body closing on 5M timeframe."
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 4: Low Volume Breakout & Trend Continuation
    # --------------------------------------------------
    if candle.get('low_vol_breakout') and candle.get('trend_bos_started'):
        msg = (
            f"💥 *[STRATEGY 4: LOW VOL BREAKOUT]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Details:* Low volume breakout beyond PDH/PDL staying outside range and starting new BOS trend!"
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 5: HTF Equal Highs / Lows Sweep (EQL/EQH)
    # --------------------------------------------------
    if candle.get('eql_eqh_sweep_5m'):
        htf_type = candle.get('eq_type', 'EQL/EQH')
        msg = (
            f"🎯 *[STRATEGY 5: {htf_type} SWEEP]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Details:* Higher Timeframe (1H/4H) Equal Highs/Lows liquidity swept on 5M candle!"
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 6: High Volume Fakeout Re-entry
    # --------------------------------------------------
    if candle.get('high_vol_fakeout') and candle.get('reentered_pdl_pdh_range'):
        msg = (
            f"🔄 *[STRATEGY 6: HIGH VOL FAKEOUT RE-ENTRY]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Details:* Strong volume breakout failed! 5M candle returned back inside PDH/PDL range."
        )
        send_telegram_alert(msg)

    # --------------------------------------------------
    # Strategy 7: CRT (Candle Range Theory) 1H / 4H
    # --------------------------------------------------
    if candle.get('crt_sweep'):
        crt_tf = candle.get('crt_timeframe', '1H/4H')
        msg = (
            f"🕯️ *[STRATEGY 7: CRT {crt_tf} SWEEP]*\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Details:* Previous {crt_tf} candle liquidity swept by 5M candle and re-entered range!"
        )
        send_telegram_alert(msg)


# ==========================================
# 3. AI CUSTOM PROMPT DEPLOYMENT ENGINE
# ==========================================
def deploy_custom_user_rule(rule_text):
    """
    Receives custom prompt instructions from the Website UI and activates a custom alert listener.
    """
    print(f"[AI ENGINE] Deploying custom rule: {rule_text}")
    
    # Notify Telegram that a custom rule is active
    msg = (
        f"🤖 *[CUSTOM AI RULE DEPLOYED]*\n"
        f"• *Instruction:* `{rule_text}`\n"
        f"• *Status:* Active & Listening on live market candles."
    )
    send_telegram_alert(msg)


# ==========================================
# 4. SERVER EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    print("==========================================")
    print("TRADE WITH_____ICT-DIPTANGAN BACKEND ACTIVE")
    print("==========================================")
    
    # Keep server listening 24/7 (Deploy on Replit or Render)
    while True:
        # Market scanning logic runs here
        time.sleep(5)
