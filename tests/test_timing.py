import pandas as pd

from scalping.config import load_config
from scalping.strategies.timing import first_cross, premarket_check, race, time_rule

CFG = load_config()


def dec():
    t = pd.to_datetime(["2026-01-05 09:20", "2026-01-05 09:25", "2026-01-05 09:45"])
    return pd.DataFrame(dict(code=["A", "B", "C"], state="READY", reason="", fill_time=t))


def test_time_rule_modes():
    assert (time_rule(dec(), "T0").state == "READY").all()
    assert time_rule(dec(), "T1").state.tolist() == ["BLOCK", "BLOCK", "READY"]
    assert time_rule(dec(), "T2", exceptions={"B"}).state.tolist() == ["BLOCK", "READY", "READY"]


def test_premarket_exception_needs_value_and_hold():
    t = pd.date_range("2026-01-05 08:00", periods=50, freq="1min")
    a = pd.DataFrame(dict(code="A", time=t, high=1100, close=1080, value=3e8))         # 150억, 고가의 98%
    b = pd.DataFrame(dict(code="B", time=t, high=1100, close=1000, value=3e8))         # 150억, 고가의 91%
    c = pd.DataFrame(dict(code="C", time=t, high=1100, close=1080, value=1e8))         # 50억
    pm = premarket_check(pd.concat([a, b, c]), pd.Series({"A": 1000, "B": 1000, "C": 1000}), CFG["timing"])
    assert pm.exception.to_dict() == {"A": True, "B": False, "C": False}


def test_first_cross_and_race():
    t = pd.date_range("2026-01-05 09:00", periods=4, freq="1min")
    b = pd.DataFrame(dict(time=t, high=[105, 112, 118, 119], low=[100, 104, 109, 103], close=[104, 111, 116, 105]))
    hit = first_cross(b, 100)
    assert hit.time == t[1] and hit.close == 111
    assert race(b.iloc[2:], 111) == "up"                  # 118 >= 111 x 1.05 = 116.55
    assert race(b.iloc[3:], 111) == "down"                # 103 <= 105.45
