"""수집 결과·계산 결과 점검. 문제가 있으면 새 데이터를 쓰지 않고 직전 데이터를 유지한다."""
import numpy as np


def validate_source(old, new, min_keep=0.9):
    problems = []
    if new is None or new.empty:
        return ["수집 결과가 비어 있음"]
    if not np.isfinite(new["value"].astype(float)).all():
        problems.append("숫자가 아닌 값 포함")
    if old is None or old.empty:
        return problems
    for series, g in old.groupby("series"):
        n = new[new["series"] == series]
        if n.empty:
            problems.append(f"{series}: 시계열이 사라짐")
            continue
        if len(n) < min_keep * len(g):
            problems.append(f"{series}: 관측치 {len(g)}→{len(n)}개로 감소")
        if n["period"].max() < g["period"].max():
            problems.append(f"{series}: 최신 기간이 {g['period'].max()}→{n['period'].max()}로 후퇴")
    return problems


def validate_result(res, min_history=200):
    problems = []
    lvl, drc = res["level"].dropna(), res["direction"].dropna()
    if len(lvl) < min_history or len(drc) < min_history:
        problems.append(f"점수 이력이 너무 짧음 (수준 {len(lvl)}, 방향 {len(drc)}개월)")
    last = res["level"].index[-1]
    for name in ("level", "direction"):
        v = res[name].iloc[-1]
        if v != v:
            problems.append(f"최신월({last}) {name} 점수 없음")
        elif not 0 <= v <= 100:
            problems.append(f"최신월 {name} 점수 범위 이탈: {v}")
    return problems
