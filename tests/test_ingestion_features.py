import numpy as np
import pandas as pd

from scalping.features.minute import bar_shape, intraday_profile, relative_turnover, tod_relative
from scalping.ingestion.minute import to_standard
from scalping.ingestion.realtime import TRADE_COLS, parse_trade_line


def raw_minute():
    """API 저장 형식: time은 HHMMSS 문자열, cum_value는 그날 누적 거래대금"""
    return pd.DataFrame({"code": "000001", "date": pd.Timestamp("2026-01-05"),
                         "time": ["090000", "090100", "090200"], "open": [100, 101, 102], "high": [101, 103, 103],
                         "low": [99, 100, 101], "close": [101, 102, 102], "volume": [10, 20, 5],
                         "cum_value": [1_000, 3_050, 3_560]})


def test_value_is_diff_of_cumulative():
    m = to_standard(raw_minute())
    assert m.value.tolist() == [1_000, 2_050, 510]
    assert m.time.iloc[1] == pd.Timestamp("2026-01-05 09:01")


def test_bar_shape_close_location():
    m = bar_shape(to_standard(raw_minute()))
    assert m.close_location.iloc[0] == 1.0            # 종가 = 고가
    assert np.isclose(m.close_location.iloc[1], 2 / 3)


def test_relative_turnover_excludes_current_bar():
    t = pd.date_range("2026-01-05 09:00", periods=6, freq="1min")
    m = pd.DataFrame({"code": "A", "date": pd.Timestamp("2026-01-05"), "time": t,
                      "value": [10, 10, 10, 10, 10, 100]})
    r = relative_turnover(m, n=5)
    assert r.iloc[:5].isna().all() and r.iloc[5] == 10.0     # 앞 5봉 중앙값 10 대비 100


def test_profile_sums_to_one_and_tod_relative():
    t = pd.date_range("2026-01-05 09:00", periods=3, freq="1min")
    m = pd.DataFrame({"code": ["A"] * 3 + ["B"] * 3, "date": pd.Timestamp("2026-01-05"),
                      "time": list(t) * 2, "value": [50, 25, 25, 500, 250, 250]})
    prof = intraday_profile(m)
    assert np.isclose(prof.sum(), 1.0) and np.isclose(prof["09:00"], 0.5)
    tod = tod_relative(m, prof, pd.Series({"A": 100, "B": 1000}))
    assert np.allclose(tod, 1.0)                              # 평소 모양 그대로면 배수 1


def test_parse_trade_line_handles_multi_records():
    rec = [str(i) for i in range(len(TRADE_COLS))]
    line = "123\t0|H0STCNT0|002|" + "^".join(rec + rec) + "\n"
    rows = parse_trade_line(line)
    assert len(rows) == 2 and rows[1]["code"] == "0" and rows[0]["recv_ns"] == 123
