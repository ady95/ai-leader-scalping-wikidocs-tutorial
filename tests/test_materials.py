import pandas as pd

from scalping.materials.classify import build_messages, classify, validate
from scalping.materials.news import align

TITLES = pd.DataFrame(dict(
    time=pd.to_datetime(["2026-01-05 08:10", "2026-01-05 09:58", "2026-01-05 10:03"]),
    source=["가상통신", "가상통신", "가상통신"],
    title=["가상 테마 상승률 상위", "가상전력C, 대규모 공급계약 체결", "가상전력C 급등세 +8%"],
    codes=[["900030", "900010"], ["900030"], ["900030"]], names=[["가상전력C", "가상로봇A"], ["가상전력C"], ["가상전력C"]]))


def test_align_counts_own_titles_before_event():
    a = align(TITLES, "900030", pd.Timestamp("2026-01-05 10:06"))
    assert a == dict(n_titles=3, n_own=2, n_own_today=2, minutes_since_own=3.0)


def test_build_messages_numbers_titles_oldest_first():
    msgs, n = build_messages("900030", "가상전력C", "2026-01-05 10:06", TITLES)
    user = msgs[1]["content"]
    assert n == 3 and "[1] 01-05 08:10" in user and "(관련 2종목)" in user and "[3] 01-05 10:03" in user


def test_validate_rejects_inconsistent_labels():
    ok = dict(has_material=True, type="수주·계약", strength=2, scope="종목", evidence=[2], price_only=False, reason="")
    assert validate(ok, 3) == []
    assert validate(dict(ok, strength=0), 3)                       # 재료가 있는데 강도 0
    assert validate(dict(ok, evidence=[4]), 3)                     # 없는 제목 번호
    assert validate(dict(ok, has_material=False), 3)               # 재료 없음인데 유형·강도가 남음


def test_no_titles_skips_llm():
    d = classify(None, None, "900040", "가상반도체D", "2026-01-05 10:21", TITLES.iloc[0:0])
    assert d["source"] == "rule" and d["has_material"] is False


def test_align_after_parquet_round_trip(tmp_path):
    TITLES.to_parquet(tmp_path / "t.parquet")
    t = pd.read_parquet(tmp_path / "t.parquet")                    # codes 가 numpy 배열로 돌아온다
    assert align(t, "900030", pd.Timestamp("2026-01-05 10:06"))["n_own"] == 2
