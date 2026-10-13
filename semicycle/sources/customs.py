"""관세청 품목별 국가별 수출입실적(data.go.kr 15100475).
HS 8542(집적회로) 수출 총액, HS 8486(반도체 제조장비) 수입 총액을 월별로 합산.
1회 조회는 1년 이내 → 연 단위 호출. 잠정치 수정 반영을 위해 최근 2개 연도만 매번 다시 받는다."""
import datetime as dt
import xml.etree.ElementTree as ET

import pandas as pd

from ..http import get

BASE = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
SERIES = {("8542", "expDlr"): "customs.ic_export_usd", ("8486", "impDlr"): "customs.equip_import_usd"}
START_YEAR = 2007
REFRESH_YEARS = 2


def _year(key, hs, y, today):
    end = f"{y}12" if y < today.year else f"{y}{today.month:02d}"
    xml = get(f"{BASE}?serviceKey={key}&strtYymm={y}01&endYymm={end}&hsSgn={hs}", timeout=120, retries=10)
    root = ET.fromstring(xml)
    code = root.findtext(".//resultCode")
    if code not in ("00", None):
        raise RuntimeError(f"관세청 응답 오류 {code}: {root.findtext('.//resultMsg')}")
    out = {}
    for it in root.iter("item"):
        f = {c.tag: c.text for c in it}
        ym = f.get("year")
        if not ym or ym == "총계" or f.get("hsCd") in (None, "-"):
            continue
        out[ym.replace(".", "-")] = out.get(ym.replace(".", "-"), {})
        for (h, col), s in SERIES.items():
            if h == hs:
                out[ym.replace(".", "-")][s] = out[ym.replace(".", "-")].get(s, 0) + int(f.get(col) or 0)
    return out


def fetch(env, existing, today=None):
    today = today or dt.date.today()
    key = env["DATA_GO_KR_KEY"]
    first = START_YEAR if existing.empty else today.year - REFRESH_YEARS + 1
    rows = []
    for hs in sorted({h for h, _ in SERIES}):
        for y in range(first, today.year + 1):
            for ym, vals in _year(key, hs, y, today).items():
                for s, v in vals.items():
                    rows.append((s, ym, float(v)))
    new = pd.DataFrame(rows, columns=["series", "period", "value"])
    if existing.empty:
        return new
    keep = existing[existing["period"] < f"{first}-01"][["series", "period", "value"]]
    return pd.concat([keep, new], ignore_index=True)
