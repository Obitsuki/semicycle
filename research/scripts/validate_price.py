"""한국은행 메모리 수출물가지수가 실제 메모리 업황(마이크론 매출·마진)을 따라가는지 검증."""
import pandas as pd, numpy as np, json

ecos = pd.read_csv("data/clean/ecos_export_price_memory.csv", parse_dates=["month"]).set_index("month")
ecos = ecos[ecos.index >= "2000-01-01"]
# 메모리 합성: ECOS 가중치(DRAM 103.4, 플래시 29.8)로 가중 평균한 YoY
w_d, w_f = 103.4, 29.8
yoy = ecos.pct_change(12, fill_method=None) * 100
yoy["memory_usd"] = (yoy["dram_usd"] * w_d + yoy["flash_usd"] * w_f) / (w_d + w_f)

mu = pd.read_csv("data/clean/micron_quarterly.csv", parse_dates=["quarter_end"])
mu = mu[mu.quarter_end >= "2009-11-01"].copy()
# 회계분기 말일이 월초(예: 6월 1일)면 실제 분기 마지막 달은 전월 → 7일을 빼서 매칭
mu["qmonth"] = (mu.quarter_end - pd.Timedelta(days=7)).dt.to_period("M")
# 마이크론 회계분기 말 월 기준으로 직전 3개월 평균 지수 YoY를 매칭
yoy_m = yoy.copy(); yoy_m.index = yoy_m.index.to_period("M")
def q_avg(col, pm):
    rng = pd.period_range(pm - 2, pm, freq="M")
    v = yoy_m.reindex(rng)[col]
    return v.mean() if v.notna().sum() == 3 else np.nan
for col in ["dram_usd", "flash_usd", "memory_usd"]:
    mu[col + "_yoy"] = [q_avg(col, p) for p in mu.qmonth]
mu = mu.sort_values("quarter_end").reset_index(drop=True)
mu["rev_yoy"] = mu.revenue_usd.pct_change(4) * 100
mu["gm_pp_yoy"] = (mu.gross_margin - mu.gross_margin.shift(4)) * 100
mu["gm_pct"] = mu.gross_margin * 100

res = {"n_quarters": int(mu.rev_yoy.notna().sum()), "period": [str(mu.quarter_end.iloc[4].date()), str(mu.quarter_end.iloc[-1].date())]}
# 상관: 지수가 k분기 앞설 때 (k>0이면 지수가 선행)
def lagcorr(x, y, k):
    return pd.concat([mu[x].shift(k), mu[y]], axis=1).dropna().corr().iloc[0, 1]
for x in ["memory_usd_yoy", "dram_usd_yoy"]:
    for y in ["rev_yoy", "gm_pp_yoy", "gm_pct"]:
        res[f"corr_{x}_vs_{y}"] = {k: round(lagcorr(x, y, k), 3) for k in [-2, -1, 0, 1, 2]}

# 전환점: 지수 YoY(분기)와 마이크론 매출 YoY의 고점·저점 시기 비교 (스무딩 없이, 4분기 창 국지 극값)
def turning(series, window=3):
    s = series.dropna()
    pts = []
    for i in range(window, len(s) - window):
        seg = s.iloc[i - window:i + window + 1]
        if s.iloc[i] == seg.max() and s.iloc[i] > 0: pts.append((s.index[i], "peak"))
        if s.iloc[i] == seg.min() and s.iloc[i] < 0: pts.append((s.index[i], "trough"))
    return pts
mu_idx = mu.set_index("quarter_end")
tp_idx = turning(mu_idx["memory_usd_yoy"])
tp_rev = turning(mu_idx["rev_yoy"])
match = []
for d, kind in tp_idx:
    cands = [(abs((d2 - d).days), d2) for d2, k2 in tp_rev if k2 == kind]
    if cands:
        dd, d2 = min(cands)
        match.append({"type": kind, "index": str(d.date()), "micron_rev": str(d2.date()), "diff_quarters": round((d2 - d).days / 91)})
res["turning_points"] = match
mu.to_csv("data/clean/validation_quarterly.csv", index=False)
yoy.to_csv("data/clean/ecos_memory_yoy_monthly.csv")
print(json.dumps(res, ensure_ascii=False, indent=1))
