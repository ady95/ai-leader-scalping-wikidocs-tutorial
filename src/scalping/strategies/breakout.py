"""05장 가격 위치에 따른 돌파매수 엔진 — WAIT · READY · BLOCK

입력: 04장 햄버거 이벤트(기준봉) + 그날 1분봉. 이벤트마다 하나의 결정 기록을 만든다.

    BLOCK  위치(높은·중간 구간), 시간(09:30 전 진입), NO_TRADE, 위험 심사(손절가 이상·0주)로 진입하지 않음
    WAIT   기준봉 확정 뒤 고가 + 1호가 돌파 주문을 걸고 기다림 → valid_bars 안에 닿지 않으면 EXPIRED
    READY  돌파 체결 + 위험 심사 통과 → 주문 (수량·손절가 포함)

1분봉 체결 모형 (실험값, 틱으로 검증 예정 — 05-4)
- 돌파 봉의 시가가 이미 트리거 이상이면 시가에, 아니면 트리거에 체결된 것으로 본다
- 그 가격에서 불리한 쪽으로 slippage_ticks 호가를 더한다
- 돌파 봉의 거래대금·종가는 체결 시점에는 모른다 → 진입 판단에 쓰지 않는다 (미래 정보)
"""

from dataclasses import asdict, dataclass

import pandas as pd

from scalping.market import add_ticks
from scalping.risk.sizing import size, stop_price


@dataclass
class Decision:
    code: str
    event_time: pd.Timestamp
    available_at: pd.Timestamp
    zone: str
    state: str                  # READY / BLOCK / EXPIRED
    reason: str
    trigger: int | None = None
    fill_time: pd.Timestamp | None = None
    fill_price: int | None = None
    gap_fill: bool | None = None
    bars_to_break: int | None = None
    stop: int | None = None
    qty: int | None = None
    binding: str | None = None
    risk_pct: float | None = None
    ref_value: float | None = None


def zone_of(ret, b0):
    if ret >= b0["high_zone_min"]:
        return "high"
    return "low" if ret < b0["low_zone_max"] else "mid"


def decide(ev, bars, cfg, no_trade=False):
    """한 이벤트(04장 events 표의 한 행)와 그 종목의 그날 1분봉(시각 순)으로 결정을 내린다."""
    b0, costs, account = cfg["b0"], cfg["costs"], cfg["account"]
    zone = zone_of(ev.ret, b0)
    d = Decision(code=ev.code, event_time=ev.time, available_at=ev.available_at, zone=zone, state="BLOCK",
                 reason="", ref_value=float(ev.value))
    if no_trade:
        d.reason = "NO_TRADE(02-5)"
        return d
    if zone == "high":
        d.reason = "높은 구간: 추격 금지, 눌림 대기(06장)"
        return d
    if zone == "mid" and not b0.get("mid_zone_breakout", False):
        d.reason = "중간 구간: 이 책의 실험 대상(12장)"
        return d
    d.trigger = add_ticks(int(ev.ref_high), 1)
    after = bars[bars.time >= ev.available_at].head(b0["breakout_valid_bars"])
    hit = after[after.high >= d.trigger]
    if hit.empty:
        d.state, d.reason = "EXPIRED", f"{b0['breakout_valid_bars']}개 봉 안에 돌파 없음"
        return d
    bar = hit.iloc[0]
    d.bars_to_break = int(after.index.get_loc(hit.index[0])) + 1
    if bar.time.strftime("%H:%M") < b0["no_entry_before"]:
        d.reason = f"{b0['no_entry_before']} 전 돌파"
        return d
    d.gap_fill = bool(bar.open >= d.trigger)
    d.fill_time = bar.time
    d.fill_price = add_ticks(int(max(bar.open, d.trigger)), costs["slippage_ticks"])
    d.stop = stop_price(d.fill_price, ev.ref_low, b0["max_loss"])
    s = size(d.fill_price, d.stop, ev.value, account)
    d.qty, d.binding, d.risk_pct = s["qty"], s["binding"], s.get("risk_pct")
    if s["qty"] <= 0:
        d.reason = f"수량 0주({s['binding']})"
        return d
    d.state, d.reason = "READY", "돌파 체결"
    return d


def run(events, minute, cfg, no_trade_times=None):
    """이벤트 표 전체에 decide를 적용한다. no_trade_times: 이벤트 확정 시각 → NO_TRADE 여부(함수)"""
    out = []
    bars_by_code = {c: g.sort_values("time").reset_index(drop=True) for c, g in minute.groupby("code")}
    for ev in events.itertuples():
        nt = bool(no_trade_times(ev.available_at)) if no_trade_times else False
        out.append(asdict(decide(ev, bars_by_code[ev.code], cfg, nt)))
    return pd.DataFrame(out)
