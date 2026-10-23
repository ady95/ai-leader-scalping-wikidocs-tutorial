"""02-1 시점별 거래대금 쏠림·등락률·상대강도

1분봉 표의 열: date, code, time(봉 시작 시각, datetime), open, high, low, close, volume, value(그 1분의 거래대금)
봉은 시작 시각 + 1분에 끝난다. `at` 시각의 스냅샷에는 그 전에 끝난 봉만 들어간다.
"""

import pandas as pd

ONE_MIN = pd.Timedelta(minutes=1)


def finished(minute, at):
    """at 시각까지 끝난 1분봉만 남긴다 (시점 정합)."""
    return minute[minute["time"] + ONE_MIN <= at]


def snapshot(minute, prev_close, at, market=None, bench=None):
    """at 시각의 종목별 누적 거래대금·현재가·등락률·대금 순위.

    prev_close: 종목코드 → 전일 종가 (Series)
    market, bench: 종목코드 → 시장, 시장 → 지수(또는 ETF) 종목코드. 주면 상대강도를 더한다.
    """
    done = finished(minute, at)
    g = done.groupby("code")
    out = pd.DataFrame({"cum_value": g["value"].sum(), "price": g["close"].last(),
                        "day_high": g["high"].max()})
    out["prev_close"] = prev_close.reindex(out.index)
    out["ret"] = out.price / out.prev_close - 1
    out["from_high"] = out.price / out.day_high - 1
    if bench:
        bench_ret = {m: out.ret.get(c) for m, c in bench.items()}
        out["bench_ret"] = market.reindex(out.index).map(bench_ret)
        out["rel_strength"] = out.ret - out.bench_ret
        out = out.drop(index=[c for c in bench.values() if c in out.index])
    out["value_share"] = out.cum_value / out.cum_value.sum()
    out["value_rank"] = out.cum_value.rank(ascending=False, method="first").astype(int)
    return out.sort_values("value_rank")
