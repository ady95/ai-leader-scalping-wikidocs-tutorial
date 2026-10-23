import importlib.util

from scalping.config import load_config
from scalping.paths import ROOT
from scalping.sample import build

spec = importlib.util.spec_from_file_location("ch01_replay", ROOT / "examples" / "ch01_replay.py")
ch01 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch01)


def run():
    return ch01.DayReplay(build(), load_config()).run()


def test_sample_is_deterministic():
    log1, trades1 = run()
    log2, trades2 = run()
    assert log1.equals(log2) and trades1.equals(trades2)


def test_each_scenario_ends_as_designed():
    log, trades = run()
    reason = trades.set_index("code").reason
    assert "3% 익절" in reason["900010"]
    assert "초단기 시간손절" in reason["900020"]
    assert "다음 날 시가" in reason["900030"]
    blocked = log[(log.code == "900040") & (log.state == "BLOCKED")].msg
    assert len(blocked) == 2 and "09:30 전" in blocked.iloc[0] and "높은 구간" in blocked.iloc[1]


def test_decisions_use_only_finished_bars():
    log, _ = run()
    locked = log[log.state == "EVENT_LOCKED"]
    for r in locked.itertuples():
        bar_time = r.msg.split("기준봉 ")[1][:5]
        assert r.at.strftime("%H:%M") > bar_time      # 기준봉이 끝난 뒤에야 잠근다
