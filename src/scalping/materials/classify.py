"""07-4 LLM으로 재료 유무·유형·강도 분류

    uv run python -m scalping.materials.classify 411080 20261023 0920   # 07-3에서 받은 제목을 분류

LLM에게 묻는 것: 이 제목들 안에 이 종목의 주가를 움직일 **새 사실(재료)** 이 있는가, 어떤 종류이고 얼마나 강한가.
LLM에게 묻지 않는 것: 오를까, 살까, 목표가는. 그 판단은 규칙(08·09장)과 모델(11장)이 데이터로 한다.

- 출력은 JSON 하나. validate() 가 형식과 앞뒤가 맞는지 검사하고, 틀리면 한 번 다시 묻는다
- 같은 입력은 캐시(data/processed/materials.jsonl)에서 꺼낸다. 키에 프롬프트 버전과 모델 이름을 넣는다
- 제목이 하나도 없으면 LLM을 부르지 않는다 (재료 없음, source="rule")
"""

import json
import os
import sys
import threading

import pandas as pd
from dotenv import load_dotenv

from scalping.paths import PROCESSED, ROOT

PROMPT_VERSION = "material-v1"
TYPES = ["실적", "수주·계약", "정책·규제", "임상·허가", "기술·제품", "M&A·지분", "자본거래", "테마·업황", "기타", "없음"]
SCOPES = ["종목", "테마", "없음"]
CACHE_PATH = PROCESSED / "materials.jsonl"
MAX_TITLES = 30
_LOCK = threading.Lock()

SYSTEM = """너는 한국 주식 뉴스·공시 제목을 분류하는 도우미다. 주어진 제목만 근거로 판단한다.
주가 전망, 매수·매도 의견, 목표가는 절대 말하지 않는다.

재료란 회사의 가치나 수급 기대를 바꾸는 새 사실이다.
- 종류: 실적, 수주·계약, 정책·규제, 임상·허가, 기술·제품, M&A·지분(인수·합병·최대주주 변경·지분 취득), 자본거래(증자·자사주·감자 등), 테마·업황(업종 전체에 걸친 뉴스), 기타
- 가격 움직임만 전하는 제목은 재료가 아니다: "급등세 기록중", "상승폭 확대", "상한가 진입", "상승률 상위 N종목", "외국계 순매수 상위", 이유 없는 특징주
- 여러 종목을 나열한 시황 기사에 이 종목 이름이 들어 있을 뿐이면 이 종목의 직접 재료가 아니다(테마 언급)
- 다른 종목에 관한 제목은 그 내용이 이 종목이 속한 업종 전체에 해당할 때만 테마·업황 재료로 본다

강도(strength): 0 = 재료 없음, 1 = 약함(테마·업황 언급, 이미 알려진 내용의 반복), 2 = 보통(이 종목의 구체적인 새 사실),
3 = 강함(대형 계약·인허가·인수·흑자전환처럼 기업가치를 크게 바꿀 사실)

아래 JSON 하나만 출력한다.
{"has_material": true 또는 false, "type": 종류 하나 또는 "없음", "strength": 0~3, "scope": "종목" 또는 "테마" 또는 "없음",
 "evidence": [근거 제목 번호], "price_only": 제목들이 가격 움직임 보도뿐이면 true, "reason": "한 문장"}"""


def build_messages(code, name, until, df):
    """제목을 오래된 것부터 번호를 붙여 넘긴다. 관련 종목이 여럿이면 표시한다."""
    df = df.tail(MAX_TITLES).reset_index(drop=True)
    lines = [f"[{i + 1}] {r.time:%m-%d %H:%M} {r.source} | {r.title}" + (f" (관련 {len(r.codes)}종목)" if len(r.codes) > 1 else "")
             for i, r in df.iterrows()]
    user = f"종목: {name} ({code})\n기준 시각: {pd.Timestamp(until):%Y-%m-%d %H:%M} (이 시각 전에 나온 제목만 있다)\n제목:\n" + "\n".join(lines)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], len(df)


def validate(d, n_titles):
    """형식·범위·앞뒤 일관성 검사. 문제가 없으면 빈 목록."""
    err = []
    if not isinstance(d.get("has_material"), bool):
        err.append("has_material은 true/false")
    if d.get("type") not in TYPES:
        err.append(f"type은 {TYPES} 중 하나")
    if d.get("strength") not in (0, 1, 2, 3):
        err.append("strength는 0~3 정수")
    if d.get("scope") not in SCOPES:
        err.append(f"scope는 {SCOPES} 중 하나")
    if not isinstance(d.get("price_only"), bool):
        err.append("price_only는 true/false")
    ev = d.get("evidence")
    if not isinstance(ev, list) or any(not isinstance(i, int) or not 1 <= i <= n_titles for i in ev):
        err.append(f"evidence는 1~{n_titles} 번호 목록")
    if not err:
        if d["has_material"] and (d["strength"] == 0 or d["type"] == "없음" or d["scope"] == "없음" or not ev):
            err.append("재료가 있으면 strength 1 이상, type·scope 지정, evidence 필요")
        if not d["has_material"] and (d["strength"] != 0 or d["type"] != "없음"):
            err.append("재료가 없으면 strength 0, type 없음")
    return err


def client_from_env():
    from openai import OpenAI
    load_dotenv(ROOT / ".env")
    return OpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY")), os.getenv("OPENAI_MODEL")


def ask(client, model, messages):
    # temperature 는 넣지 않는다: 받지 않는 모델이 있다(07-4). 대신 같은 입력의 반복 일치율을 잰다
    r = client.chat.completions.create(model=model, messages=messages, response_format={"type": "json_object"})
    return r.choices[0].message.content, r.usage


NO_TITLES = dict(has_material=False, type="없음", strength=0, scope="없음", evidence=[], price_only=False,
                 reason="창 안에 제목이 없음")


def classify(client, model, code, name, until, df):
    if df.empty:
        return dict(NO_TITLES, source="rule", n_sent=0)
    messages, n = build_messages(code, name, until, df)
    for attempt in range(2):
        text, usage = ask(client, model, messages)
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            d, err = {}, ["JSON 하나만 출력"]
        else:
            err = validate(d, n)
        if not err:
            return dict(d, source="llm", n_sent=n, attempts=attempt + 1,
                        tokens=usage.prompt_tokens + usage.completion_tokens)
        messages = messages + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "형식 오류: " + "; ".join(err) + ". JSON 하나만 다시 출력"}]
    return dict(NO_TITLES, source="invalid", n_sent=n, reason="; ".join(err))


def cache_key(code, until, model):
    return f"{code}|{pd.Timestamp(until):%Y-%m-%d %H:%M}|{PROMPT_VERSION}|{model}"


def load_cache():
    if not CACHE_PATH.exists():
        return {}
    with open(CACHE_PATH, encoding="utf-8") as f:
        return {(d := json.loads(line))["key"]: d for line in f}


def label(client, model, code, name, until, df, cache):
    key = cache_key(code, until, model)
    if key in cache:
        return cache[key]
    d = dict(classify(client, model, code, name, until, df), key=key)
    with _LOCK:                                     # 여러 스레드가 캐시 파일에 함께 쓸 때
        cache[key] = d
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return d


def main():
    from scalping.materials.news import NEWS_DIR
    code, day, hhmm = sys.argv[1], sys.argv[2], sys.argv[3]
    until = pd.Timestamp(f"{day} {hhmm[:2]}:{hhmm[2:]}")
    df = pd.read_parquet(NEWS_DIR / day / f"{code}_{hhmm}.parquet")
    name = next((n for c, n in zip(df.codes.explode(), df.names.explode()) if c == code), code) if len(df) else code
    client, model = client_from_env()
    print(json.dumps(label(client, model, code, name, until, df, load_cache()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
