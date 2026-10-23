"""configs/config.yaml 읽기"""

import yaml

from scalping.paths import CONFIGS


def load_config(path=None):
    with open(path or CONFIGS / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
