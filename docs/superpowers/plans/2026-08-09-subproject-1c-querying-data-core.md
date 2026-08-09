# 子项目 1.C 实现计划：querying_data 内核（Hologres + Power BI）

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development 或 executing-plans。步骤用 `- [ ]` 复选框跟踪。

**Goal:** 把 `querying-data`（Node：pg 连 Hologres + Azure AD + Fabric MCP HTTP）重写为纯 Python 内核（psycopg + msal + httpx），去 CLI/三态/`{ok}` 信封，失败抛 `SkillError`，行为与原 Node CLI 一致。

**Architecture:** 原仓库树不动。新 `mcp/sda_mcp/skills/querying_data.py`。原 Node 实现（`querying-data/scripts/query.js`、`lib/sql.js`、`lib/powerbi.js`）是**忠实移植的参照基准**——实现者读这些 JS 文件，用 Python 等价复刻其行为。新增共享 `mcp/sda_mcp/config.py` 读 config.json（后续 retrieving/reports/templates 共用）。测试用 mock 覆盖逻辑；另写 env 门控的集成对照测试（默认跳过，`SDA_INTEGRATION=1` 时连真服务跑「Python 内核 vs 原 Node CLI」）。

**Tech Stack:** psycopg[binary]（Hologres/Postgres）、msal（Azure AD client_credentials）、httpx（Fabric MCP HTTP）。新增到 pyproject。

**关键行为（必须与原 JS 一致）：**
- Hologres 空字段名：原 JS monkey-patch pg-protocol；Python 在**应用层**处理——`cursor.description` 里任何空/None 列名替换为 `col_{i}`（见 sql.js:282 `f.name || \`col_${i}\``）。无需 patch psycopg。
- 列结构：`{name, dataTypeID}`，dataTypeID = psycopg 的 type_code（OID）。
- schema 查询：读 SQL 模板，字面量替换 `'schema_name'`/`'table_name'`，逐表查询，返回 `[{schema, table, columns}]`。
- Power BI：JSON-RPC 2.0 POST `https://api.fabric.microsoft.com/v1/mcp/powerbi`，Bearer token（scope `https://analysis.windows.net/powerbi/api/.default`），Accept `application/json, text/event-stream`；**202 轮询**：读 `operation-location` 头，每 1s 轮询，60s 超时；401/403 → 明确鉴权错误；响应解析先 JSON，再退回 SSE `data:` 行。
- artifactId GUID 校验；daxQueries 1-4 条非空；maxRows 1-1000 默认 250。
- 凭证缺失 → `ConfigError`（带可操作提示）。

---

## 文件结构

- Create: `mcp/sda_mcp/config.py` —— 共享 config.json 读取
- Create: `mcp/sda_mcp/skills/querying_data.py` —— HologresClient + PowerBIClient + 入口函数
- Copy: `mcp/sda_mcp/skills/querying_data_schema.sql` ← `querying-data/scripts/lib/get_table_schema.sql`（数据文件，逐字复制）
- Modify: `mcp/pyproject.toml` —— 加 psycopg[binary]、msal、httpx
- Modify: `mcp/sda_mcp/skills/__init__.py` —— 导出
- Test: `mcp/tests/test_querying_data.py` —— mock 单元测试
- Test: `mcp/tests/test_querying_data_integration.py` —— env 门控集成对照（默认 skip）

**不修改**：`querying-data/` 下任何文件。

---

## Task 1: config.py + querying_data.py + schema 模板 + 依赖

- [ ] **Step 1: 写 `mcp/sda_mcp/config.py`**

```python
"""统一读取 ~/.super-data-analytics/config.json。后续所有需要凭证的内核共用。"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from sda_mcp.errors import ConfigError

DEFAULT_CONFIG_PATH = Path(os.environ.get(
    "SDA_CONFIG_PATH", Path.home() / ".super-data-analytics" / "config.json"))


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """读 config.json（整份）。文件缺失/损坏抛 ConfigError。"""
    try:
        return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {DEFAULT_CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件解析失败 {DEFAULT_CONFIG_PATH}: {exc}") from exc


def get_env(*keys: str) -> dict[str, str]:
    """从 config.json 的 env 块取指定键。缺任一项抛 ConfigError（带缺失清单）。"""
    env = load_config().get("env", {})
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise ConfigError(f"配置缺少: {', '.join(missing)}（请在 config.json 的 env 块补全）")
    return {k: str(env[k]) for k in keys}


def get_powerbi_models() -> list[Any]:
    """Power BI 语义模型候选（powerbi-semantic-models 块）。无网络。"""
    return load_config().get("powerbi-semantic-models", [])
```

- [ ] **Step 2: 复制 schema 模板**

```bash
cp querying-data/scripts/lib/get_table_schema.sql mcp/sda_mcp/skills/querying_data_schema.sql
```

- [ ] **Step 3: 写 `mcp/sda_mcp/skills/querying_data.py`**

实现者参照 `querying-data/scripts/lib/sql.js`（HologresClient，约 215-289 行）和 `lib/powerbi.js`（PowerBIClient，约 15-167 行；parseDaxPayload 178-203 行）忠实移植。骨架与契约如下（填入实现）：

```python
"""querying_data 内核：Hologres(SQL) + Power BI(DAX)，从原 Node CLI 移植。

去 CLI/三态/{ok} 信封；失败抛 SkillError（ConfigError/ValidationError/DataSourceError）。
行为对齐 querying-data/scripts/{query.js, lib/sql.js, lib/powerbi.js}。
"""
from __future__ import annotations

import importlib.resources
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import msal
import psycopg

from sda_mcp.config import get_env, get_powerbi_models
from sda_mcp.errors import ConfigError, DataSourceError, ValidationError, SkillTimeoutError

_MCP_URL = "https://api.fabric.microsoft.com/v1/mcp/powerbi"
_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_POLL_TIMEOUT_MS = 60_000
_POLL_INTERVAL_MS = 1_000
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@dataclass
class SqlResult:
    columns: list[dict[str, Any]]   # [{name, dataTypeID}]
    rows: list[dict[str, Any]]
    row_count: int


# ---------- 校验 ----------

def _require_guid(artifact_id: str) -> None:
    if not artifact_id or not _GUID_RE.match(str(artifact_id)):
        raise ValidationError(
            f'artifactId 格式错误 "{artifact_id}"，应为 GUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')


def validate_dax_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """对齐 powerbi.js parseDaxPayload。返回 {artifact_id, dax_queries, max_rows}。"""
    if not isinstance(payload, dict):
        raise ValidationError("PowerBI 载荷必须是 JSON 对象")
    artifact_id = payload.get("artifactId")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValidationError("载荷缺少 artifactId")
    _require_guid(artifact_id)
    dax = payload.get("daxQueries")
    if not isinstance(dax, list) or not (1 <= len(dax) <= 4):
        raise ValidationError("daxQueries 必须是 1 到 4 条 DAX 的数组")
    normalized = []
    for i, q in enumerate(dax):
        if not isinstance(q, str) or not q.strip():
            raise ValidationError(f"daxQueries[{i}] 必须是非空字符串")
        normalized.append(q)
    max_rows = payload.get("maxRows", 250)
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not (1 <= max_rows <= 1000):
        raise ValidationError("maxRows 必须是 1 到 1000 之间的整数")
    return {"artifact_id": artifact_id, "dax_queries": normalized, "max_rows": max_rows}


def _split_table(arg: str) -> tuple[str, str]:
    """'schema.table' → (schema, table)；缺点抛 ValidationError。"""
    idx = arg.find(".")
    if idx == -1:
        raise ValidationError(f'参数格式错误: "{arg}"，应为 schema.table')
    return arg[:idx], arg[idx + 1:]


# ---------- Hologres ----------

class HologresClient:
    """对齐 sql.js HologresClient。psycopg 连 Hologres（Postgres 协议）。"""

    def __init__(self) -> None:
        env = get_env("HOLOGRES_HOST", "HOLOGRES_PORT", "HOLOGRES_DATABASE",
                      "HOLOGRES_USER", "HOLOGRES_PASSWORD")
        self._dsn = (
            f"host={env['HOLOGRES_HOST']} port={env['HOLOGRES_PORT']} "
            f"dbname={env['HOLOGRES_DATABASE']} user={env['HOLOGRES_USER']} "
            f"password={env['HOLOGRES_PASSWORD']} connect_timeout=10")

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self._dsn)
        except psycopg.OperationalError as exc:
            raise DataSourceError(f"无法连接 Hologres（检查 VPN/白名单/凭证）: {exc}") from exc

    def test_connection(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def query(self, sql: str) -> SqlResult:
        with self._connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(sql)
            except psycopg.DatabaseError as exc:
                raise DataSourceError(f"SQL 执行失败: {exc}") from exc
            description = cur.description or []
            columns = [
                {"name": (d.name or f"col_{i}"), "dataTypeID": d.type_code}
                for i, d in enumerate(description)
            ]
            rows = [dict(zip([c["name"] for c in columns], r)) for r in cur.fetchall()]
        return SqlResult(columns=columns, rows=rows, row_count=len(rows))

    def get_table_schema(self, table: str, schema: str = "public") -> list[dict[str, Any]]:
        template = importlib.resources.files(__package__).joinpath(
            "querying_data_schema.sql").read_text(encoding="utf-8")
        sql = template.replace("'schema_name'", f"'{schema}'").replace("'table_name'", f"'{table}'")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def sql_query(sql: str) -> SqlResult:
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("sql 不能为空")
    return HologresClient().query(sql)


def sql_schema(tables: list[str]) -> list[dict[str, Any]]:
    if not tables:
        raise ValidationError("tables 不能为空")
    client = HologresClient()
    out = []
    for arg in tables:
        schema, table = _split_table(arg)
        out.append({"schema": schema, "table": table, "columns": client.get_table_schema(table, schema)})
    return out


def sql_test_connection() -> None:
    HologresClient().test_connection()


# ---------- Power BI ----------

class PowerBIClient:
    """对齐 powerbi.js PowerBIClient。msal 取 token + httpx 调 Fabric MCP。"""

    def __init__(self) -> None:
        env = get_env("POWERBI_CLIENT_ID", "POWERBI_CLIENT_SECRET", "POWERBI_TENANT_ID")
        self._client_id = env["POWERBI_CLIENT_ID"]
        self._client_secret = env["POWERBI_CLIENT_SECRET"]
        self._tenant_id = env["POWERBI_TENANT_ID"]
        self._app = msal.ConfidentialClientApplication(
            self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            client_credential=self._client_secret)

    def _token(self) -> str:
        res = self._app.acquire_token_for_client(scopes=[_SCOPE])
        token = res.get("access_token")
        if not token:
            raise DataSourceError(f"Power BI 获取 token 失败: {res.get('error_description') or res}")
        return token

    def _mcp_call(self, method: str, params: Any | None = None) -> dict[str, Any]:
        # 对齐 powerbi.js _mcpCall（含 202 轮询 + SSE/JSON 解析 + 401/403）。实现者按 JS 移植。
        token = self._token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }
        body = {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method}
        if params is not None:
            body["params"] = params
        # ... 用 httpx.Client 发 POST，处理 202 轮询（operation-location，1s 间隔，60s 超时→SkillTimeoutError）、
        #     401/403（DataSourceError 明确提示）、!ok（DataSourceError）、响应解析（先 json.loads，再退回 SSE data: 行）。
        # 返回解析后的 dict（JSON-RPC 结果对象）。
        ...  # 实现者补全，参照 powerbi.js:51-126

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._mcp_call("tools/list")
        return result.get("result", {}).get("tools", [])

    def get_schema(self, artifact_id: str) -> dict[str, Any]:
        _require_guid(artifact_id)
        return self._mcp_call("tools/call", {"name": "GetSemanticModelSchema", "arguments": {"artifactId": artifact_id}})

    def query(self, artifact_id: str, dax_queries: list[str], max_rows: int = 250) -> dict[str, Any]:
        _require_guid(artifact_id)
        if not dax_queries:
            raise ValidationError("至少需要 1 条 DAX 查询")
        if len(dax_queries) > 4:
            raise ValidationError("批量查询最多支持 4 条 DAX 语句")
        return self._mcp_call("tools/call", {"name": "ExecuteQuery",
                            "arguments": {"artifactId": artifact_id, "maxRows": max_rows, "daxQueries": dax_queries}})


def powerbi_list_models() -> list[Any]:
    return get_powerbi_models()


def powerbi_list_tools() -> list[dict[str, Any]]:
    return PowerBIClient().list_tools()


def powerbi_schema(artifact_id: str) -> dict[str, Any]:
    _require_guid(artifact_id)
    return PowerBIClient().get_schema(artifact_id)


def powerbi_query(artifact_id: str, dax_queries: list[str], max_rows: int = 250) -> dict[str, Any]:
    _require_guid(artifact_id)
    return PowerBIClient().query(artifact_id, dax_queries, max_rows)
```

> **执行注意（不是占位符）：** `_mcp_call` 的 `...` 处需要实现者按 `querying-data/scripts/lib/powerbi.js:51-126`（`_mcpCall` + `_parseResponse`）用 httpx 完整移植：POST → 若 202 读 `operation-location` 头轮询（`time.sleep(1)`，累计 60s 超时抛 `SkillTimeoutError`）→ 401/403 抛 `DataSourceError`（含三条排查提示）→ 其他非 ok 抛 `DataSourceError` → 响应文本先 `json.loads`，失败则按行找 `data:` 前缀解析，都失败抛 `DataSourceError("无法解析 Power BI MCP 端点返回的数据")`。其余代码用上面给出的。

- [ ] **Step 4: 加依赖到 `mcp/pyproject.toml`**

在现有 dependencies 列表追加（保留已有的 matplotlib 等）：

```toml
    "psycopg[binary]>=3.1",
    "msal>=1.28",
    "httpx>=0.27",
```

- [ ] **Step 5: 验证 import（不连真服务）**

```bash
cd mcp && python -c "from sda_mcp.skills import querying_data as q; print('ok', hasattr(q,'sql_query'), hasattr(q,'powerbi_query'))"
```
Expected: `ok True True`（仅 import，不发网络请求）。

- [ ] **Step 6: 提交**

```bash
git add mcp/sda_mcp/config.py mcp/sda_mcp/skills/querying_data.py mcp/sda_mcp/skills/querying_data_schema.sql mcp/pyproject.toml
git commit -m "feat(mcp): querying_data core (Hologres via psycopg + PowerBI via msal/httpx)"
```

---

## Task 2: mock 单元测试

**Files:** Test `mcp/tests/test_querying_data.py`

- [ ] **Step 1: 写测试（不连真服务，全部 mock）**

覆盖（实现者补全用例体，用 `monkeypatch` mock `HologresClient._connect` 与 `PowerBIClient._mcp_call`/`_token`）：

```python
"""querying_data 内核 mock 单元测试（离线，不连真服务）。"""
import pytest
from sda_mcp.errors import ConfigError, ValidationError, DataSourceError, SkillTimeoutError
from sda_mcp.skills import querying_data as q


# --- 校验 ---

def test_validate_dax_payload_ok():
    r = q.validate_dax_payload({"artifactId": "12345678-1234-1234-1234-123456789012",
                                "daxQueries": ["EVALUATE 'T'"], "maxRows": 100})
    assert r["max_rows"] == 100 and len(r["dax_queries"]) == 1


@pytest.mark.parametrize("payload", [
    {"artifactId": "not-a-guid", "daxQueries": ["x"]},
    {"artifactId": "12345678-1234-1234-1234-123456789012", "daxQueries": []},
    {"artifactId": "12345678-1234-1234-1234-123456789012", "daxQueries": ["a"] * 5},
    {"artifactId": "12345678-1234-1234-1234-123456789012", "daxQueries": ["a"], "maxRows": 0},
    {"artifactId": "12345678-1234-1234-1234-123456789012", "daxQueries": ["a"], "maxRows": 1001},
    {"artifactId": "12345678-1234-1234-1234-123456789012", "daxQueries": [123]},
])
def test_validate_dax_payload_rejects(payload):
    with pytest.raises(ValidationError):
        q.validate_dax_payload(payload)


def test_split_table_missing_dot():
    with pytest.raises(ValidationError):
        q._split_table("noschema")


def test_sql_query_empty_rejected():
    with pytest.raises(ValidationError):
        q.sql_query("   ")


# --- config 缺失 ---

def test_config_missing_raises(monkeypatch):
    # 让 get_env 找不到键 → ConfigError
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {}})
    with pytest.raises(ConfigError):
        q.HologresClient()  # __init__ 调 get_env


# --- Hologres query：列名规范化（mock 连接）---

def test_sql_query_normalizes_empty_column_names(monkeypatch):
    class FakeCursor:
        description = [
            type("D", (), {"name": "real_col", "type_code": 23})(),
            type("D", (), {"name": "", "type_code": 25})(),      # 空名 → col_1
        ]
        def execute(self, *a, **k): pass
        def fetchall(self): return [(1, "x"), (2, "y")]
        def fetchone(self): return (1,)
    class FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return FakeCursor()
    monkeypatch.setattr(q.HologresClient, "_connect", lambda self: FakeConn())
    monkeypatch.setattr(q.HologresClient, "__init__", lambda self: None)
    r = q.sql_query("SELECT 1")
    assert r.columns[0]["name"] == "real_col"
    assert r.columns[1]["name"] == "col_1"   # 空名已规范化
    assert r.row_count == 2
    assert not hasattr(r, "ok")


# --- Power BI：artifactId 校验 + mcp_call 行为（mock httpx）---

def test_powerbi_query_rejects_bad_artifact():
    with pytest.raises(ValidationError):
        q.powerbi_query("bad", ["EVALUATE 'T'"])


def test_powerbi_query_too_many_dax(monkeypatch):
    monkeypatch.setattr(q.PowerBIClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.PowerBIClient, "_mcp_call", lambda self, m, p=None: {"result": {}})
    with pytest.raises(ValidationError):
        q.powerbi_query("12345678-1234-1234-1234-123456789012", ["a"] * 5)
```

实现者另补 `_mcp_call` 的 HTTP 行为测试（mock `httpx.Client` 或 `PowerBIClient._mcp_call` 的内部 fetch）：
- 202 轮询 → 成功（mock 两次响应：第一次 202 带 operation-location，第二次 200 JSON）。
- 202 超时 → `SkillTimeoutError`（mock 永远 202，把 `_POLL_TIMEOUT_MS` 调小避免真等）。
- 401 → `DataSourceError` 且信息含鉴权排查提示。
- SSE 解析：响应不是纯 JSON，含 `data: {...}` 行 → 正确解析。
- 都用 monkeypatch 注入一个 fake httpx Client / 或直接 mock `PowerBIClient._mcp_call` 依赖的发送函数。

> 用 `monkeypatch.setattr(q.PowerBIClient, "_token", lambda self: "fake")` 跳过真 token 获取。

- [ ] **Step 2: 运行**

```bash
cd mcp && python -m pytest tests/test_querying_data.py -v
```
Expected: 全绿。

- [ ] **Step 3: 提交**

```bash
git add mcp/tests/test_querying_data.py
git commit -m "test(mcp): querying_data mock unit tests (validation, column normalize, httpx polling)"
```

---

## Task 3: 集成对照测试（env 门控）+ 导出 + 全量

- [ ] **Step 1: 写 `mcp/tests/test_querying_data_integration.py`（默认 skip）**

```python
"""querying_data 集成对照：连真服务跑 Python 内核 vs 原 Node CLI。
默认跳过；SDA_INTEGRATION=1 时启用（需 VPN + config.json 真凭证 + 原 Node CLI 可跑）。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用（需 VPN+凭证+Node CLI）")

REPO = Path(__file__).resolve().parent.parent.parent
NODE = ["node"]


def _node_query(args: list[str], stdin: str | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable.replace("python", "node"), str(REPO / "querying-data/scripts/query.js"), *args]
        if False else ["node", str(REPO / "querying-data/scripts/query.js"), *args],
        capture_output=True, text=True, timeout=90, input=stdin)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_sql_select_parity():
    from sda_mcp.skills.querying_data import sql_query
    sql = "SELECT 1 AS one, 'x' AS two"
    cli = _node_query(["sql", "query", "--sql", sql])
    cli.pop("source", None)
    core = sql_query(sql)
    # 比较列名与行数据（dataTypeID 因驱动不同可能差异，单独比对 name）
    assert [c["name"] for c in core.columns] == [c["name"] for c in cli["columns"]]
    assert core.rows == cli["rows"]


# powerbi 对照：实现者补 list-tools / schema / query 三个用例，结构同上（core 函数 vs _node_query powerbi ...）。
```

实现者补 powerbi 的对照用例（list-tools、schema、query），用真实 artifactId（从 config 的 powerbi-semantic-models 读第一个）。这些只在 SDA_INTEGRATION=1 下跑。

- [ ] **Step 2: 确认默认 skip**

```bash
cd mcp && python -m pytest tests/test_querying_data_integration.py -q
```
Expected: 全部 skipped（未设 SDA_INTEGRATION）。

- [ ] **Step 3: 导出 + 全量**

更新 `mcp/sda_mcp/skills/__init__.py`，追加：
```python
from sda_mcp.skills.querying_data import (
    sql_query, sql_schema, sql_test_connection, SqlResult,
    powerbi_list_models, powerbi_list_tools, powerbi_schema, powerbi_query,
)
```
并加入 `__all__`。

```bash
cd mcp && python -m pytest -q
```
Expected: 原 23 + querying_data mock 测试全绿（集成 skip 不计入失败）。

- [ ] **Step 4: 提交**

```bash
git add mcp/tests/test_querying_data_integration.py mcp/sda_mcp/skills/__init__.py
git commit -m "test(mcp): querying_data env-gated integration parity + export"
```

---

## 完成标准

- [ ] `sql_query`/`sql_schema`/`sql_test_connection` + `powerbi_*` 五个入口，去 CLI/`{ok}` 信封，失败抛 SkillError 子类。
- [ ] Hologres 空列名规范化（`col_{i}`）、Power BI 202 轮询/SSE/401-403 行为与原 JS 一致。
- [ ] mock 单元测试覆盖校验、列名规范化、HTTP 轮询/错误/SSE；离线全绿。
- [ ] 集成对照测试默认 skip，`SDA_INTEGRATION=1` 可跑 Python vs Node 对照。
- [ ] 共享 `config.py` 就位。
- [ ] 原 `querying-data/` 零改动。
- [ ] pyproject 含 psycopg/msal/httpx。
- [ ] 全量测试通过（集成 skip）。

---

## 待实测（集成测试开启时确认）

- Hologres 空字段名在 psycopg 下的真实表现（应用层 `col_{i}` 兜底应足够，但需真库确认不报错）。
- Power BI Fabric MCP 端点在 Python msal+httpx 下与 Node fetch 行为完全一致（token、轮询、SSE）。
