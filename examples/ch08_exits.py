"""08-6 청산 엔진과 10,030원 매수 가상 예제

    uv run python examples/ch08_exits.py                     # 10,030원 가상 예제 + 01장 가상 하루
    uv run python examples/ch08_exits.py --day 20261023      # 실데이터: 05장 READY + 07장 재료 라벨(ch07 예제를 먼저 실행)

정책 X0~X4로 같은 포지션을 재생해 청산 타임라인과 비용을 뺀 손익을 보여 주고
reports/ch08_trades_<날짜>.csv 로 저장한다.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from scalping.config import load_config
from scalping.events.hamburger import detect, events
from scalping.exits.engine import Position, simulate
from scalping.exits.levels import resistance, take_profit
from scalping.paths import REPORTS, SAMPLE
from scalping.risk.sizing import size
from scalping.strategies import breakout
from scalping.strategies.waves import wave_rule

pd.set_option("display.width", 200)
sys.path.insert(0, str(Path(__file__).parent))
from ch04_hamburger import load_real, load_sample  # noqa: E402

POLICIES = ["X0", "X1", "X2", "X3", "X4"]


def virtual_bars():
    """기준 고점 10,000원 돌파 → 10,030원 매수 뒤의 가상 경로 (08-6 설명용으로 만든 값)"""
    head = [(9990, 10060, 9980, 10050), (10050, 10140, 10040, 10130), (10130, 10180, 10100, 10170),
            (10170, 10260, 10160, 10250), (10250, 10300, 10220, 10280), (10280, 10360, 10270, 10340),
            (10340, 10420, 10330, 10400), (10400, 10410, 10300, 10320)]
    t = list(pd.date_range("2026-01-05 10:00", "2026-01-05 15:19", freq="1min")) + [pd.Timestamp("2026-01-05 15:30")]
    rest = []
    for i in range(len(t) - len(head)):                                # 그 뒤 15:30까지 10,320 → 10,150 으로 천천히
        c = round((10320 - 170 * (i + 1) / (len(t) - len(head))) / 10) * 10
        rest.append((c, c + 10, c - 10, c))
    return pd.DataFrame(head + rest, columns=["open", "high", "low", "close"]).assign(code="V", time=t)


def run(p, b, cfg):
    out = []
    for pol in POLICIES:
        r = simulate(p, b, cfg, pol)
        s = r.summary(p, cfg["costs"])
        tl = ", ".join(f"{t:%H:%M} {q}주@{px:,} {why}" for t, q, px, why in r.fills)
        out.append(dict(policy=pol, code=p.code, net=round(s["net"]), r=round(s["r"], 2), timeline=tl))
    return pd.DataFrame(out)


def virtual(cfg):
    entry, stop = 10030, 9930
    s = size(entry, stop, 1e12, cfg["account"])
    hist = pd.DataFrame(dict(date=pd.date_range("2025-10-01", periods=60, freq="B"), high=10000.0, close=9800.0))
    hist.loc[hist.index[-40], "high"] = 10350.0                          # 두 달 전 고점 = 저항선
    lv, name = resistance(hist, pd.Timestamp("2026-01-05"), entry)
    tgt, why = take_profit(entry, lv, True, cfg)
    print(f"[가상] 매수 {entry:,}원 · 손절 {stop:,}원 · 1R {entry - stop}원 · {s['qty']}주(한도 {s['binding']}) · "
          f"저항선 {lv:,.0f}원({name}) → 익절 {tgt:,}원({why})")
    p = Position("V", pd.Timestamp("2026-01-05 10:00"), entry, s["qty"], stop, False, True, tgt, why)
    return run(p, virtual_bars(), cfg)


def materials(day):
    path = REPORTS / f"ch07_candidates_{pd.Timestamp(day):%Y%m%d}.csv"
    if not path.exists():
        print(f"{path.name} 이 없어 재료를 모름(None)으로 둡니다. 07-5 예제를 먼저 실행하세요")
        return {}
    c = pd.read_csv(path, dtype={"code": str})
    return {r.code: (None if pd.isna(r.has_material) else bool(r.has_material)) for r in c.itertuples()}


def real(day, cfg):
    m, prev, thr, profile, typical, d = load_real(day) if day else load_sample()
    ev = events(detect(m, prev, threshold=thr, profile=profile, typical=typical), "thr")
    bo = wave_rule(breakout.run(ev, m, cfg), m, cfg)
    mats = materials(d)
    if day:
        from scalping.ingestion.daily import load_daily
        daily = load_daily()
    else:                                                              # 가상 하루: 일봉 이력 대신 전일 종가만
        st = pd.read_csv(SAMPLE / "stocks.csv", dtype={"code": str})
        daily = pd.DataFrame(dict(code=st.code, date=pd.Timestamp(d) - pd.Timedelta(days=3), high=st.prev_close,
                                  close=st.prev_close))
    out = []
    for r in bo[bo.state == "READY"].itertuples():
        dc = daily[daily.code == r.code].sort_values("date")
        lv, _ = resistance(dc, pd.Timestamp(d), r.fill_price, cfg["exits"]["resistance_windows"],
                           cfg["exits"]["resistance_min_room"])
        mat = mats.get(r.code)
        tgt, why = take_profit(r.fill_price, lv, mat, cfg)
        p = Position(r.code, pd.Timestamp(r.fill_time), int(r.fill_price), int(r.qty), int(r.stop),
                     bool(r.gap_fill), mat, tgt, why)
        print(f"[{r.code}] 매수 {p.entry:,}원 {p.qty}주 · 손절 {p.stop:,}원 · 재료 {mat} · 익절 {tgt and f'{tgt:,}'}원({why})")
        out.append(run(p, m[m.code == r.code].sort_values("time"), cfg))
    return pd.concat(out, ignore_index=True), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    a = ap.parse_args()
    cfg = load_config()
    frames = []
    if not a.day:
        v = virtual(cfg)
        print(v.to_string(index=False), "\n")
        frames.append(v)
    t, d = real(a.day, cfg)
    print(t.to_string(index=False))
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"ch08_trades_{pd.Timestamp(d):%Y%m%d}.csv"
    pd.concat(frames + [t]).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"→ reports/{path.name}")


if __name__ == "__main__":
    main()
