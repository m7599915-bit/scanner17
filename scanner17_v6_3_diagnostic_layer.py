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

# ================= V6 — Universe + Predictive + Options =================
# V5.2 فقط WATCHLIST را تحلیل می‌کرد. V6 به‌صورت پیش‌فرض کل سهام بورس و
# فرابورس را از MarketWatch می‌گیرد و سپس فیلترهای V5.2 را اعمال می‌کند.
SCAN_ALL_STOCKS = True
INCLUDE_BASE_MARKET = False
STOCK_YVALS = {"300", "303"}  # سهم بورس + سهم فرابورس
if INCLUDE_BASE_MARKET:
    STOCK_YVALS.add("309")

# واچ‌لیست قدیمی فقط برای «اولویت نمایش» حفظ شده است، نه محدودیت اسکن.
WATCHLIST = [
    "ذوب", "خودرو", "وبصادر", "فولاد", "اهرم", "دارا يكم", "تمشك",
    "خزاميا", "تاپيكو", "دلقما", "شتران", "دكوثر", "خبهمن", "حفاري", "كوچين",
]

# نوع‌های شناخته‌شده اختیار در داده‌های TSETMC.
OPTION_YVALS = {"311", "312", "321", "322", "323", "600", "601", "602"}
OPTION_SCAN_ENABLED = True
OPTION_MAX_CONTRACTS = 80
OPTION_MIN_VALUE_RIAL = 0
OPTION_MIN_SCORE = 55
OPTION_ENTRY_MIN_SCORE = 70
OPTION_ENTRY_MIN_LIQUIDITY = 60
OPTION_MAX_PREMIUM_OVER_THEO_PCT = 25
OPTION_MIN_ABS_DELTA = 0.20
OPTION_MAX_ABS_DELTA = 0.85
OPTION_STATE_FILE = os.path.expanduser("~/.scanner17_v6_2_options.json")

# ================= V6.2 — Option Mapping / Diagnostics =================
# تطبیق اختیار با سهم پایه در سه سطح: قطعی، alias معتبر، و ناموفق.
# هیچ تطبیق احتمالی/حدسی اجازه ورود نمی‌گیرد.
OPTION_MAPPING_MIN_CONFIDENCE = 0.95
OPTION_MAPPING_ALIASES = {
    "دارایکم": ["دارایکم", "دارا1", "داراییکم"],
    "اهرم": ["اهرم"],
    "خودرو": ["خودرو"],
    "فولاد": ["فولاد"],
    "فملی": ["فملی"],
    "شستا": ["شستا"],
    "شتران": ["شتران"],
    "ذوب": ["ذوب"],
    "وبصادر": ["وبصادر"],
    "خزامیا": ["خزامیا"],
    "تاپیکو": ["تاپیکو"],
    "دلقما": ["دلقما"],
    "دکوثر": ["دکوثر"],
    "خبهمن": ["خبهمن"],
    "حفاری": ["حفاری"],
    "کوچین": ["کوچین"],
}
OPTION_DIAGNOSTIC_MAX = 12


# پیش‌بینی کوتاه‌مدت/ورود قبل از صف؛ این امتیاز «پیش‌بینی قطعی» نیست.
PREDICTIVE_ENABLED = True
PREDICTIVE_MIN_SCORE = 70
PREDICTIVE_TOP_N = 15
PREDICTIVE_PREQUEUE_BONUS = 12
PREDICTIVE_CEILING_BONUS = 18
PREDICTIVE_MOMENTUM_BONUS = 15
PREDICTIVE_VOLUME_BONUS = 15
PREDICTIVE_ORDER_BONUS = 15
PREDICTIVE_DEPTH_BONUS = 15

# ================= تنظیمات پایش =================
SCAN_INTERVAL = 120
STABLE_REQUIRED = 3
REQUEST_TIMEOUT = 20
STATE_FILE = os.path.expanduser("~/.scanner17_v6_2_state.json")
PRICE_LOG_FILE = os.path.expanduser("~/prices_10min.txt")
ALERT_LOG_FILE = os.path.expanduser("~/scanner17_alerts.txt")
PRICE_LOG_INTERVAL = 600

# ================= خروجی اسکن در Downloads =================
# در Termux معمولاً بعد از اجرای termux-setup-storage این مسیر وجود دارد.
# فایل هر 10 دقیقه با آخرین خروجی کامل اسکن جایگزین می‌شود.
DOWNLOADS_CANDIDATES = [
    os.path.expanduser("~/storage/downloads"),
    "/sdcard/Download",
    "/storage/emulated/0/Download",
]
SCAN_TEXT_FILENAME = "scanner17_v6_2_scan_10min.txt"
SCAN_EXPORT_INTERVAL = 600

# ================= ساعات رسمی پایش بازار =================
# معاملات عادی سهام: شنبه تا چهارشنبه، 09:00 تا 12:30
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 12
MARKET_CLOSE_MINUTE = 30
# در datetime.weekday(): شنبه=5، یکشنبه=6، دوشنبه=0، سه‌شنبه=1، چهارشنبه=2
TRADING_WEEKDAYS = {0, 1, 2, 5, 6}
WAIT_OUTSIDE_MARKET = 30

# مدیریت سرمایه
CAPITAL_TOMAN = 1_000_000
RISK_PERCENT = 10.0
STOP_LOSS_PERCENT = 2.0
TARGET1_PERCENT = 3.0
TARGET2_PERCENT = 5.0

# فیلترهای شکست
MIN_GROWTH = 0.50
MIN_SCORE = 75
MIN_DEPTH_RATIO = 2.0
MAX_ENTRY_DISTANCE_HIGH = 1.0
# شروط سخت‌گیرانه شکست واقعی
BREAKOUT_QUEUE_MIN_SCORE = 80
BREAKOUT_VOLUME_RATIO_MIN = 1.10
BREAKOUT_PRICE_STABILITY_MAX_DROP = 0.20
QUEUE_SUSPECT_RATIO = 0.20
HISTORY_SIZE = 8

# تشخیص و امتیازدهی صف خرید
QUEUE_MIN_SCORE = 70
QUEUE_STRONG_SCORE = 85
QUEUE_MIN_GROWTH = 1.0
QUEUE_PERSISTENCE_REQUIRED = STABLE_REQUIRED

# ================= قفل سقف جلسه =================
CEILING_DROP_INVALIDATE_PERCENT = 0.75
CEILING_NEAR_PERCENT = 0.50
POST_DROP_RECONFIRM_REQUIRED = 3


def update_locked_ceiling(a, state):
    """قفل سقف جلسه؛ پس از افت معنادار، ورود تا تأیید مجدد ممنوع است."""
    name = a["name"]
    item = state.get(name, {})
    locked = f(item.get("locked_ceiling", 0))

    # سقف فقط به سمت بالا به‌روزرسانی می‌شود.
    if a["high"] > locked:
        locked = a["high"]
        item["locked_ceiling_source"] = "new_session_high"

    if locked <= 0:
        locked = a["high"]

    distance = (
        ((locked - a["last"]) / a["last"]) * 100
        if a["last"] > 0 and locked > 0 else 999
    )

    # افت بیش از حد => قفل بازیابی.
    if distance > CEILING_DROP_INVALIDATE_PERCENT:
        item["post_drop_locked"] = True
        item["post_drop_reconfirm"] = 0
    elif item.get("post_drop_locked"):
        if distance <= CEILING_NEAR_PERCENT:
            item["post_drop_reconfirm"] = min(
                int(item.get("post_drop_reconfirm", 0)) + 1,
                POST_DROP_RECONFIRM_REQUIRED
            )
            if item["post_drop_reconfirm"] >= POST_DROP_RECONFIRM_REQUIRED:
                item["post_drop_locked"] = False
        else:
            item["post_drop_reconfirm"] = 0

    a["locked_ceiling"] = locked
    a["locked_ceiling_distance"] = distance
    a["post_drop_locked"] = bool(item.get("post_drop_locked", False))
    a["post_drop_reconfirm"] = int(item.get("post_drop_reconfirm", 0))
    state[name] = item
    return a


def f(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def get_market():
    r = requests.get(
        URL,
        params=PARAMS,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("marketwatch", [])


def find_symbol(data, name):
    for x in data:
        if x.get("lva", "").strip() == name:
            return x
    return None


def analyze(x):
    name = x.get("lva", "").strip()
    last = f(x.get("pmd"))
    if last <= 0:
        return None

    yesterday = f(x.get("py"))
    value = f(x.get("qtc"))
    volume = f(x.get("qtj"))
    trades = f(x.get("ztt"))
    high = f(x.get("pmx"))
    low = f(x.get("pmn"))

    growth = ((last - yesterday) / yesterday) * 100 if yesterday > 0 else 0
    distance_high = ((high - last) / last) * 100 if high > 0 and last > 0 else 999

    books = x.get("blDs", [])
    buy1 = sell1 = buy5 = sell5 = 0

    for row in books[:5]:
        buy5 += f(row.get("qmd"))
        sell5 += f(row.get("qmo"))

    if books:
        buy1 = f(books[0].get("qmd"))
        sell1 = f(books[0].get("qmo"))

    if buy1 > 0 and sell1 > 0:
        order_ratio = buy1 / sell1
    elif buy1 > 0:
        order_ratio = 999
    else:
        order_ratio = 0

    depth_ratio = buy5 / sell5 if buy5 > 0 and sell5 > 0 else 0

    score = 0

    if 1.5 <= growth <= 3.2:
        score += 20
    elif 0 < growth < 1.5:
        score += 5
    elif growth > 3.2:
        score += 10

    if buy1 > 0 and sell1 <= 0:
        score += 5
    elif sell1 > 0:
        if order_ratio >= 100:
            order_score = 25
        elif order_ratio >= 20:
            order_score = 22
        elif order_ratio >= 10:
            order_score = 18
        elif order_ratio >= 5:
            order_score = 14
        elif order_ratio >= 2:
            order_score = 8
        elif order_ratio >= 1:
            order_score = 4
        else:
            order_score = 0

        if depth_ratio < 1:
            order_score = min(order_score, 5)
        elif depth_ratio < 2:
            order_score = min(order_score, 12)

        score += order_score

    if 0 <= distance_high <= 0.5:
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

    # توجه: sell5 == 0 دیگر به‌هیچ‌وجه به‌معنی «شکست نامعتبر» نیست.
    # صفر بودن سمت فروش می‌تواند نشانه صف خرید باشد و باید جداگانه ارزیابی شود.
    if depth_ratio >= MIN_DEPTH_RATIO and score >= MIN_SCORE:
        status = "🟢 شکست تأییدشده"
    elif score >= 60 and (depth_ratio >= 1 or buy1 > 0):
        status = "🟡 شکست در حال تأیید"
    else:
        status = "⚪ تحت نظر"

    # تشخیص صف خرید: وجود تقاضای ردیف اول/عمق بالا همراه با نبود عرضه.
    queue_detected = buy1 > 0 and sell1 <= 0
    queue_depth_detected = buy5 > 0 and sell5 <= 0
    is_buy_queue = queue_detected or queue_depth_detected

    # امتیاز مستقل صف خرید؛ وجود صف به‌تنهایی امتیاز بالایی نمی‌دهد.
    queue_score = 0
    queue_reasons = []

    if is_buy_queue:
        queue_reasons.append("صف خرید")
        queue_score += 5

        # قدرت صف نسبت به حجم معاملات روز
        queue_volume_ratio = buy5 / volume if volume > 0 else 0
        if queue_volume_ratio >= 2:
            queue_score += 25
            queue_reasons.append(f"صف/حجم {queue_volume_ratio:.1f}x قوی")
        elif queue_volume_ratio >= 1:
            queue_score += 20
            queue_reasons.append(f"صف/حجم {queue_volume_ratio:.1f}x خوب")
        elif queue_volume_ratio >= 0.50:
            queue_score += 14
            queue_reasons.append(f"صف/حجم {queue_volume_ratio:.1f}x متوسط")
        elif queue_volume_ratio >= 0.20:
            queue_score += 8
            queue_reasons.append(f"صف/حجم {queue_volume_ratio:.1f}x ضعیف")
        else:
            queue_score += 3
            queue_reasons.append(f"صف/حجم {queue_volume_ratio:.1f}x بسیار ضعیف")

        # رشد قیمت
        if growth >= 3:
            queue_score += 15
        elif growth >= 2:
            queue_score += 12
        elif growth >= 1:
            queue_score += 9
        elif growth > 0:
            queue_score += 4

        # ارزش معاملات
        if value >= 500_000_000_000:
            queue_score += 15
        elif value >= 100_000_000_000:
            queue_score += 11
        elif value >= 20_000_000_000:
            queue_score += 6
        elif value > 0:
            queue_score += 2

        # تعداد معاملات
        if trades >= 3000:
            queue_score += 10
        elif trades >= 1000:
            queue_score += 8
        elif trades >= 300:
            queue_score += 5
        elif trades > 0:
            queue_score += 2

        # فاصله از سقف
        if 0 <= distance_high <= 0.2:
            queue_score += 10
        elif distance_high <= 0.5:
            queue_score += 8
        elif distance_high <= 1:
            queue_score += 5
        elif distance_high <= 2:
            queue_score += 2

        # order_ratio=999 ناشی از sell1=0 عمداً امتیاز اضافه نمی‌دهد.
        # نبود عرضه در ردیف اول به‌تنهایی به معنی صف سالم و قوی نیست.

    queue_score = min(int(round(queue_score)), 100)

    # صف مشکوک: وجود تقاضا بدون پشتوانه کافی حجم/کیفیت.
    queue_volume_ratio = (buy5 / volume) if volume > 0 else 0
    queue_suspect = (
        is_buy_queue
        and (queue_volume_ratio < QUEUE_SUSPECT_RATIO or value <= 0)
    )

    if is_buy_queue:
        queue_signal = "🟢 صف خرید"
    else:
        queue_signal = "⚪ بدون صف خرید"

    reasons = []
    if distance_high > 2:
        reasons.append(f"فاصله سقف {distance_high:.2f}%")
    if score < 50:
        reasons.append(f"امتیاز {score}/100")

    return {
        "name": name,
        "last": last,
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
        "score": score,
        "status": status,
        "signal_type": status,
        "signal_reason": " | ".join(reasons) if reasons else "تأیید کامل نشده",
        "is_buy_queue": is_buy_queue,
        "queue_signal": queue_signal,
        "queue_score": queue_score,
        "queue_volume_ratio": queue_volume_ratio,
        "queue_suspect": queue_suspect,
        "queue_reason": " | ".join(queue_reasons) if queue_reasons else "صف خرید تشخیص داده نشد",
    }


def get_downloads_dir():
    """پیدا کردن پوشه Downloads قابل‌استفاده در Termux/Android."""
    for path in DOWNLOADS_CANDIDATES:
        try:
            if os.path.isdir(path) and os.access(path, os.W_OK):
                return path
        except Exception:
            pass
    return None


def should_export_scan():
    """بررسی می‌کند آیا زمان ذخیره خروجی کامل اسکن در Downloads رسیده است."""
    downloads = get_downloads_dir()
    if not downloads:
        return False

    path = os.path.join(downloads, SCAN_TEXT_FILENAME)
    try:
        if not os.path.exists(path):
            return True
        return (time.time() - os.path.getmtime(path)) >= SCAN_EXPORT_INTERVAL
    except Exception:
        return True


def export_scan_text(text):
    """آخرین خروجی کامل اسکن را هر 10 دقیقه در Downloads ذخیره می‌کند."""
    if not text or not should_export_scan():
        return False

    downloads = get_downloads_dir()
    if not downloads:
        return False

    path = os.path.join(downloads, SCAN_TEXT_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as file:
            file.write(text.rstrip() + "\n")
        print(f"📥 خروجی کامل اسکن هر 10 دقیقه در Downloads ذخیره شد: {path}")
        return True
    except Exception as e:
        print("خطا در ذخیره خروجی اسکن در Downloads:")
        print(e)
        return False


def should_log_prices():
    """بررسی می‌کند آیا زمان ثبت snapshot ده‌دقیقه‌ای رسیده است."""
    try:
        if not os.path.exists(PRICE_LOG_FILE):
            return True

        mtime = os.path.getmtime(PRICE_LOG_FILE)
        return (time.time() - mtime) >= PRICE_LOG_INTERVAL
    except Exception:
        return True


def log_prices(data):
    """ثبت snapshot؛ در V6 نمادهای واچ‌لیست + شمارش کل سهام ثبت می‌شوند."""
    if not should_log_prices():
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = ["", "=" * 70, f"SNAPSHOT V6.2 | {now}", "=" * 70]
    stock_count = 0
    option_count = 0
    for x in data:
        yval = str(x.get("yval", "")).strip()
        if yval in STOCK_YVALS:
            stock_count += 1
        if yval in OPTION_YVALS:
            option_count += 1
    lines.append(f"سهام بورس/فرابورس دریافت‌شده: {stock_count}")
    lines.append(f"قراردادهای اختیار دریافت‌شده: {option_count}")
    lines.append("-- واچ‌لیست اولویت‌دار --")
    for name in WATCHLIST:
        x = find_symbol(data, name)
        if x is None:
            lines.append(f"{name}: پیدا نشد")
        else:
            last = f(x.get("pmd"))
            lines.append(f"{name}: {last:,.0f}" if last > 0 else f"{name}: قیمت نامعتبر")
    lines.append("=" * 70)
    try:
        with open(PRICE_LOG_FILE, "a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        print("خطا در ثبت prices_10min.txt:")
        print(e)
        return False

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def is_trading_day(now=None):
    now = now or datetime.now()
    return now.weekday() in TRADING_WEEKDAYS


def market_status(now=None):
    """وضعیت بازار را بر اساس ساعت محلی دستگاه تعیین می‌کند."""
    now = now or datetime.now()

    if not is_trading_day(now):
        return "closed_weekend"

    current_minutes = now.hour * 60 + now.minute
    open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
    close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE

    if current_minutes < open_minutes:
        return "before_open"
    if current_minutes >= close_minutes:
        return "after_close"
    return "open"


def seconds_until_next_open(now=None):
    """تعداد ثانیه تا شروع جلسه معاملاتی بعدی."""
    now = now or datetime.now()
    candidate = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )

    if is_trading_day(now) and now < candidate:
        return max(1, int((candidate - now).total_seconds()))

    # از روز بعد جلو می‌رویم تا به یک روز معاملاتی برسیم.
    from datetime import timedelta
    candidate = candidate + timedelta(days=1)
    while candidate.weekday() not in TRADING_WEEKDAYS:
        candidate += timedelta(days=1)

    return max(1, int((candidate - now).total_seconds()))


def prepare_new_session(state, now=None):
    """پاک‌سازی state جلسه قبل برای نمادهایی که واقعاً در همان جلسه دیده می‌شوند."""
    now = now or datetime.now()
    session_date = now.strftime("%Y-%m-%d")
    if state.get("_session_date") == session_date:
        return state, False

    for key, item in list(state.items()):
        if not isinstance(item, dict) or key.startswith("_"):
            continue
        item["history"] = []
        item["consecutive_valid"] = 0
        item["stable"] = False
        item["queue_consecutive"] = 0
        item["queue_strong"] = False
        item["locked_ceiling"] = 0
        item["locked_ceiling_source"] = ""
        item["locked_ceiling_distance"] = None
        item["post_drop_reconfirm"] = 0
        item["post_drop_locked"] = False

    state["_session_date"] = session_date
    return state, True

def save_state(state):
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    os.replace(temp_file, STATE_FILE)


def append_alert(message):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ALERT_LOG_FILE, "a", encoding="utf-8") as file:
            file.write(f"[{now}] {message}\\n")
    except Exception as e:
        print("خطا در ثبت هشدار:")
        print(e)


def risk_plan(price):
    if price <= 0:
        return {}

    # RISK_PERCENT سقف ریسک مجاز از کل سرمایه است؛
    # اما ریسک واقعی بر اساس اندازه موقعیت و حدضرر محاسبه می‌شود.
    risk_budget_toman = CAPITAL_TOMAN * RISK_PERCENT / 100
    stop = price * (1 - STOP_LOSS_PERCENT / 100)
    target1 = price * (1 + TARGET1_PERCENT / 100)
    target2 = price * (1 + TARGET2_PERCENT / 100)

    # قیمت‌های API ریال هستند؛ سرمایه کاربر تومان، بنابراین به ریال تبدیل می‌شود.
    capital_rial = CAPITAL_TOMAN * 10
    risk_budget_rial = risk_budget_toman * 10

    risk_per_share = max(price - stop, 1)
    shares_by_risk = int(risk_budget_rial / risk_per_share)
    shares_by_capital = int(capital_rial / price)
    shares = max(0, min(shares_by_risk, shares_by_capital))

    position_rial = shares * price
    position_toman = position_rial / 10
    max_loss_rial = shares * risk_per_share
    max_loss_toman = max_loss_rial / 10
    actual_risk_percent = (
        (max_loss_toman / CAPITAL_TOMAN) * 100
        if CAPITAL_TOMAN > 0 else 0
    )
    position_percent_of_capital = (
        (position_toman / CAPITAL_TOMAN) * 100
        if CAPITAL_TOMAN > 0 else 0
    )

    return {
        "capital_toman": CAPITAL_TOMAN,
        "risk_budget_toman": risk_budget_toman,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "shares": shares,
        "position_rial": position_rial,
        "position_toman": position_toman,
        "position_percent_of_capital": position_percent_of_capital,
        "max_loss_rial": max_loss_rial,
        "max_loss_toman": max_loss_toman,
        "actual_risk_percent": actual_risk_percent,
        "risk_budget_percent": RISK_PERCENT,
        "stop_loss_percent": STOP_LOSS_PERCENT,
    }


def update_history(a, state):
    name = a["name"]
    old = state.get(name, {})
    history = old.get("history", [])

    previous = history[-1] if history else None

    current_volume = a.get("volume", 0)
    previous_volume = previous.get("volume", 0) if previous else 0
    delta_volume = max(0, current_volume - previous_volume) if previous else 0
    history.append({
        "last": a["last"],
        "growth": a["growth"],
        "score": a["score"],
        "depth_ratio": a["depth_ratio"],
        "volume": current_volume,
        "delta_volume": delta_volume,
        "queue_score": a.get("queue_score", 0),
        "is_buy_queue": a.get("is_buy_queue", False),
        "time": datetime.now().strftime("%H:%M:%S")
    })
    history = history[-HISTORY_SIZE:]

    if previous:
        a["price_change_since_scan"] = (
            (a["last"] - previous["last"]) / previous["last"] * 100
            if previous["last"] > 0 else 0
        )
        a["score_change_since_scan"] = a["score"] - previous["score"]
    else:
        a["price_change_since_scan"] = 0
        a["score_change_since_scan"] = 0

    prior_deltas = [h.get("delta_volume", 0) for h in history[:-1]
                    if h.get("delta_volume", 0) > 0]
    avg_delta_volume = (sum(prior_deltas) / len(prior_deltas)) if prior_deltas else 0

    # حجم روزانه qTotTran5J تجمعی است؛ برای تشخیص «ورود حجم» باید ΔVolume را
    # بین دو اسکن مقایسه کنیم، نه حجم تجمعی فعلی را با حجم تجمعی قبلی.
    if avg_delta_volume > 0 and delta_volume > 0:
        a["volume_ratio"] = delta_volume / avg_delta_volume
        a["volume_ratio_valid"] = True
    else:
        a["volume_ratio"] = None
        a["volume_ratio_valid"] = False

    a["delta_volume"] = delta_volume
    a["avg_delta_volume"] = avg_delta_volume
    # سازگاری با خروجی‌های قبلی: avg_volume همچنان موجود می‌ماند.
    prior_volumes = [h["volume"] for h in history[:-1] if h.get("volume", 0) > 0]
    a["avg_volume"] = sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0
    a["history"] = history

    return a


def update_persistence(a, state):
    name = a["name"]
    old = state.get(name, {})
    history = a.get("history", [])
    previous = history[-2] if len(history) >= 2 else None

    # تغییرات هر اسکن
    if previous:
        a["price_change_since_scan"] = (
            (a["last"] - previous["last"]) / previous["last"] * 100
            if previous["last"] > 0 else 0
        )
        a["score_change_since_scan"] = a["score"] - previous["score"]
        a["queue_score_change_since_scan"] = (
            a["queue_score"] - previous.get("queue_score", 0)
        )
    else:
        a["price_change_since_scan"] = 0
        a["score_change_since_scan"] = 0
        a["queue_score_change_since_scan"] = 0

    # ماندگاری صف خرید
    previous_queue = bool(old.get("is_buy_queue", False))
    if a["is_buy_queue"]:
        queue_consecutive = min(
            int(old.get("queue_consecutive", 0)) + 1,
            QUEUE_PERSISTENCE_REQUIRED
        )
    else:
        queue_consecutive = 0

    # رویداد ورود/خروج صف
    if a["is_buy_queue"] and not previous_queue:
        queue_event = "🟢 ورود به صف خرید"
    elif previous_queue and not a["is_buy_queue"]:
        queue_event = "🔴 خروج از صف خرید"
    else:
        queue_event = ""

    # شکسته‌شدن صف و معامله‌شدن روی سقف:
    # اگر در اسکن قبلی صف بوده و اکنون صف برداشته شده، اما قیمت همچنان
    # حداکثر 0.5% با سقف فاصله دارد، آن را به‌عنوان «جذب عرضه روی سقف»
    # ثبت می‌کنیم، نه شکست منفی.
    queue_break_absorbed = (
        previous_queue
        and not a["is_buy_queue"]
        and a["distance_high"] <= 0.5
        and a["growth"] >= QUEUE_MIN_GROWTH
        and a["value"] > 0
    )
    if queue_break_absorbed:
        queue_event = "🟢 صف شکسته و عرضه روی سقف جذب شد"

    # پایداری شکست واقعی: صف خرید به‌تنهایی مجوز شمارش شکست نیست.
    # برای هر گام تأیید باید امتیاز پایه، نزدیکی به سقف و قدرت دفتر سفارش
    # برقرار باشد؛ در صورت صف خرید، کیفیت و حجم آن نیز باید کافی باشد.
    queue_volume_ratio = (a["buy5"] / a["volume"]) if a["volume"] > 0 else 0
    queue_quality_ok = (
        not a["is_buy_queue"]
        or (
            a.get("queue_score", 0) >= BREAKOUT_QUEUE_MIN_SCORE
            and queue_volume_ratio >= QUEUE_SUSPECT_RATIO
        )
    )
    volume_ratio = a.get("volume_ratio")
    volume_ok = (
        a.get("volume_ratio_valid", False)
        and volume_ratio is not None
        and volume_ratio >= BREAKOUT_VOLUME_RATIO_MIN
    )
    valid_now = (
        a["growth"] >= MIN_GROWTH
        and a["score"] >= MIN_SCORE
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and (a["depth_ratio"] >= MIN_DEPTH_RATIO or a["is_buy_queue"])
        and queue_quality_ok
        and volume_ok
    )

    # تأیید ویژه شکست برای سهمی که روی سقف قفل شده و صف خرید پایدار دارد.
    # در این حالت ثابت ماندن قیمت طبیعی است و نباید شمارنده شکست را صفر نگه دارد.
    locked_ceiling_queue = (
        a["is_buy_queue"]
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and a["growth"] >= MIN_GROWTH
        and a.get("queue_score", 0) >= BREAKOUT_QUEUE_MIN_SCORE
        and queue_consecutive >= QUEUE_PERSISTENCE_REQUIRED
        and queue_volume_ratio >= QUEUE_SUSPECT_RATIO
        and a.get("sell_pressure") in ("🟢 بسیار پایین", "🟢 پایین", "🟡 متوسط")
        and volume_ok
    )

    previous_count = int(old.get("consecutive_valid", 0))
    ceiling_reconfirm_ok = (
        not a.get("post_drop_locked", False)
        or a.get("post_drop_reconfirm", 0) >= POST_DROP_RECONFIRM_REQUIRED
    )
    # V5.2 — دروازه واحد «شکست واقعی»
    # هر واحد از شمارنده 1/3، 2/3 و 3/3 فقط با همین دروازه ثبت می‌شود.
    # هیچ رویداد صف، امتیاز بالا یا وضعیت WATCH به‌تنهایی شمارنده را جلو نمی‌برد.
    real_breakout_now = (valid_now or locked_ceiling_queue) and ceiling_reconfirm_ok
    confirmation_valid = real_breakout_now
    consecutive = (
        min(previous_count + 1, STABLE_REQUIRED)
        if real_breakout_now else 0
    )
    a["real_breakout_now"] = real_breakout_now

    a["locked_ceiling_queue"] = locked_ceiling_queue
    a["consecutive_valid"] = consecutive
    a["stable"] = consecutive >= STABLE_REQUIRED

    # صف قدرتمند فقط وقتی اعلام می‌شود که امتیاز بالا و ماندگاری کافی داشته باشد.
    a["queue_strong"] = (
        a["is_buy_queue"]
        and a["queue_score"] >= QUEUE_STRONG_SCORE
        and queue_consecutive >= QUEUE_PERSISTENCE_REQUIRED
    )
    a["queue_consecutive"] = queue_consecutive
    a["queue_event"] = queue_event
    a["queue_break_absorbed"] = queue_break_absorbed

    # تفسیر فشار فروش؛ sell5=0 به معنی عمق صفر نیست، بلکه یعنی عرضه ثبت‌شده نداریم.
    if a["sell5"] <= 0:
        a["sell_pressure"] = "🟢 بسیار پایین"
    elif a["buy5"] / a["sell5"] >= 3:
        a["sell_pressure"] = "🟢 پایین"
    elif a["buy5"] / a["sell5"] >= 1:
        a["sell_pressure"] = "🟡 متوسط"
    elif a["buy5"] / a["sell5"] >= 0.5:
        a["sell_pressure"] = "🟠 بالا"
    else:
        a["sell_pressure"] = "🔴 بسیار بالا"

    # پایداری بخشی از کیفیت نهایی صف است.
    if a["is_buy_queue"]:
        persistence_bonus = {1: 3, 2: 7, 3: 15}.get(queue_consecutive, 0)
        a["queue_score"] = min(a["queue_score"] + persistence_bonus, 100)

        if queue_consecutive >= 3 and a["queue_score"] >= 80:
            a["queue_health"] = "🟢 سالم و پایدار"
        elif a["queue_score"] >= 70:
            a["queue_health"] = "🟡 نسبتاً سالم"
        elif a["queue_score"] >= 50:
            a["queue_health"] = "🟠 ضعیف/شکننده"
        else:
            a["queue_health"] = "🔴 بسیار ضعیف"
    else:
        a["queue_health"] = "⚪ بدون صف"

    # «صف هست» با «اجازه ورود» عمداً جداست.
    # ورود فقط با کیفیت مناسب + پایداری صف + تأیید شکست مجاز است.
    # مجوز ورود یک مرحله مستقل از «شکست تأییدشده» است.
    # تمام شروط سخت‌گیرانه باید همزمان برقرار باشند.
    entry_authorized = (
        a["is_buy_queue"]
        and consecutive >= STABLE_REQUIRED
        and a["score"] >= MIN_SCORE
        and a["queue_score"] >= QUEUE_STRONG_SCORE
        and queue_consecutive >= QUEUE_PERSISTENCE_REQUIRED
        and a.get("queue_health") == "🟢 سالم و پایدار"
        and a.get("volume_ratio_valid", False)
        and a.get("volume_ratio") is not None
        and a["volume_ratio"] >= BREAKOUT_VOLUME_RATIO_MIN
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and a["growth"] >= MIN_GROWTH
        and not a.get("post_drop_locked", False)
        and (a["sell5"] <= 0 or a["buy5"] / a["sell5"] >= 1.0)
    )
    a["entry_authorized"] = entry_authorized
    if entry_authorized:
        a["entry_permission"] = "🟢 ورود مجاز — ENTRY AUTHORIZED"
    elif a["is_buy_queue"]:
        a["entry_permission"] = "⚪ ورود ممنوع — در انتظار تأیید"
    else:
        a["entry_permission"] = "⚪ ورود ممنوع — صف وجود ندارد"

    # چهار وضعیت نهایی
    # V5.2: «شکست در حال تأیید» از «شکست واقعی در حال شمارش» جداست.
    # کاندید می‌تواند ضعیف‌تر از دروازه شکست واقعی باشد، اما شمارنده 1/3
    # فقط با real_breakout_now افزایش می‌یابد. رشد منفی/صفر نیز ممنوع است.
    confirmation_candidate = (
        a["growth"] >= MIN_GROWTH
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and a["score"] >= 60
        and (a["depth_ratio"] >= 1 or a["is_buy_queue"])
    )

    if a["stable"] and a["queue_strong"]:
        a["signal_type"] = "🟢 شکست + صف خرید قدرتمند"
    elif a["stable"]:
        a["signal_type"] = "🟢 شکست تأییدشده"
    elif confirmation_candidate:
        a["signal_type"] = "🟡 شکست در حال تأیید"
    else:
        a["signal_type"] = "⚪ تحت نظر"

    a["status"] = a["signal_type"]

    a["risk_plan"] = risk_plan(a["last"])

    previous_stable = bool(old.get("stable", False))
    previous_signal = old.get("signal_type", "")
    event = ""

    if a["stable"] and not previous_stable:
        event = "🟢 BREAKOUT CONFIRMED"
    elif previous_stable and not a["stable"]:
        event = "🔴 BREAKOUT FAILED"
    elif a["queue_strong"] and not old.get("queue_strong", False):
        event = "🟢 STRONG BUY QUEUE"
    elif queue_event:
        event = queue_event
    elif not old and a["signal_type"] != "⚪ تحت نظر":
        event = "🆕 NEW SIGNAL"
    elif old and previous_signal != a["signal_type"]:
        event = f"🔄 تغییر سیگنال: {previous_signal} → {a['signal_type']}"

    a["event"] = event

    locked_ceiling_source = state.get(name, {}).get("locked_ceiling_source", "")
    state[name] = {
        "score": a["score"],
        "last": a["last"],
        "growth": a["growth"],
        "depth_ratio": a["depth_ratio"],
        "distance_high": a["distance_high"],
        "signal_type": a["signal_type"],
        "consecutive_valid": consecutive,
        "stable": a["stable"],
        "is_buy_queue": a["is_buy_queue"],
        "queue_score": a["queue_score"],
        "queue_volume_ratio": a.get("queue_volume_ratio", 0),
        "queue_suspect": a.get("queue_suspect", False),
        "queue_consecutive": queue_consecutive,
        "queue_health": a.get("queue_health", "⚪ بدون صف"),
        "sell_pressure": a.get("sell_pressure", "N/A"),
        "volume_ratio": a.get("volume_ratio"),
        "volume_ratio_valid": a.get("volume_ratio_valid", False),
        "avg_volume": a.get("avg_volume", 0),
        "entry_permission": a.get("entry_permission", "⚪ ورود ممنوع"),
        "queue_strong": a["queue_strong"],
        "locked_ceiling": a.get("locked_ceiling", 0),
        "locked_ceiling_source": locked_ceiling_source,
        "locked_ceiling_distance": a.get("locked_ceiling_distance"),
        "post_drop_reconfirm": a.get("post_drop_reconfirm", 0),
        "post_drop_locked": a.get("post_drop_locked", False),
        "last_seen": datetime.now().isoformat(timespec="seconds"),
        "history": a.get("history", [])
    }

    if event:
        msg = (
            f"{event} | {name} | price={a['last']:.0f} | "
            f"score={a['score']} | queue_score={a['queue_score']} | "
            f"queue_health={a.get('queue_health', 'N/A')} | "
            f"growth={a['growth']:+.2f}% | depth={a['depth_ratio']:.2f} | "
            f"breakout_persistence={consecutive}/{STABLE_REQUIRED} | "
            f"queue_persistence={queue_consecutive}/{QUEUE_PERSISTENCE_REQUIRED}"
        )
        append_alert(msg)
        print(f"\\a🚨 {msg}")

    return a


def reset_persistence(name, state):
    """وقتی رشد منفی/صفر شد، شمارنده شکست آن نماد صفر می‌شود."""
    if name in state:
        state[name]["consecutive_valid"] = 0
        state[name]["stable"] = False
        state[name]["last_seen"] = datetime.now().isoformat(timespec="seconds")


def show(a):
    print()
    print("=" * 70)
    print(f"نماد: {a['name']}")
    print(f"قیمت: {a['last']:,.0f}")
    print(f"رشد واقعی: {a['growth']:+.2f}%")
    print(f"ارزش معاملات: {a['value'] / 1e9:,.2f} B ریال")
    print(f"حجم: {a['volume']:,.0f}")
    print(f"تعداد معاملات: {a['trades']:,.0f}")
    print(f"فاصله تا سقف: {a['distance_high']:.2f}%")
    if a.get("locked_ceiling", 0) > 0:
        print(f"سقف قفل‌شده جلسه: {a['locked_ceiling']:,.0f} ریال")
        print(f"فاصله از سقف قفل‌شده: {a.get('locked_ceiling_distance', 999):.2f}%")
        if a.get("post_drop_locked"):
            print(
                "قفل بازیابی سقف: 🔴 فعال | "
                f"تأیید مجدد {a.get('post_drop_reconfirm', 0)}/{POST_DROP_RECONFIRM_REQUIRED}"
            )
        else:
            print("قفل بازیابی سقف: 🟢 غیرفعال")

    print()
    print("----- ORDER BOOK -----")
    print(f"خرید1: {a['buy1']:,.0f}")
    print(f"فروش1: {a['sell1']:,.0f}")
    print(f"نسبت تقاضای ردیف اول: {a['order_ratio']:.2f}")
    print(f"خرید 5 ردیف: {a['buy5']:,.0f}")
    print(f"فروش 5 ردیف: {a['sell5']:,.0f}")
    if a["sell5"] <= 0 and a["buy5"] > 0:
        depth_display = "∞ (عرضه 5 ردیف = صفر)"
    else:
        depth_display = f"{a['depth_ratio']:.2f}"
    print(f"نسبت عمق 5 ردیف: {depth_display}")

    print()
    print("----- MOMENTUM -----")
    print(f"تغییر قیمت از اسکن قبل: {a.get('price_change_since_scan', 0):+.2f}%")
    print(f"تغییر امتیاز: {a.get('score_change_since_scan', 0):+.0f}")
    if a.get("volume_ratio_valid") and a.get("volume_ratio") is not None:
        print(f"نسبت حجم به میانگین: {a['volume_ratio']:.2f}x")
    else:
        print("نسبت حجم به میانگین: ⏳ در انتظار سابقه معتبر")

    print()
    print(f"SCORE: {a['score']}/100")
    print(f"وضعیت امتیازی: {a['status']}")
    print(f"سیگنال: {a['signal_type']}")
    print(f"پایداری شکست: {a.get('consecutive_valid', 0)}/{STABLE_REQUIRED}")
    print(f"امتیاز صف خرید: {a.get('queue_score', 0)}/100")
    print(f"ماندگاری صف: {a.get('queue_consecutive', 0)}/{QUEUE_PERSISTENCE_REQUIRED}")
    print(f"کیفیت صف: {a.get('queue_health', '⚪ بدون صف')}")
    print(f"نسبت صف به حجم: {a.get('queue_volume_ratio', 0):.2f}x")
    if a.get("queue_suspect"):
        print("هشدار صف: 🟠 صف مشکوک — پشتوانه حجم کافی نیست")
    print(f"فشار فروش: {a.get('sell_pressure', 'N/A')}")
    print(f"وضعیت صف: {a.get('queue_signal', '⚪ بدون صف خرید')}")
    print(f"اجازه ورود: {a.get('entry_permission', '⚪ ورود ممنوع')}")
    if a.get("queue_event"):
        print(f"رویداد صف: {a['queue_event']}")
    if a.get("queue_break_absorbed"):
        print("رویداد بازار: 🟢 صف شکسته و عرضه روی سقف جذب شد — این رویداد به‌تنهایی تأیید شکست نیست.")

    # توضیح دقیق علت صفر ماندن شمارنده شکست؛ برای دیباگ و تصمیم‌گیری شفاف.
    if not a.get("real_breakout_now", False) and a.get("signal_type") == "🟡 شکست در حال تأیید":
        reasons = []
        if a.get("growth", 0) < MIN_GROWTH:
            reasons.append(f"رشد {a.get('growth', 0):+.2f}% < {MIN_GROWTH:.2f}%")
        if a.get("score", 0) < MIN_SCORE:
            reasons.append(f"امتیاز {a.get('score', 0):.0f} < {MIN_SCORE}")
        if a.get("distance_high", 999) > MAX_ENTRY_DISTANCE_HIGH:
            reasons.append(f"فاصله سقف {a.get('distance_high', 0):.2f}% > {MAX_ENTRY_DISTANCE_HIGH:.2f}%")
        if not (a.get("depth_ratio", 0) >= MIN_DEPTH_RATIO or a.get("is_buy_queue")):
            reasons.append(f"عمق {a.get('depth_ratio', 0):.2f} < {MIN_DEPTH_RATIO:.2f}")
        if not a.get("volume_ratio_valid", False) or a.get("volume_ratio") is None:
            reasons.append("حجم معتبر نیست")
        elif a.get("volume_ratio", 0) < BREAKOUT_VOLUME_RATIO_MIN:
            reasons.append(f"حجم {a.get('volume_ratio', 0):.2f}x < {BREAKOUT_VOLUME_RATIO_MIN:.2f}x")
        if a.get("post_drop_locked", False) and a.get("post_drop_reconfirm", 0) < POST_DROP_RECONFIRM_REQUIRED:
            reasons.append("قفل بازیابی سقف فعال است")
        if reasons:
            print("علت عدم افزایش پایداری: " + " | ".join(reasons))

    if a.get("stable"):
        print("وضعیت زمانی: 🟢 شکست پایدار")
    elif a.get("consecutive_valid", 0) > 0:
        print("وضعیت زمانی: 🟡 در حال تأیید")
    else:
        print("وضعیت زمانی: ⚪ بدون تأیید زمانی")

    # Trade Plan فقط برای کاندید واقعی/در حال تأیید/تأییدشده نمایش داده می‌شود.
    # نمادهای صرفاً WATCH نباید با محاسبات حجم و حدضرر، شبیه توصیه ورود دیده شوند.
    rp = a.get("risk_plan", {})
    trade_plan_signal = a.get("signal_type") in (
        "🟡 شکست در حال تأیید",
        "🟢 شکست تأییدشده",
        "🟢 شکست + صف خرید قدرتمند",
    )
    if rp and trade_plan_signal:
        print()
        print("----- TRADE PLAN -----")
        if a.get("entry_permission") == "🟢 ورود مجاز":
            print("🟢 این Trade Plan مربوط به نمادی است که تمام شروط مجوز ورود را دارد.")
        else:
            print("⚠️ این Trade Plan صرفاً محاسبات ریسک است؛ هنوز مجوز ورود صادر نشده.")
        print(f"سرمایه: {rp['capital_toman']:,.0f} تومان")
        print(f"حجم موقعیت: {rp['position_toman']:,.0f} تومان")
        print(f"درصد موقعیت از سرمایه: {rp['position_percent_of_capital']:.2f}%")
        print(f"حدضرر: {rp['stop']:,.0f} ریال ({rp['stop_loss_percent']:.2f}%)")
        print(f"زیان احتمالی در حدضرر: {rp['max_loss_toman']:,.0f} تومان")
        print(f"درصد سرمایه در معرض زیان: {rp['actual_risk_percent']:.2f}%")
        print(f"سقف ریسک مجاز: {rp['risk_budget_toman']:,.0f} تومان ({rp['risk_budget_percent']:.2f}%)")
        print(f"هدف 1: {rp['target1']:,.0f} ریال")
        print(f"هدف 2: {rp['target2']:,.0f} ریال")
        print(f"تعداد پیشنهادی: {rp['shares']:,}")

    if a.get("event"):
        print(f"رویداد: {a['event']}")



def norm_text(value):
    """نرمال‌سازی حداقلی فارسی برای مقایسه نمادها."""
    s = str(value or "").strip().replace("ي", "ی").replace("ك", "ک")
    s = s.replace("‌", "").replace(" ", "")
    return s


def diagnostic_layer(data):
    """V6.2 DIAGNOSTIC LAYER — فقط مشاهده و شمارش؛ منطق اسکن را تغییر نمی‌دهد.

    این تابع عمداً فیلترهای اصلی را اجرا نمی‌کند/تغییر نمی‌دهد؛ فقط همان قواعد
    فعلی stock_universe و option_universe را به‌صورت مرحله‌ای اندازه‌گیری می‌کند.
    هدف: مشخص شود 3122 ابزار دقیقاً در کدام مرحله به صفر می‌رسند.
    """
    raw = len(data)
    named = [x for x in data if bool(norm_text(x.get("lva")))]

    # تشخیص نوع ابزار: همان خانواده‌هایی که V6.2 در حال حاضر می‌شناسد.
    stock_yval = [x for x in named if str(x.get("yval", "")).strip() in STOCK_YVALS]
    option_yval = [x for x in named if str(x.get("yval", "")).strip() in OPTION_YVALS]
    unknown_yval = [x for x in named if str(x.get("yval", "")).strip() not in STOCK_YVALS
                    and str(x.get("yval", "")).strip() not in OPTION_YVALS]

    # fallback فعلی V6.2 وقتی yval خالی است.
    fallback_stock = [x for x in named if not str(x.get("yval", "")).strip()
                      and str(x.get("flow", "")).strip() in {"1", "2"}]

    bourse = [x for x in named if str(x.get("yval", "")).strip() == "300"]
    farabourse = [x for x in named if str(x.get("yval", "")).strip() == "303"]
    base_market = [x for x in named if str(x.get("yval", "")).strip() == "309"]

    # مرحله «تشخیص نوع ابزار» برای سهام = همان مجموعه‌ای که منطق فعلی می‌تواند
    # به‌عنوان stock تشخیص دهد، بدون dedupe.
    detected_stocks = stock_yval if stock_yval else fallback_stock

    # چون V6.2 با yvalهای 300/303 سهام را تعریف می‌کند، ETF/اوراق از ابتدا
    # در universe سهم وارد نمی‌شوند. این شمارش عمداً گزارش می‌شود تا معلوم باشد
    # حذف در این مرحله اتفاق افتاده یا قبل از آن.
    etf_bond_like = [x for x in named if str(x.get("yval", "")).strip()
                     not in {"300", "303"} and str(x.get("yval", "")).strip()]

    # اعتبارسنجی قیمت دقیقاً با شرط فعلی analyze(): pmd > 0
    price_valid = [x for x in (bourse + farabourse)
                   if f(x.get("pmd")) > 0]

    # شمارش نهایی دقیقاً با stock_universe فعلی، بدون هیچ تغییر در آن.
    final_stocks = stock_universe(data)
    final_price_valid = [x for x in final_stocks if f(x.get("pmd")) > 0]

    # توزیع YVal و Flow برای تشخیص سریع ناسازگاری API
    yvals = {}
    flows = {}
    for x in data:
        y = str(x.get("yval", "")).strip() or "<empty>"
        fl = str(x.get("flow", "")).strip() or "<empty>"
        yvals[y] = yvals.get(y, 0) + 1
        flows[fl] = flows.get(fl, 0) + 1

    d = {
        "raw": raw,
        "named": len(named),
        "detected_stock": len(detected_stocks),
        "bourse": len(bourse),
        "farabourse": len(farabourse),
        "stock_yval": len(stock_yval),
        "option_yval": len(option_yval),
        "fallback_stock": len(fallback_stock),
        "base_market": len(base_market),
        "etf_bond_like": len(etf_bond_like),
        "price_valid_before_final": len(price_valid),
        "final_stock_universe": len(final_stocks),
        "final_price_valid": len(final_price_valid),
        "yvals": yvals,
        "flows": flows,
    }

    print()
    print("=" * 70)
    print("                    V6.2 DIAGNOSTIC LAYER")
    print("=" * 70)
    print(f"MarketWatch raw:                         {raw}")
    print(f"بعد از تشخیص نوع ابزار:                  {len(detected_stocks)}")
    print(f"بعد از فیلتر بورس:                       {len(bourse)}")
    print(f"بعد از فیلتر فرابورس:                    {len(farabourse)}")
    print(f"بعد از حذف ETF/اوراق:                    {len(bourse) + len(farabourse)}")
    print(f"بعد از اعتبارسنجی قیمت:                 {len(price_valid)}")
    print(f"سهام نهایی قابل تحلیل:                  {len(final_stocks)}")
    print()
    print("جزئیات تشخیص:")
    print(f"  ابزار دارای نام:                       {len(named)}")
    print(f"  YVal سهام (300/303):                   {len(stock_yval)}")
    print(f"  fallback بر اساس Flow(1/2):            {len(fallback_stock)}")
    print(f"  YVal اختیار:                           {len(option_yval)}")
    print(f"  YVal 309 (Base Market):                {len(base_market)}")
    print(f"  سایر YValهای غیرسهام:                  {len(etf_bond_like)}")
    print()
    print("توزیع YVal (برای پیدا کردن علت صفر شدن):")
    for y, n in sorted(yvals.items(), key=lambda kv: (-kv[1], kv[0]))[:25]:
        print(f"  {y:<12} {n}")
    print("توزیع Flow:")
    for fl, n in sorted(flows.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        print(f"  {fl:<12} {n}")
    print("=" * 70)
    return d


def stock_universe(data):
    """کل سهام بورس/فرابورس را از MarketWatch جدا می‌کند."""
    if not SCAN_ALL_STOCKS:
        return [x for x in data if norm_text(x.get("lva")) in {norm_text(w) for w in WATCHLIST}]
    out = []
    seen = set()
    for x in data:
        yval = str(x.get("yval", "")).strip()
        flow = str(x.get("flow", "")).strip()
        # اگر yVal در پاسخ موجود باشد، دقیق‌ترین فیلتر همین است.
        ok = yval in STOCK_YVALS
        # fallback برای نسخه‌های API که yval را برنمی‌گردانند.
        if not yval:
            ok = flow in {"1", "2"} and bool(x.get("lva"))
        name = norm_text(x.get("lva"))
        if ok and name and name not in seen:
            seen.add(name)
            out.append(x)
    return out


def option_universe(data):
    if not OPTION_SCAN_ENABLED:
        return []
    out = []
    seen = set()
    for x in data:
        yval = str(x.get("yval", "")).strip()
        name = norm_text(x.get("lva"))
        if yval in OPTION_YVALS and name and name not in seen:
            seen.add(name)
            out.append(x)
    return out


def option_kind(x):
    yval = str(x.get("yval", "")).strip()
    name = norm_text(x.get("lva"))
    if yval in {"312", "323", "600", "602"} or name.startswith("ط"):
        return "PUT"
    if yval in {"311", "321", "322"} or name.startswith("ض"):
        return "CALL"
    return "UNKNOWN"


def option_underlying_candidates(option_name, stocks):
    """V6.2 — تطبیق چندمرحله‌ای اختیار با سهم پایه.

    اول تطبیق مستقیم، سپس aliasهای معتبر و در نهایت هیچ حدسی.
    confidence برای تصمیم نهایی باید به حداقل OPTION_MAPPING_MIN_CONFIDENCE برسد.
    """
    import re
    o = norm_text(option_name)
    core = o[1:] if o[:1] in ("ض", "ط") else o
    stock_map = {}
    for stock in stocks:
        n = norm_text(stock.get("lva"))
        if n:
            stock_map[n] = stock

    candidates = []
    # مستقیم‌ترین تطبیق: نماد پایه به‌صورت کامل در هسته قرارداد.
    for n, stock in stock_map.items():
        if n and n in core:
            candidates.append((1.0, stock, "direct"))

    # alias معتبر، فقط برای نمادهایی که قبلاً در universe سهم وجود دارند.
    for base_name, aliases in OPTION_MAPPING_ALIASES.items():
        base_norm = norm_text(base_name)
        stock = stock_map.get(base_norm)
        if not stock:
            continue
        for alias in aliases:
            alias_norm = norm_text(alias)
            if alias_norm and alias_norm in core:
                candidates.append((0.98, stock, "alias"))
                break

    # تطبیق عددی/تقسیم‌شده صرفاً تشخیصی است و برای ورود مجاز نیست.
    parts = [p for p in re.split(r"[0-9]+", core) if p]
    for n, stock in stock_map.items():
        if n in parts:
            candidates.append((0.90, stock, "token"))

    # حذف تکراری‌ها با نگه‌داشتن بهترین confidence/source.
    best = {}
    for conf, stock, source in candidates:
        key = norm_text(stock.get("lva"))
        old = best.get(key)
        if old is None or conf > old[0]:
            best[key] = (conf, stock, source)
    out = list(best.values())
    out.sort(key=lambda z: (-z[0], len(norm_text(z[1].get("lva")))))
    return out[:3]


def option_number_fields(x):
    """استخراج اعداد نام قرارداد؛ فقط برای کمک به رتبه‌بندی، نه داده رسمی."""
    import re
    name = norm_text(x.get("lva"))
    nums = [int(v) for v in re.findall(r"\d+", name)]
    return nums


def option_market_metrics(x):
    """متریک‌های اختیار با تفکیک واقعی «قیمت» از «حجم سفارش».

    در BestLimits، pMeDem/pMeOf قیمت‌های خرید/فروش و
    qTitMeDem/qTitMeOf حجم سفارش‌ها هستند. برخی پاسخ‌های MarketWatch
    ممکن است نام کوتاه pmd/pmo/qmd/qmo داشته باشند؛ در آن حالت fallback
    استفاده می‌شود، اما قیمت و حجم دیگر با هم اشتباه نمی‌شوند.
    """
    price = f(x.get("pmd"))
    yesterday = f(x.get("py"))
    value = f(x.get("qtc"))
    volume = f(x.get("qtj"))
    trades = f(x.get("ztt"))
    growth = ((price - yesterday) / yesterday * 100) if yesterday > 0 else 0
    books = x.get("blDs", []) or []
    first = books[0] if books else {}

    bid_price = next((f(first.get(k)) for k in ("pMeDem", "pmd", "bidPrice", "bid")
                      if f(first.get(k)) > 0), 0)
    ask_price = next((f(first.get(k)) for k in ("pMeOf", "pmo", "askPrice", "ask")
                      if f(first.get(k)) > 0), 0)
    bid_qty = next((f(first.get(k)) for k in ("qTitMeDem", "qmd", "bidQty")
                    if f(first.get(k)) > 0), 0)
    ask_qty = next((f(first.get(k)) for k in ("qTitMeOf", "qmo", "askQty")
                    if f(first.get(k)) > 0), 0)

    spread_pct = ((ask_price - bid_price) / ((ask_price + bid_price) / 2) * 100
                  if bid_price > 0 and ask_price > 0 and ask_price >= bid_price else None)
    return {
        "price": price, "value": value, "volume": volume, "trades": trades,
        "growth": growth, "bid": bid_qty, "ask": ask_qty,
        "bid_price": bid_price, "ask_price": ask_price,
        "spread_pct": spread_pct,
        "spread_verified": bool(bid_price > 0 and ask_price > 0),
    }


def option_liquidity_score(m):
    """امتیاز نقدشوندگی اختیار؛ نبود داده، امتیاز مثبت جعلی نمی‌گیرد."""
    score = 0
    if m["value"] >= 50_000_000_000: score += 30
    elif m["value"] >= 10_000_000_000: score += 22
    elif m["value"] >= 1_000_000_000: score += 12
    elif m["value"] > 0: score += 5
    if m["volume"] >= 100_000: score += 20
    elif m["volume"] >= 20_000: score += 14
    elif m["volume"] > 0: score += 7
    if m["trades"] >= 500: score += 20
    elif m["trades"] >= 100: score += 14
    elif m["trades"] >= 20: score += 8
    elif m["trades"] > 0: score += 3
    if m["spread_pct"] is not None:
        if m["spread_pct"] <= 2: score += 30
        elif m["spread_pct"] <= 5: score += 20
        elif m["spread_pct"] <= 10: score += 10
    return min(score, 100)


def option_contract_terms(x, underlying_price):
    """تلاش برای استخراج strike/expiry از فیلدهای API یا نام.

    اگر فیلد صریح وجود نداشته باشد، از نام قرارداد فقط به‌عنوان حدس استفاده می‌شود
    و confidence پایین می‌ماند. هیچ مقدار حدسی برای تصمیم نهایی مجاز نیست.
    """
    import re
    strike_keys = ("strikePrice", "strike", "k", "exercisePrice", "exercise")
    expiry_keys = ("expiry", "expirationDate", "maturityDate", "contractDate")
    strike = None
    expiry = None
    strike_source = ""
    expiry_source = ""
    for k in strike_keys:
        if x.get(k) not in (None, "", 0):
            v = f(x.get(k), 0)
            if v > 0:
                strike, strike_source = v, k
                break
    for k in expiry_keys:
        if x.get(k) not in (None, ""):
            expiry, expiry_source = str(x.get(k)), k
            break
    if strike is None:
        nums = [int(v) for v in re.findall(r"\d+", norm_text(x.get("lva")))]
        # فقط اعداد بزرگ و محتملِ قیمت اعمال؛ این یک تخمین است.
        plausible = [n for n in nums if n > 100]
        if plausible:
            strike = plausible[-1]
            strike_source = "symbol_heuristic"
    moneyness = None
    if strike and underlying_price > 0:
        moneyness = underlying_price / strike
    return strike, expiry, strike_source, expiry_source, moneyness


def option_theoretical_metrics(kind, spot, strike, days, iv=0.60, rate=0.25, premium=0):
    """Black-Scholes تقریبی؛ فقط برای مقایسه قراردادها، نه قیمت رسمی."""
    import math
    if spot <= 0 or strike <= 0 or days <= 0:
        return None
    T = days / 365.0
    sigma = max(0.05, min(iv, 3.0))
    try:
        d1 = (math.log(spot / strike) + (rate + 0.5*sigma*sigma)*T) / (sigma*math.sqrt(T))
        d2 = d1 - sigma*math.sqrt(T)
        cdf = lambda z: 0.5*(1.0 + math.erf(z/math.sqrt(2.0)))
        if kind == "CALL":
            theo = spot*cdf(d1) - strike*math.exp(-rate*T)*cdf(d2)
            delta = cdf(d1)
        else:
            theo = strike*math.exp(-rate*T)*cdf(-d2) - spot*cdf(-d1)
            delta = cdf(d1) - 1.0
        premium_gap = ((premium-theo)/theo*100) if theo > 0 and premium > 0 else None
        return {"theoretical": theo, "delta": delta, "premium_gap_pct": premium_gap,
                "days": days, "iv": sigma}
    except Exception:
        return None


def parse_days_to_expiry(expiry):
    """محاسبه روزهای باقی‌مانده؛ Gregorian و Jalali را می‌پذیرد."""
    if not expiry:
        return None
    from datetime import datetime, date
    import re
    s = str(expiry)
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if not m:
        m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    try:
        if y >= 1700:
            target = date(y, mo, d)
        elif 1200 <= y <= 1600:
            # Jalali -> Gregorian (الگوریتم تبدیل مستقل، بدون وابستگی خارجی)
            jy, jm, jd = y, mo, d
            jy2 = jy - 979
            days = 365 * jy2 + jy2 // 33 * 8 + ((jy2 % 33) + 3) // 4
            if jm < 7:
                days += (jm - 1) * 31
            else:
                days += (jm - 1) * 30 + 6
            days += jd - 1
            gy = 1600 + 400 * (days // 146097)
            days %= 146097
            leap = True
            if days >= 36525:
                days -= 1
                gy += 100 * (days // 36524)
                days %= 36524
                if days >= 365:
                    days += 1
                else:
                    leap = False
            gy += 4 * (days // 1461)
            days %= 1461
            if days >= 366:
                leap = False
                gy += (days - 1) // 365
                days = (days - 1) % 365
            gd = days + 1
            mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            gm = 1
            while gd > mdays[gm - 1] and gm <= 12:
                gd -= mdays[gm - 1]
                gm += 1
            target = date(gy, gm, gd)
        else:
            return None
        return max(0, (target - datetime.now().date()).days)
    except Exception:
        return None


def option_risk_grade(kind, delta, liquidity, spread_pct, premium_gap_pct):
    """ترجمه متریک‌ها به ریسک قابل فهم؛ صرفاً رتبه‌بندی."""
    score = liquidity
    if delta is not None:
        ad = abs(delta)
        if 0.35 <= ad <= 0.65: score += 10
        elif 0.20 <= ad <= 0.80: score += 5
        else: score -= 5
    if spread_pct is not None:
        if spread_pct <= 2: score += 10
        elif spread_pct > 10: score -= 15
    if premium_gap_pct is not None:
        if premium_gap_pct > 30: score -= 15
        elif premium_gap_pct < -20: score += 5
    score = max(0, min(score, 100))
    if score >= 80: return score, "🟢 ریسک نسبی پایین‌تر"
    if score >= 60: return score, "🟡 ریسک متوسط"
    if score >= 40: return score, "🟠 ریسک بالا"
    return score, "🔴 ریسک بسیار بالا"


def predictive_score(a):
    """V6.2 — امتیاز پیش‌نگر تفکیک‌شده برای شکار حرکت قبل از صف.

    این امتیاز احتمال/کیفیت حرکت را رتبه‌بندی می‌کند و هرگز به‌تنهایی
    مجوز ورود صادر نمی‌کند. مؤلفه‌ها جداگانه محاسبه می‌شوند تا علت امتیاز روشن باشد.
    """
    if not PREDICTIVE_ENABLED:
        return 0, []

    g = a.get("growth", 0.0)
    d = a.get("distance_high", 999.0)
    order = a.get("order_ratio", 0.0)
    depth = a.get("depth_ratio", 0.0)
    vr = a.get("volume_ratio")
    pc = a.get("price_change_since_scan", 0.0)
    sc = a.get("score_change_since_scan", 0.0)
    qsc = a.get("queue_score_change_since_scan", 0.0)
    value = a.get("value", 0.0)
    trades = a.get("trades", 0.0)
    hist = a.get("history", []) or []

    parts = {}
    reasons = []

    # 1) شتاب قیمت: حداکثر 15
    parts["price_momentum"] = 0
    if 0.4 <= g <= 3.2:
        parts["price_momentum"] += 8
    elif 0 < g < 0.4:
        parts["price_momentum"] += 3
    if pc >= 0.15:
        parts["price_momentum"] += 4
    elif pc > 0:
        parts["price_momentum"] += 2
    if sc > 0:
        parts["price_momentum"] += 3
    parts["price_momentum"] = min(parts["price_momentum"], 15)
    if parts["price_momentum"] >= 10:
        reasons.append("شتاب قیمت مثبت")

    # 2) ورود حجم: حداکثر 15
    parts["volume"] = 0
    if vr is not None:
        if vr >= 2.0: parts["volume"] = 15
        elif vr >= 1.5: parts["volume"] = 12
        elif vr >= 1.1: parts["volume"] = 8
        elif vr >= 1.0: parts["volume"] = 4
    if parts["volume"] >= 8:
        reasons.append("ورود حجم تأییدشده")

    # 3) ارزش معاملات: حداکثر 10
    if value >= 500_000_000_000: parts["value"] = 10
    elif value >= 100_000_000_000: parts["value"] = 7
    elif value >= 20_000_000_000: parts["value"] = 4
    else: parts["value"] = 0
    if parts["value"] >= 7:
        reasons.append("ارزش معاملات مناسب")

    # 4) قدرت تقاضا و عمق: حداکثر 20
    parts["order_depth"] = 0
    if order >= 10: parts["order_depth"] += 10
    elif order >= 5: parts["order_depth"] += 8
    elif order >= 2: parts["order_depth"] += 5
    elif order >= 1: parts["order_depth"] += 2
    if depth >= 10: parts["order_depth"] += 10
    elif depth >= 5: parts["order_depth"] += 8
    elif depth >= 2: parts["order_depth"] += 5
    elif depth >= 1: parts["order_depth"] += 2
    parts["order_depth"] = min(parts["order_depth"], 20)
    if parts["order_depth"] >= 12:
        reasons.append("قدرت تقاضا و عمق بالا")

    # 5) نزدیکی سقف: حداکثر 15
    if d <= 0.25: parts["ceiling"] = 15
    elif d <= 0.50: parts["ceiling"] = 12
    elif d <= 0.75: parts["ceiling"] = 10
    elif d <= 1.00: parts["ceiling"] = 7
    elif d <= 1.50: parts["ceiling"] = 4
    else: parts["ceiling"] = 0
    if parts["ceiling"] >= 10:
        reasons.append("نزدیک سقف")

    # 6) تعداد معاملات/فعالیت: حداکثر 10
    if trades >= 3000: parts["activity"] = 10
    elif trades >= 1000: parts["activity"] = 8
    elif trades >= 300: parts["activity"] = 5
    elif trades > 0: parts["activity"] = 2
    else: parts["activity"] = 0

    # 7) پایداری دو اسکن و رفتار صف: حداکثر 15
    persistence = min(len(hist), 3)
    parts["persistence"] = min(persistence * 2, 6)
    if qsc > 0: parts["persistence"] += 3
    if a.get("queue_consecutive", 0) >= 2: parts["persistence"] += 4
    if a.get("queue_score", 0) >= 80: parts["persistence"] += 2
    parts["persistence"] = min(parts["persistence"], 15)
    if parts["persistence"] >= 8:
        reasons.append("پایداری/بهبود متوالی")

    total = sum(parts.values())
    # پیش‌صف فقط وقتی معنا دارد که هنوز صف خرید شکل نگرفته باشد.
    if a.get("is_buy_queue"):
        total = max(0, total - 8)
        reasons.append("اکنون صف خرید وجود دارد؛ امتیاز پیش‌صف تعدیل شد")
    elif g >= MIN_GROWTH and d <= 1.0:
        total += PREDICTIVE_PREQUEUE_BONUS
        reasons.append("پیش‌صف: رشد مثبت و نزدیکی به سقف")

    total = max(0, min(int(total), 100))
    a["predictive_components"] = parts
    a["predictive_score"] = total
    return total, reasons


def analyze_options(data, stocks, analyses):
    """موتور اختیار V6.2: قرارداد نامعتبر هرگز مجوز ورود نمی‌گیرد."""
    if not OPTION_SCAN_ENABLED:
        return []
    options = option_universe(data)
    if not options:
        return []
    stock_map = {norm_text(a["name"]): a for a in analyses}
    ranked = []
    for op in options:
        name = norm_text(op.get("lva"))
        candidates = option_underlying_candidates(name, stocks)
        if not candidates:
            continue
        conf, stock, mapping_source = candidates[0]
        base = stock_map.get(norm_text(stock.get("lva")))
        if not base:
            continue

        kind = option_kind(op)
        direction_ok = ((kind == "CALL" and base.get("growth", 0) > 0) or
                        (kind == "PUT" and base.get("growth", 0) < 0))
        m = option_market_metrics(op)
        liq = option_liquidity_score(m)
        strike, expiry, strike_source, expiry_source, moneyness = option_contract_terms(
            op, base.get("last", 0))
        days = parse_days_to_expiry(expiry)
        theo = option_theoretical_metrics(
            kind, base.get("last", 0), strike, days, premium=m["price"]
        ) if strike and days else None

        score = int(base.get("predictive_score", 0) * 0.45)
        reasons = []
        if base.get("stable"):
            score += 18; reasons.append("پایه: شکست پایدار")
        elif base.get("predictive_score", 0) >= PREDICTIVE_MIN_SCORE:
            score += 15; reasons.append("پایه: حرکت پیش‌نگر")
        if direction_ok:
            score += 12; reasons.append("جهت اختیار با پایه همسو")
        else:
            score -= 25; reasons.append("جهت اختیار با حرکت پایه ناسازگار")
        score += int(liq * 0.25)
        if liq >= 70: reasons.append("نقدشوندگی خوب")
        elif liq < 35: reasons.append("نقدشوندگی ضعیف")

        delta = None
        premium_gap = None
        risk_text = "⚪ نیازمند تأیید مشخصات قرارداد"
        contract_verified = bool(strike_source != "symbol_heuristic" and expiry_source and days is not None)
        if theo:
            delta = theo["delta"]
            premium_gap = theo["premium_gap_pct"]
            risk_score, risk_text = option_risk_grade(kind, delta, liq, m["spread_pct"], premium_gap)
            if OPTION_MIN_ABS_DELTA <= abs(delta) <= OPTION_MAX_ABS_DELTA:
                score += 10
            if 0.35 <= abs(delta) <= 0.65:
                reasons.append(f"Delta مناسب {delta:+.2f}")
            if premium_gap is not None:
                reasons.append(f"فاصله پریمیوم/ارزش نظری {premium_gap:+.1f}%")
        else:
            risk_score = liq

        if m["spread_pct"] is not None:
            if m["spread_pct"] <= 5: reasons.append(f"اسپرد واقعی {m['spread_pct']:.1f}%")
            elif m["spread_pct"] > 10: reasons.append(f"اسپرد واقعی بالا {m['spread_pct']:.1f}%")
        else:
            reasons.append("اسپرد قابل‌محاسبه نیست")

        if moneyness is not None:
            if kind == "CALL" and 0.95 <= moneyness <= 1.10: reasons.append("CALL نزدیک/اطراف ATM")
            if kind == "PUT" and 0.90 <= moneyness <= 1.05: reasons.append("PUT نزدیک/اطراف ATM")

        score = max(0, min(int(score), 100))
        premium_ok = (premium_gap is None or premium_gap <= OPTION_MAX_PREMIUM_OVER_THEO_PCT)
        delta_ok = (delta is not None and OPTION_MIN_ABS_DELTA <= abs(delta) <= OPTION_MAX_ABS_DELTA)
        option_entry = bool(
            conf >= OPTION_MAPPING_MIN_CONFIDENCE and mapping_source in ("direct", "alias")
            and contract_verified and direction_ok and score >= OPTION_ENTRY_MIN_SCORE
            and liq >= OPTION_ENTRY_MIN_LIQUIDITY and delta_ok and premium_ok
        )
        if option_entry:
            entry_status = "🟢 OPTION ENTRY AUTHORIZED"
        elif score >= OPTION_ENTRY_MIN_SCORE and contract_verified:
            entry_status = "🟡 OPTION WATCH — شروط ورود کامل نیست"
        else:
            entry_status = "⚪ OPTION WATCH"

        ranked.append({
            "name": name, "kind": kind, "underlying": base.get("name"),
            "confidence": conf, "mapping_source": mapping_source, "option_price": m["price"], "option_value": m["value"],
            "option_volume": m["volume"], "option_trades": m["trades"],
            "bid_price": m["bid_price"], "ask_price": m["ask_price"],
            "bid_qty": m["bid"], "ask_qty": m["ask"],
            "spread_pct": m["spread_pct"], "spread_verified": m["spread_verified"],
            "liquidity_score": liq, "strike": strike, "expiry": expiry,
            "days_to_expiry": days, "moneyness": moneyness, "delta": delta,
            "theoretical_value": theo["theoretical"] if theo else None,
            "premium_gap_pct": premium_gap, "risk_score": risk_score,
            "risk_grade": risk_text, "contract_verified": contract_verified,
            "score": score, "direction_ok": direction_ok,
            "entry_authorized": option_entry, "entry_status": entry_status,
            "reasons": reasons,
            "warning": (
                f"تطبیق پایه: {mapping_source} با confidence={conf:.0%}. "
                "مجوز ورود فقط پس از تأیید رسمی strike/سررسید؛ ارزش نظری و Delta تقریبی‌اند."
                if theo else
                "مشخصات کامل قرارداد در داده فعلی تأیید نشد؛ این قرارداد مجوز ورود ندارد."
            ),
        })
    # V6.2: گزارش تشخیصی در state؛ قراردادهای حذف‌شده حدس زده نمی‌شوند.
    diagnostics = {"options_seen": len(options), "matched": 0, "unmatched": 0,
                   "low_confidence": 0, "unknown_kind": 0, "contract_unverified": 0}
    for op in options:
        cands = option_underlying_candidates(norm_text(op.get("lva")), stocks)
        if not cands:
            diagnostics["unmatched"] += 1
            continue
        diagnostics["matched"] += 1
        conf, _, src = cands[0]
        if conf < OPTION_MAPPING_MIN_CONFIDENCE or src not in ("direct", "alias"):
            diagnostics["low_confidence"] += 1
        if option_kind(op) == "UNKNOWN":
            diagnostics["unknown_kind"] += 1
        strike, expiry, strike_source, expiry_source, _ = option_contract_terms(op, 0)
        if not (strike_source != "symbol_heuristic" and expiry_source):
            diagnostics["contract_unverified"] += 1
    state_diag = diagnostics
    ranked.sort(key=lambda z: (-int(z.get("entry_authorized", False)), -z["score"],
                               -z["liquidity_score"], -z["confidence"]))
    return ranked[:OPTION_MAX_CONTRACTS]


def print_option_diagnostics(data, stocks):
    """V6.2 — Diagnostic Layer اختیار؛ بدون تغییر در منطق رتبه‌بندی/ورود."""
    raw_options = [x for x in data if str(x.get("yval", "")).strip() in OPTION_YVALS]
    options = option_universe(data)
    calls = [x for x in options if option_kind(x) == "CALL"]
    puts = [x for x in options if option_kind(x) == "PUT"]
    valid_strike = []
    valid_expiry = []
    certain_mapping = []
    counts = {"seen": len(options), "matched": 0, "unmatched": 0,
              "low_conf": 0, "unknown_kind": 0, "unverified_terms": 0}
    for op in options:
        strike, expiry, strike_source, expiry_source, _ = option_contract_terms(op, 0)
        if strike_source and strike_source != "symbol_heuristic" and strike is not None:
            valid_strike.append(op)
        if expiry_source and expiry is not None:
            valid_expiry.append(op)
        cands = option_underlying_candidates(norm_text(op.get("lva")), stocks)
        if not cands:
            counts["unmatched"] += 1
            continue
        counts["matched"] += 1
        conf, _, src = cands[0]
        if conf < OPTION_MAPPING_MIN_CONFIDENCE or src not in ("direct", "alias"):
            counts["low_conf"] += 1
        else:
            certain_mapping.append(op)
        if option_kind(op) == "UNKNOWN":
            counts["unknown_kind"] += 1
        if not (strike_source and strike_source != "symbol_heuristic" and expiry_source):
            counts["unverified_terms"] += 1
    counts.update({
        "raw": len(raw_options),
        "valid_call": len(calls),
        "valid_put": len(puts),
        "valid_strike": len(valid_strike),
        "valid_expiry": len(valid_expiry),
        "certain_mapping": len(certain_mapping),
    })
    print()
    print("----- OPTION DIAGNOSTICS — V6.2 -----")
    print(f"اختیار خام:                              {len(raw_options)}")
    print(f"CALL معتبر:                              {len(calls)}")
    print(f"PUT معتبر:                               {len(puts)}")
    print(f"دارای Strike معتبر:                     {len(valid_strike)}")
    print(f"دارای Expiry معتبر:                     {len(valid_expiry)}")
    print(f"تطبیق قطعی با سهم پایه:                 {len(certain_mapping)}")
    print(f"بدون تطبیق:                              {counts['unmatched']}")
    print(f"تطبیق کم‌اعتماد/غیرقطعی:                {counts['low_conf']}")
    print(f"نوع CALL/PUT نامشخص:                    {counts['unknown_kind']}")
    print(f"Strike/Expiry تأییدنشده:                {counts['unverified_terms']}")
    return counts


def print_option_intelligence(option_rows):
    print()
    print("=" * 70)
    print("              🧠 OPTION INTELLIGENCE — V6.2")
    print("=" * 70)
    if not option_rows:
        print("🟡 اختیار قابل‌رتبه‌بندی با تطبیق مطمئن سهم پایه پیدا نشد.")
        print("   برنامه عمداً در صورت نبود تطبیق، قرارداد را حدس نمی‌زند.")
        return
    for i, op in enumerate(option_rows[:20], 1):
        print(
            f"{i:02d}. {op['name']} | {op['kind']} | پایه={op['underlying']} | "
            f"OptionScore={op['score']}/100 | Liquidity={op['liquidity_score']}/100 | "
            f"confidence={op['confidence']:.0%} | قیمت={op['option_price']:,.0f} | {op.get('entry_status')}"
        )
        if op.get("strike"):
            print(f"    Strike≈ {op['strike']:,.0f} | Moneyness={op.get('moneyness'):.3f}x | سررسید={op.get('expiry') or 'نامشخص'} | DTE={op.get('days_to_expiry')}")
        if op.get("delta") is not None:
            print(f"    Delta≈ {op['delta']:+.2f} | ارزش نظری≈ {op['theoretical_value']:,.0f} | فاصله پریمیوم={op.get('premium_gap_pct'):+.1f}%")
        if op.get("spread_pct") is not None:
            print(f"    Bid/Ask≈ {op.get('bid_price',0):,.0f}/{op.get('ask_price',0):,.0f} | Spread≈ {op['spread_pct']:.1f}% | {op.get('risk_grade')} | Liquidity={op['liquidity_score']}/100")
        if op.get("reasons"):
            print("    " + " | ".join(op["reasons"]))
    print("⚠️ قیمت‌گذاری این بخش تقریبی/رتبه‌بندی است و جایگزین مشخصات رسمی قرارداد نیست.")

def run_scan(state):
    print()
    print("=" * 70)
    print("        SCANNER 17 V6.2 - ALL BOURSE/FARABOURSE + PREDICTIVE + OPTIONS")
    print("=" * 70)
    print(f"زمان اسکن: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        data = get_market()
    except Exception as e:
        print("خطا در دریافت بازار:")
        print(e)
        return state

    print(f"تعداد کل ابزارهای دریافت‌شده: {len(data)}")
    diagnostic = diagnostic_layer(data)
    stocks = stock_universe(data)
    options = option_universe(data)
    print(f"سهام قابل‌تحلیل بورس/فرابورس: {len(stocks)}")
    print(f"اختیارهای موجود در MarketWatch: {len(options)}")

    if log_prices(data):
        print(f"📝 snapshot قیمت‌ها در {PRICE_LOG_FILE} ثبت شد.")

    results = []
    for x in stocks:
        a = analyze(x)
        if a is None:
            continue
        name = a["name"]
        a = update_locked_ceiling(a, state)
        if a["growth"] <= 0:
            reset_persistence(name, state)
        a = update_history(a, state)
        a = update_persistence(a, state)
        ps, reasons = predictive_score(a)
        a["predictive_score"] = ps
        a["predictive_reasons"] = reasons
        if ps >= PREDICTIVE_MIN_SCORE and not a.get("entry_authorized"):
            a["predictive_signal"] = "🟠 پیش‌بینی حرکت / ورود قبل از صف"
        elif a.get("entry_authorized"):
            a["predictive_signal"] = "🟢 ورود مجاز V5.2"
        else:
            a["predictive_signal"] = "⚪ پیش‌بینی کافی نیست"
        results.append(a)

    signal_order = {
        "🟢 شکست + صف خرید قدرتمند": 0,
        "🟢 شکست تأییدشده": 1,
        "🟡 شکست در حال تأیید": 2,
        "⚪ تحت نظر": 3,
    }
    results.sort(key=lambda x: (
        0 if x.get("entry_authorized") else 1,
        0 if x.get("stable") else 1,
        -x.get("predictive_score", 0),
        signal_order.get(x.get("signal_type", "⚪ تحت نظر"), 9),
        -x["score"],
    ))

    # فقط سیگنال‌های ارزشمند را چاپ کن تا اسکن 3000+ نماد Termux را منفجر نکند.
    display = [a for a in results if (
        a.get("signal_type") != "⚪ تحت نظر"
        or a.get("predictive_score", 0) >= PREDICTIVE_MIN_SCORE
        or a.get("entry_authorized")
    )]
    for a in display[:80]:
        show(a)
        print(f"امتیاز پیش‌نگر V6: {a.get('predictive_score', 0)}/100 | {a.get('predictive_signal')}")
        if a.get("predictive_reasons"):
            print("دلایل پیش‌نگر: " + " | ".join(a["predictive_reasons"]))

    candidates = [a for a in results if a.get("score", 0) >= MIN_SCORE and a.get("growth", 0) >= MIN_GROWTH and a.get("distance_high", 999) <= MAX_ENTRY_DISTANCE_HIGH]
    confirming = [a for a in results if a.get("signal_type") == "🟡 شکست در حال تأیید"]
    stable = [a for a in results if a.get("stable")]
    authorized = [a for a in results if a.get("entry_authorized")]
    predictive = [a for a in results if a.get("predictive_score", 0) >= PREDICTIVE_MIN_SCORE]
    strong_queues = [a for a in results if a.get("queue_strong")]

    option_diag = print_option_diagnostics(data, stocks)
    option_rows = analyze_options(data, stocks, results)
    print_option_intelligence(option_rows)

    print()
    print("=" * 70)
    print("                    📊 خلاصه عملیاتی V6")
    print("=" * 70)
    print(f"کل سهام بورس/فرابورس تحلیل‌شده: {len(results)}")
    print(f"کاندیدهای امتیازی/قیمتی: {len(candidates)}")
    print(f"شکست در حال تأیید: {len(confirming)}")
    print(f"شکست پایدار: {len(stable)}")
    print(f"صف خرید قدرتمند: {len(strong_queues)}")
    print(f"🟠 کاندیدهای پیش‌صف/پیش‌نگر: {len(predictive)}")
    print(f"🟢 ورود مجاز: {len(authorized)}")
    print(f"🧠 اختیارهای رتبه‌بندی‌شده: {len(option_rows)}")

    top_pre = sorted(predictive, key=lambda x: x.get("predictive_score", 0), reverse=True)[:PREDICTIVE_TOP_N]
    if top_pre:
        print("🟠 بهترین کاندیدهای پیش‌صف:")
        print(" | ".join(f"{a['name']}({a['predictive_score']})" for a in top_pre))
    if authorized:
        print("🟢 نمادهای دارای مجوز ورود: " + ", ".join(a["name"] for a in authorized[:30]))
    elif stable:
        print("🟡 شکست پایدار داریم، اما هنوز هیچ نمادی تمام شروط ورود را ندارد.")
    else:
        print("🟡 هنوز هیچ شکست پایداری تأیید نشده است.")

    print("=" * 70)
    state["_v6_2_summary"] = {
        "last_scan": datetime.now().isoformat(timespec="seconds"),
        "stocks_scanned": len(results),
        "options_seen": len(options),
        "options_ranked": len(option_rows),
        "option_mapping_diagnostics": option_diag,
        "predictive_count": len(predictive),
        "authorized_count": len(authorized),
        "top_predictive": [a["name"] for a in top_pre],
        "top_options": [o["name"] for o in option_rows[:10]],
        "diagnostic": diagnostic,
        "option_diagnostic": option_diag,
    }
    state["_v6_2_options"] = option_rows[:20]
    save_state(state)
    return state

def main():
    state = load_state()

    print()
    print("=" * 70)
    print("   پایش هوشمند Scanner 17 V6 فعال شد")
    print(f"   فاصله اسکن: {SCAN_INTERVAL} ثانیه (2 دقیقه)")
    print(f"   ساعات اسکن: {MARKET_OPEN_HOUR:02d}:{MARKET_OPEN_MINUTE:02d} تا {MARKET_CLOSE_HOUR:02d}:{MARKET_CLOSE_MINUTE:02d}")
    print("   روزهای معاملاتی: شنبه تا چهارشنبه")
    print(f"   تأیید شکست پایدار: {STABLE_REQUIRED} اسکن متوالی")
    print(f"   فایل وضعیت: {STATE_FILE}")
    print("   Universe: کل سهام بورس + فرابورس (YVal=300,303)")
    print("   Predictive pre-queue: فعال")
    print("   Option Intelligence: فعال — رتبه‌بندی محافظه‌کارانه")
    print(f"   ثبت قیمت‌ها: هر {PRICE_LOG_INTERVAL // 60} دقیقه")
    print(f"   فایل قیمت‌ها: {PRICE_LOG_FILE}")
    print(f"   خروجی اسکن Downloads: {SCAN_TEXT_FILENAME} | هر {SCAN_EXPORT_INTERVAL // 60} دقیقه")
    print("   برای توقف: Ctrl+C")
    print("=" * 70)

    while True:
        try:
            now = datetime.now()
            status = market_status(now)

            if status != "open":
                wait_seconds = seconds_until_next_open(now)

                if status == "before_open":
                    print()
                    print("🕘 بازار هنوز باز نشده است.")
                    print("   Scanner تا ساعت 09:00 هیچ درخواست بازاری ارسال نمی‌کند.")
                elif status == "after_close":
                    print()
                    print("🔴 ساعت معاملات تمام شده است (12:30).")
                    print("   اسکن لحظه‌ای متوقف شد؛ جلسه بعدی خودکار در 09:00 آغاز می‌شود.")
                else:
                    print()
                    print("📅 امروز روز معاملاتی نیست.")
                    print("   Scanner در روز تعطیل هیچ درخواست بازاری ارسال نمی‌کند.")

                sleep_for = min(wait_seconds, WAIT_OUTSIDE_MARKET)
                if wait_seconds > WAIT_OUTSIDE_MARKET:
                    # برای جلوگیری از چاپ مکرر پیام، در فواصل کوتاه وضعیت را چک می‌کنیم.
                    sleep_for = WAIT_OUTSIDE_MARKET
                time.sleep(sleep_for)
                continue

            # اولین ورود به هر جلسه معاملاتی: تأییدهای روز قبل مخلوط نشوند.
            state, new_session = prepare_new_session(state, now)
            if new_session:
                save_state(state)
                print()
                print("🟢 جلسه معاملاتی جدید آغاز شد؛ شمارنده‌های تأیید روز قبل صفر شدند.")

            # خروجی کامل همین اسکن را هم روی صفحه نشان می‌دهیم و هم هر 10 دقیقه
            # یک نسخه متنی از آن را در Downloads قرار می‌دهیم.
            scan_buffer = io.StringIO()
            with contextlib.redirect_stdout(scan_buffer):
                state = run_scan(state)
            scan_output = scan_buffer.getvalue()
            print(scan_output, end="")
            export_scan_text(scan_output)

            # اگر اسکن دقیقاً نزدیک پایان بازار باشد، اسکن بعدی توسط حلقه زمانی حذف می‌شود.
            print()
            print(f"⏳ اسکن بعدی تا {SCAN_INTERVAL} ثانیه دیگر...")
            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print("\nپایش متوقف شد.")
            break
        except Exception as e:
            print("\nخطای غیرمنتظره:")
            print(e)
            time.sleep(WAIT_OUTSIDE_MARKET)


if __name__ == "__main__":
    main()
