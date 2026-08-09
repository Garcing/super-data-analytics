"""evaluating 内核契约测试 + alpha 解析回归。"""
import pytest
from sda_mcp.errors import ValidationError
from sda_mcp.skills.evaluating import evaluate


def test_ab_rate_significant():
    r = evaluate({"analysis_type": "ab_rate",
                  "control": {"n": 10000, "success": 1000},
                  "treatment": {"n": 10000, "success": 1150}})
    assert r["analysis_type"] == "ab_rate"
    assert "ok" not in r
    assert r["absolute_lift"] == round(0.115 - 0.10, 6)
    assert isinstance(r["significant"], bool)


def test_did_basic():
    r = evaluate({"analysis_type": "did",
                  "treatment_before": 100, "treatment_after": 130,
                  "control_before": 100, "control_after": 110})
    assert r["did_effect"] == 10
    assert "ok" not in r


def test_roi_with_margin():
    r = evaluate({"analysis_type": "roi", "benefit": 200, "cost": 100,
                  "gross_margin_rate": 0.5})
    assert r["roi"] == 1.0
    assert r["margin_adjusted_roi"] == 0.0


def test_unknown_analysis_type_raises():
    with pytest.raises(ValidationError):
        evaluate({"analysis_type": "bogus"})


def test_non_numeric_alpha_now_raises_validation_error():
    # 原 float("abc") 抛裸 ValueError；内核已包成 ValidationError。
    with pytest.raises(ValidationError):
        evaluate({"analysis_type": "ab_rate", "alpha": "abc",
                  "control": {"n": 10, "success": 1},
                  "treatment": {"n": 10, "success": 2}})
