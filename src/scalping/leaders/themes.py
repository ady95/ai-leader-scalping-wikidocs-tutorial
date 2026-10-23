"""02-2 테마 분류와 주도 섹터

한국투자증권이 공개하는 테마 코드 파일(앱키 없이 내려받을 수 있음)을 테마-종목 표로 바꾸고,
시점별 스냅샷에서 "함께 오르는 테마"를 찾는다.

    python -m scalping.leaders.themes      # data/raw/themes.csv 저장
"""

import datetime as dt
import io
import zipfile

import pandas as pd
import requests

from scalping.paths import RAW

URL = "https://new.real.download.dws.co.kr/common/master/theme_code.mst.zip"
# 함께 움직일 이유가 없는 묶음(상장 시기 등)은 테마에서 뺀다
EXCLUDE_KEYWORDS = ["신규 상장"]


def download():
    raw = requests.get(URL, timeout=60).content
    return zipfile.ZipFile(io.BytesIO(raw)).read("theme_code.mst").decode("cp949")


def parse(text):
    """한 줄 = 테마코드 3자리 + 테마명 + 종목코드 6자리 + 빈칸 3자리 (고정폭 47자)"""
    rows = [{"theme_code": line[0:3], "theme_name": line[3:-9].strip(), "code": line[-9:-3]}
            for line in text.splitlines() if line.strip()]
    df = pd.DataFrame(rows).drop_duplicates(["theme_code", "code"])
    return df[~df.theme_name.str.contains("|".join(EXCLUDE_KEYWORDS))].reset_index(drop=True)


def theme_strength(snap, themes, min_ret=0.05, min_up=2):
    """스냅샷에서 min_ret 이상 오른 종목이 min_up개 이상인 테마만 남기고, 그 종목들의 거래대금으로 순위를 매긴다.

    한 종목만 오르는 것은 테마가 아니다(동반 상승). 반환: 테마별 상승 종목 수, 상승 종목 거래대금 합,
    전체 상승 종목 거래대금 대비 비중, 테마 안 거래대금 1위 종목.
    """
    hot = snap[snap.ret >= min_ret]
    j = themes.merge(hot[["cum_value", "ret"]], left_on="code", right_index=True)
    if j.empty:
        return pd.DataFrame(columns=["theme_name", "n_up", "up_value", "value_share", "leader", "leader_ret"])
    j = j.sort_values("cum_value", ascending=False)
    g = j.groupby("theme_code")
    out = pd.DataFrame({"theme_name": g.theme_name.first(), "n_up": g.size(), "up_value": g.cum_value.sum(),
                        "leader": g.code.first(), "leader_ret": g.ret.first()})
    out = out[out.n_up >= min_up]
    out["value_share"] = out.up_value / hot.cum_value.sum()
    return out.sort_values("up_value", ascending=False)


def main():
    df = parse(download())
    RAW.mkdir(parents=True, exist_ok=True)
    df.assign(updated=dt.date.today()).to_csv(RAW / "themes.csv", index=False, encoding="utf-8")
    print(f"테마 {df.theme_code.nunique()}개, 테마-종목 {len(df):,}쌍, 종목 {df.code.nunique():,}개 → {RAW / 'themes.csv'}")


if __name__ == "__main__":
    main()
