"""02-3 일봉 구조: 전고점 저항, 박스권, 상방 매물대, 설레는 구간

장중 판단에 쓰므로 **판단하는 날의 전날까지** 일봉만 쓴다.
일봉 표의 열: date, code, open, high, low, close, volume, value
"""

import pandas as pd


def daily_features(daily, day, high_days=120, box_days=40, supply_days=120):
    """day 전날까지의 일봉으로 종목별 일봉 구조를 계산한다.

    resistance  : 최근 high_days일 최고가 (전고점 저항)
    dist_high   : 전일 종가가 저항보다 몇 % 아래인가 (0이면 신고가 부근)
    box_width   : 최근 box_days일 고가·저가 폭 (작을수록 박스권)
    overhead    : 최근 supply_days일 거래대금 중 전일 종가보다 비싼 가격에서 거래된 비중 (상방 매물대)
    """
    hist = daily[daily.date < pd.Timestamp(day)].sort_values(["code", "date"])
    g = hist.groupby("code")
    out = pd.DataFrame({"prev_close": g.close.last(), "n_days": g.size()})
    out["resistance"] = g.tail(high_days).groupby("code").high.max()
    box = g.tail(box_days).groupby("code")
    out["box_width"] = box.high.max() / box.low.min() - 1
    out["dist_high"] = out.prev_close / out.resistance - 1
    sup = g.tail(supply_days)
    typical = (sup.high + sup.low + sup.close) / 3
    above = sup.value.where(typical > sup.code.map(out.prev_close), 0)
    out["overhead"] = above.groupby(sup.code).sum() / sup.groupby("code").value.sum()
    return out


def price_zone(price, resistance, excite=0.05):
    """현재가와 저항의 관계: 돌파(above) / 설레는 구간(excite, 저항 아래 excite 이내) / 아래(below)"""
    gap = price / resistance - 1
    return pd.cut(gap, [-float("inf"), -excite, 0, float("inf")], labels=["below", "excite", "above"], right=False)


def daily_eval(feat, max_overhead=0.2):
    """일봉 평가표 (02-3): 상방 매물대가 가벼운 종목을 승인한다. 기준값 20%는 이 책의 실험값.

    박스 폭은 승인 조건에 넣지 않는다. 2025-10~2026-10 실측에서 대장주의 40일 박스 폭(중앙값 97%)이
    다른 급등주(80%)보다 오히려 넓어, 고정된 폭 기준은 대장주를 먼저 떨어뜨렸다(02-3).
    """
    ok = feat.overhead <= max_overhead
    reason = pd.Series("", index=feat.index).where(ok, "매물대 무거움")
    return pd.DataFrame({"approve": ok, "reason": reason})
