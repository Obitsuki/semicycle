import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "site" / "data"


def load_registry(path=ROOT / "indicators.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env():
    """환경변수 우선, 로컬 실행 시 .env 파일 보조. 키는 코드·저장소에 두지 않는다."""
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if v:
            env[k] = v
    return env


def sec_user_agent(env):
    """SEC는 User-Agent에 이름과 연락처를 요구한다. Secret 형식: '이름 / 이메일'."""
    raw = env.get("SEC_USER_AGENT", "").strip()
    if raw:
        return " ".join(p.strip() for p in raw.split("/") if p.strip())
    return "semicycle github.com/Obitsuki/semicycle"
