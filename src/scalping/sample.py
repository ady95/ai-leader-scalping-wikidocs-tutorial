"""01-5 샘플 하루 데이터 — 가상 종목 4개의 1분봉을 같은 시드로 언제나 똑같이 만든다.

실제 시세가 아니다. 종목코드(9000x0)·이름·뉴스는 모두 가상이며, 이 장에서 시스템 흐름을
보여 주려고 시나리오를 미리 심어 두었다.

    python -m scalping.sample          # data/sample/ 에 CSV 4개를 쓴다
"""

import numpy as np
import pandas as pd

from scalping.market import ceil_tick, floor_tick, upper_limit
from scalping.paths import SAMPLE

DAY = "2026-01-05"          # 가상 거래일
NEXT_DAY = "2026-01-06"
SEED = 7

# path: (시각, 전일 대비 등락률) 꼭짓점 — 그 사이는 직선으로 잇고 잡음을 더한다
# events: 그 분의 봉을 (시가, 고가, 저가, 종가 등락률, 거래대금)으로 고정한다
# hot: (시작, 끝, 배수) — 그 구간의 평소 거래대금을 키운다
STOCKS = [
    dict(code="900010", name="가상로봇A", theme="가상 로봇", prev_close=10_000,
         threshold=35e8, base_value=2.5e8, news=None,
         path=[("09:00", 0.010), ("10:40", 0.045), ("10:41", 0.074), ("11:10", 0.130),
               ("13:00", 0.110), ("15:30", 0.112)],
         events={"10:41": (0.046, 0.076, 0.045, 0.074, 62e8)},
         hot=[("10:42", "11:15", 4.0)]),
    dict(code="900020", name="가상바이오B", theme="가상 바이오", prev_close=25_000,
         threshold=30e8, base_value=2.0e8, news=("13:04", "가상바이오B, 임상 결과 발표(가상 뉴스)"),
         path=[("09:00", 0.005), ("13:04", 0.020), ("13:05", 0.058), ("13:06", 0.057),
               ("13:07", 0.049), ("13:30", 0.035), ("15:30", 0.030)],
         events={"13:05": (0.021, 0.061, 0.020, 0.058, 48e8),
                 "13:06": (0.058, 0.0625, 0.054, 0.057, 25e8),
                 "13:07": (0.056, 0.057, 0.048, 0.049, 14e8)},
         hot=[("13:08", "13:20", 2.5)]),
    dict(code="900030", name="가상전력C", theme="가상 전력", prev_close=4_000,
         threshold=40e8, base_value=1.5e8, news=("09:58", "가상전력C, 대규모 공급계약 체결(가상 뉴스)"),
         path=[("09:00", 0.010), ("10:04", 0.030), ("10:05", 0.088), ("10:25", 0.300),
               ("15:30", 0.300)],
         events={"10:05": (0.031, 0.090, 0.030, 0.088, 85e8)},
         hot=[("10:06", "10:30", 6.0), ("10:31", "15:30", 0.4)],
         lock_from="10:25",     # 이 시각부터 상한가에 붙어 있다
         next_open=0.03),       # 다음 날 시가: 오늘 종가 대비 +3%
    dict(code="900040", name="가상반도체D", theme="가상 반도체", prev_close=50_000,
         threshold=60e8, base_value=4.0e8, news=None,
         path=[("09:00", 0.010), ("09:11", 0.020), ("09:12", 0.060), ("09:40", 0.100),
               ("10:19", 0.150), ("10:20", 0.175), ("11:00", 0.160), ("15:30", 0.140)],
         events={"09:12": (0.021, 0.062, 0.020, 0.060, 120e8),
                 "10:20": (0.151, 0.178, 0.150, 0.175, 90e8)}),
]


def session_minutes():
    """정규장 1분봉 시각: 09:00~15:19 + 장 마감 단일가 15:30 (15:20~15:29는 단일가 접수라 봉이 없다)"""
    t = pd.date_range(f"{DAY} 09:00", f"{DAY} 15:19", freq="1min")
    return t.append(pd.DatetimeIndex([pd.Timestamp(f"{DAY} 15:30")]))


def _minute_index(times, hhmm):
    return int(np.searchsorted(times, pd.Timestamp(f"{DAY} {hhmm}")))


def make_bars(spec, rng):
    times = session_minutes()
    n = len(times)
    base, upper = spec["prev_close"], upper_limit(spec["prev_close"])
    xs = [_minute_index(times, t) for t, _ in spec["path"]]
    pct = np.interp(np.arange(n), xs, [p for _, p in spec["path"]])
    pct = pct + rng.normal(0, 0.0012, n)

    # 평소 거래대금: 장 초반·마감에 크고 점심에 작은 U자 모양 x 잡음
    i = np.arange(n)
    shape = 1 + 2.5 * np.exp(-i / 25) + 1.2 * np.exp(-(n - 1 - i) / 15)
    value = spec["base_value"] * shape * rng.lognormal(0, 0.3, n)
    for start, end, mult in spec.get("hot", []):
        a, b = _minute_index(times, start), _minute_index(times, end)
        value[a:b + 1] *= mult

    lock = _minute_index(times, spec["lock_from"]) if "lock_from" in spec else n
    rows, prev = [], base
    for k, t in enumerate(times):
        hhmm = t.strftime("%H:%M")
        if k >= lock:                    # 상한가 도달 봉은 직전 종가에서 출발, 이후는 상한가 고정
            o, lo = (prev, prev) if k == lock else (upper, upper)
            h = c = upper
        elif hhmm in spec["events"]:
            o, h, lo, c, v = spec["events"][hhmm]
            o, h, lo, c = (floor_tick(base * (1 + x)) for x in (o, h, lo, c))
            value[k] = v
        else:
            c = floor_tick(base * (1 + pct[k]))
            o = prev
            wiggle = abs(rng.normal(0, 0.0015, 2)) * base
            h = ceil_tick(max(o, c) + wiggle[0])
            lo = floor_tick(min(o, c) - wiggle[1])
        o, h, lo, c = (min(x, upper) for x in (o, h, lo, c))
        vwap = (h + lo + c) / 3
        rows.append(dict(code=spec["code"], time=t, open=o, high=h, low=lo, close=c,
                         volume=int(value[k] / vwap), value=int(value[k])))
        prev = c
    return pd.DataFrame(rows)


def build():
    rng = np.random.default_rng(SEED)
    bars = pd.concat([make_bars(s, rng) for s in STOCKS], ignore_index=True)
    stocks = pd.DataFrame([{k: s[k] for k in ("code", "name", "theme", "prev_close", "threshold")}
                           | {"upper_limit": upper_limit(s["prev_close"])} for s in STOCKS])
    news = pd.DataFrame([dict(code=s["code"], time=pd.Timestamp(f"{DAY} {s['news'][0]}"), title=s["news"][1])
                         for s in STOCKS if s["news"]])
    last = bars.groupby("code").close.last()
    next_open = pd.DataFrame([dict(code=s["code"], date=NEXT_DAY,
                                   open=floor_tick(last[s["code"]] * (1 + s["next_open"])))
                              for s in STOCKS if "next_open" in s])
    return dict(bars=bars, stocks=stocks, news=news, next_open=next_open)


def save(data=None):
    data = data or build()
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df.to_csv(SAMPLE / f"{name}.csv", index=False, encoding="utf-8")
    return data


def load():
    """data/sample 의 CSV를 읽는다. 없으면 만든다."""
    if not (SAMPLE / "bars.csv").exists():
        return save()
    out = {name: pd.read_csv(SAMPLE / f"{name}.csv", dtype={"code": str})
           for name in ("bars", "stocks", "news", "next_open")}
    for name in ("bars", "news"):
        out[name]["time"] = pd.to_datetime(out[name]["time"])
    return out


if __name__ == "__main__":
    d = save()
    print(f"bars {len(d['bars'])}행, 종목 {len(d['stocks'])}개, 뉴스 {len(d['news'])}건 → {SAMPLE}")
