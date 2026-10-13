"""업황 사이클 위치: 수준(지금 업황이 얼마나 좋은가) × 방향(좋아지는 중인가)으로 4개 국면 판정.
- 수준: 성장률 '수준' 인자(v0 방식)의 백분위 → 필러 가중 합성
- 방향: 성장률의 '3개월 변화' 인자(v1 방식) → 필러 가중 합성 (= v1 업황 점수)
- 국면: 수준≥50·방향≥50 확장 / 수준≥50·방향<50 둔화 / 수준<50·방향<50 수축 / 수준<50·방향≥50 회복
"""
import json
import numpy as np
import pandas as pd

W = {"price": 25, "volume": 25, "inventory": 20, "earnings": 15, "demand": 15}
v0 = pd.read_csv("data/clean/index_v0_monthly.csv", index_col=0)
v1 = pd.read_csv("data/clean/index_v1_monthly.csv", index_col=0)
meta0 = json.load(open("data/clean/index_v0_meta.json"))

# 수준: v0 인자 중 '변화량'이 아닌 것만 (가격 가속도 제외)
level_cols = {k: v["pillar"] for k, v in meta0.items() if v["pillar"] in W and k != "price_accel"}
pill = pd.DataFrame({p: v0[[f"pct_{k}" for k, pp in level_cols.items() if pp == p]].mean(axis=1) for p in W})
wv = pd.Series(W, dtype=float)
avail = pill.notna()
level = pill.fillna(0).mul(wv, axis=1).sum(axis=1) / avail.mul(wv, axis=1).sum(axis=1)
level[avail.mul(wv, axis=1).sum(axis=1) / wv.sum() < 0.6] = np.nan
direction = v1["cycle"]

def phase(l, d):
    if pd.isna(l) or pd.isna(d): return None
    if l >= 50: return "확장" if d >= 50 else "둔화"
    return "회복" if d >= 50 else "수축"

out = pd.DataFrame({"level": level, "direction": direction})
out["phase"] = [phase(l, d) for l, d in zip(out.level, out.direction)]
out = out.dropna(subset=["phase"])
out.to_csv("data/clean/cycle_position.csv")

# 검증: 국면별 실제 메모리 가격 흐름(지연 없는 실제 기준월)
y = pd.read_csv("data/clean/ecos_memory_yoy_monthly.csv", parse_dates=["month"]).set_index("month")["memory_usd"]
y.index = y.index.to_period("M").astype(str)
chk = out.join(pd.DataFrame({"price_yoy_now": y, "price_yoy_6m_later": y.shift(-6)}), how="left")
chk["chg_6m"] = chk.price_yoy_6m_later - chk.price_yoy_now
order = ["회복", "확장", "둔화", "수축"]
summ = chk.groupby("phase").agg(months=("level", "size"), price_yoy_now=("price_yoy_now", "mean"),
                                 price_yoy_chg_next6m=("chg_6m", "mean"),
                                 share_up_next6m=("chg_6m", lambda s: (s > 0).mean() * 100)).reindex(order)
print("기간:", out.index[0], "~", out.index[-1])
print(summ.round(1))
# 국면 전환 빈도(깜빡임 점검)
switches = (out.phase != out.phase.shift()).sum() - 1
print("국면 전환 횟수:", switches, "/", len(out), "개월")
print(out.tail(8).round(1))
