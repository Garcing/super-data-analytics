"""分析计算工具（diagnosing / predicting / evaluating 内核）→ MCP 工具。

入参平铺：method/analysis_type 与 payload 是平铺的两个关键字参数；
payload 本身是业务数据包（各 method/analysis_type 载荷结构差异大，
统一 dict 收，内核内部校验）。

内核签名（实测）：
- predicting.forecast(payload: Mapping[str, Any]) -> ForecastResult
- diagnosing.contribute(method: str, payload: Mapping[str, Any]) -> ContributionResult
- evaluating.evaluate(payload: Mapping[str, Any]) -> dict[str, Any]
"""
from typing import Annotated, Any, Literal

from pydantic import Field

from sda_mcp.skills.diagnosing import contribute as _contribute
from sda_mcp.skills.predicting import forecast as _forecast
from sda_mcp.skills.evaluating import evaluate as _evaluate
from sda_mcp.tools._common import mcp, map_tool_errors, to_dict, tool_annotations
from sda_mcp.tools._schemas import ContributionOutput, ForecastOutput


@mcp.tool(
    name="contribute",
    annotations=tool_annotations(
        "计算指标变化贡献度",
        read_only=True, destructive=False, idempotent=True, open_world=False,
    ),
)
@map_tool_errors
def contribute(
    method: Annotated[Literal["add", "multiply", "ratio"], Field(
        description="分解方法：add=加法指标；multiply=连乘/LMDI；ratio=分子分母比率的组内、结构和交叉贡献。",
    )],
    payload: Annotated[dict[str, Any], Field(
        description=(
            "方法载荷。add: {baseline_total,current_total,items[{name,baseline,current}]}; "
            "multiply: {factors[{name,baseline>0,current>0}]}; ratio: "
            "{groups[{name,baseline_numerator,baseline_denominator>0,current_numerator,current_denominator>0}]}。"
        ),
    )],
) -> ContributionOutput:
    """对两期指标做确定性贡献度分解。

    返回 ``method``、总体变化 ``summary``、逐项 ``rows[]`` 与守恒检查
    ``checks``（含 residual/warnings）。贡献度解释差值，不证明因果。
    """
    return to_dict(_contribute(method, payload))


@mcp.tool(
    name="forecast",
    annotations=tool_annotations(
        "预测业务指标趋势",
        read_only=True, destructive=False, idempotent=True, open_world=False,
    ),
)
@map_tool_errors
def forecast(
    payload: Annotated[dict[str, Any], Field(
        description=(
            "预测载荷：metric 指标名；grain=day|week|month|quarter；horizon 正整数；"
            "model=naive|seasonal_naive|moving_average|weighted_moving_average|"
            "exponential_smoothing|holt_linear|linear_trend|log_linear_trend|auto_baseline；"
            "series=[{date:YYYY-MM-DD,value:number}]（至少 2 点）；可选 season_length/target/options。"
        ),
    )],
) -> ForecastOutput:
    """对规则时间序列做轻量预测、留出回测和启发式区间估计。

    返回模型与选型原因、``forecast[]`` 点值和上下界、``summary``、
    ``backtest``、``confidence``、假设及警告。
    """
    return to_dict(_forecast(payload))


@mcp.tool(
    name="impact",
    annotations=tool_annotations(
        "评估实验与业务动作效果",
        read_only=True, destructive=False, idempotent=True, open_world=False,
    ),
)
@map_tool_errors
def impact(
    analysis_type: Annotated[
        Literal["ab_rate", "ab_mean", "did", "roi", "sample_size_rate"],
        Field(description="计算类型：比例 AB、均值 AB、DID、ROI 或比例指标样本量。"),
    ],
    payload: Annotated[dict[str, Any] | None, Field(
        description=(
            "类型参数。ab_rate: control/treatment={n,success}; ab_mean: {n,mean,stddev}; "
            "did: treatment_before/after 与 control_before/after；roi: benefit,cost；"
            "sample_size_rate: baseline_rate,minimum_detectable_effect。可选 alpha/power 等。"
        ),
    )] = None,
) -> dict[str, Any]:
    """执行 AB、DID、ROI 或样本量的确定性统计计算。

    返回字段随 ``analysis_type`` 变化，并包含效果量、显著性/区间或收益结果
    及 ``warnings``；工具只计算，不自动证明实验设计前提成立。
    """
    body = {"analysis_type": analysis_type, **(payload or {})}
    return _evaluate(body)
