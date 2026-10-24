"""07-3 뉴스·공시 제목 수집과 시각 정렬

    uv run python -m scalping.materials.news 411080 20261023 0920     # 그 시각 전에 나온 제목 (전 거래일 15:30부터)

실측으로 확인한 것 (2026-10, 07-3)
- 종합 시황·공시 제목(FHKST01011800)은 과거 날짜·시각을 넣어 조회할 수 있다. 한 번에 40건, 최신순
- 종목코드를 넣으면 그 종목이 관련 종목(최대 10개)으로 등록된 제목만 온다. 여러 종목을 나열한 시황 기사도 섞인다
- 본문은 주지 않는다. 제목·작성 시각·제공처·관련 종목만 쓴다
시점 정합: 이벤트가 확정된 시각(available_at) **전에** 작성된 제목만 쓴다.
"""

import sys

import pandas as pd

from scalping.kis import KIS
from scalping.paths import RAW

NEWS_DIR = RAW / "news"
PATH = "/uapi/domestic-stock/v1/quotations/news-title"
PAGE = 40


def page(kis, code, until):
    """until 시각까지(포함) 작성된 제목 최대 40건, 최신순"""
    body = kis.get(PATH, "FHKST01011800", {
        "FID_NEWS_OFER_ENTP_CODE": "", "FID_COND_MRKT_CLS_CODE": "", "FID_INPUT_ISCD": code, "FID_TITL_CNTT": "",
        "FID_INPUT_DATE_1": until.strftime("00%Y%m%d"), "FID_INPUT_HOUR_1": until.strftime("0000%H%M%S"),
        "FID_RANK_SORT_CLS_CODE": "", "FID_INPUT_SRNO": ""})
    raw = pd.DataFrame(body.get("output") or [])
    if raw.empty:
        return raw
    codes = raw[[f"iscd{i}" for i in range(1, 11)]].apply(lambda r: [c for c in r if c], axis=1)
    names = raw[[f"kor_isnm{i}" for i in range(1, 11)]].apply(lambda r: [n for n in r if n], axis=1)
    return pd.DataFrame({"srno": raw.cntt_usiq_srno,
                         "time": pd.to_datetime(raw.data_dt + raw.data_tm, format="%Y%m%d%H%M%S"),
                         "source": raw.dorg.str.strip(), "title": raw.hts_pbnt_titl_cntt.str.strip(),
                         "codes": codes, "names": names})


def titles(kis, code, since, until, max_pages=5):
    """since 이상 until 미만에 작성된 제목. 40건이 꽉 차면 더 이전 쪽으로 이어서 받는다."""
    out, t = [], until - pd.Timedelta(seconds=1)
    for _ in range(max_pages):
        df = page(kis, code, t)
        if df.empty:
            break
        out.append(df)
        oldest = df.time.min()
        if len(df) < PAGE or oldest < since:
            break
        t = oldest - pd.Timedelta(seconds=1)
    if not out:
        return pd.DataFrame(columns=["srno", "time", "source", "title", "codes", "names"])
    df = pd.concat(out, ignore_index=True).drop_duplicates("srno")
    df = df[(df.time >= since) & (df.time < until)]
    return df.sort_values("time", ignore_index=True)


def window(day, prev_day, until):
    """뉴스 창: 전 거래일 정규장 마감(15:30)부터 until까지 — 장 마감 뒤·밤사이·장중 제목을 모두 담는다"""
    return pd.Timestamp(prev_day) + pd.Timedelta(hours=15, minutes=30), pd.Timestamp(until)


def align(df, code, until):
    """이벤트 시각 기준으로 제목을 요약한다 (07-3)"""
    own = df[df.codes.map(lambda c: list(c) == [code])] if len(df) else df   # 이 종목 하나만 걸린 제목 (parquet은 배열로 읽힌다)
    last = own.time.max() if len(own) else None
    return dict(n_titles=len(df), n_own=len(own),
                n_own_today=int((own.time >= pd.Timestamp(until).normalize()).sum()) if len(own) else 0,
                minutes_since_own=round((pd.Timestamp(until) - last).total_seconds() / 60, 1) if last is not None else None)


def collect(kis, code, day, prev_day, until, refresh=False):
    """제목을 받아 data/raw/news/<날짜>/<종목>_<HHMM>.parquet 로 저장하고 돌려준다"""
    path = NEWS_DIR / pd.Timestamp(day).strftime("%Y%m%d") / f"{code}_{pd.Timestamp(until):%H%M}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    since, until = window(day, prev_day, until)
    df = titles(kis, code, since, until)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def main():
    code, day, hhmm = sys.argv[1], sys.argv[2], sys.argv[3]
    until = pd.Timestamp(f"{day} {hhmm[:2]}:{hhmm[2:]}")
    prev_day = (pd.Timestamp(day) - pd.offsets.BDay(1)).strftime("%Y%m%d")   # 휴장일은 따로 확인
    df = collect(KIS("real"), code, day, prev_day, until, refresh=True)
    pd.set_option("display.width", 200)
    print(df[["time", "source", "title"]].assign(n_codes=df.codes.map(len)).to_string(index=False))
    print(align(df, code, until))


if __name__ == "__main__":
    main()
