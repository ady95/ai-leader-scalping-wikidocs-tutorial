"""06-5 눌림 진입 엔진 — 돌파 엔진(05장)과 같은 이벤트에 나란히 적용

    uv run python examples/ch06_pullback.py                       # 01장 가상 하루
    uv run python examples/ch06_pullback.py --day 20261023        # 실데이터 (04-6과 같은 준비물)
    uv run python examples/ch06_pullback.py --day 20261023 --code 000000   # 한 종목 눌림·파동 차트

낮은 구간은 돌파 엔진이, 높은 구간은 눌림 엔진이 맡는다. 두 엔진의 READY에는 같은 파동 규칙(06-4)을 적용한다.
이벤트마다 맡은 엔진의 결정을 한 줄로 보여 주고 reports/ch06_decisions_<날짜>.csv 로 저장한다.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from scalping.config import load_config
from scalping.events.hamburger import detect, events
from scalping.paths import REPORTS
from scalping.strategies import breakout, pullback
from scalping.strategies.waves import wave_marks, wave_rule

pd.set_option("display.width", 200)
sys.path.insert(0, str(Path(__file__).parent))
from ch04_hamburger import load_real, load_sample  # noqa: E402  (글꼴 설정도 함께 가져온다)


def chart(m, d, code, retrace, out):
    """눌림 결정 하나: 가격, 지지선, 닿음·확인·체결 시각, 파동으로 센 조정 지점"""
    s = m[m.code == code].sort_values("time")
    r = d[d.code == code].iloc[0]
    end = r.fill_time if pd.notna(r.fill_time) else s.time.iloc[-1] + pd.Timedelta(minutes=1)
    s = s[s.time <= end + pd.Timedelta(minutes=60)]                 # 체결 뒤 1시간까지만 그린다
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(s.time, s.low, s.high, color="#cccccc", step="post", label="1분봉 고가~저가")
    ax.plot(s.time, s.close, color="#333333", lw=1, drawstyle="steps-post", label="종가")
    ax.axvline(r.event_time, color="#ff7f0e", lw=1, label=f"기준봉 {r.event_time:%H:%M}")
    if pd.notna(r.support_price):
        ax.axhline(r.support_price, color="#2ca02c", ls="--", lw=1, label=f"지지 {r.support} {r.support_price:,.0f}")
    for name, t, c in (("닿음", r.touch_time, "#2ca02c"), ("확인", r.confirm_time, "#1f77b4"), ("체결", r.fill_time, "#d62728")):
        if pd.notna(t):
            ax.axvline(t, color=c, ls=":", lw=1.2, label=f"{name} {t:%H:%M}")
    for i, t in enumerate(wave_marks(s, end, retrace), start=1):
        lo = s.loc[s.time == t, "low"].iloc[0]
        ax.annotate(f"조정 {i}", (t, lo), xytext=(0, -18), textcoords="offset points", ha="center", fontsize=8,
                    color="#9467bd", arrowprops=dict(arrowstyle="-", color="#9467bd"))
    ax.set_title(f"{code} {r.event_time:%Y-%m-%d} 눌림 엔진: {r.state} ({r.reason})")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_ylabel("가격")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--code")
    a = ap.parse_args()
    m, prev, thr, profile, typical, day = load_real(a.day) if a.day else load_sample()
    cfg = load_config()
    ev = events(detect(m, prev, threshold=thr, profile=profile, typical=typical), "thr")
    bo = wave_rule(breakout.run(ev, m, cfg), m, cfg)
    pb = pullback.run(ev, m, cfg)
    t = lambda s: pd.to_datetime(s).dt.strftime("%H:%M")
    n = lambda s: s.map(lambda v: "" if pd.isna(v) else str(int(v)))      # 빈 값은 빈칸으로
    out = pd.DataFrame({"code": bo.code, "event": t(bo.event_time), "zone": bo.zone,
                        "breakout": bo.state + " " + bo.reason.where(bo.state != "READY", ""),
                        "pullback": pb.state + " " + pb.reason.where(pb.state != "READY", ""),
                        "support": pb.support.fillna(""), "pb_fill": t(pb.fill_time).fillna(""),
                        "pb_price": n(pb.fill_price), "wave": n(pb.wave.where(bo.zone != "low", bo.wave))})
    out.loc[out.zone == "low", "pullback"] = "-"
    out.loc[out.zone != "low", "breakout"] = "-"
    print(out.to_string(index=False))
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"ch06_decisions_{pd.Timestamp(day):%Y%m%d}.csv"
    pd.concat([bo.assign(engine="breakout"), pb.assign(engine="pullback")]).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"→ {path.relative_to(REPORTS.parent).as_posix()}")
    if a.code:
        out = REPORTS / f"ch06_{a.code}_{pd.Timestamp(day):%Y%m%d}.png"
        chart(m, pb, a.code, cfg["pullback"]["wave_retrace"], out)
        print(f"차트 → {out.relative_to(REPORTS.parent).as_posix()}")


if __name__ == "__main__":
    main()
