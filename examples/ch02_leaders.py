"""02장 주도 섹터·대장주 — 가상 시장 하루로 절마다 결과를 본다.

    uv run python examples/ch02_leaders.py turnover   # 02-1 거래대금 순위 vs 급등 종목 순위
    uv run python examples/ch02_leaders.py themes     # 02-2 시각별 주도 테마
    uv run python examples/ch02_leaders.py daily      # 02-3 일봉 구조와 평가표
    uv run python examples/ch02_leaders.py kki        # 02-4 종목의 끼
    uv run python examples/ch02_leaders.py snapshot   # 02-5 5분마다 후보 스냅샷과 NO_TRADE
"""

import json
import sys
from dataclasses import asdict

import pandas as pd

from scalping.config import load_config
from scalping.leaders import snapshot as snap
from scalping.leaders.daily_structure import daily_eval, daily_features, price_zone
from scalping.leaders.kki import day_moves, kki
from scalping.leaders.themes import theme_strength
from scalping.leaders.turnover import snapshot
from scalping.paths import REPORTS
from scalping.sample_market import BENCH, DAY, load

pd.set_option("display.width", 140)
data = load()
minute, daily, themes = data["minute"], data["daily"], data["themes"]
master = data["master"].set_index("code")
market = master.market
prev_close = daily[daily.date < DAY].groupby("code").close.last()
names = master.name
cfg = load_config()


def at(hhmm):
    return pd.Timestamp(f"{DAY} {hhmm}")


def turnover():
    s = snapshot(minute, prev_close, at("10:00"), market, BENCH)
    cols = ["cum_value", "ret", "rel_strength", "value_rank"]
    show = lambda df: df[cols].assign(name=names, cum_value=lambda x: (x.cum_value / 1e8).round(1)).head(5)
    print("10:00 거래대금 순위 (단위: 억)\n", show(s).to_string(float_format="{:.3f}".format))
    print("\n10:00 +5% 이상 종목 안에서 거래대금 순위\n", show(s[s.ret >= 0.05]).to_string(float_format="{:.3f}".format))


def themes_cmd():
    for hhmm in ("09:30", "10:00", "11:00", "13:00", "15:31"):
        s = snapshot(minute, prev_close, at(hhmm), market, BENCH)
        ts = theme_strength(s, themes, cfg["leaders"]["min_ret"], cfg["leaders"]["min_up"])
        txt = ", ".join(f"{r.theme_name}({r.n_up}종목 {r.value_share:.0%}, 대장 {r.leader})" for r in ts.itertuples())
        print(f"{hhmm}  {txt or '함께 오르는 테마 없음'}")


def daily_cmd():
    feat = daily_features(daily, DAY)
    s = snapshot(minute, prev_close, at("10:00"), market, BENCH)
    hot = s[s.ret >= 0.05].join(feat[["resistance", "dist_high", "box_width", "overhead"]])
    hot["zone"] = price_zone(hot.price, hot.resistance)
    hot = hot.join(daily_eval(feat))
    print(hot[["price", "resistance", "zone", "box_width", "overhead", "approve", "reason"]]
          .to_string(float_format="{:.2f}".format))


def kki_cmd():
    k = kki(day_moves(daily), DAY).join(names).sort_values(["n_big", "max_up"], ascending=False)
    print(k.head(8).to_string(float_format="{:.3f}".format))


def snapshot_cmd():
    feat, kt = daily_features(daily, DAY), kki(day_moves(daily), DAY)
    rows, events = [], []
    times = pd.date_range(at("09:30"), at("15:15"), freq=f"{cfg['leaders']['every_minutes']}min")
    for t in times:
        ev, reasons, _ = snap.build(minute, prev_close, t, themes, feat, kt, cfg, market, BENCH)
        events += ev
        rows.append(dict(at=t.strftime("%H:%M"), no_trade="; ".join(reasons), n=len(ev),
                         top=ev[0].symbol if ev else "", theme=ev[0].theme if ev else "",
                         score=ev[0].leader_score if ev else None))
    df = pd.DataFrame(rows)
    print(df[df["at"].isin(["09:30", "09:45", "10:00", "11:00", "12:00", "13:00", "14:00", "15:15"])].to_string(index=False))
    tops = df.top[df.top != ""]
    switches = (tops != tops.shift()).iloc[1:].sum()
    print(f"\n스냅샷 {len(df)}개, NO_TRADE {(df.no_trade != '').sum()}개, 1위 후보가 바뀐 횟수 {switches}")
    print("\n10:00 CandidateEvent 한 건:")
    print(json.dumps(asdict(next(e for e in events if e.asof.endswith("10:00:00"))), ensure_ascii=False, indent=1))
    REPORTS.mkdir(exist_ok=True)
    snap.to_frame(events).to_csv(REPORTS / "ch02_candidates.csv", index=False, encoding="utf-8-sig")


CMDS = dict(turnover=turnover, themes=themes_cmd, daily=daily_cmd, kki=kki_cmd, snapshot=snapshot_cmd)

if __name__ == "__main__":
    CMDS[sys.argv[1] if len(sys.argv) > 1 else "snapshot"]()
