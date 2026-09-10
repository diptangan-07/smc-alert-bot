import os
import time
import threading
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
import requests
from flask import Flask, jsonify

# ============================================================
# TELEGRAM
# IMPORTANT: Put the bot token in Render Environment Variables.
# Do NOT hard-code it in GitHub.
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8893050202:AAFbE8vF8-Z5Ci_axHanpJ7cZUQH89MTaOs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7476331970")

# Polling interval. Five-minute logic is evaluated after a new
# 5-minute candle becomes available.
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "35"))

# Minimum volume multiplier used by Strategy 4/6.
# Volume = current 5m volume compared with the rolling 20-candle mean.
MIN_VOLUME_MULTIPLIER = float(os.getenv("MIN_VOLUME_MULTIPLIER", "1.20"))

SYMBOLS = {
    "GOLD (PAXGUSD)": "PAXG-USD",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "GBPUSD": "GBPUSD=X",
    "JPYUSD": "JPYUSD=X",
    "EURUSD": "EURUSD=X",
    "SPX500": "^GSPC",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = Flask(__name__)

# Prevent two manual/automatic scans from running at the same time.
RUN_LOCK = threading.Lock()

# In-memory state. This is intentionally simple.
# For a multi-instance production system, move this state to a DB.
STATE = {name: {
    "last_5m": None,
    "last_daily_event": {},
    "last_1h_event": {},
    "last_4h_event": {},
    "last_bos_event": {},
    "last_range_return_event": {},
    "last_crt_event": {},
} for name in SYMBOLS}


def telegram_send(text: str):
    """Send one Telegram message."""
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN is missing.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as exc:
        logging.exception("Telegram error: %s", exc)


def fmt_price(x):
    if pd.isna(x):
        return "N/A"
    if abs(float(x)) >= 100:
        return f"{float(x):.2f}"
    return f"{float(x):.5f}"


def alert(symbol_name, strategy, message):
    text = (
        f"🔔 {strategy}\n"
        f"Asset: {symbol_name}\n"
        f"Timeframe: 5M trigger\n"
        f"{message}\n"
        f"⚠️ Trade with your risk."
    )
    logging.info(text.replace("\n", " | "))
    telegram_send(text)


def download_5m(symbol):
    """
    Yahoo Finance provides recent intraday candles. 5m data is used
    as the source of truth so higher-timeframe levels are evaluated
    from actual 5m candles.
    """
    df = yf.download(
        tickers=symbol,
        period="5d",
        interval="5m",
        auto_adjust=False,
        progress=False,
        prepost=False,
        threads=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        # yfinance can return a MultiIndex even for one ticker.
        df.columns = df.columns.get_level_values(0)

    needed = ["Open", "High", "Low", "Close", "Volume"]
    for col in needed:
        if col not in df.columns:
            return pd.DataFrame()

    df = df[needed].copy()
    df = df.dropna()

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    return df


def resample_ohlcv(df, rule):
    out = df.resample(rule, label="right", closed="right").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    return out.dropna()


def previous_day_levels(df):
    daily = resample_ohlcv(df, "1D")
    if len(daily) < 2:
        return None

    # Last completed daily candle, not today's developing candle.
    current_day = df.index[-1].date()
    completed = daily[daily.index.date < current_day]

    if completed.empty:
        return None

    prev = completed.iloc[-1]
    return float(prev["High"]), float(prev["Low"]), prev.name


def candle_body_inside(c, high_level, low_level):
    return float(c["Close"]) <= high_level and float(c["Close"]) >= low_level


def candle_closes_above(c, level):
    return float(c["Close"]) > level


def candle_closes_below(c, level):
    return float(c["Close"]) < level


def volume_is_strong(df):
    if len(df) < 21:
        return False
    current = float(df["Volume"].iloc[-1])
    avg = float(df["Volume"].iloc[-21:-1].mean())
    if avg <= 0:
        return False
    return current >= avg * MIN_VOLUME_MULTIPLIER


def local_swings(df, left=2, right=2):
    """
    Simple confirmed swing detector.
    A swing high/low is confirmed only after 'right' candles.
    """
    highs = []
    lows = []

    if len(df) < left + right + 1:
        return highs, lows

    h = df["High"].values
    l = df["Low"].values

    for i in range(left, len(df) - right):
        if h[i] == max(h[i-left:i+right+1]):
            highs.append(i)
        if l[i] == min(l[i-left:i+right+1]):
            lows.append(i)

    return highs, lows


def latest_two_swing_highs_lows(df):
    highs, lows = local_swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return None
    return highs[-2:], lows[-2:]


def detect_choch_bear_to_bull(df):
    """
    Strategy 2:
    After a PDH/PDL range-return setup, detect a bearish->bullish
    structure shift when a 5m candle BODY closes above the most
    recent confirmed bearish lower-high.

    We approximate bearish structure by a lower-high followed by a
    lower-low. The previous lower-high is the CHoCH level.
    """
    if len(df) < 30:
        return None

    highs, lows = local_swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return None

    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]

    # Latest swing high is a lower high than the preceding swing high.
    bearish = float(df["High"].iloc[h2]) < float(df["High"].iloc[h1])
    lower_low = float(df["Low"].iloc[l2]) < float(df["Low"].iloc[l1])

    if not (bearish and lower_low):
        return None

    level = float(df["High"].iloc[h2])
    c = df.iloc[-1]

    if float(c["Close"]) > level:
        return {
            "direction": "BULLISH",
            "level": level,
            "time": df.index[-1],
        }

    return None


def detect_bos_bull(df):
    """
    Strategy 3:
    After bullish CHoCH, a body close above the latest bullish
    swing high = bullish BOS.
    """
    if len(df) < 35:
        return None

    highs, lows = local_swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return None

    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]

    bullish_structure = (
        float(df["High"].iloc[h2]) > float(df["High"].iloc[h1])
        and float(df["Low"].iloc[l2]) > float(df["Low"].iloc[l1])
    )

    if not bullish_structure:
        return None

    level = float(df["High"].iloc[h2])
    c = df.iloc[-1]

    if float(c["Close"]) > level:
        return {
            "direction": "BULLISH",
            "level": level,
            "time": df.index[-1],
        }

    return None


def detect_bos_bear(df):
    """
    Bearish mirror of Strategy 3/4:
    lower-low + lower-high, then body close below latest lower-low.
    """
    if len(df) < 35:
        return None

    highs, lows = local_swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return None

    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]

    bearish_structure = (
        float(df["High"].iloc[h2]) < float(df["High"].iloc[h1])
        and float(df["Low"].iloc[l2]) < float(df["Low"].iloc[l1])
    )

    if not bearish_structure:
        return None

    level = float(df["Low"].iloc[l2])
    c = df.iloc[-1]

    if float(c["Close"]) < level:
        return {
            "direction": "BEARISH",
            "level": level,
            "time": df.index[-1],
        }

    return None


def strategy_1_daily_sweep_return(symbol_name, df):
    """
    Strategy 1:
    PDH/PDL liquidity sweep -> 5m candle closes back inside
    previous day's range.

    If price only touches/sweeps and does NOT return inside, no alert.
    If a 5m candle closes outside, we wait for a later 5m close back
    inside before alerting.
    """
    levels = previous_day_levels(df)
    if not levels or len(df) < 3:
        return

    pdh, pdl, day_key = levels
    c = df.iloc[-1]

    high_swept = float(c["High"]) >= pdh
    low_swept = float(c["Low"]) <= pdl
    inside = candle_body_inside(c, pdh, pdl)

    # Look back over recent 5m candles for the sweep.
    lookback = df.iloc[-12:-1]
    recent_high_sweep = (lookback["High"] >= pdh).any()
    recent_low_sweep = (lookback["Low"] <= pdl).any()

    key = f"{day_key}|{df.index[-1]}"

    if inside and recent_high_sweep:
        event_key = f"PDH_SWEEP_RETURN|{day_key}|{df.index[-1].date()}"
        if STATE[symbol_name]["last_daily_event"].get("s1_high") != event_key:
            STATE[symbol_name]["last_daily_event"]["s1_high"] = event_key
            alert(
                symbol_name,
                "STRATEGY 1 — PDH LIQUIDITY SWEEP + RETURN",
                f"PDH: {fmt_price(pdh)}\n"
                f"5M candle swept PDH and body closed back inside "
                f"the previous-day range."
            )

    if inside and recent_low_sweep:
        event_key = f"PDL_SWEEP_RETURN|{day_key}|{df.index[-1].date()}"
        if STATE[symbol_name]["last_daily_event"].get("s1_low") != event_key:
            STATE[symbol_name]["last_daily_event"]["s1_low"] = event_key
            alert(
                symbol_name,
                "STRATEGY 1 — PDL LIQUIDITY SWEEP + RETURN",
                f"PDL: {fmt_price(pdl)}\n"
                f"5M candle swept PDL and body closed back inside "
                f"the previous-day range."
            )


def strategy_2_choch(symbol_name, df):
    """
    Strategy 2 is armed only after Strategy 1 fired recently.
    This prevents random CHoCH alerts from being sent.
    """
    levels = previous_day_levels(df)
    if not levels:
        return

    pdh, pdl, day_key = levels
    last_event = max(
        STATE[symbol_name]["last_daily_event"].values(),
        default=""
    )

    if str(day_key) not in str(last_event):
        return

    result = detect_choch_bear_to_bull(df)
    if not result:
        return

    event_id = f"{day_key}|{df.index[-1]}"
    if STATE[symbol_name]["last_bos_event"].get("choch") == event_id:
        return

    STATE[symbol_name]["last_bos_event"]["choch"] = event_id

    alert(
        symbol_name,
        "STRATEGY 2 — BULLISH CHoCH",
        f"Previous bearish Lower High was broken.\n"
        f"5M candle BODY CLOSED above: {fmt_price(result['level'])}\n"
        f"Market structure shifted bearish → bullish."
    )


def strategy_3_bullish_bos(symbol_name, df):
    """
    Strategy 3:
    Once a CHoCH has been detected, wait for bullish BOS.
    """
    if "choch" not in STATE[symbol_name]["last_bos_event"]:
        return

    result = detect_bos_bull(df)
    if not result:
        return

    event_id = str(df.index[-1])
    if STATE[symbol_name]["last_bos_event"].get("bull_bos") == event_id:
        return

    STATE[symbol_name]["last_bos_event"]["bull_bos"] = event_id

    alert(
        symbol_name,
        "STRATEGY 3 — BULLISH BOS",
        f"New bullish Higher High was broken.\n"
        f"5M candle BODY CLOSED above: {fmt_price(result['level'])}\n"
        f"CHoCH → bullish BOS confirmed."
    )


def strategy_4_breakout_and_bos(symbol_name, df):
    """
    Strategy 4:
    PDH/PDL breakout with minimum volume, followed by continuation
    structure/BOS.

    The breakout alert fires only when a 5m BODY closes outside the
    PDH/PDL range AND volume is above the configured threshold.
    """
    levels = previous_day_levels(df)
    if not levels or len(df) < 25:
        return

    pdh, pdl, day_key = levels
    c = df.iloc[-1]

    if not volume_is_strong(df):
        return

    bullish_break = float(c["Close"]) > pdh
    bearish_break = float(c["Close"]) < pdl

    if bullish_break:
        eid = f"UPBREAK|{day_key}|{df.index[-1]}"
        if STATE[symbol_name]["last_range_return_event"].get("upbreak") != eid:
            STATE[symbol_name]["last_range_return_event"]["upbreak"] = eid
            alert(
                symbol_name,
                "STRATEGY 4 — PDH HIGH-VOLUME BREAKOUT",
                f"PDH: {fmt_price(pdh)}\n"
                f"5M BODY CLOSED above PDH with strong volume.\n"
                f"Price has broken out of the previous-day range."
            )

    if bearish_break:
        eid = f"DOWNBREAK|{day_key}|{df.index[-1]}"
        if STATE[symbol_name]["last_range_return_event"].get("downbreak") != eid:
            STATE[symbol_name]["last_range_return_event"]["downbreak"] = eid
            alert(
                symbol_name,
                "STRATEGY 4 — PDL HIGH-VOLUME BREAKDOWN",
                f"PDL: {fmt_price(pdl)}\n"
                f"5M BODY CLOSED below PDL with strong volume.\n"
                f"Price has broken down out of the previous-day range."
            )

    # Continuation BOS after breakout.
    up = STATE[symbol_name]["last_range_return_event"].get("upbreak")
    down = STATE[symbol_name]["last_range_return_event"].get("downbreak")

    if up:
        bos = detect_bos_bull(df)
        if bos:
            eid = f"UP_BOS|{day_key}|{df.index[-1]}"
            if STATE[symbol_name]["last_bos_event"].get("s4_up") != eid:
                STATE[symbol_name]["last_bos_event"]["s4_up"] = eid
                alert(
                    symbol_name,
                    "STRATEGY 4 — BULLISH CONTINUATION BOS",
                    f"After PDH breakout, bullish BOS confirmed.\n"
                    f"BODY CLOSED above: {fmt_price(bos['level'])}"
                )

    if down:
        bos = detect_bos_bear(df)
        if bos:
            eid = f"DOWN_BOS|{day_key}|{df.index[-1]}"
            if STATE[symbol_name]["last_bos_event"].get("s4_down") != eid:
                STATE[symbol_name]["last_bos_event"]["s4_down"] = eid
                alert(
                    symbol_name,
                    "STRATEGY 4 — BEARISH CONTINUATION BOS",
                    f"After PDL breakdown, bearish BOS confirmed.\n"
                    f"BODY CLOSED below: {fmt_price(bos['level'])}"
                )


def strategy_5_equal_high_low_sweep(symbol_name, df):
    """
    Strategy 5:
    1H and 4H equal-high/equal-low liquidity.
    The actual trigger must happen on a 5m candle.

    Equal liquidity is approximated using a tolerance based on price
    and the recent candle range. Two swing highs/lows within tolerance
    are treated as EQH/EQL.
    """
    for tf, rule in [("1H", "1H"), ("4H", "4H")]:
        ht = resample_ohlcv(df, rule)
        if len(ht) < 8:
            continue

        highs, lows = local_swings(ht, left=1, right=1)
        if len(highs) >= 2:
            a, b = highs[-2], highs[-1]
            p1 = float(ht["High"].iloc[a])
            p2 = float(ht["High"].iloc[b])
            tolerance = max(abs(p1) * 0.00015, float(df["Close"].iloc[-1]) * 0.00010)

            if abs(p1 - p2) <= tolerance:
                eqh = max(p1, p2)
                c = df.iloc[-1]
                if float(c["High"]) >= eqh:
                    eid = f"{tf}|EQH|{ht.index[b]}|{df.index[-1]}"
                    if STATE[symbol_name]["last_1h_event" if tf == "1H" else "last_4h_event"].get("eqh") != eid:
                        STATE[symbol_name]["last_1h_event" if tf == "1H" else "last_4h_event"]["eqh"] = eid
                        alert(
                            symbol_name,
                            f"STRATEGY 5 — {tf} EQH LIQUIDITY SWEEP",
                            f"Equal High liquidity around {fmt_price(eqh)} "
                            f"was swept by a 5M candle."
                        )

        if len(lows) >= 2:
            a, b = lows[-2], lows[-1]
            p1 = float(ht["Low"].iloc[a])
            p2 = float(ht["Low"].iloc[b])
            tolerance = max(abs(p1) * 0.00015, float(df["Close"].iloc[-1]) * 0.00010)

            if abs(p1 - p2) <= tolerance:
                eql = min(p1, p2)
                c = df.iloc[-1]
                if float(c["Low"]) <= eql:
                    eid = f"{tf}|EQL|{ht.index[b]}|{df.index[-1]}"
                    if STATE[symbol_name]["last_1h_event" if tf == "1H" else "last_4h_event"].get("eql") != eid:
                        STATE[symbol_name]["last_1h_event" if tf == "1H" else "last_4h_event"]["eql"] = eid
                        alert(
                            symbol_name,
                            f"STRATEGY 5 — {tf} EQL LIQUIDITY SWEEP",
                            f"Equal Low liquidity around {fmt_price(eql)} "
                            f"was swept by a 5M candle."
                        )


def strategy_6_range_reentry(symbol_name, df):
    """
    Strategy 6:
    A strong-volume PDH/PDL breakout happened, price continued outside,
    then a later 5m candle body closes back inside the PDH/PDL range.
    """
    levels = previous_day_levels(df)
    if not levels:
        return

    pdh, pdl, day_key = levels
    c = df.iloc[-1]

    inside = candle_body_inside(c, pdh, pdl)
    if not inside:
        return

    # Search for a strong-volume outside close earlier today.
    today = df[df.index.date == df.index[-1].date()]
    if len(today) < 5:
        return

    outside_up = today["Close"].gt(pdh)
    outside_down = today["Close"].lt(pdl)
    strong_idx = []

    for i in range(20, len(today)):
        row = today.iloc[i]
        avg = today["Volume"].iloc[max(0, i-20):i].mean()
        if avg <= 0:
            continue
        if float(row["Volume"]) >= avg * MIN_VOLUME_MULTIPLIER:
            if float(row["Close"]) > pdh or float(row["Close"]) < pdl:
                strong_idx.append(today.index[i])

    if not strong_idx:
        return

    last_break = strong_idx[-1]
    if last_break >= df.index[-1]:
        return

    eid = f"REENTRY|{day_key}|{df.index[-1]}"
    if STATE[symbol_name]["last_range_return_event"].get("reentry") == eid:
        return

    STATE[symbol_name]["last_range_return_event"]["reentry"] = eid

    alert(
        symbol_name,
        "STRATEGY 6 — PDH/PDL RANGE RE-ENTRY",
        f"Previous-day range: {fmt_price(pdl)} → {fmt_price(pdh)}\n"
        f"After a high-volume breakout and continuation outside the range, "
        f"a 5M candle BODY closed back inside the range."
    )


def crt_check(symbol_name, df, tf_name, rule):
    """
    Strategy 7 — CRT:
    Build 1H/4H candles from 5m data.
    Trigger only when a 5m candle sweeps the previous completed
    HTF candle's high/low.

    If it sweeps and the 5m candle body closes back inside the
    previous HTF candle's range -> alert.
    If it simply breaks and remains outside -> no CRT return alert.
    """
    ht = resample_ohlcv(df, rule)
    if len(ht) < 3:
        return

    # Last completed HTF candle. The final resampled candle can still
    # be developing, so use the one before it.
    prev = ht.iloc[-2]
    prev_high = float(prev["High"])
    prev_low = float(prev["Low"])
    prev_time = ht.index[-2]

    c = df.iloc[-1]
    swept_high = float(c["High"]) >= prev_high
    swept_low = float(c["Low"]) <= prev_low
    returned = candle_body_inside(c, prev_high, prev_low)

    if not (swept_high or swept_low):
        return

    # User requested 5m sweep as the actual trigger.
    direction = "HIGH" if swept_high else "LOW"
    eid = f"{tf_name}|{direction}|{prev_time}|{df.index[-1]}"

    state_key = "last_1h_event" if tf_name == "1H" else "last_4h_event"
    bucket = STATE[symbol_name][state_key]

    if not returned:
        # No CRT alert when price breaks and stays outside.
        return

    if bucket.get("crt") == eid:
        return

    bucket["crt"] = eid

    alert(
        symbol_name,
        f"STRATEGY 7 — {tf_name} CRT LIQUIDITY SWEEP",
        f"Previous {tf_name} candle high: {fmt_price(prev_high)}\n"
        f"Previous {tf_name} candle low: {fmt_price(prev_low)}\n"
        f"A 5M candle swept the previous {tf_name} liquidity "
        f"and its BODY CLOSED back inside the previous {tf_name} range."
    )


def process_symbol(name, ticker):
    df = download_5m(ticker)
    if df.empty or len(df) < 50:
        logging.warning("%s: insufficient 5m data", name)
        return "insufficient_data"

    # Only process the newest completed 5m candle once.
    last_time = df.index[-1]
    if STATE[name]["last_5m"] == str(last_time):
        return "already_processed"

    STATE[name]["last_5m"] = str(last_time)

    try:
        strategy_1_daily_sweep_return(name, df)
        strategy_2_choch(name, df)
        strategy_3_bullish_bos(name, df)
        strategy_4_breakout_and_bos(name, df)
        strategy_5_equal_high_low_sweep(name, df)
        strategy_6_range_reentry(name, df)
        crt_check(name, df, "1H", "1H")
        crt_check(name, df, "4H", "4H")
    except Exception:
        logging.exception("Strategy error for %s", name)
        return "strategy_error"

    return "processed"


def run_scan_once():
    """Run one scan across every configured asset."""
    results = {}
    with RUN_LOCK:
        for name, ticker in SYMBOLS.items():
            try:
                results[name] = process_symbol(name, ticker)
            except Exception as exc:
                logging.exception("Unexpected error for %s", name)
                results[name] = f"error: {exc}"
    return results


def monitor_loop():
    logging.info("Bot monitor started for: %s", ", ".join(SYMBOLS))
    while True:
        for name, ticker in SYMBOLS.items():
            try:
                process_symbol(name, ticker)
            except Exception:
                logging.exception("Unexpected error for %s", name)

        time.sleep(POLL_SECONDS)


@app.get("/")
def home():
    return jsonify({
        "status": "running",
        "bot": "SMC/ICT 5M alert bot",
        "assets": list(SYMBOLS.keys()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/run")
def run_now():
    """Manual one-time scan endpoint."""
    if not RUN_LOCK.acquire(blocking=False):
        return jsonify({"status": "busy", "message": "A scan is already running."}), 429

    try:
        results = {}
        for name, ticker in SYMBOLS.items():
            try:
                results[name] = process_symbol(name, ticker)
            except Exception as exc:
                logging.exception("Manual scan error for %s", name)
                results[name] = f"error: {exc}"

        return jsonify({
            "status": "ok",
            "message": "Manual scan completed.",
            "results": results,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        RUN_LOCK.release()


@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    worker = threading.Thread(target=monitor_loop, daemon=True)
    worker.start()

    # Render Web Service requires the app to listen on $PORT.
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
