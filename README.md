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

장별 코드는 책 집필에 맞춰 추가됩니다.

## 주의

- API 인증정보는 `.env`에만 보관하고 커밋하지 않습니다.
- 실제 계좌 주문은 기본적으로 비활성화되어 있습니다.

## 라이선스

MIT
