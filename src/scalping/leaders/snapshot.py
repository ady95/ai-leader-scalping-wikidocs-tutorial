"""02-5 시점별 주도주 후보 스냅샷(CandidateEvent)과 NO_TRADE

at 시각에 알 수 있던 정보만으로 후보를 고른다.
- 1분봉: at 전에 끝난 봉만 (turnover.snapshot)
- 일봉 구조·끼: 전날까지 일봉으로 장 시작 전에 계산해 둔 표
- 테마: 테마-종목 표 (주의: 과거 날짜에는 그 뒤에 생긴 테마가 섞일 수 있다 — 02-2)
"""

from dataclasses import asdict, dataclass

import pandas as pd

from scalping.leaders.daily_structure import daily_eval, price_zone
from scalping.leaders.themes import theme_strength
from scalping.leaders.turnover import snapshot

SCORE_VERSION = "leader-v1"


@dataclass
class CandidateEvent:
    symbol: str
    asof: str               # 이 스냅샷을 만든 시각
    observed_until: str     # 사용한 마지막 1분봉이 끝난 시각
    theme: str
    leader_rank: int
    leader_score: float
    ret: float
    cum_value: float
    zone: str               # 일봉 저항 기준 위치 (below / excite / above)
    daily_ok: bool
    n_big: int              # 끼: 최근 장중 +20% 이상 오른 날 수
    score_version: str = SCORE_VERSION
    source: str = "replay"


def leader_scores(snap, strength, themes, min_ret):
    """상승 종목 중 주도 테마에 속한 종목의 점수 = (거래대금 순위, 상대강도, 테마 비중)의 백분위 평균.
    세 항목을 같은 무게로 본 것은 이 책의 실험값이다."""
    hot = snap[snap.ret >= min_ret].copy()
    member = themes[themes.theme_code.isin(strength.index)].merge(
        strength[["theme_name", "value_share"]], left_on="theme_code", right_index=True, suffixes=("", "_s"))
    best = member.sort_values("value_share", ascending=False).drop_duplicates("code").set_index("code")
    hot = hot.join(best[["theme_name", "value_share"]].rename(columns={"value_share": "theme_share"}), how="inner")
    if hot.empty:
        return hot
    rs = hot.rel_strength if "rel_strength" in hot else hot.ret
    hot["leader_score"] = (hot.cum_value.rank(pct=True) + rs.rank(pct=True) + hot.theme_share.rank(pct=True)) / 3
    return hot.sort_values("leader_score", ascending=False)


def build(minute, prev_close, at, themes, daily_feat, kki_table, cfg, market=None, bench=None):
    """at 시각의 후보 목록과 NO_TRADE 사유를 돌려준다."""
    c = cfg["leaders"]
    snap = snapshot(minute, prev_close, at, market, bench)
    observed_until = minute[minute.time + pd.Timedelta(minutes=1) <= at].time.max() + pd.Timedelta(minutes=1)
    reasons = []
    if "bench_ret" in snap and snap.bench_ret.min() <= c["market_drop"]:
        reasons.append(f"시장 약세(지수 {snap.bench_ret.min():+.1%})")
    strength = theme_strength(snap, themes, c["min_ret"], c["min_up"])
    if strength.empty:
        reasons.append("함께 오르는 테마 없음")
    scored = leader_scores(snap, strength, themes, c["min_ret"]) if not strength.empty else snap.iloc[:0]
    scored = scored[scored.price >= c["min_price"]]
    if len(scored) and scored.cum_value.iloc[0] < c["min_value"]:
        reasons.append(f"거래대금 부족(1위 {scored.cum_value.iloc[0] / 1e8:.0f}억)")
    scored = scored.join(daily_feat[["resistance"]], how="left").join(kki_table[["n_big"]], how="left")
    zone = price_zone(scored.price, scored.resistance)
    ok = daily_eval(daily_feat).approve.reindex(scored.index).fillna(False)
    events = [CandidateEvent(symbol=code, asof=str(at), observed_until=str(observed_until), theme=r.theme_name,
                             leader_rank=i + 1, leader_score=round(r.leader_score, 3), ret=round(r.ret, 4),
                             cum_value=float(r.cum_value), zone=str(zone[code]), daily_ok=bool(ok[code]),
                             n_big=int(r.n_big) if pd.notna(r.n_big) else 0)
              for i, (code, r) in enumerate(scored.head(c["top_k"]).iterrows())]
    return events, reasons, strength


def to_frame(events):
    return pd.DataFrame([asdict(e) for e in events])
