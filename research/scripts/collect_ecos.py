"""한국은행 ECOS 수출물가지수(품목별, 402Y016) - DRAM·플래시메모리·시스템반도체 월별 수집."""
import json, csv, sys
from common import ENV, get

K = ENV["ECOS_API_KEY"]
STAT = "402Y016"
ITEMS = {"30911201AA": "dram", "30911202AA": "flash", "30911203AA": "system_semi"}
CURRENCIES = {"D": "usd", "W": "krw", "C": "contract"}

def fetch(item, cur, start="197101", end="203012"):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{K}/json/kr/1/10000/{STAT}/M/{start}/{end}/{item}/{cur}"
    d = json.loads(get(url))
    if "StatisticSearch" not in d:
        raise RuntimeError(d)
    return [(r["TIME"], float(r["DATA_VALUE"])) for r in d["StatisticSearch"]["row"] if r["DATA_VALUE"] not in ("", None)]

if __name__ == "__main__":
    series = {}
    for item, iname in ITEMS.items():
        for cur, cname in CURRENCIES.items():
            rows = fetch(item, cur)
            series[f"{iname}_{cname}"] = dict(rows)
            print(f"{iname}_{cname}: {len(rows)} obs {rows[0][0]}~{rows[-1][0]}")
    months = sorted(set().union(*[s.keys() for s in series.values()]))
    cols = sorted(series)
    with open("data/clean/ecos_export_price_memory.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month"] + cols)
        for m in months:
            w.writerow([f"{m[:4]}-{m[4:]}"] + [series[c].get(m, "") for c in cols])
    print("saved", len(months), "months")
