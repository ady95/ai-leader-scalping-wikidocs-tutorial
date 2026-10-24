from types import SimpleNamespace

import pandas as pd

from scalping.config import load_config
from scalping.risk.sizing import size, stop_price
from scalping.strategies.breakout import decide

CFG = load_config()


def test_stop_and_size_match_chapter1_example():
    stop = stop_price(10_780, 10_450, 0.03)
    assert stop == 10_460                                         # 01-5 로그와 같은 손절가
    s = size(10_780, stop, ref_value=62e8, account=CFG["account"])
    assert s["qty"] == 78 and s["binding"] == "risk"


def bars(times, opens, highs, code="A"):
    t = pd.to_datetime(times)
    return pd.DataFrame({"code": code, "time": t, "open": opens, "high": highs, "low": opens, "close": opens,
                         "value": 1e8})


def event(ret, t="2026-01-05 10:41", ref_high=10_760, ref_low=10_450):
    t = pd.Timestamp(t)
    return SimpleNamespace(code="A", time=t, available_at=t + pd.Timedelta(minutes=1), ret=ret,
                           ref_high=ref_high, ref_low=ref_low, value=62e8)


def test_high_zone_is_blocked_for_pullback():
    d = decide(event(0.17), bars(["2026-01-05 10:42"], [10_800], [10_900]), CFG)
    assert d.state == "BLOCK" and "눌림" in d.reason


def test_breakout_fill_at_trigger_plus_slippage():
    b = bars(["2026-01-05 10:42", "2026-01-05 10:43"], [10_700, 10_750], [10_750, 10_800])
    d = decide(event(0.074), b, CFG)
    assert d.state == "READY" and d.bars_to_break == 2 and d.fill_price == 10_780 and not d.gap_fill


def test_gap_open_fills_at_open():
    d = decide(event(0.074), bars(["2026-01-05 10:42"], [10_900], [10_950]), CFG)
    assert d.gap_fill and d.fill_price == 10_910


def test_expires_without_breakout_and_blocks_before_0930():
    b = bars(["2026-01-05 10:42", "2026-01-05 10:43", "2026-01-05 10:44", "2026-01-05 10:45"],
             [10_700] * 4, [10_700, 10_700, 10_700, 10_900])
    assert decide(event(0.074), b, CFG).state == "EXPIRED"          # 4번째 봉의 돌파는 유효 시간 밖
    early = decide(event(0.074, "2026-01-05 09:20"), bars(["2026-01-05 09:21"], [10_700], [10_800]), CFG)
    assert early.state == "BLOCK" and "09:30" in early.reason
