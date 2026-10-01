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
    "ذوب", "خودرو", "وبصادر", "فولاد", "اهرم", "دارا يكم", "تمشك",
    "خزاميا", "تاپيكو", "دلقما", "شتران", "دكوثر", "خبهمن", "حفاري", "كوچين",
]

# ================= تنظیمات پایش =================
SCAN_INTERVAL = 120
STABLE_REQUIRED = 3
REQUEST_TIMEOUT = 20
STATE_FILE = os.path.expanduser("~/.scanner17_state.json")
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
SCAN_TEXT_FILENAME = "scanner17_scan_10min.txt"
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
    """ثبت قیمت آخرین معامله واچ‌لیست در فایل prices_10min.txt."""
    if not should_log_prices():
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "",
        "=" * 70,
        f"SNAPSHOT | {now}",
        "=" * 70,
    ]

    for name in WATCHLIST:
        x = find_symbol(data, name)

        if x is None:
            lines.append(f"{name}: پیدا نشد")
            continue

        last = f(x.get("pmd"))

        if last > 0:
            lines.append(f"{name}: {last:,.0f}")
        else:
            lines.append(f"{name}: قیمت نامعتبر")

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
    """در شروع هر روز معاملاتی، تأییدهای روز قبل را پاک می‌کند.

    این کار مهم است تا سه اسکن متوالی از یک روز، با داده‌های روز قبل
    مخلوط نشود و شکست روز قبل به‌اشتباه شکست پایدار امروز تلقی نشود.
    """
    now = now or datetime.now()
    session_date = now.strftime("%Y-%m-%d")

    if state.get("_session_date") == session_date:
        return state, False

    for name in WATCHLIST:
        item = state.get(name)
        if not isinstance(item, dict):
            continue
        item["history"] = []
        item["consecutive_valid"] = 0
        item["stable"] = False
        item["queue_consecutive"] = 0
        item["queue_strong"] = False

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

    history.append({
        "last": a["last"],
        "growth": a["growth"],
        "score": a["score"],
        "depth_ratio": a["depth_ratio"],
        "volume": a["volume"],
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

    volumes = [h["volume"] for h in history[:-1] if h["volume"] > 0]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    a["volume_ratio"] = a["volume"] / avg_volume if avg_volume > 0 else 0
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
    volume_ok = (
        a.get("volume_ratio", 0) <= 0
        or a.get("volume_ratio", 0) >= BREAKOUT_VOLUME_RATIO_MIN
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
    confirmation_valid = valid_now or locked_ceiling_queue
    consecutive = (
        min(previous_count + 1, STABLE_REQUIRED)
        if confirmation_valid else 0
    )

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
        and a.get("volume_ratio", 0) >= BREAKOUT_VOLUME_RATIO_MIN
        and a["distance_high"] <= MAX_ENTRY_DISTANCE_HIGH
        and a["growth"] >= MIN_GROWTH
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
    if a["stable"] and a["queue_strong"]:
        a["signal_type"] = "🟢 شکست + صف خرید قدرتمند"
    elif a["stable"]:
        a["signal_type"] = "🟢 شکست تأییدشده"
    elif valid_now or (
        a["score"] >= 60 and (a["depth_ratio"] >= 1 or a["is_buy_queue"])
    ):
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
        "entry_permission": a.get("entry_permission", "⚪ ورود ممنوع"),
        "queue_strong": a["queue_strong"],
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
    print(f"نسبت حجم به میانگین: {a.get('volume_ratio', 0):.2f}x")

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
        print("رفتار سقف: 🟢 صف شکسته و معامله روی سقف/جذب عرضه")

    if a.get("stable"):
        print("وضعیت زمانی: 🟢 شکست پایدار")
    elif a.get("consecutive_valid", 0) > 0:
        print("وضعیت زمانی: 🟡 در حال تأیید")
    else:
        print("وضعیت زمانی: ⚪ بدون تأیید زمانی")

    rp = a.get("risk_plan", {})
    if rp:
        print()
        print("----- TRADE PLAN -----")
    if a.get("entry_permission") != "🟢 ورود مجاز":
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


def run_scan(state):
    print()
    print("=" * 70)
    print("        SCANNER 17 - SMART PERIODIC REAL BREAKOUT")
    print("=" * 70)
    print(f"زمان اسکن: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        data = get_market()
    except Exception as e:
        print("خطا در دریافت بازار:")
        print(e)
        return state

    print(f"تعداد نمادهای دریافت‌شده: {len(data)}")

    if log_prices(data):
        print(f"📝 snapshot قیمت‌ها در {PRICE_LOG_FILE} ثبت شد.")

    results = []

    for name in WATCHLIST:
        x = find_symbol(data, name)

        if x is None:
            print(f"{name}: پیدا نشد")
            continue

        a = analyze(x)
        if a is None:
            continue

        if a["growth"] <= 0:
            # رشد منفی/صفر فقط تأیید زمانی را صفر می‌کند؛
            # نماد از خروجی حذف نمی‌شود و می‌تواند «تحت نظر» بماند.
            reset_persistence(name, state)

        a = update_history(a, state)
        a = update_persistence(a, state)
        results.append(a)

    signal_order = {
        "🟢 شکست + صف خرید قدرتمند": 0,
        "🟢 شکست تأییدشده": 1,
        "🟡 شکست در حال تأیید": 2,
        "⚪ تحت نظر": 3,
    }

    results.sort(
        key=lambda x: (
            0 if x.get("stable") else 1,
            signal_order.get(x.get("signal_type", "⚪ تحت نظر"), 9),
            -x["score"],
            -x["depth_ratio"],
        )
    )

    events = [a for a in results if a.get("event")]
    if events:
        print()
        print("=" * 70)
        print("                 🚨 IMPORTANT EVENTS")
        print("=" * 70)
        for a in events:
            print(
                f"{a['event']} | {a['name']} | "
                f"Score {a['score']} | "
                f"پایداری {a.get('consecutive_valid', 0)}/{STABLE_REQUIRED}"
            )

    groups = [
        ("🟢 شکست + صف خرید قدرتمند", "CONFIRMED BREAKOUT + STRONG BUY QUEUE"),
        ("🟢 شکست تأییدشده", "CONFIRMED BREAKOUT"),
        ("🟡 شکست در حال تأیید", "BREAKOUT IN CONFIRMATION"),
        ("⚪ تحت نظر", "WATCH"),
    ]

    for signal_type, title in groups:
        group = [a for a in results if a.get("signal_type") == signal_type]
        if not group:
            continue

        print()
        print("=" * 70)
        print(f"          {title}")
        print("=" * 70)

        for a in group:
            show(a)

    stable = [a for a in results if a.get("stable")]

    print()
    print("=" * 70)
    print(f"نمادهای دارای سیگنال: {len(results)}")
    print(f"شکست‌های پایدار: {len(stable)}")

    if stable:
        print("🟢 نمادهای تأییدشده: " + ", ".join(a["name"] for a in stable))
    else:
        print("🟡 هنوز هیچ شکست پایداری تأیید نشده است.")

    print(f"کل واچ‌لیست: {len(WATCHLIST)}")
    print("=" * 70)

    save_state(state)
    return state


def main():
    state = load_state()

    print()
    print("=" * 70)
    print("   پایش هوشمند Scanner 17 فعال شد")
    print(f"   فاصله اسکن: {SCAN_INTERVAL} ثانیه (2 دقیقه)")
    print(f"   ساعات اسکن: {MARKET_OPEN_HOUR:02d}:{MARKET_OPEN_MINUTE:02d} تا {MARKET_CLOSE_HOUR:02d}:{MARKET_CLOSE_MINUTE:02d}")
    print("   روزهای معاملاتی: شنبه تا چهارشنبه")
    print(f"   تأیید شکست پایدار: {STABLE_REQUIRED} اسکن متوالی")
    print(f"   فایل وضعیت: {STATE_FILE}")
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
