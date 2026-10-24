"""04-2·04-6 햄버거 이벤트 탐지기

네 가지 대금 기준을 한 번에 계산하고, 깨끗한 기준봉 조건과 함께 이벤트 표를 만든다.
| 기준   | 조건                                          | 출처        |
| abs    | 1분 거래대금 >= abs_value                     | 비교군      |
| rel20  | 직전 20봉 중앙값 대비 >= rel_mult             | 연구 가설   |
| tod    | 시간대 정규화 배수 >= tod_mult                 | 연구 가설   |
| thr    | 과거 급등 임계치 대비 >= thr_mult              | 공개 원칙   |
배수 기준(rel20·tod·thr)은 그 봉의 거래대금이 min_value 이상일 때만 인정한다. 거래가 거의 없던 종목은
임계치·평소 대금이 수백만 원이라, 몇천만 원만 거래돼도 배수가 커지기 때문이다(04-6 실측). min_value는 이 책의 실험값.
이벤트는 봉이 끝난 시각(available_at = 봉 시작 + 1분)에 확정된다. 그 전에는 고가·종가를 쓰지 않는다.
"""

import pandas as pd

from scalping.events.clean import clean_flags
from scalping.features.minute import bar_shape, relative_turnover, tod_relative

RULE_VERSION = "hamburger-v2"
DEFAULT = dict(abs_value=30e8, rel_mult=3.0, tod_mult=3.0, thr_mult=1.0, min_value=5e8)


def detect(m, prev_close, threshold=None, profile=None, typical=None, rules=None, clean_rules=None):
    """하루치 1분봉(여러 종목)에서 봉마다 네 기준의 배수와 통과 여부, 깨끗함을 계산한다.

    threshold: 종목 → 과거 급등 임계치(원), profile·typical: 03-3의 시간대 프로필·평소 하루 거래대금
    반환: 모든 봉의 표. hit_<기준> 열이 True인 봉이 그 기준의 햄버거 후보.
    """
    r = DEFAULT | (rules or {})
    x = clean_flags(bar_shape(m), clean_rules)
    x["rel20"] = relative_turnover(x, 20)
    if profile is not None and typical is not None:
        x["tod"] = tod_relative(x, profile, typical)
    if threshold is not None:
        x["thr"] = x.value / x.code.map(threshold)
    x["ret"] = x.close / x.code.map(prev_close) - 1
    x["available_at"] = x.time + pd.Timedelta(minutes=1)
    x["hit_abs"] = x.value >= r["abs_value"]
    big = x.value >= r["min_value"]
    x["hit_rel20"] = big & (x.rel20 >= r["rel_mult"])
    x["hit_tod"] = big & (x.get("tod", pd.Series(float("nan"), index=x.index)) >= r["tod_mult"])
    x["hit_thr"] = big & (x.get("thr", pd.Series(float("nan"), index=x.index)) >= r["thr_mult"])
    return x


def events(x, criterion="thr", clean_only=True, first_only=True):
    """detect 결과에서 한 기준의 햄버거 이벤트를 고른다. first_only면 종목·날짜마다 첫 이벤트만."""
    e = x[x[f"hit_{criterion}"]]
    if clean_only:
        e = e[e.clean]
    if first_only:
        e = e.sort_values("time").groupby(["code", "date"]).head(1)
    cols = ["code", "date", "time", "available_at", "open", "high", "low", "close", "value", "ret",
            "rel20", "tod", "thr", "close_location", "body_ratio", "upper_wick", "quiet_range", "clean"]
    e = e[[c for c in cols if c in e]].rename(columns={"high": "ref_high", "low": "ref_low"})
    return e.assign(criterion=criterion, rule_version=RULE_VERSION).sort_values(["time", "code"], ignore_index=True)
