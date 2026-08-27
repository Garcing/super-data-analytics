"""P2 回归:sample_size_rate 必须披露 MDE 语义并回显推导用处理组率。

QA 实测(2026-08-26):MDE 实为绝对百分点差(p1=p0+MDE),但工具描述/返回/Skill
均未说明也不回显 p1——按相对提升理解样本量差约 93 倍(3841 vs ~356,338/臂)。
"""
from sda_mcp.skills.evaluating import evaluate


def test_sample_size_echoes_assumed_treatment_rate():
    r = evaluate({"analysis_type": "sample_size_rate",
                 "baseline_rate": 0.10, "minimum_detectable_effect": 0.02})
    assert r["sample_size_per_group"] == 3841     # QA 手算基线
    assert r["assumed_treatment_rate"] == 0.12     # 回显 p1
    assert any("绝对" in w for w in r["warnings"])  # 语义披露进 warnings
