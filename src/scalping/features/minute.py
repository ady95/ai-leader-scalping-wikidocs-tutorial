"""03-1·03-3·03-6 1분봉 특징

분석 형식의 1분봉(date, code, time, open, high, low, close, volume, value)에 특징 열을 더한다.
모든 특징은 **그 봉이 끝난 뒤** 알 수 있는 값이며, 과거 값은 shift로 한 칸 밀어 현재 봉이 섞이지 않게 한다.
"""

import numpy as np
import pandas as pd

EPS = 1e-9


def bar_shape(m):
    """봉 모양: 종가 위치·몸통 비율·윗꼬리 비율·진폭, 그리고 거래대금 근삿값 두 가지."""
    out = m.copy()
    rng = (out.high - out.low).astype(float)
    out["range_pct"] = rng / out.low
    out["close_location"] = np.where(rng > 0, (out.close - out.low) / np.maximum(rng, EPS), 0.5)
    out["body_ratio"] = np.where(rng > 0, (out.close - out.open).abs() / np.maximum(rng, EPS), 0.0)
    out["upper_wick"] = np.where(rng > 0, (out.high - out[["open", "close"]].max(axis=1)) / np.maximum(rng, EPS), 0.0)
    out["value_ohlc4"] = out.volume * (out.open + out.high + out.low + out.close) / 4     # 근삿값 (03-1)
    out["value_close"] = out.volume * out.close                                         # 더 거친 근삿값
    return out


def relative_turnover(m, n=20, col="value"):
    """직전 n개 완료 봉의 거래대금 중앙값 대비 배수 (같은 종목·같은 날 안에서). 앞쪽 n봉은 NaN."""
    g = m.groupby(["code", "date"])[col]
    base = g.transform(lambda x: x.shift(1).rolling(n, min_periods=n).median())
    return m[col] / base


def intraday_profile(m):
    """분(HH:MM)별 하루 거래대금 비중의 중앙값. 종목·날짜마다 비중을 구한 뒤 중앙값을 낸다.

    프로필은 학습 기간 데이터로만 추정하고, 평가 기간에는 고정해서 쓴다 (미래 정보 금지).
    """
    x = m[["code", "date", "time", "value"]].copy()
    x["hhmm"] = x.time.dt.strftime("%H:%M")
    x["share"] = x.value / x.groupby(["code", "date"]).value.transform("sum")
    prof = x.groupby("hhmm").share.median()
    return prof / prof.sum()                     # 비중 합이 1이 되게 다시 맞춘다


def tod_relative(m, profile, typical_daily_value):
    """시간대 정규화 배수 = 이 봉의 거래대금 ÷ (그 분의 평소 비중 × 이 종목의 평소 하루 거래대금).

    typical_daily_value: 종목코드 → 최근 20거래일 하루 거래대금 중앙값 (전날까지 일봉으로 계산)
    """
    hhmm = m.time.dt.strftime("%H:%M")
    expected = hhmm.map(profile) * m.code.map(typical_daily_value)
    return m.value / expected


def typical_daily_value(daily, day, n=20):
    """day 전날까지 n거래일의 하루 거래대금 중앙값"""
    hist = daily[daily.date < pd.Timestamp(day)].sort_values(["code", "date"])
    return hist.groupby("code").tail(n).groupby("code").value.median()
