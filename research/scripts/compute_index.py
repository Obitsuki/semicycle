"""반도체 사이클 지수 v0 계산.

원칙
- 월말(t) 기준 패널. 각 인자는 '그 월말에 실제로 공개돼 있던 값'만 사용(발표 지연 반영).
- 변환(YoY·가속도 등) → 확장창 백분위(과거~t, 최소 36개월) → 필러 평균 → 가중 합성.
- 업황: 높을수록 업황 개선. 시장 온도: 높을수록 과열. 투자 매력도 = 0.6×업황 + 0.4×(100−온도).
"""
import json
import sys
import numpy as np
import pandas as pd

MIN_HIST = 36
W_CYCLE = {"price": 25, "volume": 25, "inventory": 20, "earnings": 15, "demand": 15}
W_MARKET = {"valuation": 30, "momentum": 30, "flows": 20, "sentiment": 20}
W_HEADLINE = 0.6


def month_index(start="2000-01", end=None):
    end = end or pd.Timestamp.today().strftime("%Y-%m")
    return pd.period_range(start, end, freq="M")


def lag(s: pd.Series, months: int) -> pd.Series:
    """기준월 M 데이터가 M+months 월말에 공개된다고 보고 이동."""
    s = s.copy()
    s.index = s.index + months
    return s


def quarterly_to_monthly(values: pd.Series, avail_month: pd.Series, idx) -> pd.Series:
    """분기 데이터: 공개된 달부터 다음 공개 전까지 값 유지."""
    df = pd.DataFrame({"v": values.values, "m": avail_month.values}).dropna()
    df = df.sort_values("m").drop_duplicates("m", keep="last").set_index("m")["v"]
    return df.reindex(idx, method="ffill") if len(df) else pd.Series(np.nan, index=idx)


def expanding_pct(s: pd.Series, min_hist=MIN_HIST) -> pd.Series:
    """t 시점까지의 자기 이력 대비 백분위(0~100). 미래 정보 없음."""
    out = pd.Series(np.nan, index=s.index)
    hist = []
    for t, x in s.items():
        if pd.isna(x):
            continue
        hist.append(x)
        if len(hist) >= min_hist:
            h = np.array(hist)
            out[t] = ((h < x).sum() + 0.5 * (h == x).sum()) / len(h) * 100
    return out


def yoy(s, n=12):
    return (s / s.shift(n) - 1) * 100


# ---------------------------------------------------------------- 원자료 로드
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "v0"
IDX = month_index()
ind = {}  # name -> (pillar, direction, series aligned to IDX by availability)

# 가격: 한국은행 수출물가지수(달러 기준) — M월 지수는 M+1월 중순 공개 → 1개월 지연
ecos = pd.read_csv("data/clean/ecos_export_price_memory.csv")
ecos.index = pd.PeriodIndex(ecos.month, freq="M")
w_d, w_f = 103.4, 29.8
mem_yoy = (yoy(ecos.dram_usd) * w_d + yoy(ecos.flash_usd) * w_f) / (w_d + w_f)
ind["price_yoy"] = ("price", +1, lag(mem_yoy, 1))
ind["price_accel"] = ("price", +1, lag(mem_yoy - mem_yoy.shift(3), 1))

# 물량: 관세청 집적회로(HS 8542) 수출 3개월 합 YoY — M월 확정치는 M+1월 중순 → 1개월 지연
def customs_monthly(hs, col="exp_usd", country=None, code=None):
    d = pd.read_csv(f"data/raw/customs/hs_{hs}.csv", dtype={"hs": str})
    if country:
        d = d[d.country == country]
    if code:
        d = d[d.hs == code]
    s = d.groupby("month")[col].sum()
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))

ic_exp = customs_monthly("8542")
ind["ic_export_yoy"] = ("volume", +1, lag(yoy(ic_exp.rolling(3).sum()), 1))

# 물량: 마이크론 매출 YoY — 분기말 다음 달에 실적 발표
mu = pd.read_csv("data/clean/micron_quarterly.csv", parse_dates=["quarter_end"]).sort_values("quarter_end")
mu = mu[mu.quarter_end >= "2009-11-01"].reset_index(drop=True)
mu["rev_yoy"] = mu.revenue_usd.pct_change(4) * 100
mu["gm_chg"] = (mu.gross_margin - mu.gross_margin.shift(4)) * 100
mu_avail = (mu.quarter_end - pd.Timedelta(days=7)).dt.to_period("M") + 1
ind["micron_rev_yoy"] = ("volume", +1, quarterly_to_monthly(mu.rev_yoy, mu_avail, IDX))

# v2: 대만향 복합구조칩(HS 8542323000) 수출 3개월 합 YoY — HBM 대리지표 (PROTOCOL.md 사전 선언)
if VARIANT == "v2":
    tw_mcp = customs_monthly("854232", country="TW", code="8542323000")
    ind["tw_mcp_export_yoy"] = ("volume", +1, lag(yoy(tw_mcp.rolling(3).sum()), 1))

# 재고: KOSIS 반도체 출하 YoY − 재고 YoY(계절조정) — M월은 M+1월 말 공개 → 보수적으로 2개월 지연
ko = pd.read_csv("data/clean/kosis_semi_ship_inv.csv")
ko.index = pd.PeriodIndex(ko.month, freq="M")
ind["ship_inv_gap"] = ("inventory", +1, lag(yoy(ko.ship_sa) - yoy(ko.inv_sa), 2))

# 재고: 재고일수 YoY 변화(마이크론 2009~, 하이닉스 2015~) 평균 — 높을수록 나쁨
mi = pd.read_csv("data/clean/micron_inventory_q.csv", parse_dates=["quarter_end", "first_filed"]).sort_values("quarter_end")
mi["chg"] = mi.inventory_days - mi.inventory_days.shift(4)
mu_inv = quarterly_to_monthly(mi.chg, mi.first_filed.dt.to_period("M"), IDX)

dart = pd.read_csv("data/clean/dart_quarterly.csv", parse_dates=["filed"])
dart["qe"] = pd.PeriodIndex(dart.quarter.str.replace("Q", "-Q"), freq="Q")
dart = dart.sort_values(["company", "qe"])
hx = dart[dart.company == "skhynix"].reset_index(drop=True)
hx["inv_days"] = hx.inventory / hx.cogs * 91
hx["inv_chg"] = hx.inv_days - hx.inv_days.shift(4)
hx["opm"] = hx.op_income / hx.revenue * 100
hx["opm_chg"] = hx.opm - hx.opm.shift(4)
hx_avail = hx.filed.dt.to_period("M")
hx_inv = quarterly_to_monthly(hx.inv_chg, hx_avail, IDX)
ind["inventory_days_chg"] = ("inventory", -1, pd.concat([mu_inv, hx_inv], axis=1).mean(axis=1))

# 이익: 마진 YoY 변화(마이크론 총이익률, 하이닉스 영업이익률) 평균
mu_gm = quarterly_to_monthly(mu.gm_chg, mu_avail, IDX)
hx_opm = quarterly_to_monthly(hx.opm_chg, hx_avail, IDX)
ind["memory_margin_chg"] = ("earnings", +1, pd.concat([mu_gm, hx_opm], axis=1).mean(axis=1))
# 이익: 삼성전자 영업이익률 YoY 변화(전사)
sm = dart[dart.company == "samsung"].reset_index(drop=True)
sm["opm"] = sm.op_income / sm.revenue * 100
sm["opm_chg"] = sm.opm - sm.opm.shift(4)
ind["samsung_opm_chg"] = ("earnings", +1, quarterly_to_monthly(sm.opm_chg, sm.filed.dt.to_period("M"), IDX))

# 수요: 하이퍼스케일러 capex 합계 YoY(같은 회사끼리 비교), 공시월 기준
cx = pd.read_csv("data/clean/hyperscaler_capex_q.csv", parse_dates=["quarter_end", "first_filed"])
cx["cq"] = cx.quarter_end.dt.to_period("Q")
cx = cx.sort_values("quarter_end").drop_duplicates(["company", "cq"], keep="last")
piv = cx.pivot(index="cq", columns="company", values="capex_usd")
filed = cx.pivot(index="cq", columns="company", values="first_filed")
both = piv.notna() & piv.shift(4).notna()
capex_yoy = (piv.where(both).sum(axis=1) / piv.shift(4).where(both).sum(axis=1) - 1) * 100
capex_yoy[both.sum(axis=1) == 0] = np.nan
capex_avail = filed.max(axis=1).dt.to_period("M")  # 마지막 회사가 공시한 달에 확정
ind["hyperscaler_capex_yoy"] = ("demand", +1, quarterly_to_monthly(capex_yoy, capex_avail, IDX))

# 수요: 반도체 장비(HS 8486) 수입 3개월 합 YoY
eq = customs_monthly("8486", col="imp_usd")
ind["equipment_import_yoy"] = ("demand", +1, lag(yoy(eq.rolling(3).sum()), 1))

# 수요: 미국 컴퓨터·전자 신규주문/재고 비율 YoY — M3 확정치 M+2월 초 → 2개월 지연
fr = pd.read_csv("data/clean/fred_us_electronics.csv")
fr.index = pd.PeriodIndex(fr.month, freq="M")
ratio = fr.us_ce_new_orders / fr.us_ce_inventories
ind["us_orders_inv_ratio_yoy"] = ("demand", +1, lag(yoy(ratio), 2))

# ---------------------------------------------------------------- 시장 온도
kx = pd.read_csv("data/clean/krx_month_end.csv", dtype={"date": str})
kx.index = pd.PeriodIndex(pd.to_datetime(kx.date), freq="M")
# 밸류에이션: (삼성+하이닉스 시총) / (지배주주 자본 합) — 자본은 공시월부터 반영
eq_s = quarterly_to_monthly(sm.equity_parent, sm.filed.dt.to_period("M"), IDX)
eq_h = quarterly_to_monthly(hx.equity_parent, hx_avail, IDX)
pbr = (kx.samsung_mktcap + kx.skhynix_mktcap) / (eq_s.reindex(kx.index) + eq_h.reindex(kx.index))
ind["pbr"] = ("valuation", +1, pbr)
# 모멘텀
ind["semi_vs_10m_ma"] = ("momentum", +1, (kx.krx_semi / kx.krx_semi.rolling(10).mean() - 1) * 100)
ind["semi_rel_3m"] = ("momentum", +1, (kx.krx_semi.pct_change(3) - kx.kospi.pct_change(3)) * 100)
# 수급: 반도체 ETF 3개월 순유입(좌수 변화×NAV) / 평균 순자산 — 해외지수 추종 ETF 제외
et = pd.read_csv("data/clean/krx_semi_etf_month_end.csv", dtype={"date": str, "isu_cd": str})
foreign = "미국|글로벌|필라델피아|US|World|차이나|중국|일본|대만|아시아|S&P|나스닥|NASDAQ|Global|PHLX|Solactive|Bloomberg|MSCI|ICE|NYSE|Indxx"
et = et[~(et.name.str.contains(foreign, na=False) | et.index_name.str.contains(foreign, na=False))]
et["m"] = pd.PeriodIndex(pd.to_datetime(et.date), freq="M")
et = et.sort_values(["isu_cd", "m"])
et["dshr"] = et.groupby("isu_cd").list_shrs.diff()
et["flow"] = et.dshr * et.nav
flow = et.groupby("m").flow.sum()
aum = et.groupby("m").net_asset.sum()
ind["etf_flow_3m"] = ("flows", +1, flow.rolling(3).sum() / aum.rolling(3).mean() * 100)
# 심리: VKOSPI(높을수록 공포 → 온도 낮음)
ind["vkospi"] = ("sentiment", -1, kx.vkospi)

# ---------------------------------------------------------------- 정규화·합성
# 다음 발표 전까지는 마지막 공개값을 사용(최대 3개월). 백테스트와 실시간 표시가 같은 규칙을 따른다.
raw = pd.DataFrame({k: v[2].reindex(IDX).ffill(limit=3) for k, v in ind.items()})

# v1: 업황 성장률 인자를 '성장률의 3개월 변화(2차 미분)'로 바꾼다. 재고 갭·재고일수 변화·가격 가속도는 이미 변화량이라 유지.
if VARIANT in ("v1", "v2"):
    GROWTH = ["ic_export_yoy", "micron_rev_yoy", "memory_margin_chg", "samsung_opm_chg",
              "hyperscaler_capex_yoy", "equipment_import_yoy", "us_orders_inv_ratio_yoy"]
    if VARIANT == "v2":
        GROWTH.append("tw_mcp_export_yoy")
    for k in GROWTH:
        raw[k] = raw[k] - raw[k].shift(3)
    raw = raw.drop(columns=["price_yoy"])   # 3개월 변화로 바꾸면 price_accel과 동일
    del ind["price_yoy"]
pct = pd.DataFrame(index=IDX)
for k, (pillar, sign, _) in ind.items():
    p = expanding_pct(raw[k])
    pct[k] = p if sign > 0 else 100 - p

def pillar_scores(pillars):
    out = pd.DataFrame(index=IDX)
    for pl in pillars:
        cols = [k for k, v in ind.items() if v[0] == pl]
        out[pl] = pct[cols].mean(axis=1)
    return out

cyc_p = pillar_scores(W_CYCLE)
mkt_p = pillar_scores(W_MARKET)

def weighted(pdf, w, min_cover=0.6):
    wv = pd.Series(w, dtype=float)
    avail = pdf.notna()
    cover = avail.mul(wv, axis=1).sum(axis=1) / wv.sum()
    score = pdf.fillna(0).mul(wv, axis=1).sum(axis=1) / avail.mul(wv, axis=1).sum(axis=1)
    score[cover < min_cover] = np.nan
    return score, cover

cycle, cyc_cover = weighted(cyc_p, W_CYCLE)
market, mkt_cover = weighted(mkt_p, W_MARKET)
attract = W_HEADLINE * cycle + (1 - W_HEADLINE) * (100 - market)

res = pd.concat([raw.add_prefix("raw_"), pct.add_prefix("pct_"), cyc_p.add_prefix("p_"), mkt_p.add_prefix("p_"),
                 pd.DataFrame({"cycle": cycle, "cycle_cover": cyc_cover, "market": market,
                               "market_cover": mkt_cover, "attractiveness": attract})], axis=1)
res.index = res.index.astype(str)
res.to_csv(f"data/clean/index_{VARIANT}_monthly.csv")
meta = {k: {"pillar": v[0], "direction": v[1]} for k, v in ind.items()}
json.dump(meta, open(f"data/clean/index_{VARIANT}_meta.json", "w"), ensure_ascii=False, indent=1)
last = res.dropna(subset=["cycle"]).iloc[-1]
print("latest month with cycle score:", res.dropna(subset=["cycle"]).index[-1])
print(res[["cycle", "market", "attractiveness"]].dropna(how="all").tail(8).round(1))
print("first cycle:", res.cycle.first_valid_index(), " first market:", res.market.first_valid_index())
