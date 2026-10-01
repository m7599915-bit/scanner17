#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SCANNER 17 V6 - PREDICTIVE EXECUTABLE ENTRY / EXIT
Built on Scanner 17 V5.2 Locked Ceiling Real Breakout.

هدف V6:
1) حفظ موتور تأیید V5.2
2) تشخیص زودترِ حرکت قبل از تشکیل صف خرید
3) جلوگیری از ورود دیرهنگام با NO-CHASE
4) تشخیص RE-ENTRY بعد از تخلیه صف و حفظ حمایت
5) هشدار خروج قبل از شکست کامل ساختار

نکته:
V6 «پیش‌بینی» آماری/ساختاری است، نه تضمین سود یا اجرای سفارش.
Trade Plan فقط محاسبه ریسک است.
"""

import requests
import time
import json
import os
import io
import contextlib
from datetime import datetime

URL = "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"

PARAMS = {
    "market": 0,
    "industrialGroup": "",
    "paperTypes[0]": 1,
    "paperTypes[1]": 2,
    "paperTypes[2]": 3,
    "paperTypes[3]": 4,
    "paperTypes[4]": 5,
    "paperTypes[5]": 6,
    "paperTypes[6]": 7,
    "paperTypes[7]": 8,
    "paperTypes[8]": 9,
    "showTraded": "false",
    "withBestLimits": "true",
    "hEven": 0,
    "RefID": 0,
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

WATCHLIST = [
    "ذوب", "خودرو", "وبصادر", "فولاد", "اهرم",
    "دارا يكم", "تمشك", "خزاميا", "تاپيكو",
    "دلقما", "شتران", "دكوثر", "خبهمن", "حفاري", "كوچين"
]

# -------------------- V5.2 SETTINGS --------------------
SCAN_INTERVAL = 120
STABLE_REQUIRED = 3
TIMEOUT = 20

STATE_FILE = os.path.expanduser("~/.scanner17_v6_state.json")
PRICE_LOG = os.path.expanduser("~/prices_10min_v6.txt")
ALERT_LOG = os.path.expanduser("~/scanner17_v6_alerts.txt")
EXPORT_FILE = "scanner17_v6_scan_10min.txt"
PRICE_LOG_INTERVAL = 600

MARKET_OPEN = (9, 0)
MARKET_CLOSE = (12, 30)
TRADING_WEEKDAYS = {0, 1, 2, 5, 6}

CAPITAL_TOMAN = 1_000_000
RISK_PERCENT = 10.0
STOP_PERCENT = 2.0
TARGET1_PERCENT = 3.0
TARGET2_PERCENT = 5.0

MIN_GROWTH = 0.50
MIN_SCORE = 75
MIN_DEPTH_RATIO = 2.0
MAX_ENTRY_DISTANCE_HIGH = 1.0

BREAKOUT_QUEUE_MIN_SCORE = 80
BREAKOUT_VOLUME_RATIO_MIN = 1.10
BREAKOUT_PRICE_STABILITY_MAX_DROP = 0.20
QUEUE_SUSPECT_RATIO = 0.20
HISTORY_SIZE = 8

QUEUE_MIN_SCORE = 70
QUEUE_STRONG_SCORE = 85
QUEUE_MIN_GROWTH = 1.0
QUEUE_PERSISTENCE_REQUIRED = 3

CEILING_DROP_INVALIDATE_PERCENT = 0.75
CEILING_NEAR_PERCENT = 0.50
POST_DROP_RECONFIRM_REQUIRED = 3

# -------------------- V6 PREDICTIVE SETTINGS --------------------
EARLY_ENTRY_SCORE_MIN = 80
PRE_ENTRY_SCORE_MIN = 65
EARLY_ENTRY_MAX_DISTANCE = 1.00
EARLY_ENTRY_MIN_GROWTH = 0.50
EARLY_ENTRY_MIN_DEPTH = 1.50
EARLY_ENTRY_MIN_ORDER_RATIO = 1.50
EARLY_ENTRY_MIN_HISTORY = 2
EARLY_ENTRY_PERSISTENCE_REQUIRED = 2

# برای جلوگیری از تعقیب جهش ناگهانی
MAX_RECENT_PRICE_JUMP = 0.80
MAX_LATE_CEILING_DISTANCE = 0.05

# RE-ENTRY
REENTRY_SCORE_MIN = 75
REENTRY_DISTANCE_MAX = 0.50
REENTRY_GROWTH_MIN = 1.00
REENTRY_DEPTH_MIN = 1.50
REENTRY_PERSISTENCE_REQUIRED = 2

# EXIT
EXIT_WARNING_SCORE = 40
EXIT_SERIOUS_SCORE = 65
EXIT_SCORE = 80


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
                if isinstance(s, dict):
                    return s
    except Exception:
        pass
    return {
        "session_date": "",
        "symbols": {},
        "alerts": [],
        "last_price_log": 0,
        "last_export": 0,
    }


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def symbol_state(state, symbol):
    if symbol not in state["symbols"]:
        state["symbols"][symbol] = {}
    return state["symbols"][symbol]


def prepare_session(state):
    d = datetime.now().strftime("%Y-%m-%d")
    if state.get("session_date") != d:
        state["session_date"] = d
        state["symbols"] = {}
        state["alerts"] = []
        state["last_price_log"] = 0
        state["last_export"] = 0
        save_state(state)


def market_open_now():
    n = datetime.now()
    if n.weekday() not in TRADING_WEEKDAYS:
        return False
    hhmm = (n.hour, n.minute)
    return MARKET_OPEN <= hhmm <= MARKET_CLOSE


def fetch_market():
    r = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        for key in ("marketwatch", "marketWatch", "data", "items", "closingPrice"):
            if isinstance(data.get(key), list):
                return data[key]
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def pick(x, *keys, default=0):
    for k in keys:
        if k in x and x[k] is not None:
            return x[k]
    return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def safe_int(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return default


def get_symbol(x):
    return str(pick(x, "lVal18AFC", "lVal18", "symbol", "symbolName", "name", default="")).strip()


def normalize_rows(x):
    rows = pick(x, "blDs", "bestLimits", "bestLimitsData", default=[])
    return rows if isinstance(rows, list) else []


def update_locked_ceiling(a, state):
    ss = symbol_state(state, a["symbol"])
    today = datetime.now().strftime("%Y-%m-%d")

    if ss.get("ceiling_date") != today:
        ss["ceiling_date"] = today
        ss["locked_ceiling"] = a["high"]
        ss["post_drop_locked"] = False
        ss["post_drop_reconfirm"] = 0

    old = safe_float(ss.get("locked_ceiling"), 0)
    if a["high"] > old:
        ss["locked_ceiling"] = a["high"]
        ss["post_drop_locked"] = False
        ss["post_drop_reconfirm"] = 0

    ceiling = safe_float(ss.get("locked_ceiling"), a["high"])
    a["locked_ceiling"] = ceiling

    if ceiling > 0:
        dist_locked = (ceiling - a["price"]) / ceiling * 100
    else:
        dist_locked = 999.0

    if dist_locked > CEILING_DROP_INVALIDATE_PERCENT:
        ss["post_drop_locked"] = True
        ss["post_drop_reconfirm"] = 0
    elif ss.get("post_drop_locked"):
        if dist_locked <= CEILING_NEAR_PERCENT:
            ss["post_drop_reconfirm"] = min(
                POST_DROP_RECONFIRM_REQUIRED,
                safe_int(ss.get("post_drop_reconfirm"), 0) + 1
            )
            if ss["post_drop_reconfirm"] >= POST_DROP_RECONFIRM_REQUIRED:
                ss["post_drop_locked"] = False
                ss["post_drop_reconfirm"] = 0

    a["post_drop_locked"] = bool(ss.get("post_drop_locked", False))
    a["post_drop_reconfirm"] = safe_int(ss.get("post_drop_reconfirm"), 0)


def analyze(x):
    symbol = get_symbol(x)
    price = safe_float(pick(x, "pmd", "last", "price"))
    yesterday = safe_float(pick(x, "py", "yesterday", "yesterdayPrice"))
    value = safe_float(pick(x, "qtc", "tradeValue", "value"))
    volume = safe_float(pick(x, "qtj", "volume"))
    trades = safe_int(pick(x, "ztt", "trades", "tradeCount"))
    high = safe_float(pick(x, "pmx", "high", "maxPrice"))
    low = safe_float(pick(x, "pmn", "low", "minPrice"))

    growth = ((price - yesterday) / yesterday * 100) if yesterday else 0.0
    distance_high = ((high - price) / high * 100) if high else 999.0

    rows = normalize_rows(x)
    buy5 = sell5 = buy1 = sell1 = 0.0
    for i, row in enumerate(rows[:5]):
        b = safe_float(pick(row, "qTitMeDem", "buyVolume", "buy", "demandVolume"))
        s = safe_float(pick(row, "qTitMeOf", "sellVolume", "sell", "offerVolume"))
        buy5 += b
        sell5 += s
        if i == 0:
            buy1, sell1 = b, s

    if buy1 > 0 and sell1 <= 0:
        order_ratio = 999.0
    elif sell1 > 0:
        order_ratio = buy1 / sell1
    else:
        order_ratio = 0.0

    if sell5 > 0:
        depth_ratio = buy5 / sell5
    elif buy5 > 0:
        depth_ratio = 999.0
    else:
        depth_ratio = 0.0

    score = 0

    if 1.5 <= growth <= 3.2:
        score += 20
    elif 0 < growth < 1.5:
        score += 5
    elif growth > 3.2:
        score += 10

    if order_ratio >= 100:
        score += 25
    elif order_ratio >= 20:
        score += 22
    elif order_ratio >= 10:
        score += 18
    elif order_ratio >= 5:
        score += 14
    elif order_ratio >= 2:
        score += 8
    elif order_ratio >= 1:
        score += 4

    if depth_ratio < 1:
        score = min(score, 60)
    elif depth_ratio < 2:
        score = min(score, 70)

    if distance_high <= 0.5:
        score += 20
    elif distance_high <= 1:
        score += 15
    elif distance_high <= 2:
        score += 8

    if depth_ratio >= 10:
        score += 15
    elif depth_ratio >= 5:
        score += 12
    elif depth_ratio >= 2:
        score += 8
    elif depth_ratio >= 1:
        score += 4

    if value >= 500_000_000_000:
        score += 20
    elif value >= 100_000_000_000:
        score += 10

    if depth_ratio >= 2 and score >= 75:
        signal = "🟢 شکست تأییدشده"
    elif score >= 60 and (depth_ratio >= 1 or buy1 > 0):
        signal = "🟡 شکست در حال تأیید"
    else:
        signal = "⚪ تحت نظر"

    is_queue = (buy1 > 0 and sell1 <= 0) or (buy5 > 0 and sell5 <= 0)

    queue_ratio = (buy1 / volume) if volume > 0 else 0.0
    queue_score = 0
    if is_queue:
        queue_score += 5
        if queue_ratio >= 2:
            queue_score += 25
        elif queue_ratio >= 1:
            queue_score += 20
        elif queue_ratio >= 0.5:
            queue_score += 14
        elif queue_ratio >= 0.2:
            queue_score += 8
        else:
            queue_score += 3

        if growth >= 3:
            queue_score += 15
        elif growth >= 2:
            queue_score += 12
        elif growth >= 1:
            queue_score += 9
        elif growth > 0:
            queue_score += 4

        if value >= 500_000_000_000:
            queue_score += 15
        elif value >= 100_000_000_000:
            queue_score += 11
        elif value >= 20_000_000_000:
            queue_score += 6
        elif value > 0:
            queue_score += 2

        if trades >= 3000:
            queue_score += 10
        elif trades >= 1000:
            queue_score += 8
        elif trades >= 300:
            queue_score += 5
        elif trades > 0:
            queue_score += 2

        if distance_high <= 0.2:
            queue_score += 10
        elif distance_high <= 0.5:
            queue_score += 8
        elif distance_high <= 1:
            queue_score += 5
        elif distance_high <= 2:
            queue_score += 2

    queue_score = min(100, queue_score)
    queue_suspect = is_queue and (queue_ratio < QUEUE_SUSPECT_RATIO or value <= 0)

    if sell5 <= 0:
        sell_pressure = "🟢 بسیار پایین"
    elif depth_ratio >= 3:
        sell_pressure = "🟢 پایین"
    elif depth_ratio >= 1:
        sell_pressure = "🟡 متوسط"
    elif depth_ratio >= 0.5:
        sell_pressure = "🟠 بالا"
    else:
        sell_pressure = "🔴 بسیار بالا"

    return {
        "symbol": symbol,
        "price": price,
        "yesterday": yesterday,
        "growth": growth,
        "value": value,
        "volume": volume,
        "trades": trades,
        "high": high,
        "low": low,
        "distance_high": distance_high,
        "buy1": buy1,
        "sell1": sell1,
        "buy5": buy5,
        "sell5": sell5,
        "order_ratio": order_ratio,
        "depth_ratio": depth_ratio,
        "score": min(100, score),
        "signal": signal,
        "is_buy_queue": is_queue,
        "queue_ratio": queue_ratio,
        "queue_score": queue_score,
        "queue_suspect": queue_suspect,
        "sell_pressure": sell_pressure,
    }


def history(ss):
    h = ss.get("history", [])
    return h if isinstance(h, list) else []


def update_history(a, state):
    ss = symbol_state(state, a["symbol"])
    h = history(ss)
    prev = h[-1] if h else None

    a["price_change_scan"] = 0.0
    a["score_change_scan"] = 0.0
    a["depth_change_scan"] = 0.0
    a["volume_change_scan"] = 0.0
    a["volume_ratio"] = None
    a["volume_acceleration"] = 0.0
    a["order_ratio_change"] = 0.0

    if prev:
        if safe_float(prev.get("price")) > 0:
            a["price_change_scan"] = (a["price"] / prev["price"] - 1) * 100
        a["score_change_scan"] = a["score"] - safe_float(prev.get("score"))
        old_depth = safe_float(prev.get("depth_ratio"))
        if old_depth > 0 and old_depth < 900 and a["depth_ratio"] < 900:
            a["depth_change_scan"] = a["depth_ratio"] - old_depth
        if safe_float(prev.get("volume")) > 0:
            a["volume_change_scan"] = (a["volume"] / prev["volume"] - 1) * 100
        old_or = safe_float(prev.get("order_ratio"))
        if old_or > 0 and old_or < 900 and a["order_ratio"] < 900:
            a["order_ratio_change"] = a["order_ratio"] - old_or

    previous_volumes = [
        safe_float(v.get("volume"))
        for v in h[-HISTORY_SIZE:]
        if safe_float(v.get("volume")) > 0
    ]
    if previous_volumes:
        avg = sum(previous_volumes) / len(previous_volumes)
        if avg > 0:
            a["volume_ratio"] = a["volume"] / avg

    if len(h) >= 2:
        old_vr = []
        for i in range(max(0, len(h) - 4), len(h)):
            hh = h[i]
            vols = [
                safe_float(z.get("volume"))
                for z in h[:i]
                if safe_float(z.get("volume")) > 0
            ]
            if vols and safe_float(hh.get("volume")) > 0:
                av = sum(vols[-HISTORY_SIZE:]) / len(vols[-HISTORY_SIZE:])
                if av > 0:
                    old_vr.append(safe_float(hh.get("volume")) / av)
        if old_vr and a["volume_ratio"] is not None:
            a["volume_acceleration"] = a["volume_ratio"] - old_vr[-1]

    rec = {
        "time": now_str(),
        "price": a["price"],
        "growth": a["growth"],
        "score": a["score"],
        "depth_ratio": a["depth_ratio"],
        "volume": a["volume"],
        "order_ratio": a["order_ratio"],
        "queue_score": a["queue_score"],
        "is_buy_queue": a["is_buy_queue"],
    }
    h.append(rec)
    ss["history"] = h[-HISTORY_SIZE:]


def update_persistence(a, state):
    ss = symbol_state(state, a["symbol"])
    prev_queue = bool(ss.get("queue_active", False))
    prev_breakout = safe_int(ss.get("breakout_consecutive"), 0)

    queue_consecutive = safe_int(ss.get("queue_consecutive"), 0)
    if a["is_buy_queue"]:
        queue_consecutive += 1
    else:
        queue_consecutive = 0
    a["queue_consecutive"] = queue_consecutive

    queue_events = []
    if a["is_buy_queue"] and not prev_queue:
        queue_events.append("🟢 ورود به صف خرید")
    elif not a["is_buy_queue"] and prev_queue:
        queue_events.append("🟠 خروج از صف خرید")

    queue_break_absorbed = (
        prev_queue and not a["is_buy_queue"]
        and a["distance_high"] <= 0.5
        and a["growth"] >= 1.0
        and a["value"] > 0
        and a["depth_ratio"] >= 1.0
    )
    if queue_break_absorbed:
        queue_events.append("🟢 تخلیه صف + حفظ حمایت")

    vr_ok = a["volume_ratio"] is not None and a["volume_ratio"] >= BREAKOUT_VOLUME_RATIO_MIN

    valid_now = (
        a["growth"] >= MIN_GROWTH
        and a["score"] >= MIN_SCORE
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and (a["depth_ratio"] >= MIN_DEPTH_RATIO or a["is_buy_queue"])
        and not a["queue_suspect"]
        and vr_ok
        and abs(a["price_change_scan"]) <= (BREAKOUT_PRICE_STABILITY_MAX_DROP + 0.50)
    )

    locked_ceiling_queue = (
        a["is_buy_queue"]
        and a["queue_score"] >= BREAKOUT_QUEUE_MIN_SCORE
        and queue_consecutive >= QUEUE_PERSISTENCE_REQUIRED
        and a["queue_ratio"] >= QUEUE_SUSPECT_RATIO
        and a["sell_pressure"] in ("🟢 بسیار پایین", "🟢 پایین", "🟡 متوسط")
        and vr_ok
    )

    real_now = (valid_now or locked_ceiling_queue) and not a.get("post_drop_locked", False)

    if real_now:
        breakout_consecutive = min(STABLE_REQUIRED, prev_breakout + 1)
    else:
        breakout_consecutive = 0

    a["breakout_consecutive"] = breakout_consecutive
    a["breakout_confirmed"] = breakout_consecutive >= STABLE_REQUIRED
    a["queue_strong"] = (
        a["is_buy_queue"]
        and a["queue_score"] >= QUEUE_STRONG_SCORE
        and queue_consecutive >= QUEUE_PERSISTENCE_REQUIRED
    )

    # persistence bonus
    qscore = a["queue_score"]
    if a["is_buy_queue"]:
        if queue_consecutive >= 3:
            qscore += 15
        elif queue_consecutive == 2:
            qscore += 7
        elif queue_consecutive == 1:
            qscore += 3
    a["queue_score_final"] = min(100, qscore)

    if queue_consecutive >= 3 and a["queue_score_final"] >= 80:
        a["queue_health"] = "🟢 سالم و پایدار"
    elif queue_consecutive >= 3 and a["queue_score_final"] >= 70:
        a["queue_health"] = "🟡 نسبتاً سالم"
    elif queue_consecutive >= 1 and a["queue_score_final"] >= 50:
        a["queue_health"] = "🟠 ضعیف/شکننده"
    else:
        a["queue_health"] = "🔴 بسیار ضعیف"

    # V5.2 authorization: deliberately retained and separate from V6 timing.
    a["entry_authorized_v52"] = (
        a["is_buy_queue"]
        and a["breakout_confirmed"]
        and a["score"] >= 75
        and a["queue_score_final"] >= 85
        and queue_consecutive >= 3
        and a["queue_health"] == "🟢 سالم و پایدار"
        and vr_ok
        and a["distance_high"] <= 1.0
        and a["growth"] >= 0.5
        and not a.get("post_drop_locked", False)
        and (a["sell5"] <= 0 or a["depth_ratio"] >= 1)
    )

    a["events"] = queue_events
    if a["breakout_confirmed"] and prev_breakout < STABLE_REQUIRED:
        a["events"].append("🟢 شکست پایدار V5.2 تأیید شد")
    if not real_now and prev_breakout > 0:
        a["events"].append("🔴 شکست V5.2 از اعتبار خارج شد")

    ss["queue_active"] = a["is_buy_queue"]
    ss["breakout_consecutive"] = breakout_consecutive
    ss["queue_consecutive"] = queue_consecutive

    if a["queue_strong"] and not ss.get("strong_queue_seen", False):
        a["events"].append("🟢 صف خرید قدرتمند")
    ss["strong_queue_seen"] = a["queue_strong"]

    return a


def demand_acceleration_score(a):
    h = history(symbol_state(CURRENT_STATE, a["symbol"]))
    if len(h) < 1:
        return 0

    score = 0
    # Buy power
    r = a["order_ratio"]
    if r >= 10:
        score += 20
    elif r >= 5:
        score += 17
    elif r >= 3:
        score += 14
    elif r >= 2:
        score += 11
    elif r >= 1.5:
        score += 8
    elif r >= 1:
        score += 4

    # Buy-power acceleration
    if a["order_ratio_change"] >= 5:
        score += 15
    elif a["order_ratio_change"] >= 2:
        score += 12
    elif a["order_ratio_change"] >= 1:
        score += 9
    elif a["order_ratio_change"] > 0:
        score += 5

    return min(score, 35)


def compute_early_entry(a, state):
    ss = symbol_state(state, a["symbol"])
    h = history(ss)

    score = 0
    reasons = []
    veto = []

    # 1. Distance to ceiling: ideally before exact ceiling.
    d = a["distance_high"]
    if d <= 0.20:
        score += 20
    elif d <= 0.50:
        score += 18
    elif d <= 0.80:
        score += 15
    elif d <= 1.00:
        score += 10
    elif d <= 1.50:
        score += 5

    # 2 + 3. Demand and acceleration
    r = a["order_ratio"]
    if r >= 10:
        score += 20
    elif r >= 5:
        score += 17
    elif r >= 3:
        score += 14
    elif r >= 2:
        score += 11
    elif r >= 1.5:
        score += 8
    elif r >= 1:
        score += 4

    acc = a["order_ratio_change"]
    if acc >= 5:
        score += 15
    elif acc >= 2:
        score += 12
    elif acc >= 1:
        score += 9
    elif acc > 0:
        score += 5

    # 4. Volume vs recent history
    vr = a["volume_ratio"]
    if vr is not None:
        if vr >= 1.20:
            score += 15
        elif vr >= 1.10:
            score += 13
        elif vr >= 1.05:
            score += 10
        elif vr >= 1.00:
            score += 7
        elif vr >= 0.95:
            score += 4
    elif a["volume_change_scan"] > 0:
        score += 5

    # 5. Volume acceleration
    va = a["volume_acceleration"]
    if va >= 0.15:
        score += 10
    elif va >= 0.08:
        score += 8
    elif va > 0:
        score += 5

    # 6. Depth
    dep = a["depth_ratio"]
    if dep >= 10:
        score += 10
    elif dep >= 5:
        score += 9
    elif dep >= 3:
        score += 8
    elif dep >= 2:
        score += 7
    elif dep >= 1:
        score += 4

    # 7. Sell pressure
    if a["sell_pressure"] == "🟢 بسیار پایین":
        score += 10
    elif a["sell_pressure"] == "🟢 پایین":
        score += 9
    elif a["sell_pressure"] == "🟡 متوسط":
        score += 6
    elif a["sell_pressure"] == "🟠 بالا":
        score += 2

    # Hard vetoes
    if a["is_buy_queue"]:
        veto.append("صف خرید تشکیل شده؛ خرید عادی دیگر قابل اتکا نیست")
    if a["sell_pressure"] == "🔴 بسیار بالا":
        veto.append("فشار فروش بسیار بالا")
    if a["sell_pressure"] == "🟠 بالا" and dep < 1:
        veto.append("فشار فروش بالا + عمق ضعیف")
    if a["post_drop_locked"]:
        veto.append("قفل سقف پس از افت فعال است")
    if a["price_change_scan"] > MAX_RECENT_PRICE_JUMP:
        veto.append("جهش اخیر بیش از حد؛ ریسک تعقیب قیمت")
    if a["growth"] < EARLY_ENTRY_MIN_GROWTH:
        veto.append("رشد برای ورود زودهنگام کافی نیست")
    if d > EARLY_ENTRY_MAX_DISTANCE:
        veto.append("فاصله از سقف بیش از محدوده ورود است")
    if a["order_ratio"] < EARLY_ENTRY_MIN_ORDER_RATIO and dep < EARLY_ENTRY_MIN_DEPTH:
        veto.append("قدرت تقاضای کافی وجود ندارد")

    if len(h) < EARLY_ENTRY_MIN_HISTORY:
        veto.append("سابقه کافی برای پیش‌بینی شتاب هنوز جمع نشده است")

    # Trend quality: score must not be deteriorating sharply.
    if len(h) >= 1 and a["score_change_scan"] <= -15:
        veto.append("امتیاز ساختاری در حال افت شدید است")

    a["early_entry_score"] = min(100, score)
    a["early_entry_veto"] = veto
    a["early_entry_reasons"] = reasons

    # Persistence of executable early-entry condition
    qualified = (
        a["early_entry_score"] >= EARLY_ENTRY_SCORE_MIN
        and not veto
        and not a["is_buy_queue"]
    )
    prev_early = safe_int(ss.get("early_entry_consecutive"), 0)
    if qualified:
        early_consecutive = min(EARLY_ENTRY_PERSISTENCE_REQUIRED, prev_early + 1)
    else:
        early_consecutive = 0

    a["early_entry_consecutive"] = early_consecutive
    a["early_entry_persistent"] = early_consecutive >= EARLY_ENTRY_PERSISTENCE_REQUIRED

    # Pre-entry can appear earlier than full entry.
    pre_ok = (
        a["early_entry_score"] >= PRE_ENTRY_SCORE_MIN
        and not a["is_buy_queue"]
        and not a["post_drop_locked"]
        and a["growth"] >= EARLY_ENTRY_MIN_GROWTH
        and d <= EARLY_ENTRY_MAX_DISTANCE
        and a["sell_pressure"] not in ("🔴 بسیار بالا",)
    )

    a["pre_entry"] = pre_ok
    a["early_entry"] = (
        qualified
        and a["early_entry_persistent"]
    )

    # No-chase is a hard output if queue has appeared or a late spike occurred.
    late = (
        a["is_buy_queue"]
        or a["price_change_scan"] > MAX_RECENT_PRICE_JUMP
        or (
            d <= MAX_LATE_CEILING_DISTANCE
            and r >= 20
            and a["price_change_scan"] > 0.25
        )
    )
    a["no_chase"] = bool(late)

    if a["no_chase"]:
        a["timing_signal"] = "🔴 NO-CHASE — ورود دیر شده"
    elif a["early_entry"]:
        a["timing_signal"] = "🟢 ورود زودهنگام — قابل اجرا"
    elif a["pre_entry"]:
        a["timing_signal"] = "🟡 PRE-ENTRY — آماده‌باش"
    else:
        a["timing_signal"] = "⚪ WATCH"

    ss["early_entry_consecutive"] = early_consecutive
    return a


def compute_reentry(a, state):
    ss = symbol_state(state, a["symbol"])
    prev_queue = bool(ss.get("queue_active_before", False))

    # queue_active_before is maintained from the prior completed scan.
    released = prev_queue and not a["is_buy_queue"]
    eligible = (
        released
        and not a["post_drop_locked"]
        and a["growth"] >= REENTRY_GROWTH_MIN
        and a["distance_high"] <= REENTRY_DISTANCE_MAX
        and a["score"] >= REENTRY_SCORE_MIN
        and a["depth_ratio"] >= REENTRY_DEPTH_MIN
        and a["sell_pressure"] in ("🟢 بسیار پایین", "🟢 پایین", "🟡 متوسط")
        and not a["queue_suspect"]
    )

    prev_re = safe_int(ss.get("reentry_consecutive"), 0)
    if eligible:
        re_c = min(REENTRY_PERSISTENCE_REQUIRED, prev_re + 1)
    else:
        re_c = 0

    a["reentry_consecutive"] = re_c
    a["reentry"] = eligible and re_c >= REENTRY_PERSISTENCE_REQUIRED

    if a["reentry"]:
        a["timing_signal"] = "🟢 RE-ENTRY — صف تخلیه شد و حمایت حفظ شده"
        a["no_chase"] = False

    ss["reentry_consecutive"] = re_c
    return a


def compute_exit(a, state):
    ss = symbol_state(state, a["symbol"])
    h = history(ss)
    prev = h[-2] if len(h) >= 2 else None

    ex = 0
    reasons = []

    if prev:
        old_score = safe_float(prev.get("score"))
        drop = old_score - a["score"]
        if drop >= 25:
            ex += 25
            reasons.append("افت شدید امتیاز ساختاری")
        elif drop >= 15:
            ex += 18
            reasons.append("افت معنی‌دار امتیاز ساختاری")
        elif drop >= 8:
            ex += 10
            reasons.append("افت امتیاز ساختاری")

        old_depth = safe_float(prev.get("depth_ratio"))
        if old_depth > 0 and old_depth < 900 and a["depth_ratio"] < 900:
            if a["depth_ratio"] <= old_depth * 0.50:
                ex += 15
                reasons.append("کاهش شدید عمق تقاضا")
            elif a["depth_ratio"] <= old_depth * 0.70:
                ex += 9
                reasons.append("کاهش عمق تقاضا")

        if a["price_change_scan"] <= -0.70:
            ex += 10
            reasons.append("افت سریع قیمت")
        elif a["price_change_scan"] <= -0.40:
            ex += 6
            reasons.append("افت کوتاه‌مدت قیمت")

        old_d = safe_float(prev.get("distance_high"))
        if old_d and a["distance_high"] - old_d >= 0.50:
            ex += 10
            reasons.append("فاصله از سقف در حال افزایش")

    if a["sell_pressure"] == "🔴 بسیار بالا":
        ex += 20
        reasons.append("فشار فروش بسیار بالا")
    elif a["sell_pressure"] == "🟠 بالا":
        ex += 12
        reasons.append("فشار فروش بالا")
    elif a["sell_pressure"] == "🟡 متوسط":
        ex += 5

    if ss.get("queue_active_before") and not a["is_buy_queue"]:
        if a["depth_ratio"] < 1.0 or a["score"] < 60:
            ex += 20
            reasons.append("تخلیه صف بدون حفظ ساختار")
        else:
            ex += 5
            reasons.append("تخلیه صف؛ نیاز به پایش")

    # Only track exit warnings after a bullish state was observed.
    tracked = bool(ss.get("bullish_tracking", False))
    a["exit_score"] = min(100, ex)
    a["exit_reasons"] = reasons
    a["exit_tracked"] = tracked

    if tracked and ex >= EXIT_SCORE:
        a["exit_signal"] = "🔴 EXIT — ضعف تأییدشده"
    elif tracked and ex >= EXIT_SERIOUS_SCORE:
        a["exit_signal"] = "🟠 EXIT SERIOUS — خروج جدی مورد توجه"
    elif tracked and ex >= EXIT_WARNING_SCORE:
        a["exit_signal"] = "🟡 EXIT WARNING — هشدار خروج"
    else:
        a["exit_signal"] = "🟢 HOLD / بدون هشدار خروج"

    # Update tracking if structure is bullish.
    bullish_now = (
        a["early_entry"]
        or a["pre_entry"]
        or a["breakout_confirmed"]
        or a["queue_strong"]
        or a["reentry"]
    )
    if bullish_now:
        ss["bullish_tracking"] = True

    return a


def finalize_state_flags(a, state):
    ss = symbol_state(state, a["symbol"])
    # Preserve current queue as "before" for the next scan.
    ss["queue_active_before"] = a["is_buy_queue"]
    ss["last_timing_signal"] = a["timing_signal"]
    ss["last_exit_signal"] = a["exit_signal"]
    ss["last_score"] = a["score"]
    ss["last_early_entry_score"] = a["early_entry_score"]


def trade_plan(a):
    if a["price"] <= 0:
        return None
    capital_rial = CAPITAL_TOMAN * 10
    risk_budget_rial = capital_rial * (RISK_PERCENT / 100)
    stop_price = a["price"] * (1 - STOP_PERCENT / 100)
    risk_per_share = a["price"] - stop_price
    if risk_per_share <= 0:
        return None
    max_shares_by_risk = int(risk_budget_rial / risk_per_share)
    max_shares_by_capital = int(capital_rial / a["price"])
    shares = max(0, min(max_shares_by_risk, max_shares_by_capital))
    target1 = a["price"] * (1 + TARGET1_PERCENT / 100)
    target2 = a["price"] * (1 + TARGET2_PERCENT / 100)
    return {
        "capital_toman": CAPITAL_TOMAN,
        "risk_budget_toman": CAPITAL_TOMAN * RISK_PERCENT / 100,
        "stop": stop_price,
        "target1": target1,
        "target2": target2,
        "shares": shares,
    }


def money_toman(v):
    return f"{v:,.0f}"


def log_alert(a, text):
    try:
        with open(ALERT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{now_str()} | {a['symbol']} | {text}\n")
    except Exception:
        pass


def show(a):
    print("-" * 78)
    print(f"نماد: {a['symbol']}")
    print(f"قیمت: {a['price']:,.0f} | رشد: {a['growth']:+.2f}%")
    print(f"ارزش معاملات: {money_toman(a['value'])}")
    print(f"حجم: {money_toman(a['volume'])} | تعداد معاملات: {a['trades']:,}")
    print(f"فاصله تا سقف: {a['distance_high']:.2f}% | سقف قفل‌شده: {a.get('locked_ceiling', 0):,.0f}")
    print(
        f"Buy1/Sell1: {a['buy1']:,.0f}/{a['sell1']:,.0f} | "
        f"نسبت: {a['order_ratio']:.2f}"
    )
    print(
        f"Buy5/Sell5: {a['buy5']:,.0f}/{a['sell5']:,.0f} | "
        f"عمق: {a['depth_ratio']:.2f}"
    )
    print(
        f"Volume Ratio: "
        f"{a['volume_ratio']:.2f}" if a["volume_ratio"] is not None
        else "Volume Ratio: ---"
    )
    print(
        f"تغییر قیمت/امتیاز/عمق: "
        f"{a['price_change_scan']:+.2f}% / "
        f"{a['score_change_scan']:+.0f} / "
        f"{a['depth_change_scan']:+.2f}"
    )
    print(f"امتیاز V5.2: {a['score']}/100 | سیگنال: {a['signal']}")
    print(
        f"Breakout: {a['breakout_consecutive']}/{STABLE_REQUIRED} | "
        f"Queue: {a['queue_consecutive']}/{QUEUE_PERSISTENCE_REQUIRED}"
    )
    print(
        f"Queue Score: {a['queue_score_final']}/100 | "
        f"Health: {a['queue_health']} | Queue/Volume: {a['queue_ratio']:.2f}"
    )
    print(f"فشار فروش: {a['sell_pressure']}")
    print(f"صف خرید: {'🟢 دارد' if a['is_buy_queue'] else '⚪ ندارد'}")
    print(f"مجوز V5.2: {'🟢 ورود مجاز' if a['entry_authorized_v52'] else '⚪ ورود مجاز نیست'}")

    print()
    print("========== V6 PREDICTIVE TIMING ==========")
    print(f"Early Entry Score: {a['early_entry_score']}/100")
    print(f"Early Entry Persistence: {a['early_entry_consecutive']}/{EARLY_ENTRY_PERSISTENCE_REQUIRED}")
    print(f"Timing: {a['timing_signal']}")

    if a["early_entry_veto"]:
        print("V6 موانع:")
        for x in a["early_entry_veto"]:
            print(f"  • {x}")

    print(
        f"RE-ENTRY: "
        f"{'🟢 فعال' if a['reentry'] else '⚪ فعال نیست'} "
        f"({a['reentry_consecutive']}/{REENTRY_PERSISTENCE_REQUIRED})"
    )

    print()
    print("========== EXIT ENGINE ==========")
    print(f"Exit Score: {a['exit_score']}/100")
    print(f"Exit: {a['exit_signal']}")
    if a["exit_reasons"]:
        for x in a["exit_reasons"]:
            print(f"  • {x}")

    # Trade plan is shown only for executable/potential states.
    if a["timing_signal"] in (
        "🟢 ورود زودهنگام — قابل اجرا",
        "🟡 PRE-ENTRY — آماده‌باش",
        "🟢 RE-ENTRY — صف تخلیه شد و حمایت حفظ شده",
    ):
        plan = trade_plan(a)
        if plan:
            print()
            print("========== TRADE PLAN (RISK MATH ONLY) ==========")
            print(f"سرمایه: {plan['capital_toman']:,.0f} تومان")
            print(f"بودجه ریسک: {plan['risk_budget_toman']:,.0f} تومان")
            print(f"حدضرر محاسباتی: {plan['stop']:,.0f}")
            print(f"هدف 1: {plan['target1']:,.0f}")
            print(f"هدف 2: {plan['target2']:,.0f}")
            print(f"حداکثر تعداد بر اساس ریسک/سرمایه: {plan['shares']:,}")
            print("⚠️ این بخش به‌تنهایی مجوز خرید یا تضمین امکان معامله نیست.")


def enrich(a, state):
    update_locked_ceiling(a, state)
    update_history(a, state)
    update_persistence(a, state)
    compute_early_entry(a, state)
    compute_reentry(a, state)
    compute_exit(a, state)
    finalize_state_flags(a, state)
    return a


CURRENT_STATE = None


def run_scan(state):
    global CURRENT_STATE
    CURRENT_STATE = state

    print("=" * 78)
    print("        SCANNER 17 V6 - PREDICTIVE EXECUTABLE ENTRY / EXIT")
    print("=" * 78)
    print(f"زمان اسکن: {now_str()}")

    market = fetch_market()
    print(f"تعداد نمادهای دریافت‌شده: {len(market)}")

    by_symbol = {}
    for x in market:
        s = get_symbol(x)
        if s:
            by_symbol[s] = x

    results = []
    for symbol in WATCHLIST:
        x = by_symbol.get(symbol)
        if not x:
            continue
        try:
            a = analyze(x)
            enrich(a, state)
            results.append(a)
        except Exception as e:
            print(f"خطا در تحلیل {symbol}: {e}")

    # Ranking: executable timing first, then predictive score, then V5.2 score.
    timing_rank = {
        "🟢 RE-ENTRY — صف تخلیه شد و حمایت حفظ شده": 5,
        "🟢 ورود زودهنگام — قابل اجرا": 4,
        "🟡 PRE-ENTRY — آماده‌باش": 3,
        "🔴 NO-CHASE — ورود دیر شده": 2,
        "⚪ WATCH": 1,
    }
    results.sort(
        key=lambda a: (
            timing_rank.get(a["timing_signal"], 0),
            a["early_entry_score"],
            a["score"],
            a["depth_ratio"],
        ),
        reverse=True,
    )

    for a in results:
        if (
            a["timing_signal"] != "⚪ WATCH"
            or a["score"] >= 75
            or a["queue_score_final"] >= 70
            or a["exit_score"] >= EXIT_WARNING_SCORE
        ):
            show(a)

    early = sum(a["early_entry"] for a in results)
    pre = sum(a["pre_entry"] for a in results)
    nochase = sum(a["no_chase"] for a in results)
    reentry = sum(a["reentry"] for a in results)
    exits = sum(a["exit_score"] >= EXIT_WARNING_SCORE for a in results)
    confirmed = sum(a["breakout_confirmed"] for a in results)
    queues = sum(a["queue_strong"] for a in results)
    auth = sum(a["entry_authorized_v52"] for a in results)

    print()
    print("=" * 78)
    print("                         V6 SUMMARY")
    print("=" * 78)
    print(f"🟢 ورود زودهنگام قابل اجرا: {early}")
    print(f"🟡 PRE-ENTRY: {pre}")
    print(f"🔴 NO-CHASE: {nochase}")
    print(f"🟢 RE-ENTRY: {reentry}")
    print(f"🟡 EXIT WARNING یا بالاتر: {exits}")
    print(f"V5.2 شکست پایدار: {confirmed}")
    print(f"V5.2 صف خرید قدرتمند: {queues}")
    print(f"V5.2 ورود مجاز: {auth}")
    print(f"کل واچ‌لیست: {len(WATCHLIST)}")
    print("=" * 78)

    return results


def write_prices(results):
    try:
        with open(PRICE_LOG, "a", encoding="utf-8") as f:
            for a in results:
                f.write(
                    f"{now_str()} | {a['symbol']} | "
                    f"{a['price']:.0f} | {a['growth']:+.2f}% | "
                    f"score={a['score']} | early={a['early_entry_score']} | "
                    f"timing={a['timing_signal']} | exit={a['exit_score']}\n"
                )
    except Exception:
        pass


def export_scan(text):
    try:
        path = os.path.expanduser("~/") + EXPORT_FILE
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def capture_run_scan(state):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = run_scan(state)
    text = buf.getvalue()
    print(text, end="")
    return results, text


def main():
    state = load_state()
    last_price_log = safe_float(state.get("last_price_log"), 0)
    last_export = safe_float(state.get("last_export"), 0)

    print("پایش هوشمند Scanner 17 V6 فعال شد")
    print(f"فاصله اسکن: {SCAN_INTERVAL} ثانیه")
    print(f"Early Entry: امتیاز {EARLY_ENTRY_SCORE_MIN}+ و پایداری {EARLY_ENTRY_PERSISTENCE_REQUIRED} اسکن")
    print("صف خرید = NO-CHASE مگر اینکه بعداً تخلیه و حمایت مجدداً تأیید شود.")
    print(f"State: {STATE_FILE}")

    while True:
        if not market_open_now():
            print(f"[{now_str()}] خارج از ساعت بازار؛ بررسی مجدد...")
            time.sleep(30)
            continue

        prepare_session(state)

        try:
            results, text = capture_run_scan(state)

            ts = time.time()
            if ts - last_price_log >= PRICE_LOG_INTERVAL:
                write_prices(results)
                last_price_log = ts
                state["last_price_log"] = ts
                print(f"📝 snapshot قیمت‌ها در {PRICE_LOG} ثبت شد.")

            if ts - last_export >= PRICE_LOG_INTERVAL:
                export_scan(text)
                last_export = ts
                state["last_export"] = ts

            save_state(state)

        except Exception as e:
            print(f"❌ خطا در اسکن: {e}")

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
