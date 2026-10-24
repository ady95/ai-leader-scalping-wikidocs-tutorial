"""04-1·04-3 과거 급등 임계치 테이블 — HTS 스티커를 코드로

    uv run python -m scalping.ingestion.minute --rally     # 급등일 1분봉 수집 (처음 한 번)
    uv run python -m scalping.events.thresholds            # data/processed/rally_events.parquet

공개 영상(V1 01:00, 04:35, 10:26): 과거에 장대양봉이 나온 날 1분봉 거래대금이 얼마 터졌을 때 잘 갔는지를
종목마다 기록해 두고(스티커), 오늘 그보다 더 터지면 기준점이 생긴다.

이 책의 정의 (경계값은 이 책의 실험값)
1. 급등일: 장중 고가가 기준가보다 rally_high 이상, 종가가 rally_close 이상 오른 날 (장대양봉)
2. 발사봉: 그날 고가가 나오기 전의 깨끗한 1분봉(clean.py) 중 거래대금이 가장 큰 봉. 그 대금 = 그날의 필요 대금
   launch_max_ret 를 주면 그 상승률 아래(예: +10% 미만, 낮은 구간)의 봉만 본다 → "시발점" 변형 (04-3에서 비교)
3. 뉴스 근사: 장 시작 news_minutes 안에 상한가에 닿은 급등일은 "뉴스로 곧장 간 날"로 보고 테이블에서 뺀다
   (영상: 이런 날은 체크하지 않는다. 영상의 20% 할인 참고 방식은 discount 인자로 비교할 수 있다)
4. 임계치: 판단하는 날 **전날까지**의 급등일 발사봉 대금 중앙값 (lookback일 안, min_events개 이상)
"""

import pandas as pd

from scalping.events.clean import clean_flags
from scalping.leaders.kki import day_moves
from scalping.market import upper_limit
from scalping.paths import PROCESSED

EVENTS = PROCESSED / "rally_events.parquet"

DEFAULT = dict(rally_high=0.15, rally_close=0.10, news_minutes=10, lookback=250, min_events=1, launch_max_ret=None)


def rally_days(daily, rules=None):
    """일봉에서 급등일(장대양봉)을 고른다. 기준가는 전일 종가로 근사한다."""
    r = DEFAULT | (rules or {})
    d = day_moves(daily)
    d["close_up"] = d.close / d.base - 1
    return d[(d.up >= r["rally_high"]) & (d.close_up >= r["rally_close"])][["code", "date", "base", "up", "close_up", "limit"]]


def launch_bar(m, base, upper, rules=None):
    """한 종목·하루 1분봉에서 발사봉을 찾는다. 반환: dict(시각, 대금, 뉴스 근사 여부) 또는 None"""
    r = DEFAULT | (rules or {})
    x = clean_flags(m)
    peak_time = x.loc[x.high.idxmax(), "time"]
    first_limit = x[x.high >= upper].time.min()
    news_like = pd.notna(first_limit) and first_limit < x.time.min() + pd.Timedelta(minutes=r["news_minutes"])
    cand = x[(x.time <= peak_time) & x.clean]
    if r["launch_max_ret"] is not None:
        cand = cand[cand.close / base - 1 < r["launch_max_ret"]]
    if cand.empty:
        return dict(launch_time=None, launch_value=None, news_like=news_like, peak_time=peak_time)
    b = cand.loc[cand.value.idxmax()]
    return dict(launch_time=b.time, launch_value=float(b.value), news_like=bool(news_like), peak_time=peak_time,
                launch_ret=float(b.close / base - 1))


def threshold_at(events, day, rules=None, discount=None):
    """day 전날까지의 급등일 발사봉 대금으로 종목별 임계치를 만든다.

    events: rally_days + launch_bar 결과를 합친 표 (code, date, launch_value, news_like)
    discount: None이면 뉴스 근사 급등일을 뺀다. 0.2처럼 주면 그날 대금을 20% 깎아 넣는다(영상의 참고 방식).
    """
    r = DEFAULT | (rules or {})
    day = pd.Timestamp(day)
    e = events[(events.date < day) & (events.date >= day - pd.Timedelta(days=int(r["lookback"] * 1.45)))]
    e = e.dropna(subset=["launch_value"]).copy()
    e["news_like"] = e.news_like.astype(bool)     # 1분봉 없는 급등일이 섞이면 object 형식이 되어 ~ 가 정수를 낸다
    if discount is None:
        e = e[~e.news_like]
    else:
        e.loc[e.news_like, "launch_value"] *= 1 - discount
    g = e.groupby("code").launch_value
    out = pd.DataFrame({"threshold": g.median(), "n_events": g.size(), "last_event": e.groupby("code").date.max()})
    return out[out.n_events >= r["min_events"]]


def build_events(daily, minute_loader, rules=None):
    """급등일마다 발사봉을 찾아 이벤트 표를 만든다. minute_loader(day) → 그날 1분봉(분석 형식)"""
    rows = []
    for day, grp in rally_days(daily, rules).groupby("date"):
        m = minute_loader(day)
        have = set(m.code) if len(m) else set()
        for r in grp.itertuples():
            row = dict(code=r.code, date=day, up=r.up, close_up=r.close_up, has_minute=r.code in have)
            if r.code in have:
                row |= launch_bar(m[m.code == r.code], r.base, upper_limit(int(r.base)), rules)
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    from scalping.ingestion.daily import load_daily
    from scalping.ingestion.minute import load_minute
    ev = build_events(load_daily(), lambda d: load_minute(d, "J"))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    ev.to_parquet(EVENTS, index=False)
    ok = ev.dropna(subset=["launch_value"])
    print(f"급등일 {len(ev):,}건 (1분봉 있음 {ev.has_minute.sum():,}), 발사봉 {len(ok):,}건, "
          f"뉴스 근사 {int(ok.news_like.sum()):,}건, 발사봉 대금 중앙값 {ok.launch_value.median() / 1e8:.0f}억 → {EVENTS}")


if __name__ == "__main__":
    main()
