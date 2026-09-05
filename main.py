import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf

from datetime import datetime
import pytz
from flask import Flask, jsonify

app = Flask(__name__)

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN" ,"8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7476331970")

# ============================================================
# MARKETS
# ============================================================

SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "BTC": "BTC-USD",
    "GOLD": "GC=F"
}

# ============================================================
# SETTINGS
# ============================================================

VOLUME_MULTIPLIER = 1.20
EQ_TOLERANCE = 0.001
SWING_WINDOW = 2

# Prevent duplicate alerts
ALERT_CACHE = {}

# Sequential S2 -> S3 state
STRUCTURE_STATE = {}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if response.status_code != 200:
            print("Telegram error:", response.text)

        return response.status_code == 200

    except Exception as e:
        print("Telegram exception:", e)
        return False


def should_send_alert(symbol, strategy_id, candle_time):

    key = f"{symbol}_{strategy_id}"

    if ALERT_CACHE.get(key) == candle_time:
        return False

    ALERT_CACHE[key] = candle_time
    return True


# ============================================================
# MARKET HOURS
# ============================================================

def is_indian_market_open():

    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)

    if now.weekday() >= 5:
        return False

    start = now.replace(
        hour=9,
        minute=15,
        second=0,
        microsecond=0
    )

    end = now.replace(
        hour=15,
        minute=30,
        second=0,
        microsecond=0
    )

    return start <= now <= end


# ============================================================
# DATA HELPERS
# ============================================================

def clean_dataframe(df):

    if df is None or df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            if col == "Volume":
                df[col] = 0
            else:
                return pd.DataFrame()

    df = df.dropna(subset=[
        "Open",
        "High",
        "Low",
        "Close"
    ])

    return df


def download_data(ticker):

    try:

        df_5m = yf.download(
            ticker,
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=False
        )

        df_1h = yf.download(
            ticker,
            period="15d",
            interval="1h",
            progress=False,
            auto_adjust=False
        )

        df_1d = yf.download(
            ticker,
            period="2mo",
            interval="1d",
            progress=False,
            auto_adjust=False
        )

        df_5m = clean_dataframe(df_5m)
        df_1h = clean_dataframe(df_1h)
        df_1d = clean_dataframe(df_1d)

        return df_5m, df_1h, df_1d

    except Exception as e:

        print("Download error:", e)

        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame()
        )


# ============================================================
# SWING STRUCTURE
# ============================================================

def get_swing_points(df, window=2):

    highs = []
    lows = []

    if len(df) < window * 2 + 5:
        return highs, lows

    for i in range(window, len(df) - window):

        high = float(df["High"].iloc[i])
        low = float(df["Low"].iloc[i])

        left_highs = [
            float(df["High"].iloc[i - j])
            for j in range(1, window + 1)
        ]

        right_highs = [
            float(df["High"].iloc[i + j])
            for j in range(1, window + 1)
        ]

        left_lows = [
            float(df["Low"].iloc[i - j])
            for j in range(1, window + 1)
        ]

        right_lows = [
            float(df["Low"].iloc[i + j])
            for j in range(1, window + 1)
        ]

        if high > max(left_highs) and high > max(right_highs):
            highs.append(high)

        if low < min(left_lows) and low < min(right_lows):
            lows.append(low)

    return highs, lows


# ============================================================
# EQUAL HIGH / LOW
# ============================================================

def find_eqh_eql(df):

    swing_highs, swing_lows = get_swing_points(
        df,
        SWING_WINDOW
    )

    eqh = []
    eql = []

    for i in range(len(swing_highs)):

        for j in range(i + 1, len(swing_highs)):

            a = swing_highs[i]
            b = swing_highs[j]

            if a == 0:
                continue

            if abs(a - b) / a <= EQ_TOLERANCE:
                eqh.append(max(a, b))

    for i in range(len(swing_lows)):

        for j in range(i + 1, len(swing_lows)):

            a = swing_lows[i]
            b = swing_lows[j]

            if a == 0:
                continue

            if abs(a - b) / a <= EQ_TOLERANCE:
                eql.append(min(a, b))

    return list(set(eqh)), list(set(eql))


# ============================================================
# ALERT FORMAT
# ============================================================

def alert_header(strategy, symbol):

    return (
        f"🚨 *STRATEGY {strategy} ALERT*\n"
        f"📊 *{symbol}*\n"
        f"⏱️ *5M Confirmation*\n\n"
    )


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze_smc(symbol_name, ticker):

    # Indian market session
    if symbol_name in ["NIFTY 50", "SENSEX"]:

        if not is_indian_market_open():
            return

    try:

        df5, df1h, df1d = download_data(ticker)

        if (
            df5.empty
            or df1h.empty
            or df1d.empty
            or len(df5) < 30
            or len(df1h) < 10
            or len(df1d) < 3
        ):
            return

        # ----------------------------------------------------
        # USE LAST COMPLETED 5M CANDLE
        # ----------------------------------------------------

        current = df5.iloc[-1]
        candle = df5.iloc[-2]
        previous = df5.iloc[-3]

        candle_time = str(df5.index[-2])

        close = float(candle["Close"])
        high = float(candle["High"])
        low = float(candle["Low"])

        prev_close = float(previous["Close"])

        volume = float(candle["Volume"])

        recent_volume = df5["Volume"].iloc[-17:-2]

        avg_volume = float(
            recent_volume.mean()
        ) if len(recent_volume) else 0

        strong_volume = (
            avg_volume > 0
            and volume >= avg_volume * VOLUME_MULTIPLIER
        )

        # ----------------------------------------------------
        # PREVIOUS DAY HIGH / LOW
        # ----------------------------------------------------

        pdh = float(df1d["High"].iloc[-2])
        pdl = float(df1d["Low"].iloc[-2])

        # ====================================================
        # STRATEGY 1
        # PDH / PDL LIQUIDITY SWEEP
        # ====================================================

        # PDL sweep:
        # 5M low goes below PDL
        # but candle closes back above PDL

        pdl_sweep = (
            low < pdl
            and close >= pdl
        )

        # PDH sweep:
        # 5M high goes above PDH
        # but candle closes back below PDH

        pdh_sweep = (
            high > pdh
            and close <= pdh
        )

        if pdl_sweep:

            if should_send_alert(
                symbol_name,
                "S1_PDL",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(1, symbol_name)
                    +
                    "🟢 *PDL Liquidity Sweep Confirmed*\n\n"
                    f"• PDL: `{pdl:.2f}`\n"
                    f"• Sweep Low: `{low:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    "• Status: *Returned Inside Range*\n"
                    "• Bias: *Bullish* 📈"
                )

        if pdh_sweep:

            if should_send_alert(
                symbol_name,
                "S1_PDH",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(1, symbol_name)
                    +
                    "🔴 *PDH Liquidity Sweep Confirmed*\n\n"
                    f"• PDH: `{pdh:.2f}`\n"
                    f"• Sweep High: `{high:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    "• Status: *Returned Inside Range*\n"
                    "• Bias: *Bearish* 📉"
                )

        # ====================================================
        # STRUCTURE
        # ====================================================

        structure_df = df5.iloc[:-2]

        swing_highs, swing_lows = get_swing_points(
            structure_df,
            SWING_WINDOW
        )

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return

        last_high = swing_highs[-1]
        previous_high = swing_highs[-2]

        last_low = swing_lows[-1]
        previous_low = swing_lows[-2]

        # ====================================================
        # STRATEGY 2
        # CHoCH
        # ====================================================

        bullish_choch = (
            close > last_high
            and prev_close <= last_high
        )

        bearish_choch = (
            close < last_low
            and prev_close >= last_low
        )

        state = STRUCTURE_STATE.setdefault(
            symbol_name,
            {
                "choch": None,
                "choch_time": None
            }
        )

        if bullish_choch:

            state["choch"] = "BULLISH"
            state["choch_time"] = candle_time

            if should_send_alert(
                symbol_name,
                "S2_BULL_CHoCH",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(2, symbol_name)
                    +
                    "🟢 *Bullish CHoCH Confirmed*\n\n"
                    "Bearish → Bullish\n\n"
                    f"• Previous LH Broken: `{last_high:.2f}`\n"
                    f"• 5M Body Close: `{close:.2f}`\n"
                    "• Confirmation: *Body Close*\n"
                )

        if bearish_choch:

            state["choch"] = "BEARISH"
            state["choch_time"] = candle_time

            if should_send_alert(
                symbol_name,
                "S2_BEAR_CHoCH",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(2, symbol_name)
                    +
                    "🔴 *Bearish CHoCH Confirmed*\n\n"
                    "Bullish → Bearish\n\n"
                    f"• Previous HL Broken: `{last_low:.2f}`\n"
                    f"• 5M Body Close: `{close:.2f}`\n"
                    "• Confirmation: *Body Close*\n"
                )

        # ====================================================
        # STRATEGY 3
        # BOS AFTER CHoCH
        # ====================================================

        if state["choch"] == "BULLISH":

            bullish_bos = (
                close > last_high
                and prev_close <= last_high
                and candle_time != state["choch_time"]
            )

            if bullish_bos:

                if should_send_alert(
                    symbol_name,
                    "S3_BULL_BOS",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(3, symbol_name)
                        +
                        "🚀 *Bullish BOS Confirmed*\n\n"
                        f"• Previous HH Broken: `{last_high:.2f}`\n"
                        f"• 5M Body Close: `{close:.2f}`\n"
                        "• Direction: *Bullish* 📈"
                    )

        if state["choch"] == "BEARISH":

            bearish_bos = (
                close < last_low
                and prev_close >= last_low
                and candle_time != state["choch_time"]
            )

            if bearish_bos:

                if should_send_alert(
                    symbol_name,
                    "S3_BEAR_BOS",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(3, symbol_name)
                        +
                        "🚀 *Bearish BOS Confirmed*\n\n"
                        f"• Previous LL Broken: `{last_low:.2f}`\n"
                        f"• 5M Body Close: `{close:.2f}`\n"
                        "• Direction: *Bearish* 📉"
                    )

        # ====================================================
        # STRATEGY 4
        # PDH / PDL BREAKOUT + STRONG VOLUME
        # ====================================================

        pdl_breakout = (
            close < pdl
            and strong_volume
        )

        pdh_breakout = (
            close > pdh
            and strong_volume
        )

        if pdl_breakout:

            if should_send_alert(
                symbol_name,
                "S4_PDL_BREAK",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(4, symbol_name)
                    +
                    "🔴 *PDL Strong Volume Breakout*\n\n"
                    f"• PDL: `{pdl:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    f"• Volume: `{volume:.0f}`\n"
                    f"• Average Volume: `{avg_volume:.0f}`\n"
                    "• Direction: *Bearish* 📉"
                )

        if pdh_breakout:

            if should_send_alert(
                symbol_name,
                "S4_PDH_BREAK",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(4, symbol_name)
                    +
                    "🟢 *PDH Strong Volume Breakout*\n\n"
                    f"• PDH: `{pdh:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    f"• Volume: `{volume:.0f}`\n"
                    f"• Average Volume: `{avg_volume:.0f}`\n"
                    "• Direction: *Bullish* 📈"
                )

        # BOS after breakout
        if pdl_breakout and close < last_low:

            if should_send_alert(
                symbol_name,
                "S4_BEAR_BOS",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(4, symbol_name)
                    +
                    "📉 *Bearish BOS After PDL Breakout*\n\n"
                    f"• PDL: `{pdl:.2f}`\n"
                    f"• Previous LL: `{last_low:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`"
                )

        if pdh_breakout and close > last_high:

            if should_send_alert(
                symbol_name,
                "S4_BULL_BOS",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(4, symbol_name)
                    +
                    "📈 *Bullish BOS After PDH Breakout*\n\n"
                    f"• PDH: `{pdh:.2f}`\n"
                    f"• Previous HH: `{last_high:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`"
                )

        # ====================================================
        # STRATEGY 5
        # 1H / 4H EQUAL HIGH / LOW LIQUIDITY
        # ====================================================

        # Only COMPLETED 1H candles
        completed_1h = df1h.iloc[:-1]

        # Build 4H candles from 1H data
        completed_4h = (
            df1h.iloc[:-1]
            .resample("4h")
            .agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum"
            })
            .dropna()
        )

        eqh_1h, eql_1h = find_eqh_eql(completed_1h)
        eqh_4h, eql_4h = find_eqh_eql(completed_4h)

        # 5M candle must actually sweep HTF liquidity
        for level in eqh_1h:

            if high > level and close < level:

                if should_send_alert(
                    symbol_name,
                    "S5_1H_EQH",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(5, symbol_name)
                        +
                        "🔴 *1H Equal High Liquidity Swept*\n\n"
                        f"• EQH: `{level:.2f}`\n"
                        f"• 5M Sweep High: `{high:.2f}`\n"
                        "• Bias: *Bearish* 📉"
                    )

        for level in eql_1h:

            if low < level and close > level:

                if should_send_alert(
                    symbol_name,
                    "S5_1H_EQL",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(5, symbol_name)
                        +
                        "🟢 *1H Equal Low Liquidity Swept*\n\n"
                        f"• EQL: `{level:.2f}`\n"
                        f"• 5M Sweep Low: `{low:.2f}`\n"
                        "• Bias: *Bullish* 📈"
                    )

        for level in eqh_4h:

            if high > level and close < level:

                if should_send_alert(
                    symbol_name,
                    "S5_4H_EQH",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(5, symbol_name)
                        +
                        "🔴 *4H Equal High Liquidity Swept*\n\n"
                        f"• EQH: `{level:.2f}`\n"
                        f"• 5M Sweep High: `{high:.2f}`\n"
                        "• Bias: *Bearish* 📉"
                    )

        for level in eql_4h:

            if low < level and close > level:

                if should_send_alert(
                    symbol_name,
                    "S5_4H_EQL",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(5, symbol_name)
                        +
                        "🟢 *4H Equal Low Liquidity Swept*\n\n"
                        f"• EQL: `{level:.2f}`\n"
                        f"• 5M Sweep Low: `{low:.2f}`\n"
                        "• Bias: *Bullish* 📈"
                    )

        # ====================================================
        # STRATEGY 6
        # STRONG VOLUME BREAKOUT -> RETURN INSIDE PD RANGE
        # ====================================================

        pdl_breakout_previous = prev_close < pdl
        pdh_breakout_previous = prev_close > pdh

        pdl_return = (
            pdl_breakout_previous
            and close >= pdl
            and strong_volume
        )

        pdh_return = (
            pdh_breakout_previous
            and close <= pdh
            and strong_volume
        )

        if pdl_return:

            if should_send_alert(
                symbol_name,
                "S6_PDL_RETURN",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(6, symbol_name)
                    +
                    "🔄 *Price Returned Inside PDH–PDL Range*\n\n"
                    f"• PDL: `{pdl:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    "• Previous State: *Below PDL*\n"
                    "• Return Confirmed"
                )

        if pdh_return:

            if should_send_alert(
                symbol_name,
                "S6_PDH_RETURN",
                candle_time
            ):

                send_telegram_alert(
                    alert_header(6, symbol_name)
                    +
                    "🔄 *Price Returned Inside PDH–PDL Range*\n\n"
                    f"• PDH: `{pdh:.2f}`\n"
                    f"• 5M Close: `{close:.2f}`\n"
                    "• Previous State: *Above PDH*\n"
                    "• Return Confirmed"
                )

        # ====================================================
        # STRATEGY 7
        # CRT — ONLY 1H & 4H
        #
        # IMPORTANT:
        # User requested:
        # If 5M candle sweeps previous 1H/4H
        # liquidity -> alert immediately.
        #
        # No requirement for 5M return confirmation here.
        # ====================================================

        previous_1h = df1h.iloc[-2]

        h1_high = float(previous_1h["High"])
        h1_low = float(previous_1h["Low"])

        # Previous completed 4H candle
        if len(completed_4h) >= 2:

            previous_4h = completed_4h.iloc[-2]

            h4_high = float(previous_4h["High"])
            h4_low = float(previous_4h["Low"])

            # 1H HIGH sweep
            if high > h1_high:

                if should_send_alert(
                    symbol_name,
                    "S7_1H_HIGH",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(7, symbol_name)
                        +
                        "⏰ *1H CRT HIGH LIQUIDITY SWEPT*\n\n"
                        f"• Previous 1H High: `{h1_high:.2f}`\n"
                        f"• 5M Sweep High: `{high:.2f}`\n"
                        "• Sweep Detected by: *5M Candle*\n"
                    )

            # 1H LOW sweep
            if low < h1_low:

                if should_send_alert(
                    symbol_name,
                    "S7_1H_LOW",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(7, symbol_name)
                        +
                        "⏰ *1H CRT LOW LIQUIDITY SWEPT*\n\n"
                        f"• Previous 1H Low: `{h1_low:.2f}`\n"
                        f"• 5M Sweep Low: `{low:.2f}`\n"
                        "• Sweep Detected by: *5M Candle*\n"
                    )

            # 4H HIGH sweep
            if high > h4_high:

                if should_send_alert(
                    symbol_name,
                    "S7_4H_HIGH",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(7, symbol_name)
                        +
                        "⏰ *4H CRT HIGH LIQUIDITY SWEPT*\n\n"
                        f"• Previous 4H High: `{h4_high:.2f}`\n"
                        f"• 5M Sweep High: `{high:.2f}`\n"
                        "• Sweep Detected by: *5M Candle*\n"
                    )

            # 4H LOW sweep
            if low < h4_low:

                if should_send_alert(
                    symbol_name,
                    "S7_4H_LOW",
                    candle_time
                ):

                    send_telegram_alert(
                        alert_header(7, symbol_name)
                        +
                        "⏰ *4H CRT LOW LIQUIDITY SWEPT*\n\n"
                        f"• Previous 4H Low: `{h4_low:.2f}`\n"
                        f"• 5M Sweep Low: `{low:.2f}`\n"
                        "• Sweep Detected by: *5M Candle*\n"
                    )

    except Exception as e:

        print(
            f"Analysis error [{symbol_name}]: {e}"
        )


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route("/")
def home():

    return (
        "TRADE WITH ICT-DIPTANGAN "
        "SMC ALERT ENGINE ACTIVE"
    )


@app.route("/run")
def run_scan():

    results = []

    for name, ticker in SYMBOLS.items():

        try:

            analyze_smc(
                name,
                ticker
            )

            results.append({
                "symbol": name,
                "status": "scanned"
            })

        except Exception as e:

            results.append({
                "symbol": name,
                "status": "error",
                "error": str(e)
            })

    return jsonify({
        "status": "success",
        "markets": results
    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
