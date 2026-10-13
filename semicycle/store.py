"""소스별 원자료 저장(long 포맷), 발표 이력(releases.csv), 수집 상태(status.json).

long 포맷 열: series, period, value, released
- period  : 월 'YYYY-MM' 또는 분기말 'YYYY-MM-DD' 또는 'YYYYQn'
- released: 공시일 등 실제 공개일을 아는 경우 'YYYY-MM-DD', 모르면 빈 값(발표 지연 규칙 적용)
"""
import datetime as dt
import json

import pandas as pd

from .config import DATA

COLS = ["series", "period", "value", "released"]


def path(source):
    return DATA / f"{source}.csv"


def load(source):
    p = path(source)
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(p, dtype={"series": str, "period": str, "released": str})
    df["released"] = df["released"].fillna("")
    return df[COLS]


def normalize(df):
    df = df.copy()
    if "released" not in df:
        df["released"] = ""
    df["released"] = df["released"].fillna("").astype(str)
    df["period"] = df["period"].astype(str)
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(["series", "period"], keep="last")
    return df.sort_values(["series", "period"]).reset_index(drop=True)[COLS]


def save(source, df):
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(path(source), index=False)


def log_releases(old, new, today=None, kind_new="new"):
    """새로 나타났거나 값이 바뀐 (series, period)를 releases.csv에 추가. 실제 '처음 본 날짜' 기록."""
    today = today or dt.date.today().isoformat()
    key = ["series", "period"]
    m = new.merge(old[key + ["value"]], on=key, how="left", suffixes=("", "_old"))
    changed = m["value_old"].isna() | ((m["value"] - m["value_old"]).abs() > 1e-9 * m["value_old"].abs().clip(lower=1))
    rows = m[changed].copy()
    if rows.empty:
        return 0
    rows["kind"] = rows["value_old"].isna().map({True: kind_new, False: "revised"})
    rows["fetched_at"] = today
    out = rows[["fetched_at", "series", "period", "value", "kind"]]
    p = DATA / "releases.csv"
    out.to_csv(p, mode="a", header=not p.exists(), index=False)
    return len(out)


def load_status():
    p = DATA / "status.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_status(status):
    (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1, sort_keys=True))
