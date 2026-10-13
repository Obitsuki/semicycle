"""FRED: 미국 컴퓨터·전자제품 신규주문(A34SNO)·재고(A34STI), 반도체 산업생산(IPG3344S)."""
import json, csv
from common import load_env, get
K = load_env()["FRED_API_KEY"]
SERIES = {"A34SNO": "us_ce_new_orders", "A34STI": "us_ce_inventories", "IPG3344S": "us_ip_semis"}
out = {}
for sid, name in SERIES.items():
    d = json.loads(get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={K}&file_type=json&observation_start=1990-01-01", retries=6))
    out[name] = {o["date"][:7]: float(o["value"]) for o in d["observations"] if o["value"] not in (".", "")}
months = sorted(set().union(*[v.keys() for v in out.values()]))
with open("data/clean/fred_us_electronics.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["month"] + list(out))
    for m in months: w.writerow([m] + [out[c].get(m, "") for c in out])
print({k: (min(v), max(v), len(v)) for k, v in out.items()})
