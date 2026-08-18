"""visualizing 内核契约测试。"""
import json
from pathlib import Path

import pytest

from sda_mcp.errors import ValidationError
from sda_mcp.skills.visualizing import render, ChartResult

FIX = Path(__file__).parent / "fixtures"


def test_render_bar_png():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    r = render(spec, format="png")
    assert isinstance(r, ChartResult)
    assert r.format == "png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"   # PNG 魔数
    assert len(r.data) > 1000
    assert not hasattr(r, "ok")


def test_render_svg():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    r = render(spec, format="svg")
    assert r.format == "svg"
    assert r.data.lstrip().startswith(b"<")


def test_bad_format_rejected():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        render(spec, format="gif")


def test_bad_spec_rejected():
    with pytest.raises(ValidationError):
        render({"type": "bar", "title": "x"})  # 缺 subtitle/data/encoding
