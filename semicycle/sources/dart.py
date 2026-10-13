"""OpenDART 단일회사 전체 재무제표(fnlttSinglAcntAll): SK하이닉스·삼성전자 분기 연결재무.
손익은 분기 3개월값(4분기 = 연간 − 1~3분기), 재무상태는 분기말 잔액.
released = 접수번호 앞 8자리(공시일). 최근 2개 연도만 매번 다시 받는다."""
import datetime as dt
import json
import time

import pandas as pd

from ..http import get

CORPS = {"skhynix": "00164779", "samsung": "00126380"}
REPORTS = [("11013", 1), ("11012", 2), ("11014", 3), ("11011", 4)]
ACCOUNTS = {
    "revenue": ["ifrs-full_Revenue", "ifrs_Revenue"],
    "op_income": ["dart_OperatingIncomeLoss"],
    "cogs": ["ifrs-full_CostOfSales", "ifrs_CostOfSales"],
    "inventory": ["ifrs-full_Inventories", "ifrs_Inventories"],
    "equity_parent": ["ifrs-full_EquityAttributableToOwnersOfParent", "ifrs_EquityAttributableToOwnersOfParent"],
}
FLOW = ("revenue", "op_income", "cogs")
START_YEAR = 2015
REFRESH_YEARS = 2


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _report(key, corp, year, reprt):
    url = (f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?crtfc_key={key}&corp_code={corp}"
           f"&bsns_year={year}&reprt_code={reprt}&fs_div=CFS")
    d = json.loads(get(url, timeout=60, retries=8))
    time.sleep(0.15)
    if d.get("status") == "013":   # 해당 보고서 없음(아직 미공시 등)
        return None
    if d.get("status") != "000":
        raise RuntimeError(f"DART 응답 오류 {d.get('status')}: {d.get('message')}")
    return d["list"]


def year_rows(name, year, reports):
    """reports: {분기번호: list(rows)} → long rows. 4분기 손익은 연간 − 1~3분기."""
    q = {}
    for qn, lst in reports.items():
        rc = lst[0]["rcept_no"][:8]
        rec = {"released": f"{rc[:4]}-{rc[4:6]}-{rc[6:]}"}
        for k, ids in ACCOUNTS.items():
            hit = [r for r in lst if r.get("account_id") in ids]
            rec[k] = _num(hit[0].get("thstrm_amount")) if hit else None
        q[qn] = rec
    if 4 in q:
        if all(i in q for i in (1, 2, 3)):
            for k in FLOW:
                parts = [q[i][k] for i in (1, 2, 3)]
                q[4][k] = None if q[4][k] is None or None in parts else q[4][k] - sum(parts)
        else:
            for k in FLOW:
                q[4][k] = None
    rows = []
    for qn, rec in q.items():
        for k in ACCOUNTS:
            if rec[k] is not None:
                rows.append((f"dart.{name}.{k}", f"{year}Q{qn}", rec[k], rec["released"]))
    return rows


def fetch(env, existing, today=None):
    today = today or dt.date.today()
    key = env["DART_API_KEY"]
    first = START_YEAR if existing.empty else today.year - REFRESH_YEARS + 1
    rows = []
    for name, corp in CORPS.items():
        for y in range(first, today.year + 1):
            reports = {}
            for reprt, qn in REPORTS:
                lst = _report(key, corp, y, reprt)
                if lst:
                    reports[qn] = lst
            rows += year_rows(name, y, reports)
    new = pd.DataFrame(rows, columns=["series", "period", "value", "released"])
    if existing.empty:
        return new
    keep = existing[existing["period"].str[:4].astype(int) < first]
    return pd.concat([keep, new], ignore_index=True)
