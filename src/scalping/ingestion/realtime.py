"""03-2 장중 실시간 수집기 — 체결(H0STCNT0)·호가(H0STASP0) 원문과 장중 프로그램매매를 장 시간 내내 남긴다.

    uv run python -m scalping.ingestion.realtime --until 15:35            # 지금부터 15:35까지
    uv run python -m scalping.ingestion.realtime --probe 45               # 구독 한도 확인 (장외 가능)

과거 틱·호가·장중 프로그램매매는 API로 다시 받을 수 없다(03-2). 그래서 장이 열리는 날마다 이 수집기를 돌린다.
- 대상: 거래대금 순위(KOSPI·KOSDAQ 각 30종목) 상위 종목, 5분마다 다시 고른다
- 구독 한도: 세션당 41건(실측) → 체결+호가로 종목당 2건이라 기본 20종목
- 저장: data/raw/realtime/YYYYMMDD/
    H0STCNT0.tsv.gz, H0STASP0.tsv.gz   수신시각(ns) \t 원문 (장 마감 뒤 압축)
    program.tsv.gz                      수신시각(ns) \t 종목 \t 장중 프로그램매매 최근 30건(JSON)
    control.tsv                         구독·해지·응답 기록 — 언제 어떤 종목을 보고 있었는지
"""

import argparse
import asyncio
import datetime as dt
import gzip
import json
import shutil
import time

import pandas as pd
import websockets

from scalping.kis import KIS
from scalping.paths import REALTIME_DIR

WS_URL = "ws://ops.koreainvestment.com:21000"
TRS = ("H0STCNT0", "H0STASP0")
FILES = TRS + ("program",)
# 대상 제외: 투자위험·경고·주의 / 관리 / 정리매매 / 불성실공시 / 우선주 / 거래정지 / ETF / ETN / 신용불가 / SPAC
EXCLUDE = "1110111101"
REFRESH_SEC, PROGRAM_SEC = 300, 60
Q = "/uapi/domestic-stock/v1/quotations"

# 체결 필드 순서: 한국투자증권 공식 예제 ccnl_krx (2026-10 기준 47개)
TRADE_COLS = [
    "code", "time", "price", "sign", "change", "change_rate", "wavg", "open", "high", "low",
    "ask1", "bid1", "volume", "acc_volume", "acc_value", "sell_cnt", "buy_cnt", "net_cnt", "strength",
    "sell_vol", "buy_vol", "side", "buy_rate", "vol_rate", "open_time", "open_sign", "open_diff",
    "high_time", "high_sign", "high_diff", "low_time", "low_sign", "low_diff", "date", "new_mkop",
    "halt", "ask_qty1", "bid_qty1", "total_ask_qty", "total_bid_qty", "turnover", "prev_vol",
    "prev_vol_rate", "hour_cls", "mrkt_trtm", "vi_price", "market_cls"]


def value_rank(kis):
    """KOSPI·KOSDAQ 거래대금 순위를 합쳐 누적 거래대금 내림차순 종목코드 목록"""
    rows = []
    for iscd in ("0001", "1001"):
        body = kis.get(Q + "/volume-rank", "FHPST01710000", {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": iscd,
            "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "3", "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": EXCLUDE, "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""})
        rows += [(int(r["acml_tr_pbmn"]), r["mksc_shrn_iscd"]) for r in body.get("output", [])]
    return [c for _, c in sorted(rows, reverse=True)]


def program_rows(kis, code):
    body = kis.get(Q + "/program-trade-by-stock", "FHPPG04650101",
                   {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
    return body.get("output", [])


class Collector:
    def __init__(self, kis, day_dir, n_stocks):
        self.kis, self.dir, self.n = kis, day_dir, n_stocks
        self.dir.mkdir(parents=True, exist_ok=True)
        self.subs = {}
        self.files = {name: open(self.dir / f"{name}.tsv", "a", encoding="utf-8") for name in FILES}
        self.control = open(self.dir / "control.tsv", "a", encoding="utf-8")
        self.key = kis.approval_key()
        self.counts = {name: 0 for name in FILES}

    def log(self, kind, text):
        self.control.write(f"{time.time_ns()}\t{kind}\t{text}\n")
        self.control.flush()

    async def send(self, ws, tr_type, tr_id, code):
        await ws.send(json.dumps({
            "header": {"approval_key": self.key, "custtype": "P", "tr_type": tr_type, "content-type": "utf-8"},
            "body": {"input": {"tr_id": tr_id, "tr_key": code}}}))
        await asyncio.sleep(0.05)

    async def subscribe(self, ws, code):
        for tr in TRS:
            await self.send(ws, "1", tr, code)
        self.subs[code] = time.time()
        self.log("SUB", code)

    async def unsubscribe(self, ws, code):
        for tr in TRS:
            await self.send(ws, "2", tr, code)
        self.subs.pop(code, None)
        self.log("UNSUB", code)

    async def reader(self, ws):
        async for msg in ws:
            now = time.time_ns()
            if msg[0] in "01":                       # 실시간 데이터: 암호화여부|tr_id|건수|본문
                tr = msg.split("|", 2)[1]
                if tr in self.files:
                    self.files[tr].write(f"{now}\t{msg}\n")
                    self.counts[tr] += 1
            else:
                j = json.loads(msg)
                if j.get("header", {}).get("tr_id") == "PINGPONG":
                    await ws.send(msg)                # 받은 PINGPONG을 그대로 돌려보내야 연결이 유지된다
                else:
                    hd, bd = j.get("header", {}), j.get("body", {})
                    self.log("RESP", f"{hd.get('tr_id')}\t{hd.get('tr_key')}\t{bd.get('msg_cd')}\t{bd.get('msg1')}")

    async def refresher(self, ws, until):
        while dt.datetime.now() < until:
            try:
                ranked = await asyncio.to_thread(value_rank, self.kis)
            except Exception as e:
                self.log("ERR", f"rank {type(e).__name__} {e}")
                ranked = []
            if ranked:
                keep_zone = set(ranked[: self.n * 2])    # 순위가 잠깐 밀려도 2N 안이면 계속 본다
                for code in [c for c in self.subs if c not in keep_zone]:
                    await self.unsubscribe(ws, code)
                for code in ranked:
                    if len(self.subs) >= self.n:
                        break
                    if code not in self.subs:
                        await self.subscribe(ws, code)
            for f in self.files.values():
                f.flush()
            self.log("STAT", json.dumps({"subs": sorted(self.subs), **self.counts}))
            left = (until - dt.datetime.now()).total_seconds()
            await asyncio.sleep(max(0.0, min(REFRESH_SEC, left)))

    async def program_poller(self, until):
        """장중 프로그램매매는 최근 30건만 조회되므로 1분마다 남긴다."""
        f = self.files["program"]
        while dt.datetime.now() < until:
            started = time.time()
            for code in list(self.subs):
                try:
                    rows = await asyncio.to_thread(program_rows, self.kis, code)
                    f.write(f"{time.time_ns()}\t{code}\t{json.dumps(rows, ensure_ascii=False)}\n")
                    self.counts["program"] += 1
                except Exception as e:
                    self.log("ERR", f"program {code} {type(e).__name__} {e}")
            f.flush()
            left = (until - dt.datetime.now()).total_seconds()
            await asyncio.sleep(max(0.0, min(PROGRAM_SEC - (time.time() - started), left)))

    async def run(self, until):
        poller = asyncio.create_task(self.program_poller(until))
        while dt.datetime.now() < until:
            try:
                async with websockets.connect(WS_URL, ping_interval=None, max_size=None) as ws:
                    self.log("CONNECT", WS_URL)
                    resub, self.subs = list(self.subs), {}
                    for code in resub:                    # 끊겼다 다시 붙으면 같은 종목을 다시 구독한다
                        await self.subscribe(ws, code)
                    tasks = {asyncio.create_task(self.reader(ws)), asyncio.create_task(self.refresher(ws, until))}
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                    for t in done:
                        if t.exception():
                            raise t.exception()
            except Exception as e:
                self.log("ERR", f"ws {type(e).__name__} {e}")
                await asyncio.sleep(5)
        poller.cancel()

    def close(self):
        for f in self.files.values():
            f.close()
        self.log("STOP", json.dumps(self.counts))
        self.control.close()
        for name in FILES:
            src = self.dir / f"{name}.tsv"
            if src.exists() and src.stat().st_size:
                with open(src, "rb") as fi, gzip.open(self.dir / f"{name}.tsv.gz", "ab") as fo:
                    shutil.copyfileobj(fi, fo)
                src.unlink()


def parse_trade_line(line):
    """'수신시각(ns)\\t0|H0STCNT0|건수|필드^필드^...' 한 줄 → 체결 dict 목록"""
    recv, raw = line.rstrip("\n").split("\t", 1)
    _, tr_id, count, payload = raw.split("|", 3)
    values, k = payload.split("^"), int(count)
    n = len(values) // k
    cols = TRADE_COLS[:n] + [f"f{i}" for i in range(len(TRADE_COLS), n)]
    return [dict(zip(cols, values[i * n:(i + 1) * n]), recv_ns=int(recv)) for i in range(k)]


def load_trades(day):
    """수집한 체결 원문을 표로 읽는다. 시각 time(HHMMSS)은 거래소 체결 시각, recv_ns는 내가 받은 시각."""
    path = REALTIME_DIR / pd.Timestamp(day).strftime("%Y%m%d") / "H0STCNT0.tsv.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        rows = [r for line in f for r in parse_trade_line(line)]
    df = pd.DataFrame(rows)
    for c in ("price", "volume", "acc_volume", "acc_value"):
        df[c] = df[c].astype("int64")
    return df


async def probe(kis, n):
    """종목 n개를 체결(H0STCNT0)로 차례로 구독해 성공 건수를 센다. 연결을 닫으면 구독도 사라진다."""
    codes = value_rank(kis)[:n]
    key = kis.approval_key()
    ok = 0
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        for i, code in enumerate(codes, 1):
            await ws.send(json.dumps({"header": {"approval_key": key, "custtype": "P", "tr_type": "1",
                                                 "content-type": "utf-8"},
                                      "body": {"input": {"tr_id": "H0STCNT0", "tr_key": code}}}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), 10)
                if msg[0] in "01":
                    continue
                j = json.loads(msg)
                if j["header"]["tr_id"] == "PINGPONG":
                    await ws.send(msg)
                    continue
                if j["body"].get("msg1") == "SUBSCRIBE SUCCESS":
                    ok += 1
                else:
                    print(i, code, j["body"].get("msg_cd"), j["body"].get("msg1"))
                break
    print(f"요청 {len(codes)}건, 성공 {ok}건")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="15:35", help="종료 시각 HH:MM")
    ap.add_argument("--stocks", type=int, default=20, help="동시 구독 종목 수 (종목당 2건)")
    ap.add_argument("--probe", type=int, help="구독 한도 확인용 종목 수")
    a = ap.parse_args()
    kis = KIS("real")
    if a.probe:
        asyncio.run(probe(kis, a.probe))
        return
    today = dt.date.today()
    until = dt.datetime.combine(today, dt.time.fromisoformat(a.until))
    c = Collector(kis, REALTIME_DIR / today.strftime("%Y%m%d"), a.stocks)
    try:
        asyncio.run(c.run(until))
    finally:
        c.close()


if __name__ == "__main__":
    main()
