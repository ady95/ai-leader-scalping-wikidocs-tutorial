"""04-6 햄버거 탐지기와 기준봉 차트

    uv run python examples/ch04_hamburger.py                       # 01장 가상 하루 (가상 임계치)
    uv run python examples/ch04_hamburger.py --day 20261023        # 실데이터 (03-2 수집 + 04-3 임계치 테이블)
    uv run python examples/ch04_hamburger.py --day 20261023 --code 000000

네 기준(abs·rel20·tod·thr)의 첫 이벤트를 보여 주고, 한 종목의 가격·거래대금 차트에 기준봉을 표시해
reports/ch04_<종목>_<날짜>.png 로 저장한다.
"""

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

from scalping.events.hamburger import detect, events
from scalping.paths import REPORTS, SAMPLE

_fonts = {f.name for f in font_manager.fontManager.ttflist}       # 설치된 한글 글꼴을 고른다 (Windows·macOS·Linux)
plt.rcParams["font.family"] = next((n for n in ("Malgun Gothic", "AppleGothic", "NanumGothic") if n in _fonts),
                                   "DejaVu Sans")
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.width", 160)


def load_sample():
    from scalping.sample import load
    d = load()
    m = d["bars"].assign(date=lambda x: x.time.dt.normalize())
    s = d["stocks"].set_index("code")
    return m, s.prev_close, s.threshold, None, None, m.date.iloc[0]


def load_real(day):
    from scalping.events.thresholds import EVENTS, threshold_at
    from scalping.features.minute import typical_daily_value
    from scalping.ingestion.daily import load_daily
    from scalping.ingestion.minute import load_minute
    m = load_minute(day, "J")
    daily = load_daily()
    prev = daily[daily.date < pd.Timestamp(day)].groupby("code").close.last()
    thr = threshold_at(pd.read_parquet(EVENTS), day).threshold if EVENTS.exists() else None
    if thr is None:
        print("임계치 테이블이 없습니다. 04-3을 먼저 실행하세요: python -m scalping.events.thresholds")
    profile = pd.read_csv(SAMPLE / "minute_profile.csv", index_col=0).iloc[:, 0]
    return m, prev, thr, profile, typical_daily_value(daily, day), pd.Timestamp(day)


def chart(x, e, code, threshold, out):
    s = x[x.code == code]
    ev = e[e.code == code].iloc[0]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    a1.plot(s.time, s.close, color="#333333", lw=1)
    a1.axhline(ev.ref_high, color="#d62728", ls="--", lw=1, label=f"기준봉 고가 {ev.ref_high:,.0f}")
    a1.axhline(ev.ref_low, color="#1f77b4", ls="--", lw=1, label=f"기준봉 저가 {ev.ref_low:,.0f}")
    a1.axvline(ev.time, color="#ff7f0e", lw=1)
    a1.set_ylabel("가격")
    a1.legend(loc="upper left", fontsize=8)
    colors = ["#ff7f0e" if t == ev.time else "#9e9e9e" for t in s.time]
    a2.bar(s.time, s.value / 1e8, width=1 / 1440, color=colors)
    if threshold is not None and code in threshold:
        a2.axhline(threshold[code] / 1e8, color="#d62728", ls=":", lw=1, label=f"과거 급등 임계치 {threshold[code] / 1e8:.0f}억")
        a2.legend(loc="upper left", fontsize=8)
    a2.set_ylabel("1분 거래대금(억)")
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    a1.set_title(f"{code} {ev.time:%Y-%m-%d} 햄버거 기준봉 {ev.time:%H:%M} (확정 {ev.available_at:%H:%M})")
    fig.tight_layout()
    fig.savefig(out, dpi=120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--code")
    a = ap.parse_args()
    m, prev, thr, profile, typical, day = load_real(a.day) if a.day else load_sample()
    x = detect(m, prev, threshold=thr, profile=profile, typical=typical)
    cols = ["code", "time", "value", "ret", "rel20", "tod", "thr", "close_location", "upper_wick"]
    first = {}
    for c in ("abs", "rel20", "tod", "thr"):
        e = events(x, c)
        first[c] = e
        print(f"\n[{c}] 깨끗한 첫 이벤트 {len(e)}건")
        if len(e):
            show = e.head(5)[[k for k in cols if k in e]]
            print(show.assign(value=(show.value / 1e8).round(1)).to_string(index=False, float_format="{:.2f}".format))
    e = first["thr"] if len(first["thr"]) else first["rel20"]
    if e.empty:
        return
    code = a.code or e.code.iloc[0]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"ch04_{code}_{day:%Y%m%d}.png"
    chart(x, e, code, thr, out)
    print(f"\n차트 → {out}")


if __name__ == "__main__":
    main()
