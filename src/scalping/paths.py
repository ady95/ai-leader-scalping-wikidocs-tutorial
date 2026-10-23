"""저장소 안의 경로를 한곳에서 정한다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SAMPLE = DATA / "sample"               # 배포 가능한 합성·허용 데이터
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
CONFIGS = ROOT / "configs"
REPORTS = ROOT / "reports"
CACHE = ROOT / ".cache"                # 접근토큰 캐시
