"""02-4 종목의 끼: 과거에 얼마나 자주 크게 올랐나

판단하는 날의 전날까지 lookback 거래일만 본다.
"""

import numpy as np
import pandas as pd

from scalping.market import upper_limit

_upper = np.vectorize(upper_limit, otypes=[np.int64])


def day_moves(daily):
    """일봉에 전일 종가 대비 장중 최고 상승률(up)과 상한가 터치 여부(limit)를 붙인다."""
    d = daily.sort_values(["code", "date"]).copy()
    d["base"] = d.groupby("code").close.shift()
    d = d.dropna(subset=["base"])
    d["up"] = d.high / d.base - 1
    d["limit"] = d.high >= _upper(d.base.astype("int64"))
    return d


def kki(moves, day, lookback=120, big=0.20):
    """종목별 끼: lookback일 안에 장중 big 이상 오른 날 수, 상한가 터치 수, 최대 상승률"""
    hist = moves[moves.date < pd.Timestamp(day)].groupby("code").tail(lookback)
    g = hist.assign(is_big=hist.up >= big).groupby("code")
    return pd.DataFrame({"n_days": g.size(), "n_big": g.is_big.sum(),
                         "n_limit": g.limit.sum(), "max_up": g.up.max()})
