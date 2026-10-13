"""한국은행 ECOS 수출물가지수(품목별, 402Y016) — D램·플래시메모리, 달러 기준(D)."""
import json

import pandas as pd

from ..http import get

STAT = "402Y016"
ITEMS = {"30911201AA": "ecos.dram_usd", "30911202AA": "ecos.flash_usd"}


def fetch(env, existing):
    key = env["ECOS_API_KEY"]
    rows = []
    for item, series in ITEMS.items():
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10000/{STAT}/M/200001/209912/{item}/D"
        d = json.loads(get(url))
        if "StatisticSearch" not in d:
            raise RuntimeError(f"ECOS 응답 이상: {str(d)[:200]}")
        for r in d["StatisticSearch"]["row"]:
            if r.get("DATA_VALUE") not in ("", None):
                t = r["TIME"]
                rows.append((series, f"{t[:4]}-{t[4:]}", float(r["DATA_VALUE"])))
    return pd.DataFrame(rows, columns=["series", "period", "value"])
