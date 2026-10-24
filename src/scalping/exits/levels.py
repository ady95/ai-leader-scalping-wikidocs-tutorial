"""08-3 저항선과 익절 목표

저항선 = 진입가보다 위에 있는 가장 가까운 전고점. 후보는 최근 N거래일 일봉 고가의 최댓값(20·60·120일)과 상한가.
"저항선 직전 익절"은 저항선보다 1호가 아래에 매도 지정가를 둔다 (공개 원칙: "집에 가기 전", 신고가 직전 매도).
일봉은 **전날까지**만 쓴다. 오늘 일봉 고가는 장이 끝나야 안다.
"""

from scalping.market import add_ticks, floor_tick, upper_limit


def resistance(daily_code, day, entry, windows=(20, 60, 120), min_room=0.01):
    """한 종목 일봉(date 순)에서 진입가 x (1 + min_room) 이상인 가장 가까운 전고점과 그 창 이름. 없으면 상한가."""
    past = daily_code[daily_code.date < day]
    cands = []
    for w in windows:
        if len(past):
            cands.append((float(past.high.tail(w).max()), f"{w}일 고점"))
    if len(past):
        cands.append((float(upper_limit(int(past.close.iloc[-1]))), "상한가"))
    above = sorted([c for c in cands if c[0] >= entry * (1 + min_room)], key=lambda c: c[0])   # 같은 가격이면 짧은 창
    return above[0] if above else (None, None)


def take_profit(entry, level, material, cfg):
    """X1 익절 목표: 저항선 1호가 아래. 재료가 없으면 +no_news_take_profit 과 저항 직전 중 낮은 쪽."""
    b0 = cfg["b0"]
    t_res = add_ticks(int(level), -1) if level else None
    if material is False:
        t3 = floor_tick(entry * (1 + b0["no_news_take_profit"]))
        if t_res is None or t3 <= t_res:
            return t3, "재료 없음 3%"
    if t_res is None:
        return None, None
    return t_res, "저항 직전"
