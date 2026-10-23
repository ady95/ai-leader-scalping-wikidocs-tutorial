"""03-4 종목별 프로그램매매

    uv run python -m scalping.ingestion.program 005930 20261023     # 그날까지 30거래일 일별 프로그램매매
    uv run python -m scalping.ingestion.program 005930               # 지금 장중 프로그램매매 추이 (최근 30건)

실측으로 확인한 것 (2026-10, 03-4)
- 일별(FHPPG04650201)은 과거 날짜로 조회할 수 있다 (2024년도 확인). 한 번에 30거래일
- 장중 체결 추이(FHPPG04650101)는 **최근 30건만** 주고 연속조회가 안 된다 → 지나간 장중 흐름은 다시 받을 수 없다.
  장중 값이 필요하면 realtime.py 로 장 시간에 계속 남겨야 한다
"""

import sys

import pandas as pd

from scalping.kis import KIS
from scalping.paths import PROGRAM_DIR

Q = "/uapi/domestic-stock/v1/quotations"
NUM = ["whol_smtn_seln_tr_pbmn", "whol_smtn_shnu_tr_pbmn", "whol_smtn_ntby_tr_pbmn", "acml_tr_pbmn"]
RENAME = {"stck_bsop_date": "date", "whol_smtn_seln_tr_pbmn": "pgm_sell", "whol_smtn_shnu_tr_pbmn": "pgm_buy",
          "whol_smtn_ntby_tr_pbmn": "pgm_net", "acml_tr_pbmn": "value", "stck_clpr": "close"}


def daily(kis, code, day, market="J"):
    """day까지 30거래일의 일별 프로그램 매도·매수·순매수 거래대금(원)"""
    body = kis.get(Q + "/program-trade-by-stock-daily", "FHPPG04650201",
                   {"FID_COND_MRKT_DIV_CODE": market, "FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": day})
    df = pd.DataFrame(body.get("output", []))
    if df.empty:
        return df
    df = df[list(RENAME)].rename(columns=RENAME)
    df["date"] = pd.to_datetime(df.date, format="%Y%m%d")
    for c in ("pgm_sell", "pgm_buy", "pgm_net", "value", "close"):
        df[c] = df[c].astype("int64")
    df.insert(0, "code", code)
    return df.sort_values("date", ignore_index=True)


def intraday(kis, code, market="J"):
    """지금 시각까지의 장중 프로그램매매 추이 최근 30건 (누적 순매수 거래대금 pgm_net 포함)"""
    body = kis.get(Q + "/program-trade-by-stock", "FHPPG04650101",
                   {"FID_COND_MRKT_DIV_CODE": market, "FID_INPUT_ISCD": code})
    df = pd.DataFrame(body.get("output", []))
    if df.empty:
        return df
    df = df.rename(columns={"bsop_hour": "time", **RENAME})
    for c in ("pgm_sell", "pgm_buy", "pgm_net"):
        df[c] = df[c].astype("int64")
    df.insert(0, "code", code)
    return df[["code", "time", "stck_prpr", "pgm_sell", "pgm_buy", "pgm_net"]].sort_values("time", ignore_index=True)


def main():
    kis = KIS("real")
    if len(sys.argv) > 2:
        code, day = sys.argv[1], sys.argv[2]
        df = daily(kis, code, day)
        PROGRAM_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(PROGRAM_DIR / f"{code}_{day}.parquet", index=False)
    else:
        df = intraday(kis, sys.argv[1])
    print(df.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
