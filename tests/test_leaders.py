import pandas as pd

from scalping.config import load_config
from scalping.leaders import snapshot as snap
from scalping.leaders.daily_structure import daily_features
from scalping.leaders.kki import day_moves, kki
from scalping.leaders.themes import parse, theme_strength
from scalping.leaders.turnover import snapshot
from scalping.sample_market import BENCH, DAY, build

D = build()
MINUTE, DAILY, THEMES = D["minute"], D["daily"], D["themes"]
MARKET = D["master"].set_index("code").market
PREV = DAILY.groupby("code").close.last()
CFG = load_config()


def test_snapshot_uses_only_finished_bars():
    at = pd.Timestamp(f"{DAY} 10:00")
    s = snapshot(MINUTE, PREV, at, MARKET, BENCH)
    upto = MINUTE[MINUTE.time < at].groupby("code").value.sum()      # 09:59 봉까지 (10:00 봉은 아직 진행 중)
    assert (s.cum_value - upto.reindex(s.index)).abs().max() == 0


def test_raw_value_rank_picks_big_cap_not_leader():
    s = snapshot(MINUTE, PREV, pd.Timestamp(f"{DAY} 10:00"), MARKET, BENCH)
    assert s.index[0] == "910210" and s.ret.iloc[0] < 0.05
    assert all(c not in s.index for c in BENCH.values())


def test_theme_needs_two_rising_members():
    s = snapshot(MINUTE, PREV, pd.Timestamp(f"{DAY} 09:30"), MARKET, BENCH)
    assert (s.ret >= 0.05).sum() == 1 and theme_strength(s, THEMES).empty


def test_daily_features_ignore_the_day_itself():
    extra = DAILY.iloc[[-1]].assign(date=pd.Timestamp(DAY), high=10**9)
    a = daily_features(DAILY, DAY)
    b = daily_features(pd.concat([DAILY, extra]), DAY)
    assert a.equals(b)
    assert kki(day_moves(DAILY), DAY).equals(kki(day_moves(pd.concat([DAILY, extra])), DAY))


def test_leader_changes_intraday_and_no_trade_reason():
    feat, kt = daily_features(DAILY, DAY), kki(day_moves(DAILY), DAY)
    ev, reasons, _ = snap.build(MINUTE, PREV, pd.Timestamp(f"{DAY} 09:30"), THEMES, feat, kt, CFG, MARKET, BENCH)
    assert not ev and "함께 오르는 테마 없음" in reasons
    lead = {}
    for hhmm in ("10:00", "13:00"):
        ev, reasons, _ = snap.build(MINUTE, PREV, pd.Timestamp(f"{DAY} {hhmm}"), THEMES, feat, kt, CFG, MARKET, BENCH)
        lead[hhmm] = ev[0].symbol
        assert ev[0].observed_until <= ev[0].asof
    assert lead == {"10:00": "910010", "13:00": "910020"}


def test_parse_fixed_width_theme_line():
    line = "001가상테마".ljust(38) + "123456   "
    df = parse(line + "\n")
    assert df.iloc[0].to_dict() == {"theme_code": "001", "theme_name": "가상테마", "code": "123456"}
