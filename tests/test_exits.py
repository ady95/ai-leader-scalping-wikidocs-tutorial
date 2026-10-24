import pandas as pd

from scalping.config import load_config
from scalping.exits.engine import Position, simulate
from scalping.exits.levels import resistance, take_profit
from scalping.exits.orders import SellBook

CFG = load_config()


def bars(rows, start="2026-01-05 10:00"):
    t = pd.date_range(start, periods=len(rows), freq="1min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(time=t)


def pos(**kw):
    p = dict(code="A", entry_time=pd.Timestamp("2026-01-05 10:00"), entry=10030, qty=250, stop=9930)
    return Position(**{**p, **kw})


def test_x1_fast_stop_sells_next_open_when_no_follow_through():
    b = bars([(10000, 10040, 9990, 10030), (10030, 10060, 9990, 10020), (10010, 10020, 9950, 9960)])
    r = simulate(pos(target=10500, target_reason="저항 직전"), b, CFG, "X1")
    assert r.fills == [(b.time[2], 250, 10000, "1~2분 시간손절")]       # 10:02 시가 10,010 - 1호가


def test_stop_beats_target_in_same_bar_and_gap_fills_at_open():
    b = bars([(10000, 10040, 9990, 10030), (10030, 10200, 9900, 10100)])
    r = simulate(pos(target=10130, target_reason="저항 직전"), b, CFG, "X1")
    assert r.fills[0][3] == "손절" and r.fills[0][2] == 9920               # 같은 봉에서 목표·손절 모두 → 손절
    g = bars([(10000, 10040, 9990, 10030), (9800, 9850, 9700, 9750)])
    assert simulate(pos(), g, CFG, "X0").fills[0][2] == 9790                # 갭 하락: 시가 9,800 - 1호가


def test_x2_partial_then_session_close():
    b = bars([(10000, 10040, 9990, 10030), (10030, 10140, 10020, 10130), (10130, 10250, 10120, 10240),
              (10240, 10260, 10200, 10210)])
    r = simulate(pos(), b, CFG, "X2")
    assert [(q, p, w) for _, q, p, w in r.fills] == [(125, 10130, "+1R 분할"), (62, 10230, "+2R 분할"),
                                                     (63, 10200, "장 마감")]


def test_x3_trailing_moves_to_breakeven_then_trails():
    b = bars([(10000, 10040, 9990, 10030), (10030, 10140, 10020, 10130), (10130, 10400, 10120, 10380),
              (10380, 10390, 10290, 10300)])
    r = simulate(pos(), b, CFG, "X3")
    assert r.fills == [(b.time[3], 250, 10290, "추적 손절")]               # 고점 10,400 - 1R = 10,300 → 1호가 불리


def test_take_profit_and_resistance():
    d = pd.DataFrame(dict(date=pd.date_range("2025-12-01", periods=130, freq="B"), high=10000.0, close=9500.0))
    d.loc[d.index[-30], "high"] = 10600.0                                  # 60일 고점
    lv, name = resistance(d, pd.Timestamp("2026-07-01"), 10030)
    assert (lv, name) == (10600.0, "60일 고점")
    assert take_profit(10030, lv, True, CFG) == (10590, "저항 직전")
    assert take_profit(10030, lv, False, CFG) == (10330, "재료 없음 3%")


def test_sell_book_cancels_take_profit_before_stop():
    book = SellBook(100)
    (act, take), = book.request("take", price=10500)
    assert act == "new" and take.qty == 100
    acts = book.request("stop")                                             # 손절: 익절 지정가부터 취소
    assert acts == [("cancel", take.oid)] and book.available() == 0
    book.on_fill(take.oid, 30)                                              # 취소 전에 30주 체결
    (act, stop), = book.on_cancelled(take.oid)
    assert stop.kind == "stop" and stop.qty == 70
    assert book.request("stop") == []                                       # 중복 손절 주문 없음


def test_fast_stop_with_ticks_uses_exact_seconds():
    from scalping.exits.ticks import breakout_fill, fast_stop, with_times
    raw = pd.DataFrame(dict(code="A", time=["100005", "100012", "100130", "100211", "100215"],
                            price=[10000, 10020, 10090, 10050, 10040], recv_ns=range(5)))
    t = with_times(raw, "2026-01-05")
    f = breakout_fill(t, "A", pd.Timestamp("2026-01-05 10:00"), 10010)
    assert f.t == pd.Timestamp("2026-01-05 10:00:12")
    out = fast_stop(t, "A", f.t, 10030, CFG)                     # 2분 안 최고 10,090 < 10,030 x 1.01 = 10,130.3
    assert out["time"] == pd.Timestamp("2026-01-05 10:02:15") and out["price"] == 10030 and out["best"] == 10090
    assert fast_stop(t, "A", f.t, 9950, CFG) is None             # 9,950 x 1.01 = 10,049.5 → 유지
