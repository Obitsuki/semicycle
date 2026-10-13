"""인자 패널 → 백분위 → 필러 → 수준·방향 → 국면.

- 백분위: t 시점까지의 자기 이력 대비 위치(0~100). 미래 정보를 쓰지 않는다.
- 수준(level): 성장률 '수준' 형태 인자의 합성. 지금 업황이 과거 대비 얼마나 좋은가.
- 방향(direction): 성장률의 3개월 변화 형태 인자의 합성. 좋아지는 중인가.
- 국면: 회복(수준<50, 방향≥50) / 확장(≥50, ≥50) / 둔화(≥50, <50) / 수축(<50, <50).
"""
import numpy as np
import pandas as pd

LEVEL_ROLES = {"level_only", "growth", "change"}
DIRECTION_ROLES = {"growth", "change", "accel"}
PHASE_NAMES = {"recovery": "회복", "expansion": "확장", "slowdown": "둔화", "contraction": "수축"}


def expanding_pct(s, min_hist):
    out = pd.Series(np.nan, index=s.index)
    hist = []
    for t, x in s.items():
        if pd.isna(x):
            continue
        hist.append(x)
        if len(hist) >= min_hist:
            h = np.asarray(hist)
            out[t] = ((h < x).sum() + 0.5 * (h == x).sum()) / len(h) * 100
    return out


def phase_of(level, direction):
    if pd.isna(level) or pd.isna(direction):
        return None
    if level >= 50:
        return "expansion" if direction >= 50 else "slowdown"
    return "recovery" if direction >= 50 else "contraction"


def _weighted(pillar_scores, weights, min_cover):
    wv = pd.Series(weights, dtype=float)
    avail = pillar_scores[wv.index].notna()
    wsum = avail.mul(wv, axis=1).sum(axis=1)
    score = pillar_scores[wv.index].fillna(0).mul(wv, axis=1).sum(axis=1) / wsum.replace(0, np.nan)
    score[wsum / wv.sum() < min_cover] = np.nan
    return score


def compute(raw, registry):
    st = registry["settings"]
    inds = registry["indicators"]
    weights = {p["id"]: p["weight"] for p in registry["pillars"]}
    carried = raw.ffill(limit=st["carry_forward_months"])
    win = st["direction_window_months"]

    level_raw, dir_raw = {}, {}
    for ind in inds:
        k, role = ind["id"], ind["role"]
        if role in LEVEL_ROLES:
            level_raw[k] = carried[k]
        if role in DIRECTION_ROLES:
            dir_raw[k] = carried[k] - carried[k].shift(win) if role == "growth" else carried[k]
    sign = {i["id"]: i["sign"] for i in inds}
    pillar_of = {i["id"]: i["pillar"] for i in inds}

    def pct_frame(frame):
        out = {}
        for k, s in frame.items():
            p = expanding_pct(s, st["min_history_months"])
            out[k] = p if sign[k] > 0 else 100 - p
        return pd.DataFrame(out, index=raw.index)

    lvl_pct, dir_pct = pct_frame(level_raw), pct_frame(dir_raw)

    def pillars(pct):
        return pd.DataFrame({p: pct[[k for k in pct if pillar_of[k] == p]].mean(axis=1) for p in weights})

    lvl_p, dir_p = pillars(lvl_pct), pillars(dir_pct)
    level = _weighted(lvl_p, weights, st["min_weight_coverage"])
    direction = _weighted(dir_p, weights, st["min_weight_coverage"])
    phase = pd.Series([phase_of(l, d) for l, d in zip(level, direction)], index=raw.index)
    return {
        "level": level, "direction": direction, "phase": phase,
        "level_pillars": lvl_p, "direction_pillars": dir_p,
        "level_pct": lvl_pct, "direction_pct": dir_pct,
        "level_raw": pd.DataFrame(level_raw), "direction_raw": pd.DataFrame(dir_raw),
        "carried_raw": carried,
    }
