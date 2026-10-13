"""KOSIS 광업제조업동향조사(DT_1F02001) 반도체 제조업(C261) 출하·재고지수(계절조정)."""
import json
import urllib.parse

import pandas as pd

from ..http import get

ITEMS = {"T21": "kosis.semi_ship_sa", "T22": "kosis.semi_inv_sa"}


def fetch(env, existing):
    key = urllib.parse.quote(env["KOSIS_API_KEY"], safe="")
    rows = []
    for itm, series in ITEMS.items():
        url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
               f"&apiKey={key}&itmId={itm}&objL1=00&objL2=C261&format=json&jsonVD=Y&prdSe=M"
               "&startPrdDe=198501&endPrdDe=209912&orgId=101&tblId=DT_1F02001")
        d = json.loads(get(url, timeout=90, retries=10))
        if isinstance(d, dict):
            raise RuntimeError(f"KOSIS 응답 오류: {str(d)[:200]}")
        for r in d:
            if r.get("DT") not in (None, "", "-"):
                p = r["PRD_DE"]
                rows.append((series, f"{p[:4]}-{p[4:]}", float(r["DT"])))
    return pd.DataFrame(rows, columns=["series", "period", "value"])
