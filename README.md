# AI로 검증하는 화제의 주도주 단타매매 따라하기 — 예제 코드

위키독스 책 「[AI로 검증하는 화제의 주도주 단타매매 따라하기](https://wikidocs.net/book/21814)」의 실습 코드 저장소입니다.

> 이 저장소는 교육·연구 목적의 예제 코드이며 투자 권유나 수익률 보증이 아닙니다. 주문 실습은 모의투자(드라이런 기본값)에서만 진행합니다.

## 다루는 내용

- KRX·NXT 1분봉, 실시간 체결·호가, 프로그램매매, 뉴스 제목 수집
- 주도 섹터·대장주 선별과 시점별 후보 스냅샷(`CandidateEvent`)
- 과거 급등 임계치 테이블과 햄버거·깨끗한 기준봉 탐지
- 가격 위치별 돌파 / 눌림 진입, 파동 순번, 시간 필터, LLM 재료 판별
- 초단기 시간손절·저항선 익절·분할익절·추적손절 청산과 오버나이트 보유·다음 날 청산
- LightGBM 진입·보유 판단, 확률 보정, 비용 차감 기대손익
- 위험관리·주문 상태 기계·한국투자증권 Open API 모의자동매매
- 공개 주장 검증과 시점 정합 백테스트(H/E/T/X/O 실험)

## 빠른 시작

```bash
git clone https://github.com/ady95/ai-leader-scalping-wikidocs-tutorial.git
cd ai-leader-scalping-wikidocs-tutorial
uv sync                      # Python 3.11+ 가상환경과 패키지 설치
cp .env.example .env         # 앱키 등을 채운다 (.env 는 커밋 금지)
uv run pytest -q
```

## 장별 실행 순서

| 장 | 명령 | 결과물 |
|---|---|---|
| 01-4 | `uv run pytest -q` | 설치 확인 (호가단위·상한가 계산, 재생 결정성) |
| 01-5 | `uv run python -m scalping.sample` | `data/sample/*.csv` (가상 종목 4개의 하루 1분봉, 가상 뉴스) |
| 01-5 | `uv run python examples/ch01_replay.py` | 하루 재생 로그, `reports/ch01_replay_log.csv`, `reports/ch01_trades.csv` |
| 02-1 | `uv run python -m scalping.sample_market` | `data/sample/market/*.csv` (가상 종목 30개·테마 5개, 일봉 130일, 1분봉 하루) |
| 02-1 | `uv run python examples/ch02_leaders.py turnover` | 거래대금 순위 vs 급등 종목 안 순위 |
| 02-2 | `uv run python -m scalping.leaders.themes` | `data/raw/themes.csv` (한국투자증권 테마 코드 파일, 앱키 불필요) |
| 02-2 | `uv run python examples/ch02_leaders.py themes` | 시각별 주도 테마 |
| 02-3 | `uv run python examples/ch02_leaders.py daily` | 일봉 구조(저항·박스·상방 매물대)와 평가표 |
| 02-4 | `uv run python examples/ch02_leaders.py kki` | 종목의 끼(+20% 일수·상한가 터치) |
| 02-5 | `uv run python examples/ch02_leaders.py snapshot` | 5분 후보 스냅샷·NO_TRADE, `reports/ch02_candidates.csv` |
| 03-2 | `uv run python -m scalping.ingestion.master` | `data/raw/universe.parquet` (상장 + 최근 상장폐지, 앱키 불필요) |
| 03-2 | `uv run python -m scalping.ingestion.daily` | `data/raw/daily/<종목>.parquet` (2025-04-01~, 원주가) |
| 03-2 | `uv run python -m scalping.ingestion.minute --days 20 --top 100` | `data/raw/minute/J/<날짜>/<종목>.parquet` (`--market NX`·`UN` 으로 NXT·통합) |
| 03-2 | `uv run python -m scalping.ingestion.realtime --until 15:35` | `data/raw/realtime/<날짜>/` 체결·호가·장중 프로그램매매 (`--probe 43` 구독 한도 확인) |
| 03-4 | `uv run python -m scalping.ingestion.program 005930 20261023` | 일별 프로그램매매 (날짜 생략 시 장중 추이) |
| 03-6 | `uv run python examples/ch03_features.py --day 20261023` | `data/processed/ch03_features_<날짜>.parquet` (봉 모양·직전 20봉 배수·시간대 정규화 배수) |
| 04-3 | `uv run python -m scalping.ingestion.minute --rally` | 지난 1년 급등일의 1분봉 (임계치 테이블용) |
| 04-3 | `uv run python -m scalping.events.thresholds` | `data/processed/rally_events.parquet` (급등일·발사봉 = 임계치 테이블) |
| 04-6 | `uv run python examples/ch04_hamburger.py` | 네 기준 햄버거 첫 이벤트, `reports/ch04_<종목>_<날짜>.png` 기준봉 차트 (`--day` 로 실데이터) |

이후 장의 코드는 책 집필에 맞춰 추가됩니다.

## 폴더 구조 (예정)

```text
configs/         전략·실험 설정
data/sample/     배포 가능한 합성·허용 데이터
src/scalping/    kis(API 클라이언트), ingestion, leaders, features, events, materials,
                 strategies, exits, overnight, ml, risk, execution, backtest, reporting
examples/     장별 독립 실행 예제 (chXX_*)
notebooks/    장별 실험 노트북
tests/        누수·봉 내부 장벽·수량 산정·주문 멱등성·청산 우선순위 테스트
reports/      실험 결과 보고서
```



## 주의

- API 인증정보는 `.env`에만 보관하고 커밋하지 않습니다.
- 실제 계좌 주문은 기본적으로 비활성화되어 있습니다.

## 라이선스

MIT
