"""SEC EDGAR XBRL companyfacts.
- 마이크론: 분기 매출·매출총이익(4분기는 연간 − 1~3분기), 분기 매출원가, 분기말 재고
- 하이퍼스케일러 5사: 분기 설비투자(현금흐름표 누적값 차분)
released = 해당 값이 처음 공시된 날짜(first filed)."""
import datetime as dt
import json
import time

import pandas as pd

from ..config import sec_user_agent
from ..http import get

CIK = {"MU": 723125, "MSFT": 789019, "GOOGL": 1652044, "GOOG_OLD": 1288776,
       "AMZN": 1018724, "META": 1326801, "ORCL": 1341439}
HYPERSCALERS = ["MSFT", "GOOGL", "GOOG_OLD", "AMZN", "META", "ORCL"]
REV_TAGS = ["SalesRevenueNet", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
COGS_TAGS = ["CostOfGoodsSold", "CostOfRevenue", "CostOfGoodsAndServicesSold"]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]


def _days(s, e):
    return (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days


def _usd(g, tag):
    return g[tag]["units"].get("USD", []) if tag in g else []


def durations(g, tags):
    """(start, end) → 최신 제출값(수정 반영) + 최초 공시일."""
    out = {}
    for tag in tags:
        for x in _usd(g, tag):
            if "start" not in x:
                continue
            k = (x["start"], x["end"])
            if k not in out or x["filed"] > out[k]["filed"]:
                first = min(x["filed"], out[k]["first_filed"]) if k in out else x["filed"]
                out[k] = {"val": x["val"], "filed": x["filed"], "first_filed": first}
            else:
                out[k]["first_filed"] = min(out[k]["first_filed"], x["filed"])
    return out


def to_quarterly(d):
    """3개월 구간은 그대로, 없으면 같은 시작일의 누적값 차분(6M−3M 등)."""
    q = {}
    for (s, e), v in d.items():
        if 80 <= _days(s, e) <= 100:
            q[e] = (v["val"], v["first_filed"])
    by_start = {}
    for (s, e), v in d.items():
        by_start.setdefault(s, []).append((e, v))
    for lst in by_start.values():
        lst.sort(key=lambda t: t[0])
        for (e1, v1), (e2, v2) in zip(lst, lst[1:]):
            if 80 <= _days(e1, e2) <= 100 and e2 not in q:
                q[e2] = (v2["val"] - v1["val"], v2["first_filed"])
    return q


def quarterly_with_q4(d):
    """3개월 구간 값 + (연간 − 같은 회계연도 1~3분기)로 4분기 보충."""
    q = {}
    for (s, e), v in d.items():
        if 80 <= _days(s, e) <= 100:
            q[e] = (v["val"], v["first_filed"])
    for (s, e), v in d.items():
        if 350 <= _days(s, e) <= 380 and e not in q:
            inside = [val for k, (val, _) in q.items() if s < k < e]
            if len(inside) == 3:
                q[e] = (v["val"] - sum(inside), v["first_filed"])
    return q


def instants(g, tags):
    out = {}
    for tag in tags:
        for x in _usd(g, tag):
            if "start" in x:
                continue
            if x["end"] not in out or x["filed"] > out[x["end"]][1]:
                out[x["end"]] = (x["val"], x["filed"])
    return out


def _facts(ticker, ua):
    raw = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK[ticker]:010d}.json",
              headers={"User-Agent": ua}, timeout=120)
    time.sleep(0.3)  # SEC 요청 한도(초당 10회) 여유
    return json.loads(raw)["facts"].get("us-gaap", {})


def build(facts):
    """facts: ticker → us-gaap dict. 반환: long DataFrame(series, period, value, released)."""
    rows = []
    g = facts["MU"]
    rev = quarterly_with_q4(durations(g, REV_TAGS))
    gp = quarterly_with_q4(durations(g, ["GrossProfit"]))
    cogs_q4 = quarterly_with_q4(durations(g, COGS_TAGS))
    for e, (r, f) in rev.items():
        rows.append(("sec.MU.revenue", e, r, f))
        if e in gp:
            rows.append(("sec.MU.gross_profit", e, gp[e][0], gp[e][1]))
        elif e in cogs_q4:
            rows.append(("sec.MU.gross_profit", e, r - cogs_q4[e][0], cogs_q4[e][1]))
    for e, (v, f) in to_quarterly(durations(g, COGS_TAGS)).items():
        rows.append(("sec.MU.cogs", e, v, f))
    for e, (v, f) in instants(g, ["InventoryNet"]).items():
        rows.append(("sec.MU.inventory", e, v, f))

    capex = {}
    for t in HYPERSCALERS:
        if t not in facts:
            continue
        name = "GOOGL" if t == "GOOG_OLD" else t
        for e, (v, f) in to_quarterly(durations(facts[t], CAPEX_TAGS)).items():
            k = (name, e)
            if k not in capex or f < capex[k][1]:   # 구글 신·구 CIK 중복은 먼저 공시된 값
                capex[k] = (v, f)
    for (name, e), (v, f) in capex.items():
        rows.append((f"sec.{name}.capex", e, v, f))
    return pd.DataFrame(rows, columns=["series", "period", "value", "released"])


def fetch(env, existing):
    ua = sec_user_agent(env)
    facts = {t: _facts(t, ua) for t in CIK}
    return build(facts)
