import requests
import time

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

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

WATCHLIST = [
    "ذوب",
    "خودرو",
    "وبصادر",
    "فولاد",
    "اهرم",
    "دارا يكم",
    "تمشك",
    "خزاميا",
    "تاپيكو",
    "دلقما",
    "شتران",
    "دكوثر",
    "خبهمن",
    "حفاري",
    "كوچين",
]

def f(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except:
        return default

def get_market():
    r = requests.get(
        URL,
        params=PARAMS,
        headers=HEADERS,
        timeout=20
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

    close = f(x.get("pcl"))
    yesterday = f(x.get("py"))

    value = f(x.get("qtc"))
    volume = f(x.get("qtj"))
    trades = f(x.get("ztt"))

    high = f(x.get("pmx"))
    low = f(x.get("pmn"))

    # درصد رشد واقعی نسبت به قیمت پایه دیروز
    if yesterday > 0:
        growth = ((last - yesterday) / yesterday) * 100
    else:
        growth = 0

    # فاصله قیمت فعلی تا سقف
    if high > 0 and last > 0:
        distance_high = ((high - last) / last) * 100
    else:
        distance_high = 999

    books = x.get("blDs", [])

    buy1 = 0
    sell1 = 0
    buy5 = 0
    sell5 = 0

    for row in books[:5]:
        buy = f(row.get("qmd"))
        sell = f(row.get("qmo"))

        buy5 += buy
        sell5 += sell

    if books:
        buy1 = f(books[0].get("qmd"))
        sell1 = f(books[0].get("qmo"))

    # نسبت تقاضای ردیف اول
    if buy1 > 0 and sell1 > 0:
        order_ratio = buy1 / sell1
    elif buy1 > 0 and sell1 <= 0:
        order_ratio = 999
    else:
        order_ratio = 0

    # امتیازدهی
    score = 0

    # رشد
    if 1.5 <= growth <= 3.2:
        score += 20
    elif 0 < growth < 1.5:
        score += 5
    elif growth > 3.2:
        score += 10

    # عمق 5 ردیف
    if buy5 > 0 and sell5 > 0:
        depth_ratio = buy5 / sell5
    else:
        depth_ratio = 0

    # قدرت تقاضای ردیف اول
    # نسبت ردیف اول باید با عمق 5 ردیف تأیید شود.
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

        # اگر عمق 5 ردیف کمتر از 1 باشد،
        # نسبت سنگین ردیف اول تأیید نشده است.
        if depth_ratio < 1:
            order_score = min(order_score, 5)

        # عمق بین 1 و 2 تأیید متوسط محسوب می‌شود.
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

    # وضعیت شکست واقعی
    # امتیاز بالا به تنهایی کافی نیست؛ عمق سفارش باید تأیید کند.
    if depth_ratio >= 2 and score >= 75:
        status = "🟢 شکست معتبر"
    elif depth_ratio >= 1 and score >= 60:
        status = "🟡 کاندید شکست"
    else:
        status = "⚪ تحت نظر"
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
    }


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
    print(f"سیگنال: {a.get('signal_type', 'نامشخص')}")


def main():

    print()
    print("=" * 70)
    print("        SCANNER 15 - REAL BREAKOUT")
    print("=" * 70)

    try:
        data = get_market()
    except Exception as e:
        print("خطا در دریافت بازار:")
        print(e)
        return

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

        # رشد منفی: فعلاً وارد هیچ‌کدام از گروه‌های شکست نمی‌شود.
        if a["growth"] <= 0:
            print(f"{name} -> رد: رشد منفی یا صفر ({a['growth']:.2f}%)")
            continue

        # صف خرید کامل:
        # قدرت خرید بالاست، اما شکست واقعی با عرضه قابل مشاهده تأیید نشده.
        if a["sell5"] <= 0:
            a["signal_type"] = "🔵 صف خرید — شکست تأیید نشده"
            results.append(a)
            continue

        # عرضه وجود دارد؛ حالا کیفیت شکست را بررسی می‌کنیم.
        if a["score"] >= 75 and a["depth_ratio"] >= 2:
            a["signal_type"] = "🟢 شکست واقعی"
        elif a["score"] >= 50 and a["depth_ratio"] >= 1:
            a["signal_type"] = "🟡 کاندید شکست"
        else:
            a["signal_type"] = "⚪ تحت نظر"

            reasons = []

            if a["depth_ratio"] < 1:
                reasons.append(f"عمق {a['depth_ratio']:.2f} < 1")

            if a["distance_high"] > 2:
                reasons.append(f"فاصله سقف {a['distance_high']:.2f}%")

            if a["score"] < 50:
                reasons.append(f"امتیاز {a['score']}/100")

            a["signal_reason"] = " | ".join(reasons) if reasons else "تأیید کامل نشده"

        results.append(a)

    # اولویت نمایش سیگنال‌ها
    signal_order = {
        "🟢 شکست واقعی": 0,
        "🟡 کاندید شکست": 1,
        "🔵 صف خرید — شکست تأیید نشده": 2,
        "⚪ تحت نظر": 3,
    }

    results.sort(
        key=lambda x: (
            signal_order.get(x.get("signal_type", "⚪ تحت نظر"), 9),
            -x["score"]
        )
    )

    print()
    print("=" * 70)
    print("          TOP BREAKOUT CANDIDATES")
    print("=" * 70)

    groups = [
        ("🟢 شکست واقعی", "REAL BREAKOUT"),
        ("🟡 کاندید شکست", "BREAKOUT CANDIDATES"),
        ("🔵 صف خرید — شکست تأیید نشده", "BUY QUEUE"),
        ("⚪ تحت نظر", "WATCH"),
    ]

    for signal_type, title in groups:
        group = [
            a for a in results
            if a.get("signal_type") == signal_type
        ]

        if not group:
            continue

        print()
        print("=" * 70)
        print(f"          {title}")
        print("=" * 70)

        for a in group:
            show(a)

    positive_count = len(results)
    negative_count = sum(
        1 for name in WATCHLIST
        if (find_symbol(data, name) is not None
            and analyze(find_symbol(data, name)) is not None
            and analyze(find_symbol(data, name))["growth"] <= 0)
    )

    print()
    print("=" * 70)
    print(f"نمادهای دارای سیگنال: {positive_count}")
    print(f"حذف‌شده به علت رشد منفی یا صفر: {negative_count}")
    print(f"کل واچ‌لیست: {len(WATCHLIST)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
