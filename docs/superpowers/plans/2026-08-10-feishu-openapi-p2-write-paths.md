# 飞书开放平台 API 替换 lark-cli — P2（写路径）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用飞书开放平台 API 实现 markdown→docx 写路径（`template_create` / `template_update`），迁移完 `using_templates` 最后两个 lark-cli 调用，并**删除 `LarkCliClient` 类**。P2 后 using_templates 完全不再依赖 lark-cli。

**Architecture:** 复用 P1 的 `FeishuClient`，新增 4 个写端点方法（convert / create_doc / insert_descendants / delete_all_children）+ 一个 list_blocks 辅助。`template_create/update` 改走新端点。**核心配方已用真实飞书验证**（含表格）：convert 输出的扁平 blocks + `first_level_block_ids` 直接喂「创建嵌套块」descendant 接口（仅需剥 `table.property.merge_info`），表格单元格内容一次到位。

**Tech Stack:** Python 3.12、httpx、pytest、飞书开放平台 REST（`docx/v1/documents/blocks/convert`、`docx/v1/documents`、`docx/v1/documents/{id}/blocks/{id}/descendant`、`.../children/batch_delete`、`.../blocks` list）。

**设计依据：** `docs/superpowers/specs/2026-08-10-feishu-openapi-replace-lark-cli-design.md`（§4.2 写路径）。

**探测结论（2026-08-10，真实 base 验证）：**
- `POST /open-apis/docx/v1/documents/blocks/convert` body `{content_type:"markdown", content}` → `{data:{blocks:[...], first_level_block_ids:[...]}}`。blocks 扁平、带临时 `block_id`/`parent_id`/`children`；table(31) 块含只读 `table.property.merge_info`。
- `POST /open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant`（**创建嵌套块**）body **`{children_id: first_level_block_ids, descendants: blocks}`**（blocks 保留 temp ID + parent/children，仅剥 merge_info）→ 一次插入完整子树（表格+单元格内容）。单次 ≤1000 块。
- `POST /open-apis/docx/v1/documents` body `{folder_token, title}` → `{data:{document:{document_id}}}`（建空文档）。
- `GET /open-apis/docx/v1/documents/{doc_id}/blocks` → `{data:{items:[...]}}`；找 `block_type==1`（page 根），其 `children` 长度 = 顶层子块数 N。
- `DELETE .../blocks/{doc_id}/children/batch_delete` body `{start_index:0, end_index:N}` → 清空正文。
- **错误码**：`1770001 invalid param` = 传了只读字段（如 merge_info）；`1770029 block not support to create` = table_cell 不能单独 create-children（用 descendant 规避）；`99992424 field validation failed` = descendant body 字段名错（正确是 `children_id`+`descendants`）。

**铁律：** 原skill 目录树零改动；新代码只放 `mcp/`。`cd mcp && python -m pytest -q` 全绿。

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `mcp/sda_mcp/feishu.py` | 新增 4 写端点 + list_blocks 辅助 | 修改（追加方法） |
| `mcp/tests/test_feishu.py` | 新方法的 mock 测试 | 修改（追加测试） |
| `mcp/sda_mcp/skills/using_templates.py` | create/update 改走 FeishuClient；**删 LarkCliClient 类** | 修改 |
| `mcp/tests/test_using_templates.py` | create/update 测试改 mock FeishuClient；删 LarkCliClient 测试 | 修改 |

**FeishuClient 新增方法契约：**
```python
def convert_markdown_to_blocks(self, md: str) -> tuple[list[dict], list[str]]
    # → (blocks, first_level_block_ids)；已剥 table.property.merge_info
def create_doc(self, folder_token: str, title: str) -> str
    # → document_id
def insert_descendants(self, doc_id: str, blocks: list[dict], children_id: list[str]) -> None
    # POST .../blocks/{doc_id}/descendant body {children_id, descendants}
def list_blocks(self, doc_id: str) -> list[dict]
    # GET .../blocks → items[]
def delete_all_children(self, doc_id: str) -> None
    # list_blocks → 根(page,block_type==1) children 数 N → batch_delete 0..N
```

---

## Task 1: FeishuClient 写端点（convert / create_doc / insert_descendants / list_blocks / delete_all_children）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

- [ ] **Step 1: 写失败测试**

追加到 `mcp/tests/test_feishu.py`（沿用文件里的 `_Resp` 和 monkeypatch `_get_tenant_token` 模式）：
```python
# --- 写端点 ---

def test_convert_strips_table_merge_info(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}
    table_block = {"block_id": "b1", "block_type": 31, "children": ["c1"],
                   "table": {"cells": ["c1"], "property": {"row_size": 1, "column_size": 1,
                                                            "merge_info": [{"col_span": 1, "row_span": 1}]}}}
    def _req(method, url, json_body=None, **k):
        captured["body"] = json_body
        return _Resp({"code": 0, "data": {"blocks": [table_block], "first_level_block_ids": ["b1"]}})
    monkeypatch.setattr(f.httpx, "request", _req)
    blocks, fl = f.FeishuClient().convert_markdown_to_blocks("# x\n")
    assert fl == ["b1"]
    assert captured["body"] == {"content_type": "markdown", "content": "# x\n"}
    # merge_info 已被剥
    assert "merge_info" not in blocks[0]["table"]["property"]


def test_create_doc_returns_document_id(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 0, "data": {"document": {"document_id": "DOCNEW"}}}))
    assert f.FeishuClient().create_doc("FOLDER", "标题") == "DOCNEW"


def test_insert_descendants_payload(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}
    def _req(method, url, json_body=None, **k):
        captured["url"] = url
        captured["body"] = json_body
        return _Resp({"code": 0, "data": {"document_revision_id": 2}})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().insert_descendants("DOC", [{"block_type": 2}], ["b1"])
    assert captured["url"].endswith("/blocks/DOC/descendant")
    assert captured["body"] == {"children_id": ["b1"], "descendants": [{"block_type": 2}]}


def test_list_blocks_returns_items(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"items": [{"block_id": "P", "block_type": 1, "children": ["a", "b", "c"]},
                                      {"block_id": "a", "block_type": 2}]}}))
    items = f.FeishuClient().list_blocks("DOC")
    assert len(items) == 2
    assert items[0]["block_type"] == 1


def test_delete_all_children_uses_root_child_count(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []
    def _req(method, url, params=None, json_body=None, **k):
        calls.append((method, url, json_body))
        if url.endswith("/blocks"):
            return _Resp({"code": 0, "data": {"items": [
                {"block_id": "DOC", "block_type": 1, "children": ["a", "b", "c"]}]}})
        return _Resp({"code": 0})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_all_children("DOC")
    # 第二次调用应是 batch_delete，end_index=3
    assert calls[1][0] == "DELETE"
    assert "batch_delete" in calls[1][1]
    assert calls[1][2] == {"start_index": 0, "end_index": 3}


def test_delete_all_children_noop_when_empty(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []
    def _req(method, url, params=None, json_body=None, **k):
        calls.append(url)
        if url.endswith("/blocks"):
            return _Resp({"code": 0, "data": {"items": [
                {"block_id": "DOC", "block_type": 1, "children": []}]}})
        return _Resp({"code": 0})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_all_children("DOC")
    assert len(calls) == 1  # 根无子块 → 不调 batch_delete
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k "convert_strips or create_doc or insert_descendants or list_blocks or delete_all_children" -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 加实现**

在 `mcp/sda_mcp/feishu.py` 的 `FeishuClient` 类内（`list_bitable_records` 之后）追加：
```python
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
        """列出文档全部块。GET .../blocks。"""
        path = f"/open-apis/docx/v1/documents/{doc_id}/blocks"
        data = self._request("GET", path)
        self._check(data, path)
        return (data.get("data") or {}).get("items") or []

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
```
> 注：`_request` 已支持 `json_body` 参数（P1 实现）。`_request` 内部统一 `_check`，方法内再 `_check` 为幂等二次校验（P1 既定）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -v`
Expected: PASS（全部，含新 6 个）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient 写端点 — convert/create_doc/insert_descendants/delete_all_children"
```

---

## Task 2: 迁移 template_create / template_update + 删 LarkCliClient

**Files:**
- Modify: `mcp/sda_mcp/skills/using_templates.py`
- Test: `mcp/tests/test_using_templates.py`

- [ ] **Step 1: 改测试**

在 `mcp/tests/test_using_templates.py`：
1. **删除**全部 LarkCliClient 内部测试：`test_lark_bin_missing_raises_config`、`test_lark_nonzero_raises_external`、`test_exec_caches_identity`、`test_exec_falls_back_to_bot`（LarkCliClient 类即将删除）。
2. **删除** `_fake_run_factory` helper（不再用 subprocess mock）。
3. **重写** create/update 测试 mock `FeishuClient`：
```python
def test_create_with_content_calls_feishu(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    calls = []
    monkeypatch.setattr(t.FeishuClient, "create_doc", lambda self, f, ti: calls.append(("create_doc", f, ti)) or "NEWDOC")
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: ([{"block_type": 2}], ["b1"]))
    monkeypatch.setattr(t.FeishuClient, "insert_descendants",
                        lambda self, did, bl, cid: calls.append(("insert", did, bl, cid)))
    r = t.create_template("播报", content="# 播报\n内容")
    assert r.document_id == "NEWDOC" and r.title == "播报"
    assert calls[0][0] == "create_doc" and calls[0][1] == "F"
    assert calls[1][0] == "insert" and calls[1][1] == "NEWDOC"


def test_create_no_content_skips_insert(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    calls = []
    monkeypatch.setattr(t.FeishuClient, "create_doc", lambda self, f, ti: "NEWDOC")
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: (calls.append(("convert", md)), ([], []))[1])
    r = t.create_template("空模板")
    assert r.document_id == "NEWDOC"
    assert calls == []  # 无 content 不 convert / 不 insert


def test_create_requires_title():
    with pytest.raises(t.ValidationError):
        t.create_template("")


def test_update_overwrite_calls_feishu(monkeypatch):
    calls = []
    monkeypatch.setattr(t.FeishuClient, "delete_all_children", lambda self, did: calls.append(("del", did)))
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: ([{"block_type": 2}], ["b1"]))
    monkeypatch.setattr(t.FeishuClient, "insert_descendants",
                        lambda self, did, bl, cid: calls.append(("insert", did)))
    r = t.update_template("DOC", "新内容")
    assert r.updated is True and r.document_id == "DOC"
    assert calls[0] == ("del", "DOC")
    assert calls[1] == ("insert", "DOC")


def test_update_requires_content():
    with pytest.raises(t.ValidationError):
        t.update_template("DOC", "")
```
> 保留 list/read/delete 测试（P1 已 mock FeishuClient）+ delete 密码门测试不动。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_using_templates.py -v`
Expected: FAIL（旧 create/update 测试已删；新测试因 LarkCliClient 仍在/方法未改而状态不一）

- [ ] **Step 3: 改实现**

在 `mcp/sda_mcp/skills/using_templates.py`：
1. **删除整个 `LarkCliClient` 类**（含 `_run`/`_exec`/`_temp_dir`/`_cleanup`/`_write_temp_content`）。P2 后无引用。
2. **删除** 仅 LarkCliClient 用的 import：`import os`、`import subprocess`、`import tempfile`、`from pathlib import Path`、`_LARK_BIN`、`_TIMEOUT`、`_PAGE_SIZE`，以及 `from sda_mcp.errors import ... ExternalAPIError`（确认 create/update 重写后不再用；ValidationError/ConfigError 仍需保留）。grep 确认每个 import 无其他用途再删。
3. **重写** `create_template`：
```python
def create_template(title: str, content: str | None = None) -> CreateResult:
    if not title:
        raise ValidationError("title 不能为空")
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = FeishuClient()
    doc_id = client.create_doc(folder_token, title)
    if content is not None:
        if not isinstance(content, str) or not content:
            raise ValidationError("content 不能为空")
        blocks, children_id = client.convert_markdown_to_blocks(content)
        if blocks:
            client.insert_descendants(doc_id, blocks, children_id)
    return CreateResult(document_id=doc_id, title=title)
```
4. **重写** `update_template`（覆盖语义：删全部子块 → 插入新内容）：
```python
def update_template(doc_id: str, content: str) -> UpdateResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 不能为空")
    client = FeishuClient()
    client.delete_all_children(doc_id)
    blocks, children_id = client.convert_markdown_to_blocks(content)
    if blocks:
        client.insert_descendants(doc_id, blocks, children_id)
    return UpdateResult(updated=True, document_id=doc_id)
```
5. 更新模块 docstring：去掉"写路径暂留 lark-cli"，改为"全部走 FeishuClient"。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_using_templates.py -v`
Expected: PASS（全部；LarkCliClient 测试已删，create/update 走 FeishuClient）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/skills/using_templates.py mcp/tests/test_using_templates.py
git commit -m "refactor(mcp): template_create/update 改用 FeishuClient（删 LarkCliClient）"
```

---

## Task 3: 全量回归 + 集成冒烟

**Files:** 无代码改动（仅验证）

- [ ] **Step 1: 全量单元测试**

Run: `cd mcp && python -m pytest -q`
Expected: 全绿（P1 后 130；P2 新增 feishu 6 个 - 删 LarkCliClient 4 个 + create/update 测试调整，净增约 2）。

- [ ] **Step 2: 集成冒烟（真实飞书，自建自删）**

Run:
```bash
cd mcp && python -c "
from sda_mcp.config import load_config
from sda_mcp.feishu import FeishuClient
cfg=load_config(); folder=cfg['env']['FEISHU_TEMPLATE_FOLDER_TOKEN']
c=FeishuClient()
# create with table
md='# 冒烟\n\n| a | b |\n|---|---|\n| 1 | 2 |\n'
did=c.create_doc(folder,'P2冒烟-临时')
blocks,fl=c.convert_markdown_to_blocks(md); c.insert_descendants(did,blocks,fl)
print('created', did)
# readback
import urllib.request,json
tok=__import__('sda_mcp.feishu',fromlist=['_get_tenant_token']).__dict__
print('readback has table:', '<table>' in __import__('urllib.request',fromlist=['urlopen']).urlopen(urllib.request.Request('https://open.feishu.cn/open-apis/docs/v1/content?doc_token='+did+'&doc_type=docx&content_type=markdown',headers={'Authorization':'Bearer '+__import__('sda_mcp.feishu',fromlist=['_get_tenant_token'])._get_tenant_token()})).read().decode())
# overwrite
c.delete_all_children(did); blocks,fl=c.convert_markdown_to_blocks('# 新\n\n无表格\n'); c.insert_descendants(did,blocks,fl)
print('overwrite ok')
# cleanup
c.delete_file(did,'docx'); print('deleted')
"
```
Expected: created + readback has table: True + overwrite ok + deleted。
> 也可直接用 MCP 工具 `template_create`/`template_update`/`template_read` 端到端测（本机 Claude 已配 sda MCP）。

- [ ] **Step 3: 提交（若有测试微调）**

```bash
git add -A && git commit -m "test(mcp): P2 全量回归 + 集成冒烟通过" || echo "nothing to commit"
```

---

## 完成标准（P2）

- `cd mcp && python -m pytest -q` 全绿。
- `template_create` / `template_update` 走 FeishuClient，**`LarkCliClient` 类已删除**。
- using_templates.py 不再 `import subprocess`/`os`/`tempfile`/`shutil`，无 lark-cli 引用。
- 集成冒烟：真实飞书 create（含表格）→ readback 有表格 → overwrite → 删除，全程 OK。
- **P2 后 lark-cli 在 using_templates 完全消失**（仅 Docker 层还留，P3 物理删）。

## 后续

- **P3**：Dockerfile 删 Node/npm/lark-cli + compose 删两个密钥卷 + 更新 README/CLAUDE.md/踩坑表（部署简化落地）。此时整个 MCP 服务不再依赖 lark-cli。
