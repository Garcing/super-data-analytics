"""P1-c 回归:heatmap 默认数值标注不得出现科学计数法。

QA 实测(2026-08-26):默认 value_format=".2g" 把 120/150/110 渲染成
1.2e+02/1.5e+02/1.1e+02,业务热力图不可读。修复:未显式传 value_format 时用
智能默认(整数带千分位、小数两位);显式传入仍走原样格式串。
"""
from sda_mcp.skills.visualizing import render

_SPEC = {
    "type": "heatmap", "title": "时段×星期活跃度", "subtitle": "QA",
    "data": [
        {"hour": "早", "dow": "周一", "value": 120},
        {"hour": "晚", "dow": "周一", "value": 150},
        {"hour": "早", "dow": "周二", "value": 0.5},
        {"hour": "晚", "dow": "周二", "value": 160},
    ],
    "encoding": {"x": "hour", "y": "dow", "value": "value"},
}


def _capture_heatmap(monkeypatch):
    import sda_mcp.skills.visualizing.renderers.heatmap as hm
    captured = {}

    def fake(matrix, ax=None, **kw):
        captured["matrix"] = matrix
        captured.update(kw)
        return None

    monkeypatch.setattr(hm.sns, "heatmap", fake)
    return captured


def test_default_annotation_avoids_scientific_notation(monkeypatch):
    captured = _capture_heatmap(monkeypatch)
    render(dict(_SPEC), format="png")
    annot = captured["annot"]
    texts = [str(v) for v in annot.to_numpy().ravel()]
    assert "120" in texts and "150" in texts
    assert any(t == "0.50" for t in texts)
    assert not any("e+" in t or "e-" in t for t in texts), texts


def test_custom_value_format_passthrough(monkeypatch):
    captured = _capture_heatmap(monkeypatch)
    spec = dict(_SPEC)
    spec["options"] = {"value_format": ".1f"}
    render(spec, format="png")
    assert captured["fmt"] == ".1f"
    assert captured["annot"] is True          # 显式格式时 annot 保持矩阵布尔语义


def test_real_render_with_smart_default():
    """真实渲染一次确保 fmt=''+字符串矩阵对 seaborn 合法(不 mock)。"""
    r = render(dict(_SPEC), format="png")
    assert r.format == "png" and len(r.data) > 1000
