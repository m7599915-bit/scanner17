import requests
import time
import json
import os
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
SCAN_INTERVAL = 120       # 120 ثانیه = هر 2 دقیقه
STABLE_REQUIRED = 3       # 3 اسکن متوالی = شکست پایدار
REQUEST_TIMEOUT = 20
STATE_FILE = os.path.expanduser("~/.scanner16_state.json")


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
    buy1 = 0
    sell1 = 0
    buy5 = 0
    sell5 = 0

    for row in books[:5]:
        buy5 += f(row.get("qmd"))
        sell5 += f(row.get("qmo"))

    if books:
        buy1 = f(books[0].get("qmd"))
        sell1 = f(books[0].get("qmo"))

    if buy1 > 0 and sell1 > 0:
        order_ratio = buy1 / sell1
    elif buy1 > 0 and sell1 <= 0:
        order_ratio = 999
    else:
        order_ratio = 0

    depth_ratio = buy5 / sell5 if buy5 > 0 and sell5 > 0 else 0

    score = 0

    # رشد
    if 1.5 <= growth <= 3.2:
        score += 20
    elif 0 < growth < 1.5:
        score += 5
    elif growth > 3.2:
        score += 10

    # قدرت ردیف اول
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

        # اگر عمق 5 ردیف تأیید نکند، امتیاز ردیف اول محدود می‌شود.
        if depth_ratio < 1:
            order_score = min(order_score, 5)
        elif depth_ratio < 2:
            order_score = min(order_score, 12)

        score += order_score

    # فاصله تا سقف
    if 0 <= distance_high <= 0.5:
        score += 20
    elif distance_high <= 1:
        score += 15
    elif distance_high <= 2:
        score += 8

    # عمق 5 ردیف
    if depth_ratio >= 10:
        score += 15
    elif depth_ratio >= 5:
        score += 12
    elif depth_ratio >= 2:
        score += 8
    elif depth_ratio >= 1:
        score += 4

    # ارزش معاملات
    if value >= 500_000_000_000:
        score += 20
    elif value >= 100_000_000_000:
        score += 10

    # وضعیت امتیازی
    if depth_ratio >= 2 and score >= 75:
        status = "🟢 شکست معتبر"
    elif depth_ratio >= 1 and score >= 60:
        status = "🟡 کاندید شکست"
    else:
        status = "⚪ تحت نظر"

    # نوع سیگنال
    if sell5 <= 0:
        signal_type = "🔵 صف خرید — شکست تأیید نشده"
    elif score >= 75 and depth_ratio >= 2:
        signal_type = "🟢 شکست واقعی"
    elif score >= 50 and depth_ratio >= 1:
        signal_type = "🟡 کاندید شکست"
    else:
        signal_type = "⚪ تحت نظر"

    reasons = []
    if depth_ratio < 1:
        reasons.append(f"عمق {depth_ratio:.2f} < 1")
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
        "signal_type": signal_type,
        "signal_reason": " | ".join(reasons) if reasons else "تأیید کامل نشده",
    }


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_state(state):
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    os.replace(temp_file, STATE_FILE)


def update_persistence(a, state):
    """تأیید شکست فقط وقتی سه اسکن متوالی شرایط اصلی را حفظ کنند."""
    name = a["name"]
    old = state.get(name, {})

    valid_now = (
        a["growth"] > 0
        and a["signal_type"] == "🟢 شکست واقعی"
        and a["score"] >= 75
        and a["depth_ratio"] >= 2
        and a["distance_high"] <= 1.0
    )

    previous_count = int(old.get("consecutive_valid", 0))
    consecutive = previous_count + 1 if valid_now else 0

    a["consecutive_valid"] = consecutive
    a["stable"] = consecutive >= STABLE_REQUIRED

    previous_stable = bool(old.get("stable", False))
    previous_signal = old.get("signal_type", "")
    event = ""

    if a["stable"] and not previous_stable:
        event = "🟢 BREAKOUT CONFIRMED"
    elif previous_stable and not a["stable"]:
        event = "🔴 BREAKOUT FAILED"
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
        "last_seen": datetime.now().isoformat(timespec="seconds"),
    }

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
    print(f"نسبت عمق 5 ردیف: {a['depth_ratio']:.2f}")

    print()
    print(f"SCORE: {a['score']}/100")
    print(f"وضعیت امتیازی: {a['status']}")
    print(f"سیگنال: {a['signal_type']}")
    print(f"پایداری: {a.get('consecutive_valid', 0)}/{STABLE_REQUIRED}")

    if a.get("stable"):
        print("وضعیت زمانی: 🟢 شکست پایدار")
    elif a.get("consecutive_valid", 0) > 0:
        print("وضعیت زمانی: 🟡 در حال تأیید")
    else:
        print("وضعیت زمانی: ⚪ بدون تأیید زمانی")

    if a.get("event"):
        print(f"رویداد: {a['event']}")


def run_scan(state):
    print()
    print("=" * 70)
    print("        SCANNER 16 - PERIODIC REAL BREAKOUT")
    print("=" * 70)
    print(f"زمان اسکن: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        data = get_market()
    except Exception as e:
        print("خطا در دریافت بازار:")
        print(e)
        return state

    print(f"تعداد نمادهای دریافت‌شده: {len(data)}")

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
            print(f"{name} -> رد: رشد منفی یا صفر ({a['growth']:.2f}%)")
            reset_persistence(name, state)
            continue

        a = update_persistence(a, state)
        results.append(a)

    signal_order = {
        "🟢 شکست واقعی": 0,
        "🟡 کاندید شکست": 1,
        "🔵 صف خرید — شکست تأیید نشده": 2,
        "⚪ تحت نظر": 3,
    }

    results.sort(
        key=lambda x: (
            0 if x.get("stable") else 1,
            signal_order.get(x.get("signal_type", "⚪ تحت نظر"), 9),
            -x["score"],
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
        ("🟢 شکست واقعی", "REAL BREAKOUT"),
        ("🟡 کاندید شکست", "BREAKOUT CANDIDATES"),
        ("🔵 صف خرید — شکست تأیید نشده", "BUY QUEUE"),
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
    print("   پایش دوره‌ای فعال شد")
    print(f"   فاصله اسکن: {SCAN_INTERVAL} ثانیه (2 دقیقه)")
    print(f"   تأیید شکست پایدار: {STABLE_REQUIRED} اسکن متوالی")
    print(f"   فایل وضعیت: {STATE_FILE}")
    print("   برای توقف: Ctrl+C")
    print("=" * 70)

    while True:
        try:
            state = run_scan(state)
        except KeyboardInterrupt:
            print("\nپایش متوقف شد.")
            break
        except Exception as e:
            print("\nخطای غیرمنتظره:")
            print(e)

        print()
        print(f"⏳ اسکن بعدی تا {SCAN_INTERVAL} ثانیه دیگر...")

        try:
            time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print("\nپایش متوقف شد.")
            break


if __name__ == "__main__":
    main()
