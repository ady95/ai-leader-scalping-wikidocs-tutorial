"""08장 청산 엔진 — 1분봉으로 한 포지션을 장 마감까지 재생한다

청산 정책 (12-5의 X군)
    X0  구조적 손절 + 단일 고정 목표(+fixed_target_r R)
    X1  공개 원칙: 구조적 손절·3% 상한 + 1~2분 시간손절 + 저항선 직전 익절 + 재료 없으면 3%
    X2  구조적 손절 + +1R 50% · +2R 25% 분할익절 (연구 가설)
    X3  구조적 손절 + 추적손절 (연구 가설)
    X4  X2 + 추적손절 + 표준 시간손절 (연구 가설)
모든 정책은 남은 수량을 장 마감 단일가(15:30 봉 종가)에 판다. 다음 날까지 들고 가는 것은 09장.

한 봉 안의 순서 (08-5) — 1분봉은 봉 안의 순서를 모르므로 보수적으로 정한다
    0) 앞 봉에서 예약한 시장가 청산(시간손절)을 이 봉 시가에
    1) 시가가 이미 목표 이상이면 그 목표를 시가에 (갭 익절)
    2) 저가가 손절가 이하면 남은 수량 전부 손절 — 같은 봉에서 목표에도 닿았어도 손절로 본다
    3) 목표 지정가: 고가가 목표 + 1호가 이상일 때만 체결 (목표가에 닿기만 한 것은 체결로 보지 않는다)
    4) 봉이 끝난 뒤: 고점·추적손절가 갱신, 시간손절 판정 → 다음 봉 시가 청산 예약
체결 봉: 돌파처럼 봉 중간에 산 경우(fill_at_open=False) 그 봉의 고가·저가는 매수 전일 수 있어 쓰지 않고,
         종가만 "매수 뒤 가격"으로 쓴다. 시가에 산 경우(눌림·갭)는 그 봉 전체가 매수 뒤다.
"""

from dataclasses import dataclass, field

import pandas as pd

from scalping.market import add_ticks, floor_tick


@dataclass
class Position:
    code: str
    entry_time: pd.Timestamp
    entry: int
    qty: int
    stop: int                       # 진입 엔진이 정한 최초 손절가 (05-3, 06-3)
    fill_at_open: bool = False
    material: bool | None = None    # 07-4 재료 라벨 (None = 모름)
    target: int | None = None       # X1 익절 목표 (levels.take_profit)
    target_reason: str | None = None


@dataclass
class Result:
    fills: list = field(default_factory=list)   # (시각, 수량, 가격, 사유)

    def summary(self, pos, costs):
        sold = sum(q for _, q, _, _ in self.fills)
        gross = sum((p - pos.entry) * q for _, q, p, _ in self.fills)
        cost = pos.entry * pos.qty * costs["commission"] + sum(p * q * (costs["commission"] + costs["sell_tax"])
                                                              for _, q, p, _ in self.fills)
        net = gross - cost
        risk = (pos.entry - pos.stop) * pos.qty
        last = self.fills[-1] if self.fills else (None, 0, 0, "")
        return dict(code=pos.code, entry_time=pos.entry_time, entry=pos.entry, qty=pos.qty, sold=sold,
                    net=net, cost=cost, ret=net / (pos.entry * pos.qty), r=net / risk if risk > 0 else None,
                    exit_time=last[0], exit_reason=last[3], first_reason=self.fills[0][3] if self.fills else "",
                    hold_min=(last[0] - pos.entry_time).total_seconds() / 60 if last[0] is not None else None)


def plan_targets(pos, cfg, policy):
    """정책별 지정가 목표 [(가격, 수량 비율, 사유)]"""
    ex, R = cfg["exits"], pos.entry - pos.stop
    if policy == "X0":
        return [(floor_tick(pos.entry + ex["fixed_target_r"] * R), 1.0, f"+{ex['fixed_target_r']:g}R 목표")]
    if policy == "X1":
        return [(pos.target, 1.0, pos.target_reason)] if pos.target else []
    if policy in ("X2", "X4"):
        return [(floor_tick(pos.entry + r * R), frac, f"+{r:g}R 분할") for r, frac in ex["partial"]]
    return []


def simulate(pos, bars, cfg, policy="X1"):
    """bars: 그 종목·그날 1분봉(시각 순). 체결 목록이 담긴 Result 를 돌려준다."""
    ex, slip = cfg["exits"], cfg["costs"]["slippage_ticks"]
    R = pos.entry - pos.stop
    trail = policy in ("X3", "X4")
    fast = policy == "X1"
    targets = [[t, max(int(pos.qty * f), 1), why] for t, f, why in plan_targets(pos, cfg, policy) if t]
    after = bars[bars.time >= pos.entry_time.floor("min")].reset_index(drop=True)
    res, left, stop, stop_why = Result(), pos.qty, pos.stop, "손절"
    hi, last_new_hi, pending = pos.entry, 0, None

    def sell(t, q, px, why):
        nonlocal left
        q = min(q, left)
        if q > 0:
            res.fills.append((t, q, int(px), why))
            left -= q

    def mkt(px):
        return add_ticks(int(px), -slip)                                 # 시장가 매도는 불리한 쪽으로

    for i, bar in after.iterrows():
        if pending:                                                      # 0) 예약된 시장가 청산
            sell(bar.time, left, mkt(bar.open), pending)
            break
        last = i == len(after) - 1
        usable = i > 0 or pos.fill_at_open                               # 체결 봉의 고가·저가를 쓸 수 있나
        if usable:
            for tg in targets:                                           # 1) 갭 익절
                if tg[1] and bar.open >= tg[0]:
                    sell(bar.time, tg[1], bar.open, tg[2])
                    tg[1] = 0
            if left and bar.low <= stop:                                 # 2) 손절 (보수적으로 먼저)
                sell(bar.time, left, mkt(min(bar.open, stop)), stop_why)
            for tg in targets:                                           # 3) 지정가 목표
                if left and tg[1] and bar.high >= add_ticks(tg[0], 1):
                    sell(bar.time, tg[1], tg[0], tg[2])
                    tg[1] = 0
        if not left:
            break
        if last:                                                         # 장 마감 단일가
            sell(bar.time, left, mkt(bar.close), "장 마감")
            break
        # 4) 봉이 끝난 뒤의 갱신 — 다음 봉부터 적용
        seen_hi = bar.high if usable else bar.close
        if seen_hi > hi:
            hi, last_new_hi = seen_hi, i
        if trail:
            if hi >= pos.entry + R and stop < pos.entry:
                stop, stop_why = pos.entry, "본전 손절"
            if hi >= pos.entry + 2 * R:
                new = floor_tick(hi - ex["trail_r"] * R)
                if new > stop:
                    stop, stop_why = new, "추적 손절"
        if fast and i + 1 == cfg["b0"]["fast_stop_bars"] and hi < pos.entry * (1 + ex["fast_min_gain"]):
            pending = "1~2분 시간손절"
        if policy == "X4" and i - last_new_hi >= ex["time_stop_bars"]:
            pending = "표준 시간손절"
    return res
