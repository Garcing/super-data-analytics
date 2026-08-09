"""新内核 vs 原 CLI 行为一致性对照（安全网）。

原 CLI 未被改动、仍在原位；本测试证明剥离后的内核输出与原 CLI 一致（仅少了 ok 键）。
"""
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sda_mcp.skills.diagnosing import contribute
from sda_mcp.skills.predicting import forecast
from sda_mcp.skills.evaluating import evaluate

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent.parent  # 仓库根


def _run_cli(script_rel: str, args: list[str], input_path: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REPO / script_rel), *args, str(input_path)],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"原 CLI 失败: {proc.stderr}"
    return json.loads(proc.stdout)


def _strip_ok(d: dict) -> dict:
    d.pop("ok", None)
    return d


def _to_plain(obj):
    """把 dataclass/嵌套 dataclass 转成纯 dict，便于与 CLI 的 JSON 比对。"""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_plain(x) for x in obj]
    return obj


def test_diagnosing_add_parity():
    fix = FIX / "diagnosing_add.json"
    cli = _strip_ok(_run_cli("diagnosing-anomalies/scripts/contribution.py", ["add"], fix))
    core = _to_plain(contribute("add", json.loads(fix.read_text(encoding="utf-8"))))
    assert core == cli


def test_diagnosing_multiply_parity():
    fix = FIX / "diagnosing_multiply.json"
    cli = _strip_ok(_run_cli("diagnosing-anomalies/scripts/contribution.py", ["multiply"], fix))
    core = _to_plain(contribute("multiply", json.loads(fix.read_text(encoding="utf-8"))))
    assert core == cli


def test_forecast_parity():
    fix = FIX / "forecast_linear.json"
    cli = _strip_ok(_run_cli("predicting-trends/scripts/forecast.py", [], fix))
    core = _to_plain(forecast(json.loads(fix.read_text(encoding="utf-8"))))
    # 原 CLI 在无 target 时省略 summary.target_gap；内核 dataclass 恒带 None。
    # 此 fixture 无 target，对齐：core 侧删掉 None 的 target_gap。
    if core["summary"].get("target_gap") is None:
        core["summary"].pop("target_gap", None)
    assert core == cli


def test_impact_did_parity():
    fix = FIX / "impact_did.json"
    cli = _strip_ok(_run_cli("evaluating-impact/scripts/impact.py", [], fix))
    core = evaluate(json.loads(fix.read_text(encoding="utf-8")))
    assert core == cli
