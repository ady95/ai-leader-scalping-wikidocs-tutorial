from types import SimpleNamespace

import pandas as pd

from scalping.config import load_config
from scalping.strategies.pullback import decide, run, supports
from scalping.strategies.waves import wave_index, wave_rule

CFG = load_config()


def mk(rows, start="2026-01-05 09:30"):
    """rows: (open, high, low, close) 목록 → 1분봉. 거래량 100주, 거래대금 = 종가 × 100"""
    t = pd.date_range(start, periods=len(rows), freq="1min")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    return df.assign(code="A", time=t, volume=100, value=df.close * 100)


def test_wave_index_counts_completed_retraces():
    up = [(100 + i, 101 + i, 99 + i, 100 + i) for i in range(10)]                # 꾸준히 오름
    dip = [(108, 109, 104, 104)]                                                 # 고점 110에서 5% 넘게 조정
    up2 = [(105, 112, 104, 111)]                                                 # 새 고점
    dip2 = [(110, 110, 106, 106)]                                                # 다시 조정
    b = mk(up + dip + up2 + dip2)
    end = b.time.iloc[-1] + pd.Timedelta(minutes=1)
    assert wave_index(mk(up), mk(up).time.iloc[-1] + pd.Timedelta(minutes=1)) == 1
    assert wave_index(b, b.time.iloc[11] + pd.Timedelta(minutes=1)) == 2        # 첫 조정 뒤
    assert wave_index(b, end) == 3


def event(ret=0.17, t="2026-01-05 10:00"):
    t = pd.Timestamp(t)
    return SimpleNamespace(code="A", time=t, available_at=t + pd.Timedelta(minutes=1), ret=ret, open=1000,
                           close=1150, ref_high=1160, ref_low=990, value=50e8)


def day(after):
    before = [(1000, 1005, 995, 1000)] * 30                                     # 09:30~09:59 조용한 흐름
    ev_bar = [(1000, 1160, 990, 1150)]                                          # 10:00 기준봉
    return mk(before + ev_bar + after)


def test_pullback_touch_then_confirm_enters_next_open():
    after = [(1150, 1200, 1150, 1190), (1190, 1190, 1100, 1110), (1110, 1110, 1000, 1030),   # VWAP(약 1,006원)에 닿음
             (1030, 1060, 1028, 1050)        # 양봉, 직전 봉 고가(1110)... 위가 아니다 → 아직 확인 아님
             , (1050, 1120, 1045, 1115)      # 양봉, 직전 봉 고가 1060 위 마감 → 확인
             , (1116, 1130, 1110, 1125)]     # 다음 봉 시가에 진입
    d = decide(event(), day(after), CFG)
    assert d.state == "READY" and d.confirm_time == pd.Timestamp("2026-01-05 10:05")
    assert d.fill_time == pd.Timestamp("2026-01-05 10:06") and d.fill_price == 1117
    assert d.support == "vwap" and d.pullback_low == 1000
    assert d.stop == 1084        # 눌림 저점 아래(999)와 -3%(1083.49→1084) 중 진입가에 가까운 쪽


def test_run_applies_wave_rule():
    after = [(1150, 1200, 1150, 1190), (1190, 1190, 1100, 1110), (1110, 1110, 1000, 1030),
             (1030, 1060, 1028, 1050), (1050, 1120, 1045, 1115), (1116, 1130, 1110, 1125)]
    ev = pd.DataFrame([vars(event())])
    d = run(ev, day(after), CFG).iloc[0]
    full = decide(event(), day(after), CFG)
    assert d.state == "READY" and d.wave == 2          # 고점 1200 → 1000까지 조정 한 번 → 2파동
    assert d.qty == int(full.qty * CFG["pullback"]["wave2_size"])


def test_wave_rule_blocks_third_wave():
    up = [(100 + i, 101 + i, 99 + i, 100 + i) for i in range(10)]
    b = mk(up + [(108, 109, 104, 104), (105, 112, 104, 111), (110, 110, 106, 106), (106, 107, 105, 107)])
    dec = pd.DataFrame([dict(code="A", state="READY", reason="", qty=10, fill_time=b.time.iloc[-1])])
    r = wave_rule(dec, b, CFG).iloc[0]
    assert r.wave == 3 and r.state == "BLOCK"


def test_prev_high_is_support_only_when_broken():
    b = day([])
    assert supports(event(), b)["prev_high"] == 1005                   # 09:30~09:59 고가 1005를 기준봉이 뚫음
    assert "prev_high" not in supports(SimpleNamespace(**{**vars(event()), "ref_high": 1004}), b)


def test_close_below_reference_low_invalidates():
    after = [(1150, 1160, 1100, 1120), (1120, 1120, 980, 985)]
    assert decide(event(), day(after), CFG).state == "INVALID"


def test_low_zone_is_not_for_pullback_engine():
    assert decide(event(ret=0.05), day([(1150, 1160, 1150, 1155)]), CFG).state == "BLOCK"


def test_run_with_no_events_returns_empty_table():
    d = run(pd.DataFrame(), day([]), CFG)
    assert d.empty and "state" in d and "wave" in d
