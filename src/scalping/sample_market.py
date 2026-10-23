"""02장 가상 시장 — 종목 30개·테마 5개의 일봉 130일과 하루 1분봉 (실제 시세 아님)

이 하루에는 02장에서 확인할 장면을 심어 두었다.
- 가상 로봇 테마가 함께 오르고, 장중에 대장주가 910010에서 910020으로 바뀐다
- 가상 바이오는 오전에 한 종목만 오르다가 11시 이후에야 테마가 된다
- 910210(가상 대형주)은 거래대금이 가장 크지만 거의 오르지 않는다
- 09:30에는 함께 오르는 테마가 없어 NO_TRADE

    python -m scalping.sample_market     # data/sample/market/ 에 CSV 저장
"""

import numpy as np
import pandas as pd

from scalping.market import ceil_tick, floor_tick, upper_limit
from scalping.paths import SAMPLE

DAY = "2026-01-07"
SEED = 11
OUT = SAMPLE / "market"
BENCH = {"KOSPI": "909200", "KOSDAQ": "909100"}

THEMES = {"T01": "가상 로봇", "T02": "가상 바이오", "T03": "가상 전력", "T04": "가상 반도체", "T05": "가상 2차전지"}

# code, 이름, 시장, 테마들, 전일 종가, 평소 1분 대금(억), 일봉 변동성, 급등 확률(끼), 당일 경로, 당일 대금 배수 경로
S = [
    ("910010", "가상로봇1", "KOSDAQ", ["T01"], 12_000, 1.5, 0.035, 0.040,
     [("09:00", .01), ("09:25", .07), ("10:00", .12), ("11:00", .13), ("13:00", .11), ("15:30", .10)],
     [("09:00", 2), ("09:20", 25), ("10:00", 18), ("11:00", 8), ("15:30", 4)]),
    ("910020", "가상로봇2", "KOSDAQ", ["T01"], 8_500, 1.0, 0.040, 0.050,
     [("09:00", .00), ("09:50", .03), ("10:00", .06), ("11:00", .15), ("13:00", .25), ("15:30", .27)],
     [("09:00", 2), ("10:00", 6), ("11:00", 25), ("13:00", 30), ("15:30", 12)]),
    ("910030", "가상로봇3", "KOSDAQ", ["T01", "T05"], 22_000, 0.8, 0.030, 0.020,
     [("09:00", .00), ("09:40", .02), ("10:00", .07), ("13:00", .09), ("15:30", .08)],
     [("09:00", 2), ("10:00", 8), ("13:00", 5), ("15:30", 3)]),
    ("910040", "가상로봇4", "KOSPI", ["T01"], 45_000, 1.2, 0.025, 0.010,
     [("09:00", .00), ("10:00", .055), ("15:30", .05)], [("09:00", 2), ("10:00", 5), ("15:30", 3)]),
    ("910050", "가상로봇5", "KOSDAQ", ["T01"], 3_200, 0.5, 0.035, 0.030,
     [("09:00", .00), ("15:30", .02)], [("09:00", 1), ("15:30", 1)]),
    ("910060", "가상바이오1", "KOSDAQ", ["T02"], 31_000, 1.0, 0.040, 0.030,
     [("09:00", .01), ("09:40", .06), ("10:00", .09), ("15:30", .11)],
     [("09:00", 2), ("10:00", 12), ("15:30", 5)]),
    ("910070", "가상바이오2", "KOSDAQ", ["T02"], 15_500, 0.7, 0.040, 0.030,
     [("09:00", .00), ("11:00", .02), ("11:30", .07), ("15:30", .08)],
     [("09:00", 1), ("11:00", 2), ("11:30", 10), ("15:30", 4)]),
]
# 테마당 나머지 종목과 대형주는 조용하게 움직인다
QUIET = [("910080", "가상바이오3", "KOSDAQ", ["T02"], 9_800), ("910090", "가상바이오4", "KOSDAQ", ["T02"], 5_400),
         ("910100", "가상전력1", "KOSPI", ["T03"], 61_000), ("910110", "가상전력2", "KOSPI", ["T03"], 27_000),
         ("910120", "가상전력3", "KOSDAQ", ["T03"], 7_300), ("910130", "가상전력4", "KOSDAQ", ["T03", "T05"], 18_000),
         ("910140", "가상반도체1", "KOSDAQ", ["T04"], 33_000), ("910150", "가상반도체2", "KOSDAQ", ["T04"], 12_500),
         ("910160", "가상반도체3", "KOSPI", ["T04"], 88_000), ("910170", "가상반도체4", "KOSDAQ", ["T04"], 4_100),
         ("910180", "가상전지1", "KOSPI", ["T05"], 140_000), ("910190", "가상전지2", "KOSDAQ", ["T05"], 26_500),
         ("910200", "가상전지3", "KOSDAQ", ["T05"], 9_100), ("910220", "가상소재1", "KOSDAQ", [], 6_600),
         ("910230", "가상소재2", "KOSPI", [], 23_000), ("910240", "가상유통1", "KOSPI", [], 41_000),
         ("910250", "가상유통2", "KOSDAQ", [], 2_900), ("910260", "가상금융1", "KOSPI", [], 12_000),
         ("910270", "가상금융2", "KOSPI", [], 7_800), ("910280", "가상게임1", "KOSDAQ", [], 35_500),
         ("910290", "가상게임2", "KOSDAQ", [], 16_200), ("910300", "가상건설1", "KOSPI", [], 14_700)]
BIG = ("910210", "가상대형주", "KOSPI", ["T04"], 95_000, 40.0, 0.015, 0.0,
       [("09:00", .004), ("15:30", .008)], [("09:00", 1), ("15:30", 1)])
ETF = [(BENCH["KOSPI"], "가상KOSPI ETF", "KOSPI", [], 35_000, 3.0, 0.01, 0.0,
        [("09:00", .001), ("15:30", .003)], [("09:00", 1), ("15:30", 1)]),
       (BENCH["KOSDAQ"], "가상KOSDAQ ETF", "KOSDAQ", [], 12_000, 1.0, 0.012, 0.0,
        [("09:00", .002), ("15:30", .004)], [("09:00", 1), ("15:30", 1)])]


def specs():
    rows = list(S) + [BIG] + ETF
    for code, name, mkt, th, px in QUIET:
        rows.append((code, name, mkt, th, px, 0.6, 0.025, 0.01, [("09:00", 0.0), ("15:30", 0.005)],
                     [("09:00", 1), ("15:30", 1)]))
    return rows


def _times(day):
    t = pd.date_range(f"{day} 09:00", f"{day} 15:19", freq="1min")
    return t.append(pd.DatetimeIndex([pd.Timestamp(f"{day} 15:30")]))


def make_daily(spec, rng, dates):
    """전일 종가에서 거꾸로 거슬러 올라가며 130일 일봉을 만든다. 급등 확률이 높을수록 +20% 이상 날이 잦다(끼)."""
    code, _, _, _, last_close, value_1m, vol, p_jump = spec[:8]
    n = len(dates)
    r = rng.normal(0.0005, vol, n)
    jumps = rng.random(n) < p_jump
    r[jumps] = rng.uniform(0.15, 0.29, jumps.sum())
    closes = last_close / np.cumprod(1 + r[::-1])[::-1] * (1 + r)     # 마지막 날 종가가 last_close
    rows, prev = [], closes[0] / (1 + r[0])
    for d, c, rr, jump in zip(dates, closes, r, jumps):
        c = floor_tick(min(c, upper_limit(int(prev))))
        hi = ceil_tick(max(c, prev) * (1 + abs(rng.normal(0, vol / 2))))
        if jump:
            hi = max(hi, floor_tick(min(prev * 1.22, upper_limit(int(prev)))))
        lo = floor_tick(min(c, prev) * (1 - abs(rng.normal(0, vol / 2))))
        value = value_1m * 1e8 * 380 * (3 if jump else 1) * rng.lognormal(0, 0.3)
        rows.append(dict(date=d, code=code, open=floor_tick(prev), high=min(hi, upper_limit(int(prev))), low=lo,
                         close=c, volume=int(value / c), value=int(value)))
        prev = c
    return rows


def make_minute(spec, rng):
    code, _, _, _, base, value_1m, *_, path, vpath = spec
    times = _times(DAY)
    n = len(times)
    idx = lambda hhmm: int(np.searchsorted(times, pd.Timestamp(f"{DAY} {hhmm}")))
    pct = np.interp(np.arange(n), [idx(t) for t, _ in path], [p for _, p in path]) + rng.normal(0, 0.001, n)
    mult = np.interp(np.arange(n), [idx(t) for t, _ in vpath], [v for _, v in vpath])
    value = value_1m * 1e8 * mult * rng.lognormal(0, 0.3, n)
    upper, prev, rows = upper_limit(base), base, []
    for k, t in enumerate(times):
        c = min(floor_tick(base * (1 + pct[k])), upper)
        h = min(ceil_tick(max(prev, c) * (1 + abs(rng.normal(0, 0.001)))), upper)
        lo = floor_tick(min(prev, c) * (1 - abs(rng.normal(0, 0.001))))
        rows.append(dict(date=DAY, code=code, time=t, open=prev, high=h, low=lo, close=c,
                         volume=int(value[k] / c), value=int(value[k])))
        prev = c
    return rows


def build():
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range(end=pd.Timestamp(DAY) - pd.Timedelta(days=1), periods=130)
    sp = specs()
    daily = pd.DataFrame([r for s in sp for r in make_daily(s, rng, dates)])
    minute = pd.DataFrame([r for s in sp for r in make_minute(s, rng)])
    master = pd.DataFrame([dict(code=s[0], name=s[1], market=s[2], is_etf=s[0] in BENCH.values()) for s in sp])
    themes = pd.DataFrame([dict(theme_code=t, theme_name=THEMES[t], code=s[0]) for s in sp for t in s[3]])
    return dict(daily=daily, minute=minute, master=master, themes=themes)


def save():
    data = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8")
    return data


def load():
    if not (OUT / "minute.csv").exists():
        return save()
    d = {n: pd.read_csv(OUT / f"{n}.csv", dtype={"code": str}) for n in ("daily", "minute", "master", "themes")}
    d["daily"]["date"] = pd.to_datetime(d["daily"]["date"])
    d["minute"]["time"] = pd.to_datetime(d["minute"]["time"])
    return d


if __name__ == "__main__":
    d = save()
    print(f"일봉 {len(d['daily']):,}행, 1분봉 {len(d['minute']):,}행, 종목 {len(d['master'])}개, "
          f"테마-종목 {len(d['themes'])}쌍 → {OUT}")
