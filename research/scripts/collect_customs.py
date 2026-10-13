"""관세청 품목별 국가별 수출입실적(data.go.kr 15100475) 월별 수집.
- 8542   : 집적회로 전체(HS 6단위×국가)  → 반도체(IC) 수출 총액
- 854232 : 메모리(HS 10단위×국가)       → 메모리 수출, 대만향 복합구조칩(8542323000 = HBM 대리지표)
- 8486   : 반도체 제조장비(HS 6단위×국가) → 장비 수입
1회 조회기간 1년 이내 제한 → 연 단위 호출. 잠정월(최근월)은 다음 수집 때 덮어씀."""
import csv, json, os, sys, time, datetime as dt, urllib.request, urllib.error, xml.etree.ElementTree as ET
from common import load_env

ENV = load_env(); KEY = ENV["DATA_GO_KR_KEY"]
BASE = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
OUT = "data/raw/customs"; os.makedirs(OUT, exist_ok=True)

def call(params, tries=12):
    u = BASE + "?serviceKey=" + KEY + "&" + "&".join(f"{a}={b}" for a, b in params.items())
    err = None
    for i in range(tries):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "semicycle"}), timeout=120).read().decode()
            root = ET.fromstring(b)
            code = root.findtext(".//resultCode")
            if code not in ("00", None):
                raise RuntimeError(root.findtext(".//resultMsg"))
            return [{c.tag: c.text for c in it} for it in root.iter("item")]
        except Exception as e:
            err = e; time.sleep(min(3 * (i + 1), 20))
    raise err

def collect(hs, start_year=2007):
    path = f"{OUT}/hs_{hs}.csv"
    today = dt.date.today()
    rows = []
    for y in range(start_year, today.year + 1):
        end = f"{y}12" if y < today.year else f"{y}{today.month:02d}"
        cache = f"{OUT}/cache_{hs}_{y}.json"
        # 지난 해(확정)는 캐시 재사용, 올해·작년은 잠정치 수정 반영 위해 매번 새로 받음
        if os.path.exists(cache) and y < today.year - 1:
            items = json.load(open(cache))
        else:
            items = call({"strtYymm": f"{y}01", "endYymm": end, "hsSgn": hs})
            json.dump(items, open(cache, "w"))
        n = 0
        for it in items:
            if it.get("year") in (None, "총계") or it.get("hsCd") in (None, "-"):
                continue
            rows.append([it["year"].replace(".", "-"), it["hsCd"], it.get("statCd"), it.get("statCdCntnKor1"),
                         int(it.get("expDlr") or 0), int(it.get("expWgt") or 0), int(it.get("impDlr") or 0), int(it.get("impWgt") or 0)])
            n += 1
        print(hs, y, n, "rows", flush=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["month", "hs", "country", "country_nm", "exp_usd", "exp_kg", "imp_usd", "imp_kg"]); w.writerows(rows)
    print("saved", path, len(rows))

if __name__ == "__main__":
    for hs in (sys.argv[1:] or ["854232", "8542", "8486"]):
        collect(hs)
