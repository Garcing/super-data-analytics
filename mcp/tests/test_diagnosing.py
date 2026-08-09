"""diagnosing 内核契约测试 + bugfix 回归。"""
import pytest
from sda_mcp.errors import ValidationError
from sda_mcp.skills.diagnosing import contribute, ContributionResult


def test_add_basic():
    r = contribute("add", {
        "baseline_total": 100, "current_total": 120,
        "items": [{"name": "A", "baseline": 60, "current": 80},
                  {"name": "B", "baseline": 40, "current": 40}],
    })
    assert isinstance(r, ContributionResult)
    assert r.method == "add"
    assert r.summary.delta == 20
    assert r.summary.relative_change == 0.2
    assert r.checks.residual == 0  # 分项加总等于总体
    assert not hasattr(r, "ok")    # 去信封：无 ok 字段
    assert r.rows[0]["contribution_value"] == 20


def test_multiply_requires_positive():
    with pytest.raises(ValidationError):
        contribute("multiply", {"factors": [{"name": "x", "baseline": 0, "current": 2}]})


def test_unknown_method_raises():
    with pytest.raises(ValidationError):
        contribute("bogus", {})


def test_require_number_rejects_bool_bugfix():
    # 原 contribution.py 的 require_number 会把 True 当成 1.0 放行；内核已修。
    with pytest.raises(ValidationError):
        contribute("add", {"baseline_total": 0, "current_total": 1,
                           "items": [{"name": "A", "baseline": True, "current": 1}]})
