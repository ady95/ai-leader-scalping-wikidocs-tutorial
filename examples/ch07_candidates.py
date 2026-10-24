"""07-5 시간 필터와 재료 라벨이 붙은 후보 만들기

    uv run python examples/ch07_candidates.py                       # 01장 가상 하루 (가상 뉴스)
    uv run python examples/ch07_candidates.py --day 20261023        # 실데이터: 04-6 준비물 + 통합(UN) 분봉 + 뉴스 제목 API

1) 05·06장 엔진을 시간 제한 없이(no_entry_before 09:00) 돌리고 파동 규칙을 붙인다
2) T0·T1·T2 시간 필터를 각각 적용한다 (T2의 NXT 예외는 통합 분봉의 프리마켓으로 판정)
3) 이벤트마다 그 시각 전의 뉴스·공시 제목을 모으고 LLM으로 재료를 분류한다 (.env 에 OPENAI_* 가 없으면 건너뜀)
→ reports/ch07_candidates_<날짜>.csv, reports/ch07_materials_<날짜>.json
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import pandas as pd

from scalping.config import load_config
from scalping.events.hamburger import detect, events
from scalping.materials import classify as C
from scalping.materials.news import align
from scalping.paths import REPORTS, SAMPLE
from scalping.strategies import breakout, pullback
from scalping.strategies.timing import premarket_check, time_rule
from scalping.strategies.waves import wave_rule

pd.set_option("display.width", 220)
sys.path.insert(0, str(Path(__file__).parent))
from ch04_hamburger import load_real, load_sample  # noqa: E402


def sample_titles():
    """01장 가상 하루의 가상 뉴스를 07-3의 제목 표 형식으로"""
    s = pd.read_csv(SAMPLE / "stocks.csv", dtype={"code": str}).set_index("code").name
    n = pd.read_csv(SAMPLE / "news.csv", dtype={"code": str}, parse_dates=["time"])
    return n.assign(source="가상통신", codes=n.code.map(lambda c: [c]), names=n.code.map(lambda c: [s[c]])), s


def titles_for(day, real, sample, code, until):
    if not real:
        t = sample[sample.code == code]
        return t[t.time < until].reset_index(drop=True)
    from scalping.ingestion.daily import load_daily
    from scalping.kis import KIS
    from scalping.materials.news import collect
    dates = sorted(load_daily().date.unique())
    prev_day = max(d for d in dates if d < pd.Timestamp(day))
    titles_for.kis = getattr(titles_for, "kis", None) or KIS("real")
    return collect(titles_for.kis, code, day, prev_day, until)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    a = ap.parse_args()
    m, prev, thr, profile, typical, day = load_real(a.day) if a.day else load_sample()
    cfg = load_config()
    cfg0 = copy.deepcopy(cfg)
    cfg0["b0"]["no_entry_before"] = "09:00"                       # 시간 제한은 아래 time_rule 이 건다
    ev = events(detect(m, prev, threshold=thr, profile=profile, typical=typical), "thr")
    dec = pd.concat([wave_rule(breakout.run(ev, m, cfg0), m, cfg0).assign(engine="breakout"),
                     pullback.run(ev, m, cfg0).assign(engine="pullback")], ignore_index=True)
    dec = dec[(dec.engine == "breakout") == (dec.zone == "low")]   # 낮은 구간은 돌파, 그 밖은 눌림 엔진의 결정

    exceptions = set()
    if a.day:
        from scalping.ingestion.minute import load_minute
        un = load_minute(a.day, "UN")
        if len(un):
            pm = premarket_check(un, prev, cfg["timing"])
            exceptions = set(pm.index[pm.exception])
            print(f"NXT 프리마켓 검증 종목 {len(exceptions)}개 (통합 분봉 {un.code.nunique()}종목 중)")
    cut = cfg["b0"]["no_entry_before"]
    for mode in ("T0", "T1", "T2"):
        dec[mode] = time_rule(dec, mode, cut, exceptions).state

    sample, names = (None, None) if a.day else sample_titles()
    llm = bool(os.getenv("OPENAI_API_KEY")) or (C.ROOT / ".env").exists()
    client, model = C.client_from_env() if llm else (None, None)
    if not client or not model:
        print("LLM 설정(.env 의 OPENAI_*)이 없어 재료 분류를 건너뜁니다")
    cache, labels = C.load_cache(), {}
    for r in dec.itertuples():
        until = pd.Timestamp(r.event_time) + pd.Timedelta(minutes=1)     # 기준봉이 확정된 시각 (04-1)
        t = titles_for(day, bool(a.day), sample, r.code, until)
        lb = dict(code=r.code, until=str(until), **align(t, r.code, until))
        if model:
            name = names[r.code] if names is not None else next(
                (n for c, n in zip(t.codes.explode(), t.names.explode()) if c == r.code), r.code)
            lb.update(C.label(client, model, r.code, name, until, t, cache))
        labels[r.code] = lb
    L = pd.DataFrame(labels.values()).set_index("code")
    out = dec.join(L[[c for c in ("n_titles", "n_own", "has_material", "type", "strength", "price_only") if c in L]], on="code")
    show = out.assign(event=pd.to_datetime(out.event_time).dt.strftime("%H:%M"),
                      fill=pd.to_datetime(out.fill_time).dt.strftime("%H:%M").fillna(""),
                      strength=out.get("strength", pd.Series(dtype=object)).map(lambda v: "" if pd.isna(v) else int(v)))
    cols = ["code", "event", "zone", "engine", "fill", "T0", "T1", "T2", "n_titles", "n_own", "type", "strength", "price_only"]
    print(show[[c for c in cols if c in show]].to_string(index=False))
    REPORTS.mkdir(exist_ok=True)
    stem = f"{pd.Timestamp(day):%Y%m%d}"
    out.to_csv(REPORTS / f"ch07_candidates_{stem}.csv", index=False, encoding="utf-8-sig")
    (REPORTS / f"ch07_materials_{stem}.json").write_text(json.dumps(list(labels.values()), ensure_ascii=False, indent=1,
                                                                    default=str), encoding="utf-8")
    print(f"→ reports/ch07_candidates_{stem}.csv, reports/ch07_materials_{stem}.json")


if __name__ == "__main__":
    main()
