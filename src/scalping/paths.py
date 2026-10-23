"""저장소 안의 경로를 한곳에서 정한다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SAMPLE = DATA / "sample"               # 배포 가능한 합성·허용 데이터
RAW = DATA / "raw"
UNIVERSE = RAW / "universe.parquet"    # 상장 + 최근 상장폐지 종목 (03-2)
DAILY_DIR = RAW / "daily"              # 종목별 일봉, 원주가 (03-2)
MINUTE_DIR = RAW / "minute"            # 시장/날짜/종목별 1분봉 (03-2, 03-5)
PROGRAM_DIR = RAW / "program"          # 종목별 일별 프로그램매매 (03-4)
REALTIME_DIR = RAW / "realtime"        # 실시간 체결·호가·장중 프로그램매매 (03-2)
PROCESSED = DATA / "processed"
CONFIGS = ROOT / "configs"
REPORTS = ROOT / "reports"
CACHE = ROOT / ".cache"                # 접근토큰 캐시
