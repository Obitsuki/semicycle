"""원자료(long) → 발표 시점 기준 월별 인자 패널.

각 인자 값은 '그 달 말에 실제로 공개돼 있던 정보'만으로 계산한다.
- 월간 통계: 기준월 + lag_months 에 공개된 것으로 본다.
- 분기 공시: 공시일이 속한 달부터 반영(마이크론 매출·마진은 분기 종료 다음 달 실적 발표 기준).
반환: raw(인자 원값, 월×인자), info(인자별 최신 기준기간·공개일).
"""
import numpy as np
import pandas as pd

W_DRAM, W_FLASH = 103.4, 29.8   # 한국은행 수출물가지수 품목 가중치(2020=100 기준)


# ---------------------------------------------------------------- 공통 도구
def yoy(s, n=12):
    return (s / s.shift(n) - 1) * 100


def lag(s, months):
    s = s.copy()
    s.index = s.index + months
    return s


def monthly(df, series):
    d = df[df["series"] == series]
    if d.empty:
        return pd.Series(dtype=float)
    s = pd.Series(d["value"].values, index=pd.PeriodIndex(d["period"], freq="M")).sort_index()
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))


def quarterly_to_monthly(values, avail_month, idx):
    """분기 값: 공개된 달부터 다음 공개 전까지 유지."""
    d = pd.DataFrame({"v": np.asarray(values, dtype=float), "m": list(avail_month)}).dropna()
    if d.empty:
        return pd.Series(np.nan, index=idx)
    d = d.sort_values("m").drop_duplicates("m", keep="last").set_index("m")["v"]
    d.index = pd.PeriodIndex(d.index, freq="M")
    return d.reindex(idx, method="ffill")


def _wide(df, prefix):
    """'dart.skhynix.revenue' 같은 series를 회사별 wide 표로. released는 항목 중 하나에서."""
    d = df[df["series"].str.startswith(prefix)].copy()
    d["item"] = d["series"].str[len(prefix):]
    w = d.pivot(index="period", columns="item", values="value")
    rel = d.groupby("period")["released"].agg(lambda x: max((v for v in x if v), default=""))
    w["released"] = rel
    return w.sort_index()


# ---------------------------------------------------------------- 인자 빌더
def build(data, idx):
    """data: {source: long DataFrame}. 반환 (raw DataFrame, info dict)."""
    raw, info = {}, {}

    def put(key, series, period=None, released=None):
        raw[key] = series
        info[key] = {"data_period": period, "released": released}

    def last_period(s):
        s = s.dropna()
        return str(s.index[-1]) if len(s) else None

    # 가격: 한국은행 메모리 수출물가지수(달러) — 가중 합성 YoY
    e = data["ecos"]
    dram, flash = monthly(e, "ecos.dram_usd"), monthly(e, "ecos.flash_usd")
    mem = (yoy(dram) * W_DRAM + yoy(flash) * W_FLASH) / (W_DRAM + W_FLASH)
    put("price_yoy", lag(mem, 1), last_period(mem))
    put("price_accel", lag(mem - mem.shift(3), 1), last_period(mem))

    # 물량: 관세청 집적회로 수출 3개월 합 YoY
    c = data["customs"]
    ic = yoy(monthly(c, "customs.ic_export_usd").rolling(3).sum())
    put("ic_export_yoy", lag(ic, 1), last_period(ic))

    # 마이크론 분기 매출·마진 (분기 종료 다음 달 실적 발표 기준)
    s = data["sec"]
    mu = _wide(s, "sec.MU.")
    mu.index = pd.to_datetime(mu.index)
    mu = mu[mu.index >= "2009-11-01"].dropna(subset=["revenue"])
    mu_rev_yoy = mu["revenue"].pct_change(4, fill_method=None) * 100
    mu_gm_chg = (mu["gross_profit"] / mu["revenue"]).diff(4) * 100
    mu_avail = (mu.index - pd.Timedelta(days=7)).to_period("M") + 1
    put("micron_rev_yoy", quarterly_to_monthly(mu_rev_yoy, mu_avail, idx),
        str(mu.index[-1].date()) if len(mu) else None)

    # 재고: KOSIS 반도체 출하 YoY − 재고 YoY (계절조정)
    k = data["kosis"]
    gap = yoy(monthly(k, "kosis.semi_ship_sa")) - yoy(monthly(k, "kosis.semi_inv_sa"))
    put("ship_inv_gap", lag(gap, 2), last_period(gap))

    # 재고일수 변화: 마이크론(10-Q 공시일) + SK하이닉스(DART 공시일)
    mi = _wide(s, "sec.MU.")[["cogs", "inventory"]].dropna()
    cogs_rel = s[s["series"] == "sec.MU.cogs"].set_index("period")["released"]
    mi = mi.join(cogs_rel.rename("rel"), how="left").sort_index()
    mi["days"] = mi["inventory"] / mi["cogs"] * 91
    mi["chg"] = mi["days"].diff(4)
    mu_inv = quarterly_to_monthly(mi["chg"], pd.to_datetime(mi["rel"]).dt.to_period("M"), idx)

    d = data["dart"]
    hx = _wide(d, "dart.skhynix.")
    hx.index = pd.PeriodIndex([p.replace("Q", "-Q") for p in hx.index], freq="Q")
    hx = hx.sort_index()
    hx_avail = pd.to_datetime(hx["released"]).dt.to_period("M")
    hx_inv = quarterly_to_monthly((hx["inventory"] / hx["cogs"] * 91).diff(4), hx_avail, idx)
    put("inventory_days_chg", pd.concat([mu_inv, hx_inv], axis=1).mean(axis=1),
        f"MU {mi.index[-1] if len(mi) else '-'} / SK하이닉스 {hx.index[-1]}",
        f"MU {mi['rel'].iloc[-1] if len(mi) else '-'} / SK하이닉스 {hx['released'].iloc[-1]}")

    # 이익: 마이크론 GM 변화 + 하이닉스 OPM 변화, 삼성전자 OPM 변화
    hx_opm_chg = (hx["op_income"] / hx["revenue"] * 100).diff(4)
    put("memory_margin_chg", pd.concat([quarterly_to_monthly(mu_gm_chg, mu_avail, idx),
                                        quarterly_to_monthly(hx_opm_chg, hx_avail, idx)], axis=1).mean(axis=1),
        f"MU {mu.index[-1].date() if len(mu) else '-'} / SK하이닉스 {hx.index[-1]}",
        f"SK하이닉스 {hx['released'].iloc[-1]}")
    sm = _wide(d, "dart.samsung.")
    sm.index = pd.PeriodIndex([p.replace("Q", "-Q") for p in sm.index], freq="Q")
    sm = sm.sort_index()
    sm_opm_chg = (sm["op_income"] / sm["revenue"] * 100).diff(4)
    put("samsung_opm_chg", quarterly_to_monthly(sm_opm_chg, pd.to_datetime(sm["released"]).dt.to_period("M"), idx),
        str(sm.index[-1]), sm["released"].iloc[-1])

    # 수요: 하이퍼스케일러 capex 합계 YoY (같은 회사끼리 비교, 마지막 회사 공시 달에 확정)
    cx = s[s["series"].str.endswith(".capex")].copy()
    cx["company"] = cx["series"].str.split(".").str[1]
    cx["qe"] = pd.to_datetime(cx["period"])
    cx["cq"] = cx["qe"].dt.to_period("Q")
    cx = cx.sort_values("qe").drop_duplicates(["company", "cq"], keep="last")
    piv = cx.pivot(index="cq", columns="company", values="value")
    filed = cx.assign(rel=pd.to_datetime(cx["released"])).pivot(index="cq", columns="company", values="rel")
    prev = piv.shift(4)
    both = piv.notna() & prev.notna()
    # 1년 전 값이 있는 회사가 모두 이번 분기를 공시해야 그 분기를 확정(일부 회사만으로 계산하지 않음)
    complete = (piv.notna() | prev.isna()).all(axis=1)
    capex_yoy = (piv.where(both).sum(axis=1) / prev.where(both).sum(axis=1) - 1) * 100
    capex_yoy[(both.sum(axis=1) == 0) | ~complete] = np.nan
    capex_avail = filed.max(axis=1).dt.to_period("M")
    put("hyperscaler_capex_yoy", quarterly_to_monthly(capex_yoy, capex_avail, idx),
        str(capex_yoy.dropna().index[-1]) if capex_yoy.notna().any() else None,
        str(filed.max(axis=1)[capex_yoy.dropna().index[-1]].date()) if capex_yoy.notna().any() else None)

    # 수요: 반도체 장비 수입 3개월 합 YoY
    eq = yoy(monthly(c, "customs.equip_import_usd").rolling(3).sum())
    put("equipment_import_yoy", lag(eq, 1), last_period(eq))

    # 수요: 미국 컴퓨터·전자 신규주문/재고 비율 YoY
    f = data["fred"]
    ratio = yoy(monthly(f, "fred.A34SNO") / monthly(f, "fred.A34STI"))
    put("us_orders_inv_ratio_yoy", lag(ratio, 2), last_period(ratio))

    frame = pd.DataFrame({k: v.reindex(idx) for k, v in raw.items()})
    return frame, info


def memory_price_yoy(data):
    """검증용: 지연 없이 실제 기준월로 본 메모리 수출물가 YoY."""
    e = data["ecos"]
    dram, flash = monthly(e, "ecos.dram_usd"), monthly(e, "ecos.flash_usd")
    return (yoy(dram) * W_DRAM + yoy(flash) * W_FLASH) / (W_DRAM + W_FLASH)
