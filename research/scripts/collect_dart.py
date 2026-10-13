"""OpenDART 단일회사 전체 재무제표(fnlttSinglAcntAll): SK하이닉스·삼성전자 분기 재무.
손익은 분기 3개월값(4분기 = 연간 − 1~3분기), 재무상태는 분기말 잔액. rcept_no 앞 8자리 = 공시일."""
import json, csv, time, datetime as dt
from common import load_env, get
K = load_env()["DART_API_KEY"]
CORPS = {"skhynix": "00164779", "samsung": "00126380"}
REPRT = [("11013", 1), ("11012", 2), ("11014", 3), ("11011", 4)]
IDS = {
    "revenue": ["ifrs-full_Revenue", "ifrs_Revenue"],
    "op_income": ["dart_OperatingIncomeLoss"],
    "cogs": ["ifrs-full_CostOfSales", "ifrs_CostOfSales"],
    "inventory": ["ifrs-full_Inventories", "ifrs_Inventories"],
    "equity_parent": ["ifrs-full_EquityAttributableToOwnersOfParent", "ifrs_EquityAttributableToOwnersOfParent"],
}
def num(s):
    try: return float(str(s).replace(",", ""))
    except Exception: return None

def fetch(corp, year, reprt):
    u = (f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?crtfc_key={K}&corp_code={corp}"
         f"&bsns_year={year}&reprt_code={reprt}&fs_div=CFS")
    d = json.loads(get(u, timeout=60, retries=6))
    if d.get("status") != "000": return None
    return d["list"]

rows = []
this_year = dt.date.today().year
for name, corp in CORPS.items():
    for y in range(2015, this_year + 1):
        annual = {}
        qvals = {}
        for reprt, qn in REPRT:
            lst = fetch(corp, y, reprt); time.sleep(0.15)
            if not lst: continue
            rcept = lst[0]["rcept_no"][:8]
            rec = {"filed": f"{rcept[:4]}-{rcept[4:6]}-{rcept[6:]}"}
            for key, ids in IDS.items():
                hit = [r for r in lst if r.get("account_id") in ids]
                if not hit: rec[key] = None; continue
                r = hit[0]
                rec[key] = num(r.get("thstrm_amount"))
            qvals[qn] = rec
        # 4분기 손익 = 연간 − (1~3분기)
        if 4 in qvals and all(q in qvals for q in (1, 2, 3)):
            for key in ("revenue", "op_income", "cogs"):
                vals = [qvals[q][key] for q in (1, 2, 3)]
                if qvals[4][key] is not None and None not in vals:
                    qvals[4][key] = qvals[4][key] - sum(vals)
        elif 4 in qvals:
            for key in ("revenue", "op_income", "cogs"): qvals[4][key] = None
        for qn, rec in sorted(qvals.items()):
            rows.append([name, f"{y}Q{qn}", rec["filed"]] + [rec[k] for k in IDS])
        print(name, y, sorted(qvals), flush=True)
with open("data/clean/dart_quarterly.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["company", "quarter", "filed"] + list(IDS)); w.writerows(rows)
print("saved", len(rows))
