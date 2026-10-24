"""05-5 돌파 진입 엔진 — WAIT · READY · BLOCK

    uv run python examples/ch05_breakout.py                       # 01장 가상 하루
    uv run python examples/ch05_breakout.py --day 20261023        # 실데이터 (04-6과 같은 준비물)

04장 탐지기의 과거 임계치 햄버거(깨끗한 첫 이벤트)마다 돌파 엔진의 결정을 보여 주고
reports/ch05_decisions_<날짜>.csv 로 저장한다. 실데이터 모드는 NO_TRADE(02-5)를 적용하지 않는다
(지수 ETF 1분봉이 필요하다).
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from scalping.config import load_config
from scalping.events.hamburger import detect, events
from scalping.paths import REPORTS
from scalping.strategies.breakout import run

pd.set_option("display.width", 180)
sys.path.insert(0, str(Path(__file__).parent))     # 04-6 예제의 데이터 읽기 함수를 같이 쓴다


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    a = ap.parse_args()
    if a.day:
        from ch04_hamburger import load_real as load
        m, prev, thr, profile, typical, day = load(a.day)
    else:
        from ch04_hamburger import load_sample
        m, prev, thr, profile, typical, day = load_sample()
    cfg = load_config()
    x = detect(m, prev, threshold=thr, profile=profile, typical=typical)
    ev = events(x, "thr")
    d = run(ev, m, cfg)
    show = d[["code", "event_time", "zone", "state", "reason", "trigger", "fill_time", "fill_price", "stop", "qty",
              "risk_pct"]].copy()
    for c in ("event_time", "fill_time"):
        show[c] = pd.to_datetime(show[c]).dt.strftime("%H:%M")
    for c in ("trigger", "fill_price", "stop", "qty"):
        show[c] = show[c].astype("Int64").astype(str).replace("<NA>", "")
    print(show.to_string(index=False, na_rep="", float_format="{:.4f}".format))
    print("\n상태별", d.state.value_counts().to_dict())
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"ch05_decisions_{pd.Timestamp(day):%Y%m%d}.csv"
    d.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
