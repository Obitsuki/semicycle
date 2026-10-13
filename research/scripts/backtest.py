"""지수 v0 백테스트: KRX 반도체지수 향후 수익률과 점수의 관계.
- IC: 월말 점수와 향후 3·6·12개월 로그수익률의 스피어만 순위상관.
- 구간: 점수 0~20, 20~40, …, 80~100별 평균 향후 수익률.
주의: 월별 표본에 향후 6·12개월 수익률은 기간이 겹쳐 유효 표본이 훨씬 적다(t값 과대).
"""
import json
import sys
import numpy as np
import pandas as pd

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "v0"
SPLIT = "2020-12"  # 전반/후반 안정성 확인용
res = pd.read_csv(f"data/clean/index_{VARIANT}_monthly.csv", index_col=0)
res.index = pd.PeriodIndex(res.index, freq="M")
kx = pd.read_csv("data/clean/krx_month_end.csv", dtype={"date": str})
kx.index = pd.PeriodIndex(pd.to_datetime(kx.date), freq="M")
px = kx.krx_semi

fwd = pd.DataFrame({f"fwd_{h}m": np.log(px.shift(-h) / px) * 100 for h in (3, 6, 12)})
df = res.join(fwd, how="inner")

def ic(score, h, part=None):
    d = df[[score, f"fwd_{h}m"]].dropna()
    if part == "early": d = d[d.index <= pd.Period(SPLIT, "M")]
    if part == "late": d = d[d.index > pd.Period(SPLIT, "M")]
    if len(d) < 24:
        return np.nan, len(d)
    return d[score].rank().corr(d[f"fwd_{h}m"].rank()), len(d)

scores = ["attractiveness", "cycle", "market"] + [c for c in df.columns if c.startswith("p_")] + [c for c in df.columns if c.startswith("pct_")]
rows = []
for s in scores:
    r = {"score": s}
    for h in (3, 6, 12):
        v, n = ic(s, h)
        r[f"ic_{h}m"] = v
        r[f"n_{h}m"] = n
    for part in ("early", "late"):
        r[f"ic6_{part}"] = ic(s, 6, part)[0]
    rows.append(r)
ic_tbl = pd.DataFrame(rows).set_index("score")

bins = [0, 20, 40, 60, 80, 100.01]
labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
buckets = {}
for s in ["attractiveness", "cycle", "market"]:
    d = df[[s, "fwd_6m", "fwd_12m"]].dropna(subset=[s, "fwd_6m"])
    d["bucket"] = pd.cut(d[s], bins=bins, labels=labels, right=False)
    buckets[s] = d.groupby("bucket", observed=False).agg(n=("fwd_6m", "size"), fwd_6m=("fwd_6m", "mean"), fwd_12m=("fwd_12m", "mean"))

ic_tbl.to_csv(f"data/clean/backtest_{VARIANT}_ic.csv")
with open(f"data/clean/backtest_{VARIANT}_buckets.json", "w") as f:
    json.dump({k: v.round(2).reset_index().to_dict(orient="records") for k, v in buckets.items()}, f, ensure_ascii=False, indent=1)
pd.set_option("display.width", 160)
print(ic_tbl.round(2))
for k, v in buckets.items():
    print("\n", k); print(v.round(1))
print("\nsample:", df.attractiveness.first_valid_index(), "~", df.fwd_6m.last_valid_index())
