import numpy as np
import pandas as pd
import pytest

from semicycle import store
from semicycle.config import load_registry, sec_user_agent
from semicycle.http import redact, register_secrets
from semicycle.indicators import lag, quarterly_to_monthly, yoy
from semicycle.score import compute, expanding_pct, phase_of
from semicycle.sources.dart import year_rows
from semicycle.sources.sec import quarterly_with_q4, to_quarterly
from semicycle.validate import validate_source


def test_expanding_pct_uses_only_past():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=120), index=pd.period_range("2010-01", periods=120, freq="M"))
    full = expanding_pct(s, 36)
    for cut in (50, 80, 119):
        part = expanding_pct(s.iloc[: cut + 1], 36)
        assert part.iloc[-1] == pytest.approx(full.iloc[cut])


def test_score_at_t_unchanged_by_future_data():
    """t 시점 점수는 t 이후 데이터가 추가돼도 바뀌지 않아야 한다(미래 정보 누수 없음)."""
    reg = load_registry()
    idx = pd.period_range("2000-01", periods=200, freq="M")
    rng = np.random.default_rng(1)
    raw = pd.DataFrame({i["id"]: rng.normal(size=len(idx)).cumsum() for i in reg["indicators"]}, index=idx)
    full = compute(raw, reg)
    cut = compute(raw.iloc[:150], reg)
    for k in ("level", "direction"):
        assert cut[k].iloc[-1] == pytest.approx(full[k].iloc[149])


def test_lag_and_yoy():
    s = pd.Series(np.arange(1, 25, dtype=float), index=pd.period_range("2020-01", periods=24, freq="M"))
    assert yoy(s).iloc[12] == pytest.approx((13 / 1 - 1) * 100)
    assert str(lag(s, 2).index[0]) == "2020-03"


def test_quarterly_to_monthly_holds_until_next_release():
    idx = pd.period_range("2024-01", "2024-12", freq="M")
    out = quarterly_to_monthly([1.0, 2.0], [pd.Period("2024-02", "M"), pd.Period("2024-05", "M")], idx)
    assert np.isnan(out["2024-01"]) and out["2024-02"] == 1.0 and out["2024-04"] == 1.0 and out["2024-12"] == 2.0


def _fact(start, end, val, filed):
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_sec_q4_from_annual():
    d = {("2025-08-29", "2025-11-27"): {"val": 10, "filed": "2025-12-18", "first_filed": "2025-12-18"},
         ("2025-11-28", "2026-02-26"): {"val": 20, "filed": "2026-03-19", "first_filed": "2026-03-19"},
         ("2026-02-27", "2026-05-28"): {"val": 30, "filed": "2026-06-25", "first_filed": "2026-06-25"},
         ("2025-08-29", "2026-09-03"): {"val": 100, "filed": "2026-10-09", "first_filed": "2026-10-09"}}
    q = quarterly_with_q4(d)
    assert q["2026-09-03"] == (40, "2026-10-09")


def test_sec_cumulative_differencing():
    d = {("2026-01-01", "2026-03-31"): {"val": 5, "filed": "a", "first_filed": "2026-04-30"},
         ("2026-01-01", "2026-06-30"): {"val": 12, "filed": "b", "first_filed": "2026-07-30"}}
    q = to_quarterly(d)
    assert q["2026-06-30"] == (7, "2026-07-30")


def test_dart_q4_is_annual_minus_q1_to_q3():
    def rep(rev, rc):
        return [{"account_id": "ifrs-full_Revenue", "thstrm_amount": f"{rev:,}", "rcept_no": rc + "000001"}]
    rows = year_rows("x", 2025, {1: rep(10, "20250515"), 2: rep(20, "20250814"), 3: rep(30, "20251114"), 4: rep(100, "20260310")})
    q4 = [r for r in rows if r[1] == "2025Q4"][0]
    assert q4[2] == 40 and q4[3] == "2026-03-10"


def test_validate_source_rejects_shrink_and_regression():
    old = pd.DataFrame({"series": ["a"] * 10, "period": [f"2020-{m:02d}" for m in range(1, 11)], "value": 1.0, "released": ""})
    assert validate_source(old, old) == []
    assert validate_source(old, old.iloc[:5])  # 감소·후퇴


def test_phase_rules():
    assert phase_of(60, 60) == "expansion" and phase_of(60, 40) == "slowdown"
    assert phase_of(40, 60) == "recovery" and phase_of(40, 40) == "contraction"


def test_secrets_redacted_including_url_encoded():
    register_secrets(["abc/def=ghi12345"])
    assert "abc" not in redact("x?k=abc%2Fdef%3Dghi12345&y=abc/def=ghi12345")


def test_sec_user_agent_format():
    assert sec_user_agent({"SEC_USER_AGENT": "Name / me@example.com"}) == "Name me@example.com"


def test_log_releases_records_new_and_revised(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    old = pd.DataFrame({"series": ["a", "a"], "period": ["2020-01", "2020-02"], "value": [1.0, 2.0], "released": ""})
    new = pd.DataFrame({"series": ["a", "a", "a"], "period": ["2020-01", "2020-02", "2020-03"], "value": [1.0, 2.5, 3.0], "released": ""})
    assert store.log_releases(old, new, "2026-01-01") == 2
    log = pd.read_csv(tmp_path / "releases.csv")
    assert set(log["kind"]) == {"new", "revised"}
