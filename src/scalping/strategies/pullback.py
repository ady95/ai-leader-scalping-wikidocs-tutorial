"""06장 눌림·재상승 매수 엔진

입력: 04장 햄버거 이벤트(주로 높은 구간 — 05장에서 BLOCK된 것) + 그날 1분봉.

    지지 후보 (06-2) : 기준봉이 뚫은 전고점, 기준봉 몸통 하단, 그 시각까지의 VWAP, 기준봉 저가
    눌림     (06-1) : 기준봉 확정 뒤 어떤 봉의 저가가 지지 후보 중 하나에 닿음 (가장 높은 후보부터)
    무효화          : 종가가 기준봉 저가 아래로 마감 (기준봉 붕괴) → INVALID
    재상승 확인 (06-3): 눌림 뒤 양봉이 직전 봉 고가 위에서 마감 → **다음 봉 시가**에 진입
                       (확인은 봉이 끝나야 알 수 있다. 확인 봉 안에서 사면 미래 정보)
    손절            : 눌림 저점 - 1호가와 진입가 -max_loss 중 진입가에 가까운 쪽
    파동 (06-4)     : run()이 waves.wave_rule 로 3파동 이상 BLOCK, 2파동 수량 축소
기준값(watch_bars, wave_retrace, wave2_size)은 모두 이 책의 실험값이다.
"""

from dataclasses import asdict, dataclass, fields

import pandas as pd

from scalping.market import add_ticks, ceil_tick
from scalping.risk.sizing import size
from scalping.strategies.breakout import zone_of
from scalping.strategies.waves import wave_rule


ZONE_KO = {"low": "낮은", "mid": "중간", "high": "높은"}


@dataclass
class PullbackDecision:
    code: str
    event_time: pd.Timestamp
    zone: str
    state: str                      # READY / BLOCK / INVALID / EXPIRED
    reason: str
    support: str | None = None      # 닿은 지지 후보 이름
    support_price: float | None = None
    touch_time: pd.Timestamp | None = None
    confirm_time: pd.Timestamp | None = None
    fill_time: pd.Timestamp | None = None
    fill_price: int | None = None
    pullback_low: int | None = None
    stop: int | None = None
    qty: int | None = None
    risk_pct: float | None = None
    depth: float | None = None      # 기준봉 뒤 고점 대비 눌림 깊이


def supports(ev, bars_upto):
    """지지 후보: 이름 → 가격. VWAP는 bars_upto(그 시각까지 끝난 봉)로 계산한다."""
    vwap = bars_upto.value.sum() / max(bars_upto.volume.sum(), 1)
    sup = {"body_low": float(min(ev.open, ev.close)), "vwap": float(vwap), "ref_low": float(ev.ref_low)}
    before = bars_upto[bars_upto.time < ev.time]
    if len(before) and before.high.max() < ev.ref_high:         # 기준봉이 뚫고 올라간 그날의 전고점
        sup["prev_high"] = float(before.high.max())
    return sup


def decide(ev, bars, cfg, zones=("high",)):
    b0, pb, costs, account = cfg["b0"], cfg["pullback"], cfg["costs"], cfg["account"]
    zone = zone_of(ev.ret, b0)
    d = PullbackDecision(code=ev.code, event_time=ev.time, zone=zone, state="BLOCK", reason="")
    if zone not in zones:
        d.reason = f"{ZONE_KO[zone]} 구간: 눌림 엔진 대상 아님"
        return d
    after = bars[bars.time >= ev.available_at].reset_index(drop=True).head(pb["watch_bars"] + 1)
    peak, touched, low_since = float(ev.ref_high), None, None
    for i in range(len(after)):
        bar = after.iloc[i]
        if bar.close < ev.ref_low:
            d.state, d.reason = "INVALID", f"{bar.time:%H:%M} 기준봉 저가 아래 마감"
            return d
        if touched is None:
            peak = max(peak, float(bar.high))
            upto = bars[bars.time <= bar.time]
            sup = supports(ev, upto)
            for name in sorted(sup, key=sup.get, reverse=True):   # 가격이 높은 지지부터
                if bar.low <= sup[name] < peak:
                    touched, d.support, d.support_price, d.touch_time = name, name, sup[name], bar.time
                    low_since = int(bar.low)
                    d.depth = 1 - bar.low / peak
                    break
            continue
        low_since = min(low_since, int(bar.low))
        prev = after.iloc[i - 1]
        if bar.close > bar.open and bar.close > prev.high and i + 1 < len(after):
            nxt = after.iloc[i + 1]
            d.confirm_time, d.fill_time = bar.time, nxt.time
            d.fill_price = add_ticks(int(nxt.open), costs["slippage_ticks"])
            d.pullback_low = low_since
            break
    else:
        d.state = "EXPIRED"
        d.reason = "눌림 없음" if touched is None else "재상승 확인 없음"
        return d
    if d.fill_time.strftime("%H:%M") < b0["no_entry_before"]:
        d.reason = f"{b0['no_entry_before']} 전 진입"
        return d
    d.stop = max(add_ticks(d.pullback_low, -1), ceil_tick(d.fill_price * (1 - b0["max_loss"])))
    s = size(d.fill_price, d.stop, ev.value, account)
    d.qty, d.risk_pct = s["qty"], s.get("risk_pct")
    if s["qty"] <= 0:
        d.reason = f"수량 0주({s['binding']})"
        return d
    d.state, d.reason = "READY", "눌림 후 재상승 확인"
    return d


def run(events, minute, cfg, zones=("high",)):
    out = []
    by_code = {c: g.sort_values("time").reset_index(drop=True) for c, g in minute.groupby("code")}
    for ev in events.itertuples():
        out.append(asdict(decide(ev, by_code[ev.code], cfg, zones)))
    cols = [f.name for f in fields(PullbackDecision)]               # 이벤트가 없어도 열은 갖춘 빈 표
    return wave_rule(pd.DataFrame(out, columns=cols), minute, cfg)
