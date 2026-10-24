"""07-1·07-2 시간 필터 — T0(없음) · T1(09:30 전 진입 금지) · T2(T1 + NXT 프리마켓 검증 종목 예외)

엔진(05·06장)을 no_entry_before "09:00" 으로 돌린 결정 표에 time_rule 을 덧붙인다.
config 의 b0.no_entry_before "09:30" 으로 엔진을 돌린 결과는 T1과 같다.

NXT 예외(공개 원칙, V1 13:29~13:57): 프리마켓(08:00~08:50)에서 거래가 크게 터지고 가격을 지킨 종목은
"내구성이 8시부터 확인"된 것으로 보고 9시 30분 제한을 두지 않는다. 기준값은 이 책의 실험값이다.
프리마켓은 08:50에 끝나므로 09:00 전에 판정이 끝난다 (미래 정보 없음).
"""

import pandas as pd


def premarket_check(un, prev_close, timing):
    """통합(UN) 1분봉 → 종목별 프리마켓 거래대금·고가·마지막 가격과 예외 여부"""
    pm = un[un.time.dt.strftime("%H:%M") < "08:50"].sort_values("time")
    g = pm.groupby("code")
    out = pd.DataFrame({"pm_value": g.value.sum(), "pm_high": g.high.max(), "pm_close": g.close.last()})
    out["prev_close"] = prev_close.reindex(out.index)
    out["exception"] = ((out.pm_value >= timing["nxt_min_value"])
                        & (out.pm_close >= out.pm_high * timing["nxt_hold_ratio"])
                        & (out.pm_close >= out.prev_close))
    return out


def time_rule(dec, mode, cutoff="09:30", exceptions=()):
    """READY 중 cutoff 전 체결을 BLOCK 한다. T2는 exceptions(프리마켓 검증 종목)를 막지 않는다."""
    out = dec.copy()
    if mode == "T0" or out.empty:
        return out
    early = (out.state == "READY") & (pd.to_datetime(out.fill_time).dt.strftime("%H:%M") < cutoff)
    if mode == "T2":
        early &= ~out.code.isin(set(exceptions))
    out.loc[early, "state"] = "BLOCK"
    out.loc[early, "reason"] = f"{mode}: {cutoff} 전 진입"
    return out


def first_cross(bars, prev_close, level=0.10):
    """한 종목·하루 1분봉에서 종가가 처음 전일 대비 +level 이상으로 끝난 봉 (없으면 None)"""
    hit = bars[bars.close >= prev_close * (1 + level)]
    return hit.iloc[0] if len(hit) else None


def race(after, p, up=0.05, dn=0.05):
    """p 이후 봉에서 +up 과 -dn 중 먼저 닿은 쪽. 같은 봉에서 둘 다 닿으면 순서를 모르므로 down(보수적)"""
    for hi, lo in zip(after.high.to_numpy(), after.low.to_numpy()):
        if lo <= p * (1 - dn):
            return "down"
        if hi >= p * (1 + up):
            return "up"
    return "none"
