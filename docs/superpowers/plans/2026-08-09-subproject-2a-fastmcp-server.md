# 子项目 2 阶段 A 实现计划：FastMCP 服务 + 23 工具 + 容器化（本地，不部署）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把子项目 1 的 8 个 Python 内核包成一个 FastMCP（MCP v2 `MCPServer`）streamable-HTTP 服务，暴露 23 个工具（第 1 批 18 + 模板 5；`sync` 延后——依赖未移植的 sync pipeline + ONNX 探针），配 Bearer 鉴权、Pydantic 入参、structuredContent 出参、画图 ImageContent+Blob URL 双保险。写 Dockerfile / docker-compose / Caddyfile（**只写不部署**）。全部本地可单测，零对外操作。

**架构：** `server.py` 建 `MCPServer("sda")` 实例 + 静态 Bearer `TokenVerifier` + `run()`。`tools/*.py` 按技能分组定义工具（`@mcp.tool`），入参用 Pydantic v2 BaseModel，出参用 `dict[str, Any]` 注解（FastMCP 直接当 structuredContent，不包 `result`）。工具是 **sync def**（FastMCP 线程池跑），直接调 sync 内核；内核抛 `SkillError` → FastMCP 自动 `isError:true` + 可操作 message。共享转换/校验放 `tools/_common.py`（替代设计文档里的 runner.py，职责相同）。

**Tech Stack:** mcp（Python SDK v2）、pydantic v2、uvicorn（mcp 依赖会带入）、现有 8 内核。

---

## 权威 API 事实（已核实官方文档 2026-08，照此实现）

**版本校验（实现前必做，第一步）：** `mcp` SDK 处于 v1→v2 过渡期，类名有漂移。安装后先跑：
```bash
cd mcp && pip install 'mcp>=1.12' pydantic uvicorn && python -c "
import mcp.server as s
print('MCPServer:', hasattr(s, 'MCPServer'))
try:
    from mcp.server import MCPServer; print('v2 MCPServer OK')
except Exception as e: print('v2 import failed:', e)
try:
    from mcp.server.mcpserver import Image; print('Image(v2) OK')
except Exception:
    from mcp.server.fastmcp.utilities.types import Image; print('Image(legacy) OK')
"
```
- 若 `from mcp.server import MCPServer` 可用 → 用 v2 命名（本文档默认）。
- 若只有 `FastMCP`（旧版）→ 全文 `MCPServer` 换成 `FastMCP`，`from mcp.server.fastmcp import FastMCP`，`Image` 用 `from mcp.server.fastmcp.utilities.types import Image`。**以安装版本为准，别两种混用。**

**关键事实：**
1. 服务：`mcp = MCPServer("sda")`；运行 `mcp.run(transport="streamable-http", host="0.0.0.0", port=3100)`；端点默认 `/mcp`。transport 选项给 `run()`，**不**给构造器。
2. 鉴权：`from mcp.server.auth.provider import AccessToken, TokenVerifier`、`from mcp.server.auth.settings import AuthSettings`、`from pydantic import AnyHttpUrl`。`MCPServer("sda", token_verifier=StaticTokenVerifier(), auth=AuthSettings(issuer_url=AnyHttpUrl("http://localhost"), resource_server_url=AnyHttpUrl("http://localhost:3100/mcp"), required_scopes=[]))`。无/错 token → 401。
3. 图片：`Image(data=<bytes>, format="png")`；返回 `[Image(...), "图表 URL: ..."]` → 客户端收到 image+text 两个 content block。
4. 结构化输出：返回类型注解即 outputSchema；`-> dict[str, Any]` 直接作 structuredContent（不包 `result`）。
5. sync 工具：`@mcp.tool() def f(...) -> ...:` 支持，FastMCP 线程池执行。
6. 单测：`async with Client(mcp) as client: r = await client.call_tool("name", {...}); r.structured_content / r.is_error`（in-memory，不走 HTTP/鉴权）。需 `pip install anyio pytest-anyio`（或用 `pytest.mark.anyio`，需 `anyio` + `pytest plugin`）。若不便装 anyio，改用 `asyncio.run` 包一层同步测试。**优先 `asyncio.run` 同步包装，零额外插件。**

---

## 文件结构

- Modify: `mcp/pyproject.toml` —— 加 `mcp`、`pydantic`、`uvicorn` 运行依赖
- Create: `mcp/sda_mcp/auth.py` —— StaticTokenVerifier
- Create: `mcp/sda_mcp/server.py` —— MCPServer 入口（注册所有工具 + run）
- Create: `mcp/sda_mcp/tools/__init__.py` —— 注册器：导入各分组触发 `@mcp.tool`
- Create: `mcp/sda_mcp/tools/_common.py` —— 共享：dataclass→dict、错误包装、mcp 实例
- Create: `mcp/sda_mcp/tools/query_tools.py` —— 5 工具
- Create: `mcp/sda_mcp/tools/retrieve_tools.py` —— 4 工具
- Create: `mcp/sda_mcp/tools/analyze_tools.py` —— 3 工具（contribute/forecast/impact）
- Create: `mcp/sda_mcp/tools/viz_tools.py` —— chart（Image+URL）
- Create: `mcp/sda_mcp/tools/report_tools.py` —— 5 工具
- Create: `mcp/sda_mcp/tools/template_tools.py` —— 5 工具
- Create: `mcp/tests/test_server_tools.py` —— 工具 in-memory 单测
- Create: `mcp/tests/test_auth.py` —— StaticTokenVerifier 单测
- Create: `mcp/Dockerfile`
- Create: `mcp/docker-compose.yml`
- Create: `mcp/Caddyfile`

**不修改**：任何原 skill 目录（铁律）；不改 `mcp/sda_mcp/skills/` 下内核（只调用它们）。

---

## Task 1: 依赖 + auth + _common + server 骨架 + 测试基座

**Files:** `pyproject.toml`, `auth.py`, `tools/_common.py`, `tools/__init__.py`, `server.py`, `tests/test_auth.py`

- [ ] **Step 1: 加依赖**

`mcp/pyproject.toml` 的 `dependencies` 末尾追加（保留现有 matplotlib/pandas/seaborn/scipy/pillow/psycopg/msal/httpx/neo4j/fastembed）：
```toml
    "mcp>=1.12",
    "pydantic>=2.6",
    "uvicorn>=0.30",
```

- [ ] **Step 2: 跑版本校验**（见上"版本校验"），记录可用命名。后续按结果选 MCPServer/FastMCP。

- [ ] **Step 3: 写 `mcp/sda_mcp/auth.py`**

```python
"""静态 Bearer token 鉴权（MCP v2 TokenVerifier）。

单 token：环境变量 SDA_MCP_TOKEN（或 config.json env）。hermes/笔记本经 Caddy 都带同一 token。
"""
from __future__ import annotations

import os

from mcp.server.auth.provider import AccessToken, TokenVerifier

# token 来源：SDA_MCP_TOKEN 环境变量（容器 run 时注入；镜像不含密钥）
_EXPECTED = os.environ.get("SDA_MCP_TOKEN", "")


class StaticTokenVerifier(TokenVerifier):
    """校验单个静态 Bearer token。token 匹配 → AccessToken；否则 None（→ 401）。"""

    async def verify_token(self, token: str) -> AccessToken | None:
        if _EXPECTED and token and token == _EXPECTED:
            return AccessToken(token=token, client_id="sda", scopes=[])
        return None
```

- [ ] **Step 4: 写 `mcp/sda_mcp/tools/_common.py`**

```python
"""工具层共享：mcp 实例 + dataclass→dict 转换。

设计文档原列 runner.py，其职责（内核 dataclass → MCP 结果、错误包装）折叠到此。
错误：内核抛 SkillError，FastMCP 自动转 isError:true（无需手动捕获）。
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

# 单一 mcp 实例，各 tools/*.py 用 @mcp.tool 注册到它
try:
    from mcp.server import MCPServer as _Server
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp import FastMCP as _Server

mcp = _Server("sda")


def to_dict(obj: Any) -> dict[str, Any]:
    """把内核返回（dataclass / dict）转成 JSON 安全 dict（丢 bytes）。
    dataclass 经 asdict；dict 原样；其余包成 {"result": obj}。"""
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return _strip_bytes(asdict(obj))
    return {"result": obj}


def _strip_bytes(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (bytes, bytearray)):
            continue
        out[k] = v
    return out
```

- [ ] **Step 5: 写 `mcp/sda_mcp/server.py`**

```python
"""FastMCP(v2 MCPServer) 入口：streamable HTTP，静态 Bearer 鉴权，注册 23 工具。

运行：SDA_MCP_TOKEN=<token> python -m sda_mcp.server
端点：http://0.0.0.0:3100/mcp
"""
from __future__ import annotations

import os

from pydantic import AnyHttpUrl

from sda_mcp.auth import StaticTokenVerifier
from sda_mcp.tools import register_all  # noqa: F401  触发各 tools/*.py 的 @mcp.tool
from sda_mcp.tools._common import mcp

_TOKEN = os.environ.get("SDA_MCP_TOKEN", "")


def build_server():
    """构造带鉴权的 MCPServer（仅当配了 token 才挂鉴权，便于本地裸跑测试）。"""
    if _TOKEN:
        from mcp.server.auth.settings import AuthSettings
        try:
            from mcp.server import MCPServer
            return MCPServer  # mcp 已是带 tool 的实例；鉴权见下方说明
        except ImportError:
            pass
    return mcp


def main() -> None:
    # streamable HTTP；transport 选项给 run()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("SDA_MCP_PORT", "3100")))


if __name__ == "__main__":
    main()
```

> **鉴权接线说明（实现时定）：** v2 把 `token_verifier`/`auth` 传给 `MCPServer(...)` 构造器，但 `tools/_common.py` 已在导入期用 `mcp = _Server("sda")` 建了实例（工具注册到它）。若 v2 允许**实例后补鉴权**（如 `mcp = MCPServer("sda", token_verifier=..., auth=...)`），则把鉴权参数移到 `_common.py` 的 `mcp` 构造、由 `SDA_MCP_TOKEN` 是否存在决定是否传。**实现时第一步：读安装版 `MCPServer.__init__` 签名确认 auth 参数名**（`python -c "import inspect; from mcp.server import MCPServer; print(inspect.signature(MCPServer.__init__))"`），据此把 `StaticTokenVerifier` + `AuthSettings` 正确接到 `mcp` 实例。若该版本鉴权必须构造期传入，则在 `_common.py` 内根据 env 一次性建好带鉴权的 `mcp`。**目标：有 token 时未授权请求得 401，无 token 时本地可裸跑测试。** 这一步的结论写进 `tools/__init__.py` 顶部注释。

- [ ] **Step 6: 写 `mcp/sda_mcp/tools/__init__.py`**

```python
"""导入各分组以触发 @mcp.tool 注册。"""
from sda_mcp.tools import query_tools      # noqa: F401
from sda_mcp.tools import retrieve_tools   # noqa: F401
from sda_mcp.tools import analyze_tools    # noqa: F401
from sda_mcp.tools import viz_tools        # noqa: F401
from sda_mcp.tools import report_tools     # noqa: F401
from sda_mcp.tools import template_tools   # noqa: F401


def register_all() -> None:
    """显式注册点（server.py 调用以确保导入）。模块导入即注册，此函数仅作锚点。"""
    pass
```

- [ ] **Step 7: 写 `mcp/tests/test_auth.py`**

```python
"""StaticTokenVerifier 单测（直接调 verify_token，不走 HTTP）。"""
import asyncio
import pytest
from sda_mcp import auth


def test_valid_token_returns_accesstoken(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "secret-token")
    at = asyncio.run(auth.StaticTokenVerifier().verify_token("secret-token"))
    assert at is not None and at.token == "secret-token"


def test_wrong_token_returns_none(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "secret-token")
    assert asyncio.run(auth.StaticTokenVerifier().verify_token("nope")) is None


def test_empty_when_unconfigured(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "")
    assert asyncio.run(auth.StaticTokenVerifier().verify_token("anything")) is None
```

- [ ] **Step 8: 装 + 跑**

```bash
cd mcp && pip install -e . && python -m pytest tests/test_auth.py -v
```
Expected: 3 passed。并确认 `python -c "from sda_mcp.tools._common import mcp; print(type(mcp).__name__)"` 打印 `MCPServer`（或 `FastMCP`）。

- [ ] **Step 9: 提交**

```bash
git add mcp/pyproject.toml mcp/sda_mcp/auth.py mcp/sda_mcp/server.py mcp/sda_mcp/tools/__init__.py mcp/sda_mcp/tools/_common.py mcp/tests/test_auth.py
git commit -m "feat(mcp): FastMCP server skeleton + static Bearer auth + tool registry"
```

---

## Task 2: query_tools.py —— 5 个取数工具

**Files:** `mcp/sda_mcp/tools/query_tools.py`, 测试在 Task 7

**工具清单**（入参 Pydantic / 出参 `dict[str, Any]`）：
| 工具 | 内核 | annotation |
|---|---|---|
| `sql_query` | `sql_query(sql)` + max_rows | readOnly |
| `sql_schema` | `sql_schema(tables)` | readOnly |
| `powerbi_list_models` | `powerbi_list_models()` | readOnly |
| `powerbi_schema` | `powerbi_schema(artifact_id)` | readOnly |
| `powerbi_query` | `powerbi_query(artifact_id, dax_queries, max_rows)` | readOnly |

- [ ] **Step 1: 写 `query_tools.py`**

```python
"""取数工具（querying_data 内核）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.querying_data import (
    sql_query as _sql_query, sql_schema as _sql_schema,
    powerbi_list_models as _powerbi_list_models, powerbi_schema as _powerbi_schema,
    powerbi_query as _powerbi_query,
)
from sda_mcp.tools._common import mcp, to_dict


class SqlQueryIn(BaseModel):
    sql: str = Field(..., description="单条 SELECT SQL", min_length=1)
    max_rows: int | None = Field(default=None, description="预留（内核未用）", ge=1)


class SqlSchemaIn(BaseModel):
    tables: list[str] = Field(..., description='schema.table 列表，如 ["public.orders"]', min_length=1)


class ArtifactIn(BaseModel):
    artifact_id: str = Field(..., description="Power BI 语义模型 GUID")


class PowerBIQueryIn(BaseModel):
    artifact_id: str = Field(..., description="Power BI 语义模型 GUID")
    dax_queries: list[str] = Field(..., description="1-4 条 DAX", min_length=1, max_length=4)
    max_rows: int = Field(default=250, description="每条最大行数", ge=1, le=1000)


@mcp.tool(name="sql_query")
def sql_query(params: SqlQueryIn) -> dict[str, Any]:
    """在 Hologres 执行单条 SQL，返回列与行。readOnly。"""
    return to_dict(_sql_query(params.sql))


@mcp.tool(name="sql_schema")
def sql_schema(params: SqlSchemaIn) -> dict[str, Any]:
    """查多张表的列定义。readOnly。"""
    return {"tables": to_dict(_sql_schema(params.tables))}


@mcp.tool(name="powerbi_list_models")
def powerbi_list_models() -> dict[str, Any]:
    """列出 config.json 配置的 Power BI 语义模型。readOnly。"""
    return {"models": _powerbi_list_models()}


@mcp.tool(name="powerbi_schema")
def powerbi_schema(params: ArtifactIn) -> dict[str, Any]:
    """取某语义模型的表/列 schema。readOnly。"""
    return _powerbi_schema(params.artifact_id)


@mcp.tool(name="powerbi_query")
def powerbi_query(params: PowerBIQueryIn) -> dict[str, Any]:
    """对语义模型跑 1-4 条 DAX。readOnly。"""
    return _powerbi_query(params.artifact_id, params.dax_queries, params.max_rows)
```

- [ ] **Step 2: 冒烟** `python -c "from sda_mcp.tools import query_tools; print('ok')"`
- [ ] **Step 3: 提交** `git add mcp/sda_mcp/tools/query_tools.py && git commit -m "feat(mcp): query tools (sql/powerbi)"`

---

## Task 3: retrieve_tools.py（4）+ analyze_tools.py（3）

**Files:** `retrieve_tools.py`, `analyze_tools.py`

**retrieve 清单：** `retrieve_search(question, top_k?, targets?)` readOnly / `retrieve_cypher(statement)` (destructiveHint) / `retrieve_schema()` readOnly / `retrieve_doc(doc)` readOnly。

- [ ] **Step 1: 写 `retrieve_tools.py`**

```python
"""语义检索工具（retrieving_context 内核）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.retrieving_context import (
    search as _search, cypher as _cypher, schema as _schema, doc as _doc,
)
from sda_mcp.tools._common import mcp


class SearchIn(BaseModel):
    question: str = Field(..., min_length=1, description="自然语言问题")
    top_k: int = Field(default=5, ge=1, le=20)
    targets: list[str] | None = Field(default=None, description="限定实体标签")


class CypherIn(BaseModel):
    statement: str = Field(..., min_length=1, description="Cypher 语句（可写库）")


class DocIn(BaseModel):
    doc: str = Field(..., min_length=1, description="飞书文档 URL 或 token")


@mcp.tool(name="retrieve_search")
def retrieve_search(params: SearchIn) -> dict[str, Any]:
    """向量检索语义层 + 图扩展上下文。readOnly。"""
    return _search(params.question, params.top_k, params.targets)


@mcp.tool(name="retrieve_cypher")
def retrieve_cypher(params: CypherIn) -> dict[str, Any]:
    """直接跑 Cypher（可能写库）。destructive。"""
    return _cypher(params.statement)


@mcp.tool(name="retrieve_schema")
def retrieve_schema() -> dict[str, Any]:
    """返回图 schema（实体/关系/embedding 配置）。readOnly。"""
    return _schema()


@mcp.tool(name="retrieve_doc")
def retrieve_doc(params: DocIn) -> dict[str, Any]:
    """读取飞书文档为 markdown。readOnly。"""
    return _doc(params.doc)
```

- [ ] **Step 2: 写 `analyze_tools.py`**（contribute / forecast / impact→evaluate）

```python
"""分析计算工具（diagnosing / predicting / evaluating 内核）→ MCP 工具。

入参用 dict（各 method/analysis_type 载荷结构差异大，统一 dict 收，内核内部校验）。
"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.diagnosing import contribute as _contribute
from sda_mcp.skills.predicting import forecast as _forecast
from sda_mcp.skills.evaluating import evaluate as _evaluate
from sda_mcp.tools._common import mcp


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
    return _contribute(params.method, params.payload)


@mcp.tool(name="forecast")
def forecast(params: ForecastIn) -> dict[str, Any]:
    """时序预测 + 回测 + 置信带。"""
    return _forecast(params.payload)


@mcp.tool(name="impact")
def impact(params: ImpactIn) -> dict[str, Any]:
    """效果评估（AB/DID/ROI 等）。"""
    body = {"analysis_type": params.analysis_type, **params.payload}
    return _evaluate(body)
```

> `forecast`/`contribute` 内核签名以实际为准（`predicting.forecast(payload)` / `diagnosing.contribute(method, payload)`）。实现前 `python -c "import inspect; from sda_mcp.skills import predicting,diagnosing; print(inspect.signature(predicting.forecast)); print(inspect.signature(diagnosing.contribute))"` 确认，按真实签名接线。

- [ ] **Step 3: 冒烟 + 提交**
```bash
python -c "from sda_mcp.tools import retrieve_tools, analyze_tools; print('ok')"
git add mcp/sda_mcp/tools/retrieve_tools.py mcp/sda_mcp/tools/analyze_tools.py
git commit -m "feat(mcp): retrieve + analyze tools"
```

---

## Task 4: viz_tools.py —— chart（ImageContent + Blob URL 双保险）

**Files:** `viz_tools.py`

- [ ] **Step 1: 写 `viz_tools.py`**

```python
"""可视化工具：chart 渲染为图片，ImageContent + Vercel Blob URL 双保险。

hermes 能转发 ImageContent → 直推图；不能 → 用 URL（企微"上传素材再发"也吃 URL）。
"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.visualizing import render as _render
from sda_mcp.tools._common import mcp

try:
    from mcp.server.mcpserver import Image
except ImportError:
    from mcp.server.fastmcp.utilities.types import Image


class ChartIn(BaseModel):
    spec: dict[str, Any] = Field(..., description="图表 JSON：type/title/subtitle/data/encoding/options")
    format: str = Field(default="png", description="png（默认，飞书/企微兼容）| svg")
    dpi: int = Field(default=144, ge=72, le=300)


@mcp.tool(name="chart")
def chart(params: ChartIn):
    """渲染图表。返回图片(image content) + 一个文本块(可分享 URL)。"""
    res = _render(params.spec, format=params.format, dpi=params.dpi)
    url = ""
    # 双保险：尝试把 PNG 传到 Vercel Blob 给公网 URL（失败不影响返回图片）
    if params.format == "png":
        try:
            from sda_mcp.skills.building_reports.blob_store import VercelBlobClient
            info = VercelBlobClient().put(f"charts/{_safe_name(params.spec)}.png", res.data,
                                          content_type="image/png", cache_control_max_age=3600)
            url = info.url
        except Exception:
            url = ""
    blocks = [Image(data=res.data, format=params.format)]
    text = f"图表已生成（{res.width}x{res.height}）。" + (f" URL: {url}" if url else "（未上传 Blob，仅返回图片字节）")
    blocks.append(text)
    return blocks
```

加 `_safe_name`（按 spec.title 生成安全文件名，fallback 时间戳/随机）：

```python
import re
def _safe_name(spec: dict[str, Any]) -> str:
    t = str(spec.get("title") or "chart")
    s = re.sub(r"[^\w\-]", "-", t).strip("-")[:32] or "chart"
    return s
```
（放 `viz_tools.py` 模块内、`chart` 之前。）

- [ ] **Step 2: 冒烟** `python -c "from sda_mcp.tools import viz_tools; print('ok')"`
- [ ] **Step 3: 提交** `git add mcp/sda_mcp/tools/viz_tools.py && git commit -m "feat(mcp): chart tool (ImageContent + Blob URL)"`

---

## Task 5: report_tools.py（5）+ template_tools.py（5）

**Files:** `report_tools.py`, `template_tools.py`

- [ ] **Step 1: 写 `report_tools.py`**

```python
"""报告工具（building_reports 内核，html+image）→ MCP 工具。streamlit 已砍。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.building_reports import (
    publish_report as _publish, list_reports as _list, get_report as _get,
    delete_report as _delete, generate_image as _gen,
)
from sda_mcp.tools._common import mcp, to_dict


class PublishIn(BaseModel):
    id: str = Field(..., min_length=1, description="报告 ID")
    report: dict[str, Any] = Field(..., description="报告 JSON：meta/summary/conclusions")


class IdIn(BaseModel):
    id: str = Field(..., min_length=1)


class ImageGenIn(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str | None = Field(default=None, description="gpt-image-2 | gpt-image-2-official")
    size: str | None = None
    resolution: str | None = None
    n: int | None = Field(default=None, ge=1, le=4)


@mcp.tool(name="report_html_publish")
def report_html_publish(params: PublishIn) -> dict[str, Any]:
    """发布 HTML 报告到 Vercel Blob，返回可分享前端 URL。"""
    r = _publish(params.report, params.id)
    return {"url": r.url, "report_id": r.report_id, "blob_url": r.blob_url}


@mcp.tool(name="report_html_list")
def report_html_list() -> dict[str, Any]:
    """列出已发布报告（索引）。readOnly。"""
    return {"reports": _list()}


@mcp.tool(name="report_html_get")
def report_html_get(params: IdIn) -> dict[str, Any]:
    """取某报告完整 JSON。readOnly。"""
    return _get(params.id)


@mcp.tool(name="report_html_delete")
def report_html_delete(params: IdIn) -> dict[str, Any]:
    """删除报告（destructive）。"""
    return _delete(params.id)


@mcp.tool(name="report_image_generate")
def report_image_generate(params: ImageGenIn) -> dict[str, Any]:
    """apimart gpt-image-2 异步生图（最长 ~180s）。返回图片 URL+字节。"""
    opts = {k: v for k, v in params.model_dump().items() if k != "prompt" and v is not None}
    r = _gen(params.prompt, **opts)
    return {"task_id": r.task_id, "cost": r.cost, "status": r.status,
            "images": [{"url": im.url, "error": im.error} for im in r.images]}
```

- [ ] **Step 2: 写 `template_tools.py`**

```python
"""模板工具（using_templates 内核，包 lark-cli）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.using_templates import (
    list_templates as _list, read_template as _read, create_template as _create,
    update_template as _update, delete_template as _delete,
)
from sda_mcp.tools._common import mcp


class CreateTemplateIn(BaseModel):
    title: str = Field(..., min_length=1)
    content: str | None = Field(default=None, description="markdown 正文；缺省则建空文档")


class UpdateTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, description="覆盖写入的 markdown")


class DeleteTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)
    password: str | None = Field(default=None, description="FEISHU_TEMPLATE_DELETE_PASSWORD 已配置时必填")


@mcp.tool(name="template_list")
def template_list() -> dict[str, Any]:
    """列出飞书模板文件夹下的文档。readOnly。"""
    return {"templates": _list()}


@mcp.tool(name="template_read")
def template_read(params) -> dict[str, Any]:  # params 见下，补 BaseModel
    return {"content": _read(params.doc_id)}


class ReadTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)


# 修正：template_read 应使用 ReadTemplateIn（实现时把上面占位 def 换成下方）
@mcp.tool(name="template_read")
def template_read(params: ReadTemplateIn) -> dict[str, Any]:
    """读取模板为 markdown。readOnly。"""
    return {"content": _read(params.doc_id)}


@mcp.tool(name="template_create")
def template_create(params: CreateTemplateIn) -> dict[str, Any]:
    """创建模板文档。"""
    r = _create(params.title, params.content)
    return {"document_id": r.document_id, "title": r.title}


@mcp.tool(name="template_update")
def template_update(params: UpdateTemplateIn) -> dict[str, Any]:
    """覆盖更新模板。"""
    r = _update(params.doc_id, params.content)
    return {"updated": r.updated, "document_id": r.document_id}


@mcp.tool(name="template_delete")
def template_delete(params: DeleteTemplateIn) -> dict[str, Any]:
    """删除模板（destructive，可能需密码）。"""
    r = _delete(params.doc_id, params.password)
    return {"deleted": r.deleted, "document_id": r.document_id}
```

> **实现注意（删占位）：** 上面 `template_read` 写了两遍——第 1 个用未定义 `params` 的占位是错误，**实现时只保留用 `ReadTemplateIn` 的那个版本**，删掉错误占位。（这是计划自查暴露的笔误，按修正版落地。）

- [ ] **Step 3: 冒烟 + 提交**
```bash
python -c "from sda_mcp.tools import report_tools, template_tools; print('ok')"
git add mcp/sda_mcp/tools/report_tools.py mcp/sda_mcp/tools/template_tools.py
git commit -m "feat(mcp): report + template tools"
```

---

## Task 6: Dockerfile + docker-compose.yml + Caddyfile

- [ ] **Step 1: 写 `mcp/Dockerfile`**

```dockerfile
# super-data-analytics MCP 服务镜像
FROM python:3.12-slim

# CJK 字体（中文图表必需）+ 基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（分层缓存）
COPY pyproject.toml ./
# 项目以 editable 安装；依赖在 pyproject 的 dependencies 声明
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir uvicorn

# 预下载 bge-small ONNX 模型，避免运行时拉取（fastembed 首次会下载）
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')"

# 代码
COPY sda_mcp ./sda_mcp

ENV PYTHONUNBUFFERED=1 \
    SDA_MCP_PORT=3100
EXPOSE 3100

# config.json 由 compose 卷挂载（SDA_CONFIG_PATH 指向），镜像不含密钥
CMD ["python", "-m", "sda_mcp.server"]
```

- [ ] **Step 2: 写 `mcp/docker-compose.yml`**

```yaml
services:
  sda-mcp:
    build: .
    container_name: sda-mcp
    # host 网络：连 127.0.0.1:7687 Neo4j；hermes 走 localhost:3100；eth0/tailscale 直通
    network_mode: host
    environment:
      # 静态 Bearer token（hermes/笔记本经 Caddy 同一 token）。部署时在此填或用 .env
      SDA_MCP_TOKEN: ${SDA_MCP_TOKEN}
      # config.json 挂载点（宿主 ~/.super-data-analytics/config.json）
      SDA_CONFIG_PATH: /root/.super-data-analytics/config.json
    volumes:
      - ${HOME}/.super-data-analytics/config.json:/root/.super-data-analytics/config.json:ro
    restart: unless-stopped
```

> 注：host 网络下不需 `ports:`。config.json 路径以服务器实际为准（部署时核对 `~/.super-data-analytics/config.json`）。

- [ ] **Step 3: 写 `mcp/Caddyfile`**

```caddy
# 笔记本经公网接入：mcp.super-data-analytics.online -> localhost:3100
# TLS-ALPN-01 自动签证书（80 被 hermes 占，Caddy 用 443 ALPN，不抢 80）
mcp.super-data-analytics.online {
    reverse_proxy localhost:3100
    # Bearer 由客户端（笔记本/hermes）自带；Caddy 仅做 TLS 转发
    # 如需双保险，可在此加 header_up / basic_auth，非必需
}
```

- [ ] **Step 4: 提交**
```bash
git add mcp/Dockerfile mcp/docker-compose.yml mcp/Caddyfile
git commit -m "build(mcp): Dockerfile + host-network compose + Caddyfile (written, not deployed)"
```

---

## Task 7: 工具 in-memory 单测

**Files:** `mcp/tests/test_server_tools.py`

用 `Client(mcp)` in-memory 调用工具（不走 HTTP/鉴权），mock 各内核，断言 `structured_content` / `is_error`。

- [ ] **Step 1: 写 `test_server_tools.py`**

```python
"""MCP 工具 in-memory 单测（Client(mcp)，mock 内核，不走 HTTP）。"""
import asyncio
import json
import pytest


def _call(name, args):
    """同步包装：用 in-memory Client 调工具，返回 (structured_content, is_error, content)。"""
    from mcp import Client
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool(name, args)
            return r.structured_content, r.is_error, r.content
    return asyncio.run(_run())


def test_sql_query_tool(monkeypatch):
    from sda_mcp.skills import querying_data as q
    from sda_mcp.skills.querying_data import SqlResult
    monkeypatch.setattr(q, "sql_query", lambda sql: SqlResult(columns=[{"name": "a"}], rows=[{"a": 1}], row_count=1))
    sc, err, _ = _call("sql_query", {"params": {"sql": "SELECT 1"}})
    assert not err
    assert sc["row_count"] == 1 and sc["columns"][0]["name"] == "a"


def test_skill_error_becomes_is_error(monkeypatch):
    from sda_mcp.skills import querying_data as q
    from sda_mcp.errors import DataSourceError
    def _boom(sql): raise DataSourceError("连不上 Hologres（检查 VPN）")
    monkeypatch.setattr(q, "sql_query", _boom)
    sc, err, content = _call("sql_query", {"params": {"sql": "SELECT 1"}})
    assert err is True
    # 可操作 message 进了 text content
    joined = "".join(getattr(c, "text", "") for c in content)
    assert "Hologres" in joined or "VPN" in joined


def test_powerbi_list_models(monkeypatch):
    from sda_mcp.skills import querying_data as q
    monkeypatch.setattr(q, "powerbi_list_models", lambda: [{"id": "m1"}])
    sc, err, _ = _call("powerbi_list_models", {})
    assert sc["models"] == [{"id": "m1"}]


def test_retrieve_search(monkeypatch):
    from sda_mcp.skills import retrieving_context as r
    monkeypatch.setattr(r, "search", lambda question, top_k=5, targets=None: {"question": question, "results": []})
    sc, err, _ = _call("retrieve_search", {"params": {"question": "Q"}})
    assert sc["results"] == []


def test_contribute(monkeypatch):
    from sda_mcp.skills import diagnosing as d
    monkeypatch.setattr(d, "contribute", lambda method, payload: {"summary": "s", "rows": [], "checks": []})
    sc, err, _ = _call("contribute", {"params": {"method": "add", "payload": {"a": [1, 2]}}})
    assert sc["summary"] == "s"


def test_chart_returns_image_block(monkeypatch):
    from sda_mcp.skills import visualizing as v
    from sda_mcp.skills.visualizing import ChartResult
    monkeypatch.setattr(v, "render", lambda spec, format="png", dpi=144: ChartResult(
        format="png", dpi=144, width=10, height=20, data=b"\x89PNG\r\n\x1a\n", warnings=[]))
    sc, err, content = _call("chart", {"params": {"spec": {"type": "bar", "title": "T"}, "format": "png"}})
    assert not err
    # 至少有一个 image 内容块（Blob 上传会失败因无凭证，不影响图片块）
    types = [getattr(c, "type", "") for c in content]
    assert "image" in types


def test_report_publish(monkeypatch):
    from sda_mcp.skills import building_reports as br
    from sda_mcp.skills.building_reports.html_reports import PublishResult
    from sda_mcp.skills.building_reports import html_reports as hr
    monkeypatch.setattr(hr, "publish_report", lambda report, rid: PublishResult(url=f"https://app/report/{rid}", report_id=rid, blob_url="b"))
    sc, err, _ = _call("report_html_publish", {"params": {"id": "r1", "report": {"meta": {"title": "t"}}}})
    assert sc["url"].endswith("/report/r1")


def test_template_list(monkeypatch):
    from sda_mcp.skills import using_templates as ut
    monkeypatch.setattr(ut, "list_templates", lambda: [{"id": "d1", "name": "日报"}])
    sc, err, _ = _call("template_list", {})
    assert sc["templates"][0]["id"] == "d1"


def test_validation_error_is_error():
    # Pydantic 校验失败（缺必填）→ is_error
    sc, err, _ = _call("sql_query", {"params": {}})
    assert err
```

> **入参传法（实现时确认）：** FastMCP 工具入参是单个 Pydantic 模型时，`call_tool("name", {"params": {...}})` 或 `{"<field>": ...}` 取决于版本。实现时先跑一个 `test_sql_query_tool` 看报错，确定正确入参键名（v2 单 BaseModel 参数 → 用 `{"params": {...}}`；若版本要求平铺则改平铺）。在测试顶部加注释说明采用的入参约定。

- [ ] **Step 2: 跑**
```bash
cd mcp && python -m pytest tests/test_server_tools.py -v
```
Expected: 9 passed（允许根据真实入参约定微调 call_tool 调用形态）。

- [ ] **Step 3: 全量 + 铁律**
```bash
python -m pytest -q
git diff --stat -- using-templates/ building-reports/ visualizing-data/ querying-data/ retrieving-context/ diagnosing-data/ predicting-data/ evaluating-data/
```
Expected: 全绿（90 + auth 3 + server_tools 9 = 102）；原目录零改动。

- [ ] **Step 4: 服务冒烟（本地裸跑，无 token）**
```bash
python -c "
import os; os.environ.pop('SDA_MCP_TOKEN', None)
from sda_mcp.tools._common import mcp
import asyncio
from mcp import Client
async def t():
    async with Client(mcp) as c:
        tools = await c.list_tools()
        print('tools:', len(tools.tools))
        names = sorted(t.name for t in tools.tools)
        print(names)
asyncio.run(t())
"
```
Expected: 打印 23 个工具名（sql_query…template_delete）。

- [ ] **Step 5: 提交**
```bash
git add mcp/tests/test_server_tools.py
git commit -m "test(mcp): in-memory tool tests (23 tools wired, SkillError→isError)"
```

---

## 完成标准

- [ ] `mcp/sda_mcp/server.py` + `auth.py` + `tools/`（6 分组 23 工具）可 import，`list_tools` 返回 23 个。
- [ ] Bearer StaticTokenVerifier 单测 3 个；工具 in-memory 单测 9 个；全量 ≥102 通过；原 skill 目录零改动。
- [ ] chart 返回 image content 块 + URL 文本（Blob 上传失败不影响图片）。
- [ ] SkillError → `isError:true` + 可操作 text。
- [ ] Dockerfile（CJK 字体 + 预下载 bge ONNX + CMD）/ docker-compose（host 网络 + 挂载 config.json）/ Caddyfile 写好（不部署）。
- [ ] 鉴权接线按安装版 SDK 实测确认（auth 参数正确挂到 mcp 实例）。
- [ ] `sync` 工具不在 2.A（延后，依赖 sync pipeline + ONNX 探针）。

---

## 2.A 之后的待办（不在本计划内）

- 2.B 服务器探针：ONNX 向量一致性 / psycopg 空字段 / lark-cli 容器身份绑定。
- 补 `sync` 工具：先移植 retrieve.js 的 sync pipeline 为内核（fetch→graph→embed→写库），再加 `sync` 工具。
- 2.C 对外部署（需用户逐步确认）：DNS / 安全组 443 / 构建启动 / Caddy 证书 / hermes config.yaml `sda` / 飞书企微端到端。
- 评估集（10 道只读题，mcp-builder Phase 4）。
