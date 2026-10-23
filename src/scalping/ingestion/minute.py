"""03-2·03-5 1분봉 — KRX(J), NXT(NX), 통합(UN = KRX + NXT)

    uv run python -m scalping.ingestion.minute --days 20 --top 100            # 최근 20거래일, 날마다 거래대금 상위 100종목
    uv run python -m scalping.ingestion.minute --days 20 --top 100 --market NX
    uv run python -m scalping.ingestion.minute 005930:20261023                # 특정 종목·날짜

실측으로 확인한 것 (2026-10, 03-2)
- 한국투자증권 일별 분봉 API는 **최근 약 1년**만 돌려준다. 오래된 날부터 사라지므로 미리 쌓아 둔다
- 분봉 가격은 그 뒤의 분할·증자를 반영한 수정주가다 (형제 도서 실측)
- 시각(stck_cntg_hour)은 봉이 **시작한** 시각이다. 09:00 봉은 09:00:00~09:00:59의 체결
- acml_tr_pbmn 은 그날 누적 거래대금 → 앞 봉과의 차이가 그 1분의 실제 체결대금 (03-1)
- NXT는 프리마켓 08:00~08:50, 애프터마켓 15:30~20:00 봉도 함께 온다
- 통합(UN) 봉의 거래량·거래대금은 같은 분의 KRX + NXT 합이다 (03-5)
- NXT에서 거래되지 않는 종목은 NX 봉이 비어 있다. UN은 과거 날짜면 비어 있고, 최근 날짜면 19:59에
  하루 누적값만 담은 봉 하나가 온다 → load_minute 이 걸러 낸다
"""

import argparse
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from scalping.ingestion.daily import load_daily
from scalping.kis import KIS, KISError
from scalping.paths import MINUTE_DIR, RAW

PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
TR_ID = "FHKST03010230"       # 주식 일별 분봉 조회, 한 번에 최대 120행 (최근 시각부터 과거 방향)
SESSION = {"J": ("090000", "153900"), "NX": ("080000", "200000"), "UN": ("080000", "200000")}
SPECIAL_LAST = {("J", "20251113"): "163900"}     # 대학수학능력시험일: 1시간 늦게 열고 늦게 닫는다
COLUMNS = {"stck_cntg_hour": "time", "stck_oprc": "open", "stck_hgpr": "high", "stck_lwpr": "low",
           "stck_prpr": "close", "cntg_vol": "volume", "acml_tr_pbmn": "cum_value"}
INT_COLS = ["open", "high", "low", "close", "volume", "cum_value"]


def fetch_day(kis, code, day, market="J"):
    """하루치 분봉. 받은 행의 가장 이른 시각 1분 전부터 다시 요청하며 과거 방향으로 내려간다."""
    first, last = SESSION[market]
    last = SPECIAL_LAST.get((market, day), last)
    rows, hour = {}, last
    while hour >= first:
        body = kis.get(PATH, TR_ID, {
            "FID_COND_MRKT_DIV_CODE": market, "FID_INPUT_ISCD": code, "FID_INPUT_HOUR_1": hour,
            "FID_INPUT_DATE_1": day, "FID_PW_DATA_INCU_YN": "N", "FID_FAKE_TICK_INCU_YN": ""})
        page = [r for r in body.get("output2", []) if r.get("stck_bsop_date") == day
                and first <= r.get("stck_cntg_hour", "") <= last]
        new = [r for r in page if r["stck_cntg_hour"] not in rows]
        if not new:
            break
        rows.update({r["stck_cntg_hour"]: r for r in new})
        earliest = dt.datetime.strptime(min(r["stck_cntg_hour"] for r in new), "%H%M%S")
        hour = (earliest - dt.timedelta(minutes=1)).strftime("%H%M%S")
    df = pd.DataFrame(list(rows.values()), columns=list(COLUMNS)).rename(columns=COLUMNS)
    df[INT_COLS] = df[INT_COLS].astype("int64")
    df.insert(0, "date", pd.Timestamp(day))
    df.insert(0, "code", code)
    return df.sort_values("time", ignore_index=True)


def to_standard(df):
    """저장 형식 → 분석 형식: time을 시각으로, value(그 1분의 실제 체결대금)를 더한다."""
    df = df.copy()
    df["time"] = pd.to_datetime(df.date.dt.strftime("%Y-%m-%d") + " " + df.time, format="%Y-%m-%d %H%M%S")
    df = df.sort_values(["code", "time"], ignore_index=True)
    df["value"] = df.groupby("code").cum_value.diff().fillna(df.cum_value).astype("int64")
    return df


def collect(kis, code, day, market, refresh=False):
    path = MINUTE_DIR / market / day / f"{code}.parquet"
    if path.exists() and not refresh:
        return -1
    df = fetch_day(kis, code, day, market)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)               # 빈 결과도 저장해 다시 묻지 않는다
    return len(df)


def load_minute(day, market="J", codes=None):
    """저장된 하루치 분봉을 분석 형식으로 읽는다."""
    files = sorted((MINUTE_DIR / market / pd.Timestamp(day).strftime("%Y%m%d")).glob("*.parquet"))
    if codes is not None:
        files = [f for f in files if f.stem in set(codes)]
    frames = [pd.read_parquet(f) for f in files]
    frames = [f for f in frames if len(f) > (1 if market == "UN" else 0)]   # UN의 요약 봉 1개짜리는 분봉이 아니다
    return to_standard(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()


def top_value_targets(days, top):
    """최근 days거래일 동안 날마다 거래대금 상위 top종목.

    주의: 장 마감 거래대금으로 고르므로 표본 자체에 그날의 결과가 들어 있다(02-1). 장중 순위로 고른
    후보는 실시간 수집(realtime.py)으로 따로 쌓는다.
    """
    d = load_daily()
    recent = sorted(d.date.unique())[-days:]
    d = d[d.date.isin(recent)]
    picked = d.sort_values("value", ascending=False).groupby("date").head(top)
    return sorted(zip(picked.code, picked.date.dt.strftime("%Y%m%d")), key=lambda p: (p[1], p[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", help="종목코드:YYYYMMDD")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--market", choices=["J", "NX", "UN"], default="J")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    pairs = [tuple(t.split(":")) for t in args.targets] or top_value_targets(args.days, args.top)
    kis = KIS("real")
    t0, done, empty, skipped, failed = time.time(), 0, 0, 0, []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(collect, kis, c, d, args.market): (c, d) for c, d in pairs}
        for fut in as_completed(futures):
            done += 1
            try:
                n = fut.result()
                skipped += n == -1
                empty += n == 0
            except KISError as e:
                failed.append(f"{futures[fut]}\t{e}")
            if done % 200 == 0 or done == len(futures):
                el = time.time() - t0
                print(f"{done:>5}/{len(futures)}  빈 날 {empty}  기존 {skipped}  경과 {el / 60:.1f}분", flush=True)
    if failed:
        (RAW / "minute_failed.txt").write_text("\n".join(failed), encoding="utf-8")
        print(f"실패 {len(failed)}건 → {RAW / 'minute_failed.txt'}")


if __name__ == "__main__":
    main()
