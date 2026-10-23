"""03-6 1분봉·수급 특징 데이터셋

    uv run python examples/ch03_features.py                         # 02장 가상 시장 하루
    uv run python examples/ch03_features.py --day 20261023          # 03-2에서 수집한 실데이터 (KRX)

1분봉마다 봉 모양, 직전 20봉 대비 배수, 시간대 정규화 배수를 붙여 data/processed/ 에 저장한다.
시간대 프로필(data/sample/minute_profile.csv)은 2025-10~2026-04 실데이터로 추정한 분별 거래대금 비중이다(03-3).
"""

import argparse

import pandas as pd

from scalping.features.minute import bar_shape, relative_turnover, tod_relative, typical_daily_value
from scalping.paths import PROCESSED, SAMPLE

pd.set_option("display.width", 160)
BUCKETS = ([539, 549, 569, 599, 719, 779, 899, 919, 931],
           ["09:00~09:09", "09:10~09:29", "09:30~09:59", "10:00~11:59", "12:00~12:59", "13:00~14:59",
            "15:00~15:19", "15:30"])


def load(day):
    if day is None:
        from scalping.sample_market import BENCH, load as load_market
        d = load_market()
        m = d["minute"][~d["minute"].code.isin(BENCH.values())]
        return m, d["daily"], d["minute"].date.iloc[0] if "date" in d["minute"] else m.time.dt.date.iloc[0]
    from scalping.ingestion.daily import load_daily
    from scalping.ingestion.minute import load_minute
    m = load_minute(day, "J")
    return m, load_daily(m.code.unique()), pd.Timestamp(day)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="YYYYMMDD (생략하면 가상 시장)")
    a = ap.parse_args()
    m, daily, day = load(a.day)
    profile = pd.read_csv(SAMPLE / "minute_profile.csv", index_col=0).iloc[:, 0]
    x = bar_shape(m)
    x["rel20"] = relative_turnover(x, 20)
    x["tod"] = tod_relative(x, profile, typical_daily_value(daily, day))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / f"ch03_features_{pd.Timestamp(day):%Y%m%d}.parquet"
    x.to_parquet(out, index=False)

    cols = ["code", "time", "close", "value", "rel20", "tod", "close_location", "body_ratio", "upper_wick"]
    top = x.sort_values("tod", ascending=False).head(5)[cols]
    print("시간대 정규화 배수 상위 5봉\n", top.assign(value=(top.value / 1e8).round(1)).to_string(
        index=False, float_format="{:.2f}".format))
    minute_of_day = x.time.dt.hour * 60 + x.time.dt.minute
    b = pd.cut(minute_of_day, BUCKETS[0], labels=BUCKETS[1])
    t = x.groupby(b, observed=True).agg(bars=("value", "size"),
                                        rel20_3x=("rel20", lambda s: (s >= 3).sum()),
                                        tod_3x=("tod", lambda s: (s >= 3).sum()))
    print("\n시간대별 3배 이상 봉 수\n", t.to_string())
    print(f"\n{len(x):,}봉 → {out}")


if __name__ == "__main__":
    main()
