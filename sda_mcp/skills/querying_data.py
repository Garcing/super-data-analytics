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

from sda_mcp.config import get_env
from sda_mcp.errors import ConfigError, DataSourceError, SkillTimeoutError, ValidationError

_MCP_URL = "https://api.fabric.microsoft.com/v1/mcp/powerbi"
_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_POLL_TIMEOUT_MS = 60_000
_POLL_INTERVAL_S = 1.0
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
# 建连失败重试一次：吸收 VPN 转发器随 openvpn 微重置产生的瞬断（查询只读且
# 每次新建连接，建连期重试安全；2026-08-26 QA 实测 ~11% sql_query 因此抖动）。
_CONNECT_RETRIES = 1
_RETRY_DELAY_S = 0.5


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
            f"password={env['HOLOGRES_PASSWORD']} connect_timeout=20")

    def _connect(self) -> psycopg.Connection:
        last_exc: psycopg.OperationalError | None = None
        for attempt in range(_CONNECT_RETRIES + 1):
            try:
                return psycopg.connect(self._dsn)
            except psycopg.OperationalError as exc:
                last_exc = exc
                if attempt < _CONNECT_RETRIES:
                    time.sleep(_RETRY_DELAY_S)
        raise DataSourceError(f"无法连接 Hologres（检查 VPN/白名单/凭证）: {last_exc}") from last_exc

    def test_connection(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def query(self, sql: str) -> SqlResult:
        with self._connect() as conn, conn.cursor() as cur:
            try:
                # Enforce the MCP tool's read-only contract at the database
                # transaction level instead of relying on SQL text parsing.
                cur.execute("SET TRANSACTION READ ONLY")
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
            rows = cur.fetchall()
            if not rows and not self._table_exists(conn, table, schema):
                # QA 2026-08-26:不存在表/逻辑语义表静默返回空列,误导调用方
                # "表存在但没结构"——必须显式报错并指引逻辑表的正确路径。
                raise ValidationError(
                    f"表 {schema}.{table} 在 Hologres 中不存在。请检查拼写；语义层"
                    "“实现方式=sql_query”的逻辑表不落物理库，应通过 retrieve_doc_read "
                    "读取其 SQL 文档获取底层物理表。")
        return [dict(zip(cols, r)) for r in rows]

    @staticmethod
    def _table_exists(conn, table: str, schema: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s LIMIT 1",
                (schema, table))
            return bool(cur.fetchone())


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


_DAX_ERROR_TEXT_RE = re.compile(r"(?i)^\s*dax query .*(error|failed)")


def _normalize_powerbi_result(result: Any) -> Any:
    """解码 Microsoft MCP 结果 content[].text 的内嵌 JSON,并统一错误信封。

    QA 2026-08-26 发现:JSON-RPC 信封内 text 块再包一层 JSON 字符串(中文全
    \\uXXXX 转义,费 token);错误信封三态不一致(协议 error 对象 / Answer JSON /
    纯文本 DAX 错误)。统一为:
    - 协议级 error 对象或 Answer.Status=error 或纯文本 DAX 错误 → DataSourceError;
    - text 块可解析为 JSON 对象/数组 → 解码后替换,调用方免二次解析。
    """
    if not isinstance(result, dict):
        return result
    if "error" in result and "result" not in result:
        err = result["error"] or {}
        raise DataSourceError(f"Power BI 调用失败: {err.get('message') or err}")
    content = (result.get("result") or {}).get("content")
    if not isinstance(content, list):
        return result
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if stripped[:1] in "{[":
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                answer = decoded.get("Answer")
                if isinstance(answer, dict) and str(answer.get("Status", "")).lower() == "error":
                    inner = answer.get("Error") or {}
                    raise DataSourceError(
                        f"Power BI 执行失败: "
                        f"{answer.get('Message') or inner.get('Message') or stripped[:300]}")
                block["text"] = decoded
            elif decoded is not None:
                block["text"] = decoded
        elif _DAX_ERROR_TEXT_RE.match(stripped):
            raise DataSourceError(f"DAX 查询失败: {stripped[:500]}")
    return result


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
        return _normalize_powerbi_result(self._mcp_call(
            "tools/call", {"name": "GetSemanticModelSchema", "arguments": {"artifactId": artifact_id}}))

    def query(self, artifact_id: str, dax_queries: list[str], max_rows: int = 250) -> dict[str, Any]:
        _require_guid(artifact_id)
        if not dax_queries:
            raise ValidationError("至少需要 1 条 DAX 查询")
        if len(dax_queries) > 4:
            raise ValidationError("批量查询最多支持 4 条 DAX 语句")
        return _normalize_powerbi_result(self._mcp_call(
            "tools/call", {"name": "ExecuteQuery",
                           "arguments": {"artifactId": artifact_id, "maxRows": max_rows, "daxQueries": dax_queries}}))


def powerbi_list_tools() -> list[dict[str, Any]]:
    return PowerBIClient().list_tools()


def powerbi_schema(artifact_id: str) -> dict[str, Any]:
    _require_guid(artifact_id)
    return PowerBIClient().get_schema(artifact_id)


def powerbi_query(artifact_id: str, dax_queries: list[str], max_rows: int = 250) -> dict[str, Any]:
    _require_guid(artifact_id)
    return PowerBIClient().query(artifact_id, dax_queries, max_rows)
