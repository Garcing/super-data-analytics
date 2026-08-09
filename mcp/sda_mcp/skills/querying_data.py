"""querying_data 内核：Hologres(SQL) + Power BI(DAX)，从原 Node CLI 移植。

去 CLI/三态/{ok} 信封；失败抛 SkillError（ConfigError/ValidationError/DataSourceError）。
行为对齐 querying-data/scripts/{query.js, lib/sql.js, lib/powerbi.js}。
"""
from __future__ import annotations

import importlib.resources
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import msal
import psycopg

from sda_mcp.config import get_env, get_powerbi_models
from sda_mcp.errors import ConfigError, DataSourceError, SkillTimeoutError, ValidationError

_MCP_URL = "https://api.fabric.microsoft.com/v1/mcp/powerbi"
_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_POLL_TIMEOUT_MS = 60_000
_POLL_INTERVAL_S = 1.0
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@dataclass
class SqlResult:
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int


def _require_guid(artifact_id: str) -> None:
    if not artifact_id or not _GUID_RE.match(str(artifact_id)):
        raise ValidationError(
            f'artifactId 格式错误 "{artifact_id}"，应为 GUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')


def validate_dax_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
    idx = arg.find(".")
    if idx == -1:
        raise ValidationError(f'参数格式错误: "{arg}"，应为 schema.table')
    return arg[:idx], arg[idx + 1:]


class HologresClient:
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
            names = [c["name"] for c in columns]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
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


class PowerBIClient:
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
            raise DataSourceError(
                f"Power BI 获取 token 失败: {res.get('error_description') or res}")
        return token

    def _mcp_call(self, method: str, params: Any | None = None) -> dict[str, Any]:
        """Port of powerbi.js _mcpCall + _parseResponse (51-126) using httpx. Contract:
        POST _MCP_URL with JSON-RPC body {jsonrpc:'2.0', id:<epoch ms>, method, params?}, headers
        Content-Type application/json, Authorization Bearer <token>, Accept 'application/json, text/event-stream'.
        202 polling: read 'operation-location' header (missing → DataSourceError('收到 202 但缺少 operation-location 头'));
        sleep _POLL_INTERVAL_S then GET that location with same headers; if still 202 past _POLL_TIMEOUT_MS total → SkillTimeoutError.
        401/403 → DataSourceError with 3 hints (1 Azure AD 应用已授 Power BI 权限 2 已管理员同意 3 租户ID 正确) + response text[:300].
        other non-ok → DataSourceError(f'HTTP {status}: {text[:500]}').
        Parse response text: json.loads whole; else split '\\n', find 'data:' prefix, json.loads the rest; else DataSourceError('无法解析 Power BI MCP 端点返回的数据'). Return parsed dict.
        """
        token = self._token()
        request_id = int(time.time() * 1000)

        body: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            body["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }

        deadline = time.monotonic() + _POLL_TIMEOUT_MS / 1000.0
        with httpx.Client(timeout=httpx.Timeout(_POLL_TIMEOUT_MS / 1000.0)) as client:
            resp = client.post(_MCP_URL, headers=headers, json=body)

            # 202 轮询
            while resp.status_code == 202 and time.monotonic() < deadline:
                location = resp.headers.get("operation-location")
                if not location:
                    raise DataSourceError("收到 202 状态码但缺少 operation-location 头")
                time.sleep(_POLL_INTERVAL_S)
                resp = client.get(location, headers=headers)

            if resp.status_code == 202:
                raise SkillTimeoutError(f"查询超时（{_POLL_TIMEOUT_MS // 1000}秒）")

            if resp.status_code in (401, 403):
                text = resp.text
                raise DataSourceError(
                    f"HTTP {resp.status_code}: Token 无效或权限不足\n"
                    "请检查: 1) Azure AD 应用已授予 Power BI API 权限 2) 已完成管理员同意 3) 租户ID 正确\n"
                    f"详情: {text[:300]}"
                )

            if resp.status_code >= 400:
                text = resp.text
                raise DataSourceError(f"HTTP {resp.status_code}: {text[:500]}")

        return self._parse_response(resp.text)

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        for line in text.split("\n"):
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        raise DataSourceError("无法解析 Power BI MCP 端点返回的数据")

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
