"""Micron 분기 매출·매출총이익 (SEC XBRL companyfacts) → 3개월 구간만 추출."""
import json, csv, datetime as dt, urllib.request, os

PATH = "data/raw/sec_mu_companyfacts.json"
if not os.path.exists(PATH):
    req = urllib.request.Request("https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json",
                                 headers={"User-Agent": "semicycle-research"})
    open(PATH, "wb").write(urllib.request.urlopen(req, timeout=60).read())
g = json.load(open(PATH))["facts"]["us-gaap"]

def quarterly(tags):
    out = {}
    for tag in tags:
        if tag not in g: continue
        for x in list(g[tag]["units"].values())[0]:
            if "start" not in x: continue
            s = dt.date.fromisoformat(x["start"]); e = dt.date.fromisoformat(x["end"])
            days = (e - s).days
            if 80 <= days <= 100:
                # 같은 분기를 여러 공시가 보고하면 가장 늦게 제출된 값(수정 반영)을 사용
                key = x["end"]
                if key not in out or x["filed"] > out[key][1]:
                    out[key] = (x["val"], x["filed"])
    return {k: v[0] for k, v in out.items()}

def annual(tags):
    out = {}
    for tag in tags:
        if tag not in g: continue
        for x in list(g[tag]["units"].values())[0]:
            if "start" not in x: continue
            s = dt.date.fromisoformat(x["start"]); e = dt.date.fromisoformat(x["end"])
            if 350 <= (e - s).days <= 380:
                if x["end"] not in out or x["filed"] > out[x["end"]][1]:
                    out[x["end"]] = (x["val"], x["filed"], x["start"])
    return out

def with_q4(tags):
    """10-K는 4분기 단독값을 따로 태깅하지 않는 경우가 많아 연간 − 1~3분기로 4분기를 계산."""
    q = quarterly(tags)
    for end, (val, _, start) in annual(tags).items():
        if end in q: continue
        inside = [v for k, v in q.items() if start < k < end]
        if len(inside) == 3:
            q[end] = val - sum(inside)
    return q

REV_TAGS = ["SalesRevenueNet", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
rev = with_q4(REV_TAGS)
gp = with_q4(["GrossProfit"])
cogs = with_q4(["CostOfGoodsSold", "CostOfRevenue", "CostOfGoodsAndServicesSold"])
rows = []
for e in sorted(rev):
    r = rev[e]
    gpv = gp.get(e, r - cogs[e] if e in cogs else None)
    rows.append((e, r, gpv, (gpv / r) if gpv is not None else None))
with open("data/clean/micron_quarterly.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["quarter_end", "revenue_usd", "gross_profit_usd", "gross_margin"])
    for row in rows: w.writerow(row)
print(len(rows), rows[0][0], rows[-1][0])
for row in rows[-4:]: print(row[0], round(row[1]/1e9,2), "GM", round(row[3]*100,1) if row[3] else None)
