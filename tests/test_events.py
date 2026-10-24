import pandas as pd

from scalping.events.clean import clean_flags
from scalping.events.hamburger import detect, events
from scalping.events.thresholds import launch_bar, threshold_at


def day_bars(code="A", closes=None, values=None, start="2026-01-05 09:00"):
    t = pd.date_range(start, periods=len(closes), freq="1min")
    c = pd.Series(closes, dtype="int64")
    return pd.DataFrame({"code": code, "date": pd.Timestamp(t[0].date()), "time": t, "open": c.shift(fill_value=c[0]),
                         "high": c + 5, "low": c - 5, "close": c, "volume": 100, "value": values})


def test_early_and_gap_bars_are_not_clean():
    m = day_bars(closes=[1000] * 30, values=[1e8] * 30)
    m = m.drop(index=20)                                  # 09:20 봉이 비어 있다 (체결 없는 분)
    x = clean_flags(m)
    assert x[x.time.dt.strftime("%H:%M") < "09:15"].early.all()
    assert x.set_index(x.time.dt.strftime("%H:%M")).loc["09:21", "vi_like"]


def test_run_top_uses_same_stock_only():
    a = day_bars("A", [1000] * 15, [1e8] * 15)
    b = day_bars("B", [500 + 10 * i for i in range(15)], [1e8] * 15)   # 계속 오르는 종목
    x = clean_flags(pd.concat([a, b], ignore_index=True))
    assert not x[x.code == "A"].run_top.any() and x[x.code == "B"].run_top.any()


def test_launch_bar_is_before_peak_and_clean():
    closes = [1000] * 20 + [1050, 1100, 1150, 1120, 1100] + [1080] * 5
    values = [1e8] * 20 + [50e8, 20e8, 10e8, 5e8, 3e8] + [90e8] * 5   # 고점 뒤의 큰 대금은 발사봉이 아니다
    b = launch_bar(day_bars(closes=closes, values=values), base=1000, upper=1300)
    assert b["launch_time"] == pd.Timestamp("2026-01-05 09:20") and b["launch_value"] == 50e8


def test_threshold_uses_only_past_and_drops_news_days():
    ev = pd.DataFrame({"code": ["A", "A", "A"], "date": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-05"]),
                       "launch_value": [40e8, 100e8, 1e8], "news_like": [False, True, False]})
    t = threshold_at(ev, "2026-01-05")
    assert t.loc["A", "threshold"] == 40e8 and t.loc["A", "n_events"] == 1
    t2 = threshold_at(ev, "2026-01-05", discount=0.2)
    assert t2.loc["A", "threshold"] == (40e8 + 80e8) / 2


def test_threshold_handles_rally_days_without_minute_bars():
    ev = pd.DataFrame({"code": ["A", "B"], "date": pd.to_datetime(["2026-01-02", "2026-01-02"]),
                       "launch_value": [40e8, None], "news_like": [False, None]})     # B는 1분봉이 없던 급등일
    assert list(threshold_at(ev, "2026-01-05").index) == ["A"]


def test_detect_marks_threshold_hamburger_after_bar_closes():
    closes = [1000] * 30
    values = [2e8] * 25 + [60e8] + [2e8] * 4
    m = day_bars(closes=closes, values=values)
    x = detect(m, pd.Series({"A": 950}), threshold=pd.Series({"A": 50e8}))
    e = events(x, "thr")
    assert len(e) == 1 and e.time[0] == pd.Timestamp("2026-01-05 09:25")
    assert e.available_at[0] == pd.Timestamp("2026-01-05 09:26") and e.thr[0] == 1.2


def test_program_at_respects_receive_time():
    import json as _json

    from scalping.events.program import parse_program_lines, program_at
    recv1 = int(pd.Timestamp("2026-01-05 10:00:30", tz="Asia/Seoul").value)   # 10:00:30에 받은 기록
    recv2 = int(pd.Timestamp("2026-01-05 10:01:30", tz="Asia/Seoul").value)
    rows1 = [{"bsop_hour": "100010", "whol_smtn_ntby_tr_pbmn": "1000000000"}]
    rows2 = rows1 + [{"bsop_hour": "100050", "whol_smtn_ntby_tr_pbmn": "3000000000"}]
    lines = [f"{recv1}\tA\t{_json.dumps(rows1)}\n", f"{recv2}\tA\t{_json.dumps(rows2)}\n"]
    p = parse_program_lines(lines, "2026-01-05")
    assert program_at(p, "A", "2026-01-05 10:01:00") == 10e8        # 10:00:50 기록은 10:01:30에야 받았다
    assert program_at(p, "A", "2026-01-05 10:02:00") == 30e8
    assert program_at(p, "B", "2026-01-05 10:02:00") is None
