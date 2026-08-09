"""visualizing 内核契约测试 + 与原 CLI 像素级对照。"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from sda_mcp.errors import ValidationError
from sda_mcp.skills.visualizing import render, ChartResult

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent.parent


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


def test_parity_vs_original_cli(tmp_path):
    """原 CLI 写文件、新内核出字节；解码后像素应完全一致。"""
    spec_path = FIX / "chart_bar.json"
    out = tmp_path / "orig.png"
    proc = subprocess.run(
        [sys.executable, str(REPO / "visualizing-data/scripts/chart.py"),
         "--data", f"@{spec_path}", "--output", str(out)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    orig = Image.open(out).convert("RGB")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    core = render(spec, format="png")
    new = Image.open(io.BytesIO(core.data)).convert("RGB")

    assert orig.size == new.size
    assert ImageChops.difference(orig, new).getbbox() is None  # 像素完全一致
