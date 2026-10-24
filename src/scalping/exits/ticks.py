"""08-2 체결 원문(틱)으로 판정하기 — 1~2분 시간손절과 돌파 체결

1분봉 판정이 거친 이유
- 봉 중간에 산 돌파는 그 봉의 고가가 매수 전인지 뒤인지 모른다 → 1분봉 엔진은 체결 봉의 종가만 쓴다
- "2분"이 실제로는 체결 시각에 따라 2분~3분 사이로 들쭉날쭉하다 (2번째 봉이 끝난 뒤 다음 봉 시가에 판다)
틱(03-2 실시간 수집기의 H0STCNT0)이 있으면 체결 시각부터 정확히 N초를 재고, 그동안의 최고 체결가로 판정한다.
과거 기간은 틱이 없으므로 1분봉 판정을 쓰고, 그것이 근사라는 것을 결과에 표시한다.
"""

import pandas as pd

from scalping.market import add_ticks


def with_times(trades, day):
    """load_trades 결과의 time(HHMMSS 문자열)을 그날 시각 t 로"""
    t = pd.to_datetime(pd.Timestamp(day).strftime("%Y-%m-%d ") + trades.time.astype(str).str.zfill(6), format="%Y-%m-%d %H%M%S")
    return trades.assign(t=t).sort_values(["t", "recv_ns"], kind="stable", ignore_index=True)


def breakout_fill(trades, code, after, trigger):
    """after 이후 처음으로 trigger 이상에 체결된 틱 — 돌파 주문이 실제로 걸렸을 시각과 그때의 체결가"""
    x = trades[(trades.code == code) & (trades.t >= after) & (trades.price >= trigger)]
    return None if x.empty else x.iloc[0]


def fast_stop(trades, code, fill_t, entry, cfg):
    """체결 뒤 fast_stop_bars 분 동안 최고 체결가가 entry x (1 + fast_min_gain)에 못 미치면,
    그 시각 직후 첫 체결가(에서 슬리피지만큼 불리하게)에 판다. 판정이 '유지'면 None."""
    sec = cfg["b0"]["fast_stop_bars"] * 60
    end = fill_t + pd.Timedelta(seconds=sec)
    x = trades[trades.code == code]
    win = x[(x.t > fill_t) & (x.t <= end)]
    best = int(win.price.max()) if len(win) else entry
    if best >= entry * (1 + cfg["exits"]["fast_min_gain"]):
        return None
    nxt = x[x.t > end].head(1)
    if nxt.empty:
        return None
    px = add_ticks(int(nxt.price.iloc[0]), -cfg["costs"]["slippage_ticks"])
    return dict(time=nxt.t.iloc[0], price=px, best=best, seconds=sec)
