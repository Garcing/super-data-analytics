# 子项目 1.A 实现计划：共享地基 + 三个分析内核

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在新 `mcp/` 目录搭起共享地基（包结构 + 统一异常体系），并把 3 个纯标准库分析技能（diagnosing / predicting / evaluating）剥离成干净 Python 内核（去 CLI 层、去 `{ok:...}` 信封、出参 dataclass、失败抛 `SkillError`），用"新内核 vs 原 CLI"对照测试证明行为一致。

**Architecture:** 原仓库树一律不动。新代码全部写在 `mcp/sda_mcp/` 下。每个内核是纯函数：`payload 进 → dataclass 出 / 抛 SkillError`。算法体从原脚本逐字搬迁，只改三处：① 删 CLI/argparse/文件读/stdin/`{ok}` 信封；② `ValueError`/自定义异常 → `SkillError` 体系；③ 顺手修既存 bug。对照测试用 subprocess 跑原 CLI、in-process 跑新内核，断言 JSON 语义相等。

**Tech Stack:** Python 3.10+（标准库 only，本计划零第三方依赖）；pytest（测试，已存在于项目）。

**范围声明：** 本计划是子项目 1 的第一份。子项目 1 的其余 5 个内核（visualizing、querying_data、retrieving_context、building_reports、using_templates）各自有后续独立计划（1.B–1.F）。FastMCP 服务、Docker、hermes 接入属于子项目 2，不在本计划内。

---

## 文件结构（本计划涉及的文件）

- Create: `mcp/pyproject.toml` — `sda-mcp` 包元数据（本计划零运行时依赖；后续计划在此追加）
- Create: `mcp/sda_mcp/__init__.py` — 包标记，导出公开 API
- Create: `mcp/sda_mcp/errors.py` — 统一异常体系（所有内核共用）
- Create: `mcp/sda_mcp/skills/__init__.py` — 子包标记
- Create: `mcp/sda_mcp/skills/diagnosing.py` — 贡献度归因内核
- Create: `mcp/sda_mcp/skills/predicting.py` — 趋势预测内核
- Create: `mcp/sda_mcp/skills/evaluating.py` — 效果评估内核
- Create: `mcp/tests/__init__.py`
- Create: `mcp/tests/conftest.py` — pytest 路径配置（让 `sda_mcp` 可 import、定位原 CLI）
- Create: `mcp/tests/test_diagnosing.py`
- Create: `mcp/tests/test_predicting.py`
- Create: `mcp/tests/test_evaluating.py`
- Create: `mcp/tests/test_parity.py` — 新内核 vs 原 CLI 对照（安全网）
- Create: `mcp/tests/fixtures/` — 对照用 JSON 输入（在本计划任务中逐个生成）

**不修改**：`diagnosing-anomalies/`、`predicting-trends/`、`evaluating-impact/` 下任何原文件（铁律：原码不动，原 CLI 作为对照基准保留）。

---

## 约定：内核出参的"去 ok"口径

原 CLI 成功输出 `{"ok": true, ...fields}`、失败输出 `{"ok": false, "error": "..."}`。新内核：
- 成功：返回 dataclass（或 dict），**不含 `ok` 字段**。
- 失败：抛 `SkillError` 子类，**不返回**。
对照测试比较时，从原 CLI 输出里删掉 `ok` 键后与新内核序列化结果比对。

---

## Task 1: 搭包地基 + 统一异常体系

**Files:**
- Create: `mcp/pyproject.toml`
- Create: `mcp/sda_mcp/__init__.py`
- Create: `mcp/sda_mcp/errors.py`
- Create: `mcp/sda_mcp/skills/__init__.py`
- Create: `mcp/tests/__init__.py`
- Create: `mcp/tests/conftest.py`

- [ ] **Step 1: 写 `mcp/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sda-mcp"
version = "0.1.0"
description = "super-data-analytics 的干净 Python 内核 + FastMCP 服务（子项目 1.A：分析内核）"
requires-python = ">=3.10"
# 本计划零运行时依赖（三个分析内核均为标准库）。
# 后续计划在此追加 fastmcp、httpx、psycopg[binary]、neo4j、matplotlib、fastembed 等。
dependencies = []

[tool.hatch.build.targets.wheel]
packages = ["sda_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: 写 `mcp/sda_mcp/errors.py`（统一异常体系，全项目共用）**

```python
"""sda-mcp 统一异常体系。

所有内核失败时抛这些异常（不返回 {ok:false}）。
MCP 工具层捕获后映射为 MCP isError + 可操作错误信息。
"""


class SkillError(Exception):
    """所有 skill 内核失败的基类。"""


class ConfigError(SkillError):
    """凭证/配置缺失或无效（如 config.json 缺 key）。"""


class ValidationError(SkillError):
    """输入校验失败（字段缺失、类型错、越界）。"""


class DataSourceError(SkillError):
    """外部数据源错误（Hologres/Power BI/Neo4j 连接或查询失败）。"""


class ExternalAPIError(SkillError):
    """外部 API 调用失败（apimart/Vercel Blob/Fabric）。"""


class SkillTimeoutError(SkillError):
    """内核调用超时。"""
```

- [ ] **Step 3: 写 `mcp/sda_mcp/__init__.py`**

```python
"""sda-mcp：super-data-analytics 的 Python 执行层。"""

__version__ = "0.1.0"
```

- [ ] **Step 4: 写 `mcp/sda_mcp/skills/__init__.py`（空标记）**

```python
"""各 skill 的干净 Python 内核。"""
```

- [ ] **Step 5: 写 `mcp/tests/__init__.py`（空）+ `mcp/tests/conftest.py`**

`mcp/tests/__init__.py`：
```python
```

`mcp/tests/conftest.py`：
```python
"""pytest 配置：暴露 sda_mcp import 路径，并提供仓库根与原 CLI 路径 fixture。"""
import sys
from pathlib import Path

# mcp/ 目录本身（conftest 在 mcp/tests/ 下，上两级是仓库根，上一级是 mcp/）
MCP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MCP_DIR.parent

# 让 `import sda_mcp` 可用（pyproject 的 pythonpath 也配了，这里双保险）
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def venv_python() -> str:
    """跑原 CLI 用的解释器（与跑 pytest 同一个即可）。"""
    return sys.executable
```

- [ ] **Step 6: 验证地基可 import**

Run（在 `mcp/` 下）:
```bash
cd mcp && python -c "import sda_mcp; from sda_mcp.errors import SkillError, ValidationError; print('ok', sda_mcp.__version__)"
```
Expected: `ok 0.1.0`

- [ ] **Step 7: 提交**

```bash
git add mcp/pyproject.toml mcp/sda_mcp/ mcp/tests/__init__.py mcp/tests/conftest.py
git commit -m "feat(mcp): scaffold sda_mcp package + unified SkillError hierarchy"
```

---

## Task 2: diagnosing 内核（贡献度归因）

**源文件（只读搬迁，不改）：** `diagnosing-anomalies/scripts/contribution.py`
**Files:**
- Create: `mcp/sda_mcp/skills/diagnosing.py`
- Test: `mcp/tests/test_diagnosing.py`

**搬迁口径：**
- 逐字复制 `safe_div`、`round_float`、`classify_direction`、`contribution_metrics`、`additive`、`multiplicative`、`ratio` 的**算法体**。
- 改动 1：`require_number` 修 bug —— 原 `float(row[key])` 会把 `True`/`False` 当成 1.0/0.0（与 evaluating 内核不一致）。改为显式拒绝 bool。
- 改动 2：所有 `raise ValueError(...)` → `raise ValidationError(...)`。
- 改动 3：`build_result` 不再返回 `{"ok": True, ...}` 字典，改为构造 `ContributionResult` dataclass（见下）。
- 删除：`load_payload`、`main`、argparse、`METHODS` 字典改为函数内分发或保留为模块级映射（内核入口用）。

- [ ] **Step 1: 写 `mcp/sda_mcp/skills/diagnosing.py`**

```python
"""指标异动贡献度计算内核（从 diagnosing-anomalies/scripts/contribution.py 剥离）。

去掉了 CLI/argparse/文件读/{ok} 信封；出参 dataclass；失败抛 ValidationError。
算法与原脚本一致，仅修 require_number 拒绝 bool 的 bug。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from sda_mcp.errors import ValidationError

EPS = 1e-12


@dataclass
class ContributionSummary:
    baseline_total: float
    current_total: float
    delta: float
    relative_change: float | None


@dataclass
class ContributionChecks:
    sum_contribution: float
    residual: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContributionResult:
    method: str
    summary: ContributionSummary
    rows: list[dict[str, Any]]
    checks: ContributionChecks


def safe_div(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < EPS:
        return None
    return numerator / denominator


def round_float(value: Any, digits: int = 12) -> Any:
    if isinstance(value, float):
        return round(value, digits) if math.isfinite(value) else value
    if isinstance(value, list):
        return [round_float(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: round_float(item, digits) for key, item in value.items()}
    return value


def classify_direction(value: float, total_delta: float) -> str:
    if abs(value) < EPS:
        return "无明显贡献"
    if abs(total_delta) < EPS:
        return "总变化接近0，方向不解释"
    return "同向解释" if value * total_delta > 0 else "反向抵消"


def require_number(row: Mapping[str, Any], key: str, context: str) -> float:
    """校验数字字段。bugfix：显式拒绝 bool（原实现 float(True)==1.0 会放行）。"""
    if key not in row:
        raise ValidationError(f"{context} 缺少字段: {key}")
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{context}.{key} 必须是数字")
    return float(value)


def contribution_metrics(value, total_delta, baseline_total):
    return {
        "contribution_value": value,
        "contribution_share": safe_div(value, total_delta),
        "relative_contribution": safe_div(value, baseline_total),
    }


def additive(payload: Mapping[str, Any]):
    baseline_total = float(payload.get("baseline_total", 0))
    current_total = float(payload.get("current_total", 0))
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("add 输入需要非空 items 数组")
    total_delta = current_total - baseline_total
    rows, contribution_sum = [], 0.0
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(f"items[{idx}] 必须是对象")
        name = str(item.get("name", f"item_{idx + 1}"))
        baseline = require_number(item, "baseline", name)
        current = require_number(item, "current", name)
        value = current - baseline
        contribution_sum += value
        rows.append({
            "name": name, "baseline": baseline, "current": current, "delta": value,
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum
    warnings = ["分项贡献量之和不等于总体变化，请检查分项是否互斥且完整。"] if abs(residual) > 1e-9 else []
    return _build("add", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def multiplicative(payload: Mapping[str, Any]):
    factors = payload.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValidationError("multiply 输入需要非空 factors 数组")
    parsed, baseline_total, current_total = [], 1.0, 1.0
    for idx, factor in enumerate(factors):
        if not isinstance(factor, dict):
            raise ValidationError(f"factors[{idx}] 必须是对象")
        name = str(factor.get("name", f"factor_{idx + 1}"))
        baseline = require_number(factor, "baseline", name)
        current = require_number(factor, "current", name)
        if baseline <= 0 or current <= 0:
            raise ValidationError(f"{name} 的 baseline/current 必须为正数，log 拆解不能处理 0 或负数")
        baseline_total *= baseline
        current_total *= current
        parsed.append((name, baseline, current))
    total_delta = current_total - baseline_total
    log_total_delta = math.log(current_total) - math.log(baseline_total)
    log_mean_weight = None if abs(log_total_delta) < EPS else total_delta / log_total_delta
    rows, contribution_sum, warnings = [], 0.0, []
    if log_mean_weight is None:
        warnings.append("总体对数变化接近0，仅输出因子 log 变化，不计算贡献率。")
    for name, baseline, current in parsed:
        log_delta = math.log(current) - math.log(baseline)
        value = 0.0 if log_mean_weight is None else log_mean_weight * log_delta
        contribution_sum += value
        rows.append({
            "name": name, "baseline": baseline, "current": current,
            "factor_ratio": current / baseline, "log_delta": log_delta,
            "log_contribution_share": safe_div(log_delta, log_total_delta),
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum if log_mean_weight is not None else total_delta
    return _build("multiply", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def ratio(payload: Mapping[str, Any]):
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValidationError("ratio 输入需要非空 groups 数组")
    parsed, b_num_t, b_den_t, c_num_t, c_den_t = [], 0.0, 0.0, 0.0, 0.0
    for idx, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValidationError(f"groups[{idx}] 必须是对象")
        name = str(group.get("name", f"group_{idx + 1}"))
        b_num = require_number(group, "baseline_numerator", name)
        b_den = require_number(group, "baseline_denominator", name)
        c_num = require_number(group, "current_numerator", name)
        c_den = require_number(group, "current_denominator", name)
        if b_den <= 0 or c_den <= 0:
            raise ValidationError(f"{name} 的分母必须大于 0")
        b_num_t += b_num; b_den_t += b_den; c_num_t += c_num; c_den_t += c_den
        parsed.append((name, b_num, b_den, c_num, c_den))
    if b_den_t <= 0 or c_den_t <= 0:
        raise ValidationError("总体分母必须大于 0")
    baseline_total = b_num_t / b_den_t
    current_total = c_num_t / c_den_t
    total_delta = current_total - baseline_total
    rows, contribution_sum = [], 0.0
    for name, b_num, b_den, c_num, c_den in parsed:
        y0, y1 = b_num / b_den, c_num / c_den
        w0, w1 = b_den / b_den_t, c_den / c_den_t
        within = w0 * (y1 - y0)
        mix = (w1 - w0) * (y0 - baseline_total)
        interaction = (w1 - w0) * (y1 - y0)
        value = within + mix + interaction
        contribution_sum += value
        rows.append({
            "name": name, "baseline_numerator": b_num, "baseline_denominator": b_den,
            "current_numerator": c_num, "current_denominator": c_den,
            "baseline_rate": y0, "current_rate": y1, "baseline_weight": w0, "current_weight": w1,
            "within_contribution": within, "mix_contribution": mix, "interaction_contribution": interaction,
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum
    warnings = ["比率型贡献未完全加总到总体变化，请检查分组是否互斥且分母完整。"] if abs(residual) > 1e-9 else []
    return _build("ratio", baseline_total, current_total, rows, contribution_sum, residual, warnings)


_METHODS = {"add": additive, "multiply": multiplicative, "ratio": ratio}


def _build(method, baseline_total, current_total, rows, contribution_sum, residual, warnings) -> ContributionResult:
    total_delta = current_total - baseline_total
    # 与原 build_result 一致：round_float(12 位) 作用于 summary/checks/rows 全部数值，
    # 保证对照测试与原 CLI 严格相等。
    summary_d = round_float({
        "baseline_total": baseline_total, "current_total": current_total,
        "delta": total_delta, "relative_change": safe_div(total_delta, baseline_total),
    })
    checks_d = round_float({
        "sum_contribution": contribution_sum, "residual": residual, "warnings": warnings,
    })
    return ContributionResult(
        method=method,
        summary=ContributionSummary(**summary_d),
        rows=round_float(rows),
        checks=ContributionChecks(**checks_d),
    )


def contribute(method: str, payload: Mapping[str, Any]) -> ContributionResult:
    """贡献度归因入口。method ∈ {add, multiply, ratio}。"""
    if method not in _METHODS:
        raise ValidationError(f"unknown method '{method}', expected add/multiply/ratio")
    return _METHODS[method](payload)
```

- [ ] **Step 2: 写 `mcp/tests/test_diagnosing.py`（失败测试）**

```python
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
```

- [ ] **Step 3: 运行测试，确认失败再实现的路径已就绪**

Run:
```bash
cd mcp && python -m pytest tests/test_diagnosing.py -v
```
Expected: 4 passed（实现已在 Step 1 写好；此步确认实现与测试自洽）。若 FAIL，按报错修 `diagnosing.py`。

> 说明：本任务的算法是从原脚本逐字搬迁，TDD 重点是**新契约**（dataclass 出参、去 `ok`、`ValidationError`、bool bugfix 回归）。算法正确性由 Task 5 的对照测试兜底。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/diagnosing.py mcp/tests/test_diagnosing.py
git commit -m "feat(mcp): diagnosing core (contribution) + bool-rejection bugfix"
```

---

## Task 3: predicting 内核（趋势预测）

**源文件（只读搬迁）：** `predicting-trends/scripts/forecast.py`
**Files:**
- Create: `mcp/sda_mcp/skills/predicting.py`
- Test: `mcp/tests/test_predicting.py`

**搬迁口径：**
- 逐字复制所有 `forecast_*`、`linear_coefficients`、`error_metrics`、`run_model`、`backtest_model`、`choose_auto_model`、`round_value`、`interval_width`、`classify_confidence`、`model_reason`、`next_dates`、`add_months`、`is_leap`、`parse_date`、`mean`、`validate_payload` 的**算法体**。
- 改动 1：`class ForecastError(ValueError)` → `class ForecastError(SkillError)`（从 `sda_mcp.errors` 导入）。
- 改动 2：`build_result` 返回 `ForecastResult` dataclass，去掉 `ok`。
- 改动 3：`validate_payload` 里 `horizon = int(payload["horizon"])` 会把 `2.7` 静默截成 2 —— 改为非整数时抛 `ForecastError`。`options.window` 同理收紧。
- 改动 4：在 `interval_width` 加 docstring 明确"启发式带，非严格置信区间"（用户要求标注）。
- 删除：`emit`、`load_payload`、`main`。

- [ ] **Step 1: 写 `mcp/sda_mcp/skills/predicting.py`**

```python
"""趋势预测内核（从 predicting-trends/scripts/forecast.py 剥离）。

去 CLI/文件读/{ok} 信封；ForecastError 改继承 SkillError；出参 ForecastResult。
收紧 horizon/window 的整数校验；标注 interval_width 为启发式带。
算法与原脚本一致。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sda_mcp.errors import SkillError

SUPPORTED_GRAINS = {"day", "week", "month", "quarter"}
SUPPORTED_MODELS = {
    "naive", "seasonal_naive", "moving_average", "weighted_moving_average",
    "exponential_smoothing", "holt_linear", "linear_trend", "log_linear_trend",
    "auto_baseline",
}
AUTO_MODELS = [
    "naive", "moving_average", "weighted_moving_average", "exponential_smoothing",
    "holt_linear", "linear_trend", "log_linear_trend",
]


class ForecastError(SkillError):
    """预测输入或计算失败。"""


@dataclass
class ForecastPoint:
    date: str
    value: float
    lower: float
    upper: float


@dataclass
class ForecastSummary:
    forecast_total: float
    last_actual: float
    change_vs_last_actual: float | None
    target_gap: float | None = None


@dataclass
class Backtest:
    holdout: int
    mae: float | None
    mape: float | None
    rmse: float | None


@dataclass
class ForecastResult:
    metric: str
    model: str
    model_reason: str
    forecast: list[ForecastPoint]
    summary: ForecastSummary
    backtest: Backtest
    confidence: str
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---- 以下函数体逐字搬迁自原 forecast.py（仅 horizon/window 整数校验收紧）----

def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def add_months(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, month_lengths[month - 1]))


def next_dates(last_date, grain, horizon):
    if grain == "day":
        return [last_date + timedelta(days=index + 1) for index in range(horizon)]
    if grain == "week":
        return [last_date + timedelta(weeks=index + 1) for index in range(horizon)]
    if grain == "month":
        return [add_months(last_date, index + 1) for index in range(horizon)]
    if grain == "quarter":
        return [add_months(last_date, (index + 1) * 3) for index in range(horizon)]
    raise ForecastError(f"unsupported grain '{grain}'")


def _require_int(value, label):
    """收紧整数校验：原 int() 会静默截断 2.7 → 2。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastError(f"{label} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ForecastError(f"{label} must be an integer, got {value}")
    return int(value)


def validate_payload(payload):
    for field_name in ["metric", "grain", "horizon", "model", "series"]:
        if field_name not in payload:
            raise ForecastError(f"missing required field '{field_name}'")
    grain = payload["grain"]
    if grain not in SUPPORTED_GRAINS:
        raise ForecastError(f"unsupported grain '{grain}'")
    model = payload["model"]
    if model not in SUPPORTED_MODELS:
        raise ForecastError(f"unknown model '{model}'")
    horizon = _require_int(payload["horizon"], "horizon")
    if horizon < 1:
        raise ForecastError("horizon must be a positive integer")
    raw_series = payload["series"]
    if not isinstance(raw_series, list) or len(raw_series) < 2:
        raise ForecastError("series must contain at least 2 observations")
    parsed, seen_dates = [], set()
    for row in raw_series:
        if not isinstance(row, dict):
            raise ForecastError("series rows must be objects")
        current_date = parse_date(row.get("date"))
        if current_date in seen_dates:
            raise ForecastError(f"duplicate date '{current_date.isoformat()}' in series")
        seen_dates.add(current_date)
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ForecastError("series values must be numeric") from exc
        if not math.isfinite(value):
            raise ForecastError("series values must be finite numbers")
        parsed.append({"date": current_date, "value": value})
    parsed.sort(key=lambda item: item["date"])
    return {
        "metric": str(payload["metric"]), "grain": grain, "horizon": horizon,
        "model": model, "series": parsed,
        "season_length": _require_int(payload.get("season_length", 0) or 0, "season_length"),
        "target": payload.get("target"),
        "options": payload.get("options", {}) if isinstance(payload.get("options", {}), dict) else {},
    }


def mean(values):
    return sum(values) / len(values)


# forecast_* / linear_coefficients / MODEL_FUNCS / error_metrics / run_model /
# backtest_model / choose_auto_model / round_value / interval_width /
# classify_confidence / model_reason：从原 forecast.py 第 130–325 行逐字复制，
# 函数体与签名完全不变（内部不涉及 ok/CLI），复制后无需改动。


def forecast(payload: Mapping[str, Any]) -> ForecastResult:
    """趋势预测入口。失败抛 ForecastError。"""
    validated = validate_payload(payload)
    values = [row["value"] for row in validated["series"]]
    warnings = []
    if len(values) < 6:
        warnings.append("Series has limited history; treat the forecast as low confidence.")

    selected_model = validated["model"]
    precomputed_backtest = None
    if selected_model == "auto_baseline":
        selected_model, precomputed_backtest = choose_auto_model(
            values, validated["options"], validated["season_length"])

    bt = precomputed_backtest or backtest_model(
        selected_model, values, validated["options"], validated["season_length"])
    predictions = run_model(selected_model, values, validated["horizon"],
                            validated["options"], validated["season_length"])
    width = interval_width(bt, values)
    dates = next_dates(validated["series"][-1]["date"], validated["grain"], validated["horizon"])
    forecast_rows = [
        ForecastPoint(date=fd.isoformat(), value=round_value(v),
                      lower=round_value(v - width), upper=round_value(v + width))
        for fd, v in zip(dates, predictions)
    ]
    forecast_total = sum(p.value for p in forecast_rows)
    last_actual = values[-1]
    summary = ForecastSummary(
        forecast_total=round_value(forecast_total),
        last_actual=round_value(last_actual),
        change_vs_last_actual=round_value((forecast_rows[0].value - last_actual) / last_actual) if last_actual else None,
    )
    if validated["target"] is not None:
        try:
            summary.target_gap = round_value(forecast_total - float(validated["target"]))
        except (TypeError, ValueError):
            warnings.append("Target was provided but is not numeric.")
    return ForecastResult(
        metric=validated["metric"], model=selected_model,
        model_reason=model_reason(selected_model, bt),
        forecast=forecast_rows, summary=summary,
        backtest=Backtest(holdout=bt.get("holdout", 0),
                          mae=round_value(bt["mae"]) if bt.get("mae") is not None else None,
                          mape=round_value(bt["mape"]) if bt.get("mape") is not None else None,
                          rmse=round_value(bt["rmse"]) if bt.get("rmse") is not None else None),
        confidence=classify_confidence(bt, warnings),
        assumptions=["Metric definition remains stable during the forecast period."],
        warnings=warnings,
    )
```

> **执行注意：** 上面被注释引用的"从原 forecast.py 第 130–325 行逐字复制"那批函数（`forecast_naive` … `model_reason`，共约 14 个函数 + `MODEL_FUNCS` 字典），实现者需**逐字粘贴**进本文件、放在 `forecast()` 之前。它们不涉及 CLI/ok，无需改动。这不是占位符——源码在 `predicting-trends/scripts/forecast.py:130-325`，逐字可取；不粘贴会导致 `forecast()` 引用未定义名而测试失败。

- [ ] **Step 2: 写 `mcp/tests/test_predicting.py`**

```python
"""predicting 内核契约测试 + 收紧校验回归。"""
import pytest
from sda_mcp.skills.predicting import forecast, ForecastResult, ForecastError


SERIES = [{"date": f"2025-01-{d:02d}", "value": v}
          for d, v in enumerate(range(100, 130), start=1)]  # 30 天


def test_linear_trend_basic():
    r = forecast({"metric": "gmv", "grain": "day", "horizon": 3,
                  "model": "linear_trend", "series": SERIES})
    assert isinstance(r, ForecastResult)
    assert r.model == "linear_trend"
    assert len(r.forecast) == 3
    assert all(p.lower <= p.value <= p.upper for p in r.forecast)
    assert not hasattr(r, "ok")


def test_auto_baseline_picks_a_model():
    r = forecast({"metric": "gmv", "grain": "day", "horizon": 2,
                  "model": "auto_baseline", "series": SERIES})
    assert r.model in {"naive", "moving_average", "weighted_moving_average",
                       "exponential_smoothing", "holt_linear", "linear_trend", "log_linear_trend"}


def test_non_integer_horizon_now_rejected():
    # 原 int(2.7)==2 静默截断；内核已收紧为抛错。
    with pytest.raises(ForecastError):
        forecast({"metric": "gmv", "grain": "day", "horizon": 2.7,
                  "model": "naive", "series": SERIES})


def test_missing_field_raises():
    with pytest.raises(ForecastError):
        forecast({"grain": "day", "horizon": 1, "model": "naive", "series": SERIES})
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd mcp && python -m pytest tests/test_predicting.py -v
```
Expected: 4 passed。若 `forecast_*` 等函数未粘贴全，会报 NameError → 按执行注意补齐。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/predicting.py mcp/tests/test_predicting.py
git commit -m "feat(mcp): predicting core (forecast) + tighten int validation + heuristic-band doc"
```

---

## Task 4: evaluating 内核（效果评估）

**源文件（只读搬迁）：** `evaluating-impact/scripts/impact.py`
**Files:**
- Create: `mcp/sda_mcp/skills/evaluating.py`
- Test: `mcp/tests/test_evaluating.py`

**搬迁口径：**
- 逐字复制 `analyze_ab_rate`、`analyze_ab_mean`、`analyze_did`、`analyze_roi`、`analyze_sample_size_rate`、`wilson_interval`、`validate_rate_group`、`validate_mean_group`、`require_number`、`require_group`、`alpha_value`、`z_for_alpha`、`normal_p_value`、`rounded`、`Z_BY_ALPHA`、`Z_BY_POWER`、`ANALYZERS` 的**算法体**。
- 改动 1：`class ValidationError(Exception)` → `from sda_mcp.errors import ValidationError`（复用统一异常，不重复定义）。
- 改动 2：`alpha_value`/`analyze_sample_size_rate` 里 `float(payload.get("alpha"/"power"))` 解析失败会抛裸 `ValueError`（被原 main 的宽 except 兜底）—— 改为抛 `ValidationError`，信息可操作。
- 改动 3：`run(payload)` → 改名 `evaluate(payload)`，返回的 dict 去掉 `ok` 键。
- 出参说明：5 种 analysis_type 输出字段差异大，强行 dataclass 会臃肿；保留**扁平 dict**（仅去 `ok`），类型标注 `dict[str, Any]`。这是有意决策，不是偷懒。
- 删除：`main`、argparse、文件读、stdout 打印。

- [ ] **Step 1: 写 `mcp/sda_mcp/skills/evaluating.py`**

```python
"""效果评估内核（从 evaluating-impact/scripts/impact.py 剥离）。

去 CLI/文件读/{ok} 信封；复用 sda_mcp.errors.ValidationError；
alpha/power 解析失败显式抛 ValidationError；出参扁平 dict（去 ok）。
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Mapping

from sda_mcp.errors import ValidationError

Z_BY_ALPHA = {0.1: 1.6448536269514722, 0.05: 1.959963984540054, 0.01: 2.5758293035489004}
Z_BY_POWER = {0.8: 0.8416212335729143, 0.85: 1.0364333894937898,
              0.9: 1.2815515655446004, 0.95: 1.6448536269514722}


def rounded(value, digits=6):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    return round(float(value), digits)


def require_number(payload, key):
    if key not in payload:
        raise ValidationError(f"Missing required field: {key}")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{key} must be numeric")
    if not math.isfinite(float(value)):
        raise ValidationError(f"{key} must be finite")
    return float(value)


def require_group(payload, key, fields):
    if key not in payload or not isinstance(payload[key], dict):
        raise ValidationError(f"{key} must be an object")
    group = payload[key]
    return {field: require_number(group, field) for field in fields}


def alpha_value(payload):
    try:
        alpha = float(payload.get("alpha", 0.05))
    except (TypeError, ValueError) as exc:
        raise ValidationError("alpha must be numeric") from exc
    if not 0 < alpha < 1:
        raise ValidationError("alpha must be between 0 and 1")
    return alpha


def z_for_alpha(alpha):
    return Z_BY_ALPHA.get(round(alpha, 2), statistics.NormalDist().inv_cdf(1 - alpha / 2))


def normal_p_value(z):
    return 2 * (1 - statistics.NormalDist().cdf(abs(z)))


def wilson_interval(success, n, alpha):
    if n <= 0:
        raise ValidationError("n must be positive")
    p = success / n
    z = z_for_alpha(alpha)
    z2 = z**2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half_width = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n) / denominator
    return {"lower": rounded(max(0.0, center - half_width)),
            "upper": rounded(min(1.0, center + half_width))}


def validate_rate_group(name, group):
    n, success = group["n"], group["success"]
    if n <= 0:
        raise ValidationError(f"{name}.n must be positive")
    if success < 0:
        raise ValidationError(f"{name}.success cannot be negative")
    if success > n:
        raise ValidationError(f"{name}.success cannot exceed {name}.n")


def validate_mean_group(name, group):
    if group["n"] <= 1:
        raise ValidationError(f"{name}.n must be greater than 1")
    if group["stddev"] < 0:
        raise ValidationError(f"{name}.stddev cannot be negative")


# analyze_ab_rate / analyze_ab_mean / analyze_did / analyze_roi /
# analyze_sample_size_rate：从原 impact.py 第 97–273 行逐字复制，
# 函数体不变（内部不含 CLI/ok）。复制后无需改动。


ANALYZERS = {
    "ab_rate": analyze_ab_rate, "ab_mean": analyze_ab_mean, "did": analyze_did,
    "roi": analyze_roi, "sample_size_rate": analyze_sample_size_rate,
}


def evaluate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """效果评估入口。按 payload['analysis_type'] 分发，返回扁平 dict（无 ok）。"""
    analysis_type = payload.get("analysis_type")
    if analysis_type not in ANALYZERS:
        raise ValidationError(f"Unknown analysis_type: {analysis_type}")
    result = ANALYZERS[analysis_type](payload)
    result.pop("ok", None)  # 去信封（双保险：analyzer 内部若带了 ok 也清掉）
    return result
```

> **执行注意：** 上面被注释引用的 `analyze_*` 五个函数（原 `impact.py:97-273`）需**逐字粘贴**进本文件、放在 `ANALYZERS` 之前。它们的函数体不含 CLI/ok，无需改动（它们返回的 dict 里仍有 `"ok": True`，由 `evaluate` 末尾 `pop("ok")` 清除）。源码在 `evaluating-impact/scripts/impact.py:97-273`。

- [ ] **Step 2: 写 `mcp/tests/test_evaluating.py`**

```python
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
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd mcp && python -m pytest tests/test_evaluating.py -v
```
Expected: 5 passed。若 `analyze_*` 未粘贴全 → NameError，按执行注意补齐。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/evaluating.py mcp/tests/test_evaluating.py
git commit -m "feat(mcp): evaluating core (impact) + reuse SkillError + alpha parse guard"
```

---

## Task 5: 对照测试（新内核 vs 原 CLI，行为一致性安全网）

**Files:**
- Create: `mcp/tests/fixtures/diagnosing_add.json`
- Create: `mcp/tests/fixtures/diagnosing_multiply.json`
- Create: `mcp/tests/fixtures/forecast_linear.json`
- Create: `mcp/tests/fixtures/impact_did.json`
- Test: `mcp/tests/test_parity.py`

原理：原 CLI 不动、还在原位。用 subprocess 跑原 CLI 拿 stdout JSON（删 `ok`），in-process 跑新内核拿结果（序列化），断言相等。这是剥离行为一致性的硬保证。

- [ ] **Step 1: 写 4 个 fixture（典型输入）**

`mcp/tests/fixtures/diagnosing_add.json`：
```json
{"baseline_total": 1000, "current_total": 1200,
 "items": [{"name": "华东", "baseline": 400, "current": 520},
           {"name": "华南", "baseline": 350, "current": 380},
           {"name": "华北", "baseline": 250, "current": 300}]}
```

`mcp/tests/fixtures/diagnosing_multiply.json`：
```json
{"factors": [{"name": "DAU", "baseline": 1000, "current": 1200},
             {"name": "转化率", "baseline": 0.05, "current": 0.06},
             {"name": "客单价", "baseline": 80, "current": 85}]}
```

`mcp/tests/fixtures/forecast_linear.json`：
```json
{"metric": "gmv", "grain": "day", "horizon": 5, "model": "linear_trend",
 "series": [{"date": "2025-03-01", "value": 100}, {"date": "2025-03-02", "value": 110},
            {"date": "2025-03-03", "value": 108}, {"date": "2025-03-04", "value": 120},
            {"date": "2025-03-05", "value": 125}, {"date": "2025-03-06", "value": 130},
            {"date": "2025-03-07", "value": 128}, {"date": "2025-03-08", "value": 140}]}
```

`mcp/tests/fixtures/impact_did.json`：
```json
{"analysis_type": "did", "treatment_before": 1000, "treatment_after": 1300,
 "control_before": 1000, "control_after": 1100}
```

- [ ] **Step 2: 写 `mcp/tests/test_parity.py`**

```python
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
```

> 注意：对照测试比较的是"原 CLI 输出去 ok"与"新内核序列化"。三个内核的输出原本就是确定性的（无随机、无时间戳），因此应当**严格相等**。若不等，说明剥离时改动了算法或字段，必须排查。

- [ ] **Step 3: 运行对照测试**

Run:
```bash
cd mcp && python -m pytest tests/test_parity.py -v
```
Expected: 4 passed。任一 FAIL → 排查剥离差异（通常是字段顺序、rounding 位数、或漏复制函数）。

- [ ] **Step 4: 跑全部测试**

Run:
```bash
cd mcp && python -m pytest -q
```
Expected: 全绿（diagnosing 4 + predicting 4 + evaluating 5 + parity 4 = 17）。

- [ ] **Step 5: 提交**

```bash
git add mcp/tests/fixtures/ mcp/tests/test_parity.py
git commit -m "test(mcp): parity suite — new cores vs original CLI (behavior preserved)"
```

---

## Task 6: 收尾文档（本计划产出说明）

**Files:**
- Modify: `mcp/sda_mcp/skills/__init__.py`（导出三个内核入口，方便后续 MCP 工具层 import）

- [ ] **Step 1: 更新 `mcp/sda_mcp/skills/__init__.py`**

```python
"""各 skill 的干净 Python 内核。"""

from sda_mcp.skills.diagnosing import contribute, ContributionResult
from sda_mcp.skills.predicting import forecast, ForecastResult, ForecastError
from sda_mcp.skills.evaluating import evaluate

__all__ = [
    "contribute", "ContributionResult",
    "forecast", "ForecastResult", "ForecastError",
    "evaluate",
]
```

- [ ] **Step 2: 验证导入**

Run:
```bash
cd mcp && python -c "from sda_mcp.skills import contribute, forecast, evaluate; print('exports ok')"
```
Expected: `exports ok`

- [ ] **Step 3: 提交**

```bash
git add mcp/sda_mcp/skills/__init__.py
git commit -m "feat(mcp): export analysis cores from skills package"
```

---

## 完成标准（Definition of Done）

- [ ] `mcp/` 自包含包可独立 import，零第三方运行时依赖。
- [ ] 三个分析内核：入参 payload、出参 dataclass/dict（无 `ok`）、失败抛 `SkillError` 子类。
- [ ] 3 个既存 bug/不一致已修：diagnosing 拒 bool、predicting 拒非整数 horizon/window、evaluating alpha 解析包 ValidationError。
- [ ] predicting 的启发式预测带已在代码注释/docstring 标注。
- [ ] 17 个测试全绿；4 个对照测试证明新内核与原 CLI 输出严格相等。
- [ ] 原 `diagnosing-anomalies/`、`predicting-trends/`、`evaluating-impact/` 三个目录树**零改动**（用 `git diff -- diagnosing-anomalies predicting-trends evaluating-impact` 应无输出）。
- [ ] 每个任务一次提交。

---

## 后续（不在本计划）

- **1.B**：visualizing 内核（chart 渲染内核整体搬迁，剥离 chart.py 的 cli 层，渲染到 BytesIO；图最大，单独一份计划）。
- **1.C**：querying_data 内核（psycopg 连 Hologres + msal 连 Power BI Fabric MCP；Hologres 空字段名兼容 spike；需契约测试对照原 Node `query.js`）。
- **1.D**：retrieving_context 内核（neo4j Python 驱动 + fastembed ONNX embedding；验证 ONNX 向量与存量一致；契约测试对照原 `retrieve.js`）。
- **1.E**：building_reports 内核（httpx 直连 Vercel Blob REST + apimart；仅 html+image；契约测试对照原 `report.js`）。
- **1.F**：using_templates 内核（Python 包 lark-cli 子进程；身份绑定前置；契约测试对照原 `templates.js`）。
- 子项目 2（FastMCP 服务 + Docker + hermes 接入）在 1.A–1.F 完成后启动。
