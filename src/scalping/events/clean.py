"""04-4 깨끗한 기준봉: "누구나 살 수 있는 구간"에서 터진 봉을 걸러 낸다

공개 영상의 제외 대상(V1 03:24~06:20): 장 극초반 시가 매매, VI로 갭이 뜬 상황, 뉴스 직후, 쉬지 않고 오른 꼭대기.
1분봉만으로는 VI·뉴스를 직접 알 수 없으므로 아래 근사를 쓴다. 경계값은 모두 이 책의 실험값이다.
- early    : 09:00~(early_until) 봉
- vi_like  : 직전 1분봉이 비어 있거나(체결 없는 분), 시가가 직전 종가보다 vi_gap 이상 벌어진 봉
- run_top  : 직전 run_bars개 봉 동안 run_ret 이상 쉬지 않고 오른 뒤의 봉 (꼭대기 근사)
- quiet    : 직전 quiet_bars개 봉의 고저 폭 (작을수록 고요한 흐름 뒤의 폭발)
뉴스는 07장에서 뉴스 제목으로 직접 확인한다. 이 절의 뉴스 근사는 급등일 쪽(thresholds.py)에서만 쓴다.
"""

import pandas as pd

DEFAULT = dict(early_until="09:15", vi_gap=0.02, run_bars=10, run_ret=0.05, quiet_bars=20)


def clean_flags(m, rules=None):
    """1분봉(종목·하루, 시각 순)에 노이즈 표시와 직전 흐름의 고요함을 붙인다."""
    r = DEFAULT | (rules or {})
    x = m.sort_values(["code", "time"]).copy()
    g = x.groupby(["code", "date"])
    hh = x.time.dt.strftime("%H:%M")
    gap_min = g.time.diff().dt.total_seconds().div(60)
    prev_close = g.close.shift()
    x["early"] = hh < r["early_until"]
    x["vi_like"] = (gap_min > 1) & (hh != "15:30") | ((x.open / prev_close - 1).abs() >= r["vi_gap"])
    x["run_ret"] = g.close.shift(1) / g.close.shift(r["run_bars"] + 1) - 1
    x["run_top"] = x.run_ret >= r["run_ret"]
    hi = g.high.transform(lambda s: s.shift(1).rolling(r["quiet_bars"], min_periods=5).max())
    lo = g.low.transform(lambda s: s.shift(1).rolling(r["quiet_bars"], min_periods=5).min())
    x["quiet_range"] = hi / lo - 1
    x["closing"] = hh == "15:30"                      # 장 마감 단일가 봉 (03-3)
    x["clean"] = ~(x.early | x.vi_like | x.run_top | x.closing)
    return x
