"""KRX Open API 월말 스냅샷(2010~): KRX 반도체지수, 코스피, VKOSPI, 삼성전자·SK하이닉스, 반도체 ETF.
월말 영업일을 찾기 위해 말일부터 거꾸로 조회. 날짜별 응답은 캐시."""
import json, os, time, datetime as dt, urllib.request, urllib.error, calendar, csv
from common import load_env
K = load_env()["KRX_API_KEY"]
BASE = "https://data-dbg.krx.co.kr/svc/apis"
CACHE = "data/raw/krx"; os.makedirs(CACHE, exist_ok=True)

def api(path, d):
    p = f"{CACHE}/{path.replace('/', '_')}_{d}.json"
    if os.path.exists(p): return json.load(open(p))
    u = f"{BASE}/{path}?basDd={d}"
    err = None
    for i in range(8):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers={"AUTH_KEY": K, "User-Agent": "semicycle"}), timeout=60).read()
            rows = json.loads(b).get("OutBlock_1", [])
            json.dump(rows, open(p, "w"), ensure_ascii=False)
            return rows
        except Exception as e:
            err = e; time.sleep(min(2 * (i + 1), 15))
    raise err

def month_end_trading_day(y, m):
    last = calendar.monthrange(y, m)[1]
    today = dt.date.today()
    for dd in range(last, 0, -1):
        d = dt.date(y, m, dd)
        if d >= today: continue
        if d.weekday() >= 5: continue
        rows = api("idx/krx_dd_trd", d.strftime("%Y%m%d"))
        if rows: return d.strftime("%Y%m%d"), rows
    return None, None

def f(x):
    try: return float(str(x).replace(",", ""))
    except Exception: return None

out, etf_rows = [], []
today = dt.date.today()
y, m = 2010, 1
while (y, m) <= (today.year, today.month):
    d, krx = month_end_trading_day(y, m)
    if d:
        rec = {"date": d}
        for r in krx:
            if r["IDX_NM"] == "KRX 반도체": rec["krx_semi"] = f(r["CLSPRC_IDX"])
        for r in api("idx/kospi_dd_trd", d):
            if r["IDX_NM"] == "코스피": rec["kospi"] = f(r["CLSPRC_IDX"])
        for r in api("idx/drvprod_dd_trd", d):
            if r["IDX_NM"] == "코스피 200 변동성지수": rec["vkospi"] = f(r["CLSPRC_IDX"])
        for r in api("sto/stk_bydd_trd", d):
            code = r["ISU_CD"][-6:] if len(r["ISU_CD"]) > 6 else r["ISU_CD"]
            if code in ("005930", "000660"):
                tag = "samsung" if code == "005930" else "skhynix"
                rec[f"{tag}_close"] = f(r["TDD_CLSPRC"]); rec[f"{tag}_mktcap"] = f(r["MKTCAP"]); rec[f"{tag}_shares"] = f(r["LIST_SHRS"])
        for r in api("etp/etf_bydd_trd", d):
            txt = (r.get("ISU_NM") or "") + "|" + (r.get("IDX_IND_NM") or "")
            if "반도체" in txt:
                etf_rows.append([d, r["ISU_CD"], r["ISU_NM"], r.get("IDX_IND_NM"), f(r.get("LIST_SHRS")), f(r.get("NAV")), f(r.get("INVSTASST_NETASST_TOTAMT"))])
        out.append(rec)
        print(d, {k: v for k, v in rec.items() if k != "date"}, flush=True)
    m += 1
    if m == 13: y, m = y + 1, 1
cols = ["date", "krx_semi", "kospi", "vkospi", "samsung_close", "samsung_mktcap", "samsung_shares", "skhynix_close", "skhynix_mktcap", "skhynix_shares"]
with open("data/clean/krx_month_end.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(cols)
    for r in out: w.writerow([r.get(c, "") for c in cols])
with open("data/clean/krx_semi_etf_month_end.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["date", "isu_cd", "name", "index_name", "list_shrs", "nav", "net_asset"]); w.writerows(etf_rows)
print("saved", len(out), "months,", len(etf_rows), "etf rows")
