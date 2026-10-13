"""FRED: 미국 컴퓨터·전자제품 신규주문(A34SNO)·재고(A34STI)."""
import json

import pandas as pd

from ..http import get

SERIES = ["A34SNO", "A34STI"]


def fetch(env, existing):
    key = env["FRED_API_KEY"]
    rows = []
    for sid in SERIES:
        url = (f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={key}"
               "&file_type=json&observation_start=1992-01-01")
        for o in json.loads(get(url))["observations"]:
            if o["value"] not in (".", ""):
                rows.append((f"fred.{sid}", o["date"][:7], float(o["value"])))
    return pd.DataFrame(rows, columns=["series", "period", "value"])
