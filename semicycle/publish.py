"""사이트용 JSON 생성: site/data/latest.json, history.json, validation.json."""
import datetime as dt
import json
import math

import pandas as pd

from .config import DATA, SITE_DATA
from .indicators import memory_price_yoy
from .score import PHASE_NAMES

DISCLAIMER = ("이 지표는 공개 통계로 반도체(메모리) 업황의 사이클 위치를 보여줄 뿐, "
              "주가 방향을 예측하거나 투자를 권유하지 않습니다.")


def _r(x, nd=1):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def _list(s, nd=1):
    return [_r(v, nd) for v in s.tolist()]


def _months_since(raw_col):
    s = raw_col.dropna()
    if s.empty:
        return None
    return (raw_col.index[-1] - s.index[-1]).n


def phase_stats(history, price_yoy, horizon=6, split="2020-12"):
    """국면 판정 이후 horizon개월 동안 실제 메모리 가격 상승률 변화."""
    y = price_yoy.copy()
    fwd = (y.shift(-horizon) - y).rename("chg")
    df = pd.DataFrame({"phase": history}).join(fwd, how="left").dropna()
    out = {}
    for label, part in [("all", df), ("until_2020", df[df.index <= pd.Period(split, "M")]),
                        ("since_2021", df[df.index > pd.Period(split, "M")])]:
        rows = []
        for ph in ["recovery", "expansion", "slowdown", "contraction"]:
            g = part[part["phase"] == ph]["chg"]
            rows.append({"phase": ph, "phase_name": PHASE_NAMES[ph], "months": int(len(g)),
                         "mean_change_pp": _r(g.mean()) if len(g) else None,
                         "share_improved_pct": _r((g > 0).mean() * 100, 0) if len(g) else None})
        out[label] = {"from": str(part.index.min()) if len(part) else None,
                      "to": str(part.index.max()) if len(part) else None, "rows": rows}
    return {"horizon_months": horizon, "target": "메모리 수출물가 상승률(%p)의 이후 6개월 변화", "periods": out}


def _log_published(latest):
    """사이트에 실제로 게시된 판정을 기록(값이 바뀐 날만). 나중에 '당시 무엇을 보여줬는지' 확인용."""
    p = DATA / "published.csv"
    row = {"date": dt.date.today().isoformat(), "as_of": latest["as_of"], "phase": latest["phase"],
           "level": latest["level"], "direction": latest["direction"]}
    if p.exists():
        prev = pd.read_csv(p, dtype={"as_of": str}).iloc[-1]
        if (prev["as_of"], prev["phase"], prev["level"], prev["direction"]) == (row["as_of"], row["phase"], row["level"], row["direction"]):
            return
    pd.DataFrame([row]).to_csv(p, mode="a", header=not p.exists(), index=False)


def publish(reg, data, raw, info, res, status):
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    idx = res["level"].index
    last = idx[-1]
    pillars = {p["id"]: p for p in reg["pillars"]}
    sources = reg["sources"]

    def snapshot(t):
        ph = res["phase"].loc[t]
        return {"month": str(t), "phase": ph, "phase_name": PHASE_NAMES.get(ph),
                "level": _r(res["level"].loc[t]), "direction": _r(res["direction"].loc[t])}

    ind_rows = []
    for ind in reg["indicators"]:
        k = ind["id"]
        ind_rows.append({
            "id": k, "name": ind["name"], "pillar": ind["pillar"], "pillar_name": pillars[ind["pillar"]]["name"],
            "role": ind["role"], "sign": ind["sign"], "unit": ind["unit"], "description": ind["description"],
            "value": _r(res["carried_raw"][k].iloc[-1], 2),
            "level_pct": _r(res["level_pct"][k].iloc[-1]) if k in res["level_pct"] else None,
            "direction_pct": _r(res["direction_pct"][k].iloc[-1]) if k in res["direction_pct"] else None,
            "data_period": info[k]["data_period"], "released": info[k]["released"],
            "months_since_update": _months_since(raw[k]),
            "sources": [{"id": s, "name": sources[s]["name"], "url": sources[s]["url"]} for s in ind["sources"]],
        })

    latest = {
        "as_of": str(last),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        **{k: v for k, v in snapshot(last).items() if k != "month"},
        "previous": [snapshot(idx[-i]) for i in (2, 4, 7) if len(idx) >= i],
        "pillars": [{"id": p["id"], "name": p["name"], "weight": p["weight"],
                     "level": _r(res["level_pillars"][p["id"]].iloc[-1]),
                     "direction": _r(res["direction_pillars"][p["id"]].iloc[-1])} for p in reg["pillars"]],
        "indicators": ind_rows,
        "sources": [{"id": s, **meta, **{k: status.get(s, {}).get(k) for k in ("last_success", "error", "latest_period")}}
                    for s, meta in sources.items()],
        "phases": reg["phases"],
        "settings": reg["settings"],
        "disclaimer": DISCLAIMER,
    }
    valid = res["level"].notna() & res["direction"].notna()
    h_idx = idx[valid.values]
    history = {
        "months": [str(t) for t in h_idx],
        "level": _list(res["level"][h_idx]), "direction": _list(res["direction"][h_idx]),
        "phase": res["phase"][h_idx].tolist(),
        "pillars": {p: {"level": _list(res["level_pillars"][p][h_idx]), "direction": _list(res["direction_pillars"][p][h_idx])}
                    for p in pillars},
        "indicators": {k: _list(res["carried_raw"][k][h_idx], 2) for k in raw.columns},
    }
    validation = phase_stats(res["phase"][h_idx], memory_price_yoy(data))

    _log_published(latest)
    for name, obj in [("latest", latest), ("history", history), ("validation", validation)]:
        (SITE_DATA / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    return latest
