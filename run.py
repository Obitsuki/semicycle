"""반도체 업황 사이클 위치 갱신.

사용:
  python run.py                 # 수집 → 점검 → 계산 → 사이트 데이터 발행
  python run.py --skip-fetch    # 저장된 데이터로 계산·발행만
  python run.py --only ecos,fred
  python run.py --health        # 갱신 지연 소스 점검(지연 시 종료코드 2)
"""
import argparse
import datetime as dt
import sys

import pandas as pd

from semicycle import store
from semicycle.config import load_env, load_registry
from semicycle.http import redact, register_secrets
from semicycle.indicators import build
from semicycle.publish import publish
from semicycle.score import compute
from semicycle.sources import SOURCES
from semicycle.validate import validate_result, validate_source

KEYS = ["ECOS_API_KEY", "DATA_GO_KR_KEY", "KOSIS_API_KEY", "DART_API_KEY", "FRED_API_KEY", "SEC_USER_AGENT"]
STALE_DAYS = 3


def fetch_all(env, only=None):
    status = store.load_status()
    today = dt.date.today().isoformat()
    for name, mod in SOURCES.items():
        if only and name not in only:
            continue
        st = status.setdefault(name, {})
        st["last_attempt"] = today
        old = store.load(name)
        try:
            new = store.normalize(mod.fetch(env, old))
            problems = validate_source(old, new)
            if problems:
                raise RuntimeError("점검 실패: " + "; ".join(problems))
            n = store.log_releases(old, new, today, kind_new="backfill" if old.empty else "new")
            store.save(name, new)
            st.update(last_success=today, error=None, rows=len(new), new_or_revised=n,
                      latest_period=new.groupby("series")["period"].max().to_dict())
            print(f"[ok]   {name}: {len(new)}행, 신규·수정 {n}건")
        except Exception as e:
            st["error"] = redact(f"{type(e).__name__}: {e}")[:500]
            print(f"[fail] {name}: {st['error']}")
        store.save_status(status)
    return status


def compute_all(asof=None):
    reg = load_registry()
    end = asof or pd.Timestamp.today().strftime("%Y-%m")
    idx = pd.period_range(reg["settings"]["history_start"], end, freq="M")
    data = {name: store.load(name) for name in SOURCES}
    raw, info = build(data, idx)
    res = compute(raw, reg)
    return reg, data, raw, info, res


def health():
    status = store.load_status()
    today = dt.date.today()
    late = []
    for name in SOURCES:
        ls = status.get(name, {}).get("last_success")
        if not ls or (today - dt.date.fromisoformat(ls)).days > STALE_DAYS:
            late.append(f"{name}(마지막 성공 {ls}, 오류: {status.get(name, {}).get('error')})")
    if late:
        print("갱신 지연:", "; ".join(late))
        return 2
    print("모든 소스 정상")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--asof", default=None, help="계산 기준월 YYYY-MM (기본: 이번 달)")
    ap.add_argument("--health", action="store_true")
    a = ap.parse_args()
    if a.health:
        return health()
    env = load_env()
    register_secrets([env.get(k, "") for k in KEYS])
    if not a.skip_fetch:
        fetch_all(env, set(filter(None, a.only.split(","))) or None)
    reg, data, raw, info, res = compute_all(a.asof)
    problems = validate_result(res)
    if problems:
        print("계산 결과 점검 실패 — 발행하지 않음:", "; ".join(problems))
        return 1
    out = publish(reg, data, raw, info, res, store.load_status())
    print(f"발행: {out['as_of']} {out['phase_name']} (수준 {out['level']}, 방향 {out['direction']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
