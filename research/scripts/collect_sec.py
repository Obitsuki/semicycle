"""SEC XBRL companyfacts: 하이퍼스케일러 capex(분기), 마이크론 재고·매출원가(분기).
현금흐름표 항목은 10-Q에서 누적(YTD)으로 보고되므로 누적 차분으로 분기값을 만든다."""
import json, csv, os, time, datetime as dt, urllib.request
UA = {"User-Agent": "semicycle-research"}
RAW = "data/raw/sec"; os.makedirs(RAW, exist_ok=True)
CIK = {"MSFT": 789019, "GOOGL": 1652044, "GOOG_OLD": 1288776, "AMZN": 1018724, "META": 1326801, "ORCL": 1341439, "MU": 723125}

def facts(t):
    p = f"{RAW}/{t}.json"
    if not os.path.exists(p):
        u = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK[t]:010d}.json"
        for i in range(5):
            try:
                open(p, "wb").write(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90).read()); break
            except Exception as e:
                time.sleep(3 * (i + 1))
        time.sleep(0.3)
    return json.load(open(p))["facts"].get("us-gaap", {})

def durations(g, tags):
    """(start, end) -> 값. 같은 구간은 가장 최근 제출값(수정 반영). 첫 공시일(filed 최소)도 함께 보관."""
    out = {}
    for tag in tags:
        if tag not in g: continue
        for unit, arr in g[tag]["units"].items():
            if unit != "USD": continue
            for x in arr:
                if "start" not in x: continue
                k = (x["start"], x["end"])
                if k not in out or x["filed"] > out[k]["filed"]:
                    first = min(x["filed"], out[k]["first_filed"]) if k in out else x["filed"]
                    out[k] = {"val": x["val"], "filed": x["filed"], "first_filed": first}
                else:
                    out[k]["first_filed"] = min(out[k]["first_filed"], x["filed"])
    return out

def to_quarterly(d):
    """3개월 구간은 그대로, 없으면 같은 시작일의 누적값 차분(6M-3M 등)으로 분기값 생성."""
    q = {}
    days = lambda s, e: (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days
    for (s, e), v in d.items():
        if 80 <= days(s, e) <= 100: q[e] = (v["val"], v["first_filed"])
    by_start = {}
    for (s, e), v in d.items():
        by_start.setdefault(s, []).append((e, v))
    for s, lst in by_start.items():
        lst.sort()
        for (e1, v1), (e2, v2) in zip(lst, lst[1:]):
            if 80 <= days(e1, e2) <= 100 and e2 not in q:
                q[e2] = (v2["val"] - v1["val"], v2["first_filed"])
    return q

def instants(g, tags):
    out = {}
    for tag in tags:
        if tag not in g: continue
        for unit, arr in g[tag]["units"].items():
            if unit != "USD": continue
            for x in arr:
                if "start" in x: continue
                if x["end"] not in out or x["filed"] > out[x["end"]][1]:
                    out[x["end"]] = (x["val"], x["filed"])
    return out

CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
rows = []
for t in ["MSFT", "GOOGL", "GOOG_OLD", "AMZN", "META", "ORCL"]:
    q = to_quarterly(durations(facts(t), CAPEX_TAGS))
    name = "GOOGL" if t == "GOOG_OLD" else t
    for e, (v, filed) in q.items():
        rows.append([name, e, v, filed])
# 같은 회사·분기 중복(구글 신·구 CIK)은 하나만
seen = {}
for r in rows:
    k = (r[0], r[1])
    if k not in seen or r[3] < seen[k][3]: seen[k] = r
with open("data/clean/hyperscaler_capex_q.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["company", "quarter_end", "capex_usd", "first_filed"])
    for r in sorted(seen.values(), key=lambda r: (r[0], r[1])): w.writerow(r)
cnt = {}
for r in seen.values(): cnt.setdefault(r[0], []).append(r[1])
print({k: (min(v), max(v), len(v)) for k, v in cnt.items()})

# 마이크론 재고·매출원가 (재고일수 = 재고 / 분기 매출원가 × 91)
g = facts("MU")
inv = instants(g, ["InventoryNet"])
cogs = to_quarterly(durations(g, ["CostOfGoodsSold", "CostOfRevenue", "CostOfGoodsAndServicesSold"]))
with open("data/clean/micron_inventory_q.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["quarter_end", "inventory_usd", "cogs_usd", "inventory_days", "first_filed"])
    for e in sorted(cogs):
        if e in inv:
            w.writerow([e, inv[e][0], cogs[e][0], round(inv[e][0] / cogs[e][0] * 91, 1), cogs[e][1]])
print("MU inventory quarters:", len([e for e in cogs if e in inv]))
