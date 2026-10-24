"""06-4 파동 순번과 재활용 규칙 — 돌파(05장)·눌림(06장) 엔진의 READY에 공통으로 덧붙인다

    파동 1 : 아직 의미 있는 조정 없이 오르는 중 (낮은 구간 돌파는 대개 1파동)
    파동 2 : 한 번 조정을 받은 뒤 — 재활용 매매. 이 책은 수량을 wave2_size 배로 줄인다
    파동 3+: 두 번 이상 조정을 받은 뒤 — 공개 영상 "세 번째부터 확률이 많이 떨어진다" → 이 책은 진입 제외

조정 한 번 = 그날 고점(그때까지의 최고가)에서 retrace 이상 내려간 일. 새 고점을 만들어야 다음 조정을 셀 수 있다.
t 시각 **전에 끝난** 봉만 쓴다 (시점 정합).
"""

import math

import pandas as pd


def wave_marks(bars, t, retrace=0.04):
    """bars: 한 종목·하루 1분봉(시각 순). t 이전에 끝난 봉 중 조정 한 번으로 센 봉의 시각 목록."""
    done = bars[bars.time + pd.Timedelta(minutes=1) <= t]
    peak, counted, marks = None, False, []
    for tm, hi, lo in zip(done.time, done.high.to_numpy(), done.low.to_numpy()):
        if peak is None or hi > peak:
            peak, counted = hi, False               # 새 고점 → 다음 조정을 셀 수 있다
            continue                                # 같은 봉 안에서 고점과 저점의 순서는 알 수 없으므로 세지 않는다
        if not counted and lo <= peak * (1 - retrace):
            marks.append(tm)
            counted = True
    return marks


def wave_index(bars, t, retrace=0.04):
    """t 시각의 파동 순번 = 그때까지 센 조정 횟수 + 1"""
    return len(wave_marks(bars, t, retrace)) + 1


def wave_rule(dec, minute, cfg):
    """결정 표(05·06장 엔진의 run 결과)의 READY에 파동 순번을 붙이고 규칙을 적용한다."""
    pb = cfg["pullback"]
    bars = {c: g.sort_values("time") for c, g in minute.groupby("code")}
    out = dec.copy()
    out["wave"] = None
    if out.empty:                                   # 그날 해당 구간 이벤트가 없으면 빈 표 그대로
        return out
    for i, r in out[out.state == "READY"].iterrows():
        w = wave_index(bars[r.code], r.fill_time, pb["wave_retrace"])
        out.at[i, "wave"] = w
        if w > pb["max_wave"]:
            out.at[i, "state"], out.at[i, "reason"] = "BLOCK", f"{w}파동: 진입 제외"
        elif w >= 2:
            qty = math.floor(r.qty * pb["wave2_size"])
            out.at[i, "qty"] = qty
            if qty <= 0:
                out.at[i, "state"], out.at[i, "reason"] = "BLOCK", "수량 0주(2파동 비중 축소)"
    return out
