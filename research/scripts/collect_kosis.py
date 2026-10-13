"""KOSIS 광업제조업동향조사(DT_1F02001) 반도체 제조업(C261) 생산·출하·재고지수 월별."""
import json, csv, urllib.parse
from common import load_env, get
ENV = load_env(); K = urllib.parse.quote(ENV["KOSIS_API_KEY"], safe="")
ITEMS = {"T11": "ship_raw", "T12": "inv_raw", "T21": "ship_sa", "T22": "inv_sa", "T10": "prod_raw", "T20": "prod_sa"}

def fetch(itm, start="200001", end="203012"):
    u = (f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={K}"
         f"&itmId={itm}&objL1=00&objL2=C261&format=json&jsonVD=Y&prdSe=M&startPrdDe={start}&endPrdDe={end}"
         f"&orgId=101&tblId=DT_1F02001")
    d = json.loads(get(u, timeout=90, retries=10))
    if isinstance(d, dict):
        raise RuntimeError(d)
    return {r["PRD_DE"]: float(r["DT"]) for r in d if r.get("DT") not in (None, "", "-")}

if __name__ == "__main__":
    s = {name: fetch(itm, start="198501") for itm, name in ITEMS.items()}
    months = sorted(set().union(*[v.keys() for v in s.values()]))
    with open("data/clean/kosis_semi_ship_inv.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["month"] + list(s))
        for m in months:
            w.writerow([f"{m[:4]}-{m[4:]}"] + [s[c].get(m, "") for c in s])
    print({k: (min(v), max(v), len(v)) for k, v in s.items()})
