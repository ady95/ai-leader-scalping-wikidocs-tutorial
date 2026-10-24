"""04-5 진성 수급 확인: 이벤트 시각까지의 장중 프로그램 순매수

실시간 수집기(03-2)가 1분마다 남긴 program.tsv.gz 를 읽는다. 한 줄 = 수신시각(ns) \t 종목 \t 최근 30건 JSON.
시점 정합 규칙: at 시각의 값으로는 **거래소 시각이 at 이전이고, 내가 at 이전에 받은** 기록만 쓴다.
"""

import gzip
import json

import pandas as pd

from scalping.paths import REALTIME_DIR


def parse_program_lines(lines, day):
    rows = []
    for line in lines:
        recv, code, payload = line.rstrip("\n").split("\t", 2)
        for r in json.loads(payload):
            rows.append(dict(code=code, time=pd.Timestamp(f"{day} {r['bsop_hour'][:2]}:{r['bsop_hour'][2:4]}:{r['bsop_hour'][4:6]}"),
                             pgm_net=int(r["whol_smtn_ntby_tr_pbmn"]), recv=pd.Timestamp(int(recv), tz="UTC")
                             .tz_convert("Asia/Seoul").tz_localize(None)))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 같은 거래소 시각의 기록은 가장 먼저 받은 것을 남긴다 (처음 알게 된 시각이 판단 가능 시각)
    return df.sort_values("recv").drop_duplicates(["code", "time"]).sort_values(["code", "time"], ignore_index=True)


def load_program(day):
    d = pd.Timestamp(day)
    path = REALTIME_DIR / d.strftime("%Y%m%d") / "program.tsv.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return parse_program_lines(f, d.strftime("%Y-%m-%d"))


def program_at(program, code, at):
    """at 시각까지 알 수 있었던 누적 프로그램 순매수 거래대금(원). 기록이 없으면 None."""
    at = pd.Timestamp(at)
    p = program[(program.code == code) & (program.time <= at) & (program.recv <= at)]
    return None if p.empty else int(p.sort_values("time").pgm_net.iloc[-1])


def add_program(events, program, minute):
    """이벤트 표에 확정 시각(available_at)까지의 프로그램 순매수와, 같은 시각까지 누적 거래대금 대비 비율을 붙인다."""
    out = events.copy()
    out["pgm_net"] = [program_at(program, r.code, r.available_at) for r in out.itertuples()]
    cum = [minute[(minute.code == r.code) & (minute.time < r.available_at)].value.sum() for r in out.itertuples()]
    out["pgm_share"] = out.pgm_net / pd.Series(cum, index=out.index).where(lambda s: s > 0)
    return out
