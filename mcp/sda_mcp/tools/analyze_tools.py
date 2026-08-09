"""分析计算工具（diagnosing / predicting / evaluating 内核）→ MCP 工具。

入参用 dict（各 method/analysis_type 载荷结构差异大，统一 dict 收，内核内部校验）。

内核签名（实测）：
- predicting.forecast(payload: Mapping[str, Any]) -> ForecastResult
- diagnosing.contribute(method: str, payload: Mapping[str, Any]) -> ContributionResult
- evaluating.evaluate(payload: Mapping[str, Any]) -> dict[str, Any]
"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.diagnosing import contribute as _contribute
from sda_mcp.skills.predicting import forecast as _forecast
from sda_mcp.skills.evaluating import evaluate as _evaluate
from sda_mcp.tools._common import mcp, to_dict


class ContributeIn(BaseModel):
    method: str = Field(..., description="add | multiply | ratio")
    payload: dict[str, Any] = Field(..., description="对应方法的载荷（同原 CLI）")


class ForecastIn(BaseModel):
    payload: dict[str, Any] = Field(..., description="预测载荷：metric/grain/horizon/model/series 等")


class ImpactIn(BaseModel):
    analysis_type: str = Field(..., description="ab_rate | did | roi | ...")
    payload: dict[str, Any] = Field(default_factory=dict, description="对应类型的参数（可平铺到顶层）")


@mcp.tool(name="contribute")
def contribute(params: ContributeIn) -> dict[str, Any]:
    """贡献度归因（add/multiply/ratio）。"""
    return to_dict(_contribute(params.method, params.payload))


@mcp.tool(name="forecast")
def forecast(params: ForecastIn) -> dict[str, Any]:
    """时序预测 + 回测 + 置信带。"""
    return to_dict(_forecast(params.payload))


@mcp.tool(name="impact")
def impact(params: ImpactIn) -> dict[str, Any]:
    """效果评估（AB/DID/ROI 等）。"""
    body = {"analysis_type": params.analysis_type, **params.payload}
    return _evaluate(body)
