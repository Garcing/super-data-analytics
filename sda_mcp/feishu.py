"""飞书开放平台 REST 客户端（httpx 直连，tenant_access_token 鉴权）。

替代 lark-cli 子进程的读/删调用：docx↔markdown（读=原始块自序列化，写=官方 convert）、
drive 文件列表/删除、bitable 字段/记录。
对齐 VercelBlobClient 模式：失败抛 ConfigError(缺凭证)/ExternalAPIError(HTTP/code!=0)。

接口契约见 docs/superpowers/specs/2026-08-10-feishu-openapi-replace-lark-cli-design.md。
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import unquote as _unquote

import httpx

from sda_mcp.config import get_env
from sda_mcp.errors import ConfigError, ExternalAPIError, SkillError

_FEISHU_BASE = "https://open.feishu.cn"
_TIMEOUT = httpx.Timeout(30.0)
_TOKEN_REFRESH_MARGIN = 300  # 过期前 5 分钟刷新

# bitable 字段类型（开放平台用 int；lark-cli 用字符串名）
# 已用真实 base（BHINbLiOKa4rXDsLTlQcRwuSn9c）逐字段验证值结构（2026-08-10）：
#   Text(1)/SingleSelect(3) → 裸字符串；MultiSelect(4) → 字符串列表；
#   Formula(20)/Lookup(19) 文本结果 → [{text,type}] 片段数组（官方：查找引用本质=公式，value 同构）。
# 注意：这些常量被 sync 层（skills/retrieving_context_sync.py）import 做字段类型分派，
# 看似"未使用"实则跨模块契约，勿删。
_F_TEXT = 1
_F_NUMBER = 2
_F_SINGLE_SELECT = 3
_F_MULTI_SELECT = 4
_F_DATE = 5
_F_CHECKBOX = 7
_F_USER = 11
_F_PHONE = 13
_F_URL = 15
_F_ATTACHMENT = 17
_F_SINGLE_LINK = 18
_F_LOOKUP = 19
_F_FORMULA = 20
_F_DUPLEX_LINK = 21
_F_LOCATION = 22
_F_GROUP_CHAT = 23
_F_CREATED_TIME = 1001
_F_MODIFIED_TIME = 1002
_F_CREATED_USER = 1003
_F_MODIFIED_USER = 1004
_F_AUTO_NUMBER = 1005

# 模块级 token 缓存：FastMCP stateless 每次调用新建 client 实例，
# 跨调用复用 token 必须模块级。冗余并发刷新无害，不加锁。
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _reset_token_cache() -> None:
    """仅供测试：清 token 缓存。"""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


# --- docx 块 → markdown 自序列化（读路径）---
# 官方导出 docs/v1/content?content_type=markdown 对机器消费有三类保真缺陷
# （2026-08-26 / 2026-08-31 探针实证；docx 存储层块文本始终干净）：
#   1) " & < > 先 HTML 实体化（&#34; &amp; &lt; &gt;）；
#   2) &/# 前再叠一层 markdown 反斜杠转义（\&\#34;）；
#   3) 代码围栏内仍把斜体 run 序列化成 * 定界符（实测 24 个斜体 run 把
#      `select * from` 变成 `select ** *from`、`round(` 变成 `*round*(`）。
# 因此读路径不走导出端点，改由原始块自序列化：代码围栏逐字拼接 run 文本、
# 无视样式；围栏外只渲染 markdown 可往返的行内样式（bold/italic/inline_code/
# link），underline/strikethrough 丢样式保文本；段落内特殊字符不转义；
# 单元格内 "|" 与表格合并单元格不保证往返。块类型覆盖实测语义层文档全集
# （page/text/heading1-9/bullet/ordered/code/quote/divider/table+cell/
# quote_container），其余块类型与行内元素硬报错，拒绝静默降级。
_CODE_LANGUAGES = {56: "SQL"}  # 块 API CodeLanguage 枚举；56=SQL 已实测，其余按需增补

# 块类型 → 元素属性键（headings 3..11 动态映射 heading1..9）
_LINE_KEYS = {2: "text", 12: "bullet", 13: "ordered", 15: "quote"}
_LINE_PREFIX = {2: "", 12: "- ", 13: "1. ", 15: "> "}


def _render_runs(elements: list[dict] | None, *, verbatim: bool) -> str:
    """行内元素 → markdown 文本。verbatim=True（代码块内）逐字拼接、无视样式。"""
    parts: list[str] = []
    for el in elements or []:
        run = el.get("text_run")
        if run is None:
            kind = next(iter(el), "unknown")
            raise SkillError(f"文档包含暂不支持的行内元素 {kind}，无法无损转 markdown")
        text = run.get("content") or ""
        if verbatim:
            parts.append(text)
            continue
        style = run.get("text_element_style") or {}
        link = (style.get("link") or {}).get("url")
        if link:
            # 存储层 URL 为百分号编码（实测 https%3A%2F%2F...），解码后人类可读且与旧导出一致
            link = _unquote(link)
            text = f"[{text}]({link})"
        if style.get("inline_code"):
            text = f"`{text}`"
        if style.get("bold"):
            text = f"**{text}**"
        if style.get("italic"):
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts)


def _cell_text(cell: dict, by_id: dict[str, dict]) -> str:
    """表格单元格 → 单行文本（多段落以空格连接；仅支持 text 子块）。"""
    parts: list[str] = []
    for cid in cell.get("children") or []:
        child = by_id.get(cid)
        if child is None:
            raise SkillError(f"表格单元格子块 {cid} 缺失于 blocks 响应，无法无损转 markdown")
        if child.get("block_type") != 2:
            raise SkillError(
                f"表格单元格包含暂不支持的块类型 {child.get('block_type')}，无法无损转 markdown")
        parts.append(_render_runs(child.get("text", {}).get("elements"), verbatim=False))
    return " ".join(p for p in parts if p)


def _table_markdown(block: dict, by_id: dict[str, dict]) -> str:
    """表格块 → markdown 管道表格（cells 为行优先扁平 id 数组，实测于 2026-08-31）。"""
    table = block.get("table") or {}
    cols = (table.get("property") or {}).get("column_size") or 0
    cell_ids = table.get("cells") or block.get("children") or []
    if cols <= 0 or not cell_ids or len(cell_ids) % cols:
        raise SkillError(f"表格块 {block.get('block_id')} 行列结构异常，无法无损转 markdown")
    lines: list[str] = []
    for i in range(0, len(cell_ids), cols):
        texts = []
        for cid in cell_ids[i:i + cols]:
            cell = by_id.get(cid)
            if cell is None:
                raise SkillError(f"表格单元格 {cid} 缺失于 blocks 响应，无法无损转 markdown")
            texts.append(_cell_text(cell, by_id))
        lines.append("| " + " | ".join(texts) + " |")
    lines.insert(1, "| " + " | ".join(["---"] * cols) + " |")
    return "\n".join(lines)


def _block_markdown(block: dict, by_id: dict[str, dict]) -> str:
    """单个块 → markdown 片段（块间空行由调用方拼接）。"""
    t = block.get("block_type")
    if 3 <= t <= 11:  # heading1..9
        prop = block.get(f"heading{t - 2}") or {}
        return "#" * (t - 2) + " " + _render_runs(prop.get("elements"), verbatim=False)
    if t in _LINE_KEYS:
        prop = block.get(_LINE_KEYS[t]) or {}
        return _LINE_PREFIX[t] + _render_runs(prop.get("elements"), verbatim=False)
    if t == 14:  # code
        code = block.get("code") or {}
        lang = _CODE_LANGUAGES.get((code.get("style") or {}).get("language"), "")
        body = _render_runs(code.get("elements"), verbatim=True)
        if body and not body.endswith("\n"):
            body += "\n"
        return f"```{lang}\n{body}```"
    if t == 22:  # divider
        return "---"
    if t == 34:  # quote_container
        lines: list[str] = []
        for cid in block.get("children") or []:
            child = by_id.get(cid)
            if child is None:
                raise SkillError(f"引用容器子块 {cid} 缺失于 blocks 响应，无法无损转 markdown")
            for line in _block_markdown(child, by_id).splitlines() or [""]:
                lines.append("> " + line)
        return "\n".join(lines)
    if t == 31:  # table
        return _table_markdown(block, by_id)
    raise SkillError(
        f"文档包含暂不支持的块类型 block_type={t}（block_id={block.get('block_id')}），"
        "无法无损转 markdown；请把该块改为文本/列表/代码块/表格，或为序列化器补充该类型")


def blocks_to_markdown(blocks: list[dict], title: str) -> str:
    """原始块列表 + 文档标题 → markdown（get_doc_markdown 的序列化核心）。

    标题来自文档元数据（GET /docx/v1/documents，不在块里），渲染为 `# 标题`。
    """
    by_id = {b.get("block_id"): b for b in blocks}
    root = next((b for b in blocks if b.get("block_type") == 1), None)
    if root is None:
        raise ExternalAPIError("blocks 响应缺 page 根块，无法序列化 markdown")
    chunks: list[str] = []
    for cid in root.get("children") or []:
        block = by_id.get(cid)
        if block is None:
            raise SkillError(f"顶层子块 {cid} 缺失于 blocks 响应，无法无损转 markdown")
        md = _block_markdown(block, by_id)
        if md:
            chunks.append(md)
    head = f"# {title}\n\n" if title else ""
    return head + "\n\n".join(chunks)


def _get_tenant_token() -> str:
    """返回 tenant_access_token；模块级缓存，剩 ≤5min 刷新。"""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    env = get_env("FEISHU_APP_ID", "FEISHU_APP_SECRET")
    try:
        resp = httpx.post(
            f"{_FEISHU_BASE}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # ValueError 覆盖 json.JSONDecodeError：网关返回非 JSON 200 响应（如 Caddy HTML 错误页）时，
        # resp.json() 抛 ValueError（非 httpx.HTTPError），需归一成 ExternalAPIError。
        raise ExternalAPIError(f"获取 tenant_access_token 失败: {exc}") from exc
    if data.get("code") != 0:
        raise ExternalAPIError(f"获取 tenant_access_token 失败: {data.get('msg')}")
    token = data.get("tenant_access_token")
    if not token:
        raise ExternalAPIError("tenant_access_token 响应缺 token 字段")
    expire = int(data.get("expire", 7200))
    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + expire - _TOKEN_REFRESH_MARGIN
    return token


def _next_token(data: dict[str, Any]) -> str | None:
    """drive 返回 next_page_token，bitable 返回 page_token；兼容两者。"""
    payload = data.get("data") or data
    return payload.get("next_page_token") or payload.get("page_token")


class FeishuClient:
    """飞书开放平台 REST 客户端。"""

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                 json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = _get_tenant_token()
        try:
            resp = httpx.request(
                method, f"{_FEISHU_BASE}{path}", params=params, json=json_body,
                headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError 覆盖 json.JSONDecodeError：非 JSON 200 响应（网关 HTML 错误页）归一为 ExternalAPIError。
            raise ExternalAPIError(f"飞书 API {method} {path} 失败: {exc}") from exc
        # 业务码校验在 _request 内统一做（_check 抛 ExternalAPIError，非 HTTPError，
        # 不会被上面的 except 捕获）。各端点方法的 _check 调用因此成为幂等无副作用的二次校验。
        self._check(data, path)
        return data

    @staticmethod
    def _check(data: dict[str, Any], path: str) -> None:
        if data.get("code") != 0:
            msg = data.get("msg") or data.get("message") or "未知错误"
            raise ExternalAPIError(f"飞书 API {path} 返回错误: {str(msg)[:300]}")

    # --- docx → markdown（读：元数据标题 + 原始块自序列化）---
    def get_doc_markdown(self, doc_token: str) -> str:
        """读 docx 文档为 markdown。不走官方导出端点（三类污染，见模块 docstring），
        代码围栏内容逐字保真、可直接执行。"""
        meta_path = f"/open-apis/docx/v1/documents/{doc_token}"
        meta = self._request("GET", meta_path)
        self._check(meta, meta_path)
        title = ((meta.get("data") or {}).get("document") or {}).get("title") or ""
        blocks = self.list_blocks(doc_token)
        return blocks_to_markdown(blocks, title)

    # --- drive 文件列表（读）---
    def list_folder_files(self, folder_token: str) -> list[dict[str, Any]]:
        """列出文件夹下文件（含子文件夹）。GET /open-apis/drive/v1/files，自动翻页。"""
        path = "/open-apis/drive/v1/files"
        files: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"folder_token": folder_token, "page_size": 200}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            files.extend(payload.get("files") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return files

    # --- drive 删除 ---
    def delete_file(self, file_token: str, file_type: str = "docx") -> None:
        """删除文件。DELETE /open-apis/drive/v1/files/{file_token}?type=。"""
        path = f"/open-apis/drive/v1/files/{file_token}"
        data = self._request("DELETE", path, params={"type": file_type})
        self._check(data, path)

    # --- bitable 数据表（读）---
    def list_tables(self, app_token: str) -> list[dict[str, Any]]:
        """列出多维表下的全部数据表。GET /open-apis/bitable/v1/apps/{app_token}/tables。

        返回 [{table_id, name, revision}, ...]，自动翻页。给 app_token 即可发现表，
        无需事先知道 table_id。
        """
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items

    # --- bitable 字段（读，原始）---
    def list_bitable_fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        """列出多维表字段（原始，含 auto_number；domain 过滤由调用方做）。"""
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items

    # --- bitable 记录（读，原始）---
    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        """列多维表全部记录（原始 items，含 record_id + fields map；值简化由调用方做）。

        走官方推荐的 POST /records/search（无 filter 即全量）；旧 GET /records 已被
        飞书标记为历史接口、不推荐使用。响应仍是 data.items/has_more/page_token。
        """
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 500}
            if page_token:
                body["page_token"] = page_token
            data = self._request("POST", path, json_body=body)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items

    # --- 写路径（markdown → docx）---
    def convert_markdown_to_blocks(self, markdown: str) -> tuple[list[dict[str, Any]], list[str]]:
        """markdown → (blocks, first_level_block_ids)。已剥表格 table.property.merge_info（只读）。
        POST /open-apis/docx/v1/documents/blocks/convert。"""
        path = "/open-apis/docx/v1/documents/blocks/convert"
        data = self._request("POST", path, json_body={
            "content_type": "markdown", "content": markdown})
        self._check(data, path)
        payload = data.get("data") or {}
        blocks = payload.get("blocks") or []
        for b in blocks:
            if b.get("block_type") == 31:  # table
                (b.get("table", {}).get("property", {}) or {}).pop("merge_info", None)
        first_level = payload.get("first_level_block_ids") or []
        return blocks, first_level

    def create_doc(self, folder_token: str, title: str) -> str:
        """建空 docx 文档，返回 document_id。POST /open-apis/docx/v1/documents。"""
        path = "/open-apis/docx/v1/documents"
        data = self._request("POST", path, json_body={"folder_token": folder_token, "title": title})
        self._check(data, path)
        doc_id = (data.get("data") or {}).get("document", {}).get("document_id")
        if not doc_id:
            raise ExternalAPIError(f"创建文档失败：响应缺 document_id: {str(data)[:200]}")
        return doc_id

    def insert_descendants(self, doc_id: str, blocks: list[dict[str, Any]],
                           children_id: list[str]) -> None:
        """批量插入嵌套块（表格+内容一次到位）。POST .../blocks/{doc_id}/descendant。
        blocks 为 convert 返回的扁平块（带临时 ID），children_id 为顶层块 ID 列表。"""
        path = f"/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant"
        data = self._request("POST", path, json_body={
            "children_id": children_id, "descendants": blocks})
        self._check(data, path)

    def list_blocks(self, doc_id: str) -> list[dict[str, Any]]:
        """列出文档全部块（自动翻页，page_size=500）。GET .../blocks。"""
        path = f"/open-apis/docx/v1/documents/{doc_id}/blocks"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items

    def delete_all_children(self, doc_id: str) -> None:
        """清空文档正文（删除根 page 块的所有直接子块）。
        GET blocks 取根(block_type==1) children 数 N → batch_delete 0..N。"""
        blocks = self.list_blocks(doc_id)
        root = next((b for b in blocks if b.get("block_type") == 1), None)
        n = len((root or {}).get("children") or [])
        if n == 0:
            return
        path = f"/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children/batch_delete"
        data = self._request("DELETE", path, json_body={"start_index": 0, "end_index": n})
        self._check(data, path)
