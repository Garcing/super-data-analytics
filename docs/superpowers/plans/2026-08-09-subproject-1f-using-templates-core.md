# 子项目 1.F 实现计划：using_templates 内核（飞书模板 lark-cli 封装）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 `using-templates/scripts/templates.js`（Node CLI）移植成干净 Python 内核，管理飞书个人文件夹里的报告模板（list/read/create/update/delete）。原脚本封装的是外部 `lark-cli` 二进制，**Python 内核继续以子进程调用 lark-cli**（lark-cli 是独立二进制，不重写），只把 Node 那层壳换成 Python，并去 CLI/三态/scratch 临时文件/`{ok}` 信封。

**Architecture:** 单文件 `using_templates.py`。`LarkCliClient` 封装子进程：`lark-cli` + `--as user`，失败回退 `--as bot`，命中后实例级缓存身份（同 Node 的 `resolvedIdentity`）。lark-cli 的 `@文件` 引用必须是 cwd 内相对路径 → 用 `tempfile.mkdtemp` 临时目录写 params.json / content 文件，调用后清理。list 的子文件夹查询用 `ThreadPoolExecutor` 并行（对齐 Node `Promise.all`，仅深入一层）。create/update 直接收 **markdown 字符串**（MCP 无 scratch 文件，落临时目录再 `@` 引用），不再走 `--file` 路径参数。delete 的密码门：`FEISHU_TEMPLATE_DELETE_PASSWORD` 已配置则强制校验，未配置则跳过门（同 Node 275-279）。

**Tech Stack:** Python 3.10+；标准库 `subprocess`/`tempfile`/`concurrent.futures`/`json`/`os`；无新依赖。

**Config 契约（已核实 `mcp/sda_mcp/config.py`）：**
- `get_env(*keys)`：任一 key 缺失/空 → 抛 `ConfigError`。**仅必填 key 走它**。
- `load_config()`：返回完整 config dict（lru_cached）。
- `FEISHU_TEMPLATE_FOLDER_TOKEN`：list/create 必填（懒读，read/update/delete 不需要 → 不要在 `__init__` 读）。
- `FEISHU_TEMPLATE_DELETE_PASSWORD`：可选（delete 门，未配置则跳过）→ 用 `load_config()` 直接读，**不走 get_env**。

**lark-cli 子命令（移植自 templates.js，行为逐行对齐）：**
- list: `drive files list --params @params.json --format json --page-all`，cwd=临时目录，params.json=`{folder_token, page_size:'200'}`
- read: `docs +fetch --api-version v2 --doc <id> --doc-format markdown --format json`
- create: `docs +create --api-version v2 --parent-token <folder> --content @<file> --doc-format markdown`，cwd=内容文件所在临时目录
- update: `docs +update --api-version v2 --doc <id> --command overwrite --content @<file> --doc-format markdown`，cwd=临时目录
- delete: `drive +delete --file-token <id> --type docx --yes`
- 身份：所有命令尾部加 `--as user`，失败回退 `--as bot`

**范围：** 仅子项目 1.F。原 `using-templates/` 一律不动（铁律）。

---

## 文件结构

- Create: `mcp/sda_mcp/skills/using_templates.py` —— LarkCliClient + list/read/create/update/delete
- Modify: `mcp/sda_mcp/skills/__init__.py` —— 导出新函数
- Create: `mcp/tests/test_using_templates.py`

**不修改**：`using-templates/` 下任何文件。

---

## Task 1: using_templates.py —— lark-cli 封装内核

**Files:**
- Create: `mcp/sda_mcp/skills/using_templates.py`
- Test: `mcp/tests/test_using_templates.py`

- [ ] **Step 1: 写 `using_templates.py`**

```python
"""飞书报告模板内核：封装 lark-cli 子进程管理飞书文档模板。

移植 using-templates/scripts/templates.js。lark-cli 是独立外部二进制，本内核以子进程
调用它（不重写），只把 Node 壳换成 Python，去 CLI/三态/scratch 文件/{ok}。

行为对齐点：
- 身份：--as user 失败回退 --as bot，命中后实例级缓存（同 Node resolvedIdentity）。
- @文件引用必须是 cwd 内相对路径 → tempfile.mkdtemp 临时目录 + finally 清理。
- list：根目录 + 每个子文件夹一层（ThreadPoolExecutor 并行），过滤 docx/doc。
- create/update：收 markdown 字符串（不是文件路径），落临时文件再 @引用。
- delete：FEISHU_TEMPLATE_DELETE_PASSWORD 已配置则强制校验，否则跳过门。

失败抛 ConfigError(凭证/lark-cli 缺失)/ExternalAPIError(lark-cli 非 0)/ValidationError(参数)。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError

_LARK_BIN = "lark-cli"
_TIMEOUT = 120
_PAGE_SIZE = "200"


@dataclass
class CreateResult:
    document_id: str
    title: str


@dataclass
class UpdateResult:
    updated: bool
    document_id: str


@dataclass
class DeleteResult:
    deleted: bool
    document_id: str


class LarkCliClient:
    """lark-cli 子进程封装。身份命中后实例级缓存，避免每次重试 user/bot。"""

    def __init__(self) -> None:
        self._identity: str | None = None

    # --- 子进程执行 ---
    def _run(self, args: list[str], cwd: str | None = None, identity: str | None = None) -> str:
        full = [_LARK_BIN, *args]
        if identity:
            full += ["--as", identity]
        try:
            proc = subprocess.run(
                full, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT,
                shell=(os.name == "nt"),  # Windows 上 lark-cli 常是 .cmd 垫片，需 shell（同 Node opts.shell=true）
            )
        except FileNotFoundError as exc:
            raise ConfigError(
                "找不到 lark-cli 可执行文件，请先安装并完成 lark-cli config init / lark-cli auth login"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExternalAPIError(f"lark-cli 执行超时（{_TIMEOUT}s）") from exc
        if proc.returncode != 0:
            raise ExternalAPIError(
                f"lark-cli 失败 ({proc.returncode}): {(proc.stderr or '').strip()[:500]}")
        return proc.stdout

    def _exec(self, args: list[str], cwd: str | None = None) -> str:
        """带身份回退：--as user → 失败 → --as bot；命中后缓存。"""
        if self._identity:
            return self._run(args, cwd, self._identity)
        try:
            out = self._run(args, cwd, "user")
            self._identity = "user"
            return out
        except ExternalAPIError:
            out = self._run(args, cwd, "bot")
            self._identity = "bot"
            return out

    # --- 临时目录辅助（lark-cli 要求 @引用文件在 cwd 内） ---
    @staticmethod
    def _temp_dir(label: str) -> str:
        # mkdtemp 自带唯一性，无需 pid/时间戳（移植 Node newTempDir 的意图）
        return tempfile.mkdtemp(prefix=f"templates-{label}-")

    @staticmethod
    def _cleanup(path: str) -> None:
        try:
            for p in Path(path).glob("*"):
                p.unlink()
            Path(path).rmdir()
        except OSError:
            pass

    def _list_folder(self, folder_token: str) -> list[dict[str, Any]]:
        d = self._temp_dir("list")
        params_path = os.path.join(d, "params.json")
        try:
            with open(params_path, "w", encoding="utf-8") as fh:
                json.dump({"folder_token": folder_token, "page_size": _PAGE_SIZE}, fh)
            output = self._exec([
                "drive", "files", "list",
                "--params", "@params.json",
                "--format", "json",
                "--page-all",
            ], cwd=d)
            data = json.loads(output)
            return data.get("data", {}).get("files") or data.get("files") or []
        except json.JSONDecodeError as exc:
            raise ExternalAPIError(f"lark-cli list 返回非 JSON: {output[:300]}") from exc
        finally:
            self._cleanup(d)

    def _write_temp_content(self, label: str, content: str) -> tuple[str, str]:
        """把 content 写到临时目录的 markdown 文件，返回 (dir, basename)。"""
        d = self._temp_dir(label)
        name = "content.md"
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(content)
        return d, name


def list_templates() -> list[dict[str, Any]]:
    """列出文件夹下文档：根目录（category 为空）+ 每个子文件夹一层。"""
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = LarkCliClient()
    root_files = client._list_folder(folder_token)

    def _entry(f: dict[str, Any], category: str) -> dict[str, Any]:
        return {
            "id": f.get("token") or f.get("id"),
            "name": f.get("name"),
            "category": category,
            "type": f.get("type"),
            "url": f.get("url"),
            "modified_time": f.get("modified_time"),
        }

    results = [_entry(f, "") for f in root_files if f.get("type") in ("docx", "doc")]
    sub_folders = [f for f in root_files if f.get("type") == "folder"]

    def _sub(folder: dict[str, Any]) -> list[dict[str, Any]]:
        files = client._list_folder(folder.get("token") or folder.get("id"))
        return [_entry(f, folder.get("name", "")) for f in files if f.get("type") in ("docx", "doc")]

    if sub_folders:
        with ThreadPoolExecutor(max_workers=min(8, len(sub_folders))) as ex:
            for sub in ex.map(_sub, sub_folders):
                results.extend(sub)
    return results


def read_template(doc_id: str) -> str:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    client = LarkCliClient()
    output = client._exec([
        "docs", "+fetch",
        "--api-version", "v2",
        "--doc", doc_id,
        "--doc-format", "markdown",
        "--format", "json",
    ])
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return output
    return (data.get("data", {}).get("document", {}).get("content")
            or data.get("data", {}).get("markdown")
            or data.get("markdown")
            or "")


def create_template(title: str, content: str | None = None) -> CreateResult:
    if not title:
        raise ValidationError("title 不能为空")
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = LarkCliClient()
    # 两条路径都解析 create 输出的 document_id（同 Node 231-233）。inline 与 @file 均返回 doc_id。
    args = ["docs", "+create", "--api-version", "v2", "--parent-token", folder_token,
            "--doc-format", "markdown"]
    cwd: str | None = None
    if content is None:
        args += ["--content", f"# {title}"]            # 无内容：直接传标题（同 Node 227）
    else:
        if not isinstance(content, str) or not content:
            raise ValidationError("content 不能为空")
        cwd, name = client._write_temp_content("create", content)
        args += ["--content", f"@{name}"]
    try:
        output = client._exec(args, cwd=cwd)
    finally:
        if cwd:
            client._cleanup(cwd)
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ExternalAPIError(f"创建文档失败：返回非 JSON: {output[:300]}") from exc
    doc_id = (data.get("data", {}).get("doc_id")
              or data.get("data", {}).get("document", {}).get("document_id")
              or data.get("data", {}).get("document_id")
              or data.get("document_id"))
    if not doc_id:
        raise ExternalAPIError(f"创建文档失败：未返回 document_id。输出: {output[:300]}")
    return CreateResult(document_id=doc_id, title=title)


def update_template(doc_id: str, content: str) -> UpdateResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 不能为空")
    client = LarkCliClient()
    d, name = client._write_temp_content("update", content)
    try:
        client._exec([
            "docs", "+update",
            "--api-version", "v2",
            "--doc", doc_id,
            "--command", "overwrite",
            "--content", f"@{name}",
            "--doc-format", "markdown",
        ], cwd=d)
    finally:
        client._cleanup(d)
    return UpdateResult(updated=True, document_id=doc_id)


def delete_template(doc_id: str, password: str | None = None) -> DeleteResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    env_password = (load_config().get("env", {}) or {}).get("FEISHU_TEMPLATE_DELETE_PASSWORD")
    if env_password:
        if not password:
            raise ValidationError("需要密码（已设置 FEISHU_TEMPLATE_DELETE_PASSWORD）")
        if password != env_password:
            raise ValidationError("密码错误")
    client = LarkCliClient()
    client._exec(["drive", "+delete", "--file-token", doc_id, "--type", "docx", "--yes"])
    return DeleteResult(deleted=True, document_id=doc_id)
```

- [ ] **Step 2: 写 `mcp/tests/test_using_templates.py`**

```python
"""using_templates mock 单元测试（mock 子进程，不依赖真实 lark-cli）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.skills import using_templates as t


# --- _exec / _run 行为 ---

def test_lark_bin_missing_raises_config(monkeypatch):
    def _boom(*a, **k):
        raise FileNotFoundError("no such file")
    monkeypatch.setattr(t.subprocess, "run", _boom)
    client = t.LarkCliClient()
    with pytest.raises(ConfigError):
        client._run(["docs"], identity="user")


def test_lark_nonzero_raises_external(monkeypatch):
    class _P:
        returncode = 1
        stdout = ""
        stderr = "boom"
    monkeypatch.setattr(t.subprocess, "run", lambda *a, **k: _P())
    client = t.LarkCliClient()
    with pytest.raises(ExternalAPIError):
        client._run(["docs"], identity="user")


def _fake_run_factory(monkeypatch, outputs):
    """按 FIFO 吐 stdout；记每次调用的 args/cwd/identity。user 第 1 次返回非 0 强制回退 bot。"""
    calls = []
    q = list(outputs)
    import itertools
    fail_user_times = [0]  # 控制是否让 user 失败

    class _P:
        def __init__(self, stdout):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def _run(args, cwd=None, identity=None, **k):
        full = list(args) + (["--as", identity] if identity else [])
        calls.append({"args": full, "cwd": cwd})
        return _P(q.pop(0))
    monkeypatch.setattr(t.subprocess, "run", _run)
    return calls


def test_exec_caches_identity(monkeypatch):
    """user 成功 → 缓存 user，后续不再回退。"""
    calls = _fake_run_factory(monkeypatch, ["out1", "out2"])
    client = t.LarkCliClient()
    assert client._exec(["docs"]) == "out1"
    assert client._identity == "user"
    assert client._exec(["docs"]) == "out2"
    # 两次都带 --as user
    assert calls[0]["args"][-2:] == ["--as", "user"]
    assert calls[1]["args"][-2:] == ["--as", "user"]


def test_exec_falls_back_to_bot(monkeypatch):
    """user 失败 → 回退 bot，缓存 bot。"""
    calls = []
    class _P:
        def __init__(self, stdout, rc=0):
            self.returncode = rc; self.stdout = stdout; self.stderr = "e"
    def _run(args, cwd=None, identity=None, **k):
        calls.append({"identity": identity})
        if identity == "user":
            return _P("", rc=1)          # user 失败
        return _P("bot-out")
    monkeypatch.setattr(t.subprocess, "run", _run)
    client = t.LarkCliClient()
    out = client._exec(["docs"])
    assert out == "bot-out"
    assert client._identity == "bot"
    assert [c["identity"] for c in calls] == ["user", "bot"]


# --- list_templates ---

def test_list_flat_and_subfolder(monkeypatch):
    root = [
        {"type": "docx", "token": "d1", "name": "日报", "url": "u1", "modified_time": "1"},
        {"type": "folder", "token": "f1", "name": "销售"},
    ]
    sub = [{"type": "docx", "token": "d2", "name": "周报", "url": "u2", "modified_time": "2"}]
    outputs = [json.dumps({"data": {"files": root}}), json.dumps({"data": {"files": sub}})]
    _fake_run_factory(monkeypatch, outputs)
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "ROOT"})
    res = t.list_templates()
    assert len(res) == 2
    assert res[0] == {"id": "d1", "name": "日报", "category": "", "type": "docx", "url": "u1", "modified_time": "1"}
    assert res[1]["category"] == "销售" and res[1]["id"] == "d2"


def test_list_missing_folder_token(monkeypatch):
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {}})
    with pytest.raises(ConfigError):
        t.list_templates()


# --- read ---

def test_read_parses_markdown(monkeypatch):
    body = json.dumps({"data": {"document": {"content": "# 标题\n正文"}}})
    _fake_run_factory(monkeypatch, [body])
    monkeypatch.setattr(t.LarkCliClient, "_exec", lambda self, args, cwd=None: body)
    assert t.read_template("DOC") == "# 标题\n正文"


def test_read_empty_doc_id():
    with pytest.raises(ValidationError):
        t.read_template("")


# --- create ---

def test_create_requires_title():
    with pytest.raises(ValidationError):
        t.create_template("")


def test_create_success(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    captured = {}

    def _exec(self, args, cwd=None):
        captured["args"] = list(args)
        captured["cwd"] = cwd
        return json.dumps({"data": {"doc_id": "NEWDOC"}})
    monkeypatch.setattr(t.LarkCliClient, "_exec", _exec)
    r = t.create_template("播报", content="# 播报\n内容")
    assert r.document_id == "NEWDOC" and r.title == "播报"
    assert "@content.md" in captured["args"]
    assert "--parent-token" in captured["args"] and "F" in captured["args"]
    assert captured["cwd"] is not None          # 用了临时目录


def test_create_no_doc_id_raises(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    monkeypatch.setattr(t.LarkCliClient, "_exec", lambda self, a, cwd=None: json.dumps({"data": {}}))
    with pytest.raises(ExternalAPIError):
        t.create_template("t", content="x")


# --- update ---

def test_update_requires_content():
    with pytest.raises(ValidationError):
        t.update_template("DOC", "")


def test_update_success(monkeypatch):
    captured = {}
    def _exec(self, args, cwd=None):
        captured["args"] = list(args); captured["cwd"] = cwd; return ""
    monkeypatch.setattr(t.LarkCliClient, "_exec", _exec)
    r = t.update_template("DOC", "新内容")
    assert r.updated is True and r.document_id == "DOC"
    assert "--doc" in captured["args"] and "DOC" in captured["args"]
    assert "--command" in captured["args"] and "overwrite" in captured["args"]


# --- delete ---

def test_delete_password_gate_enforced(monkeypatch):
    monkeypatch.setattr(t, "load_config", lambda: {"env": {"FEISHU_TEMPLATE_DELETE_PASSWORD": "secret"}})
    with pytest.raises(ValidationError):               # 未传密码
        t.delete_template("DOC")
    with pytest.raises(ValidationError):               # 密码错
        t.delete_template("DOC", password="wrong")


def test_delete_password_correct(monkeypatch):
    monkeypatch.setattr(t, "load_config", lambda: {"env": {"FEISHU_TEMPLATE_DELETE_PASSWORD": "secret"}})
    monkeypatch.setattr(t.LarkCliClient, "_exec", lambda self, a, cwd=None: "")
    r = t.delete_template("DOC", password="secret")
    assert r.deleted is True


def test_delete_no_password_config_skips_gate(monkeypatch):
    monkeypatch.setattr(t, "load_config", lambda: {"env": {}})
    monkeypatch.setattr(t.LarkCliClient, "_exec", lambda self, a, cwd=None: "")
    r = t.delete_template("DOC")
    assert r.deleted is True
```

- [ ] **Step 3: 运行**

```bash
cd mcp && python -m pytest tests/test_using_templates.py -v
```
Expected: 13 passed。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/using_templates.py mcp/tests/test_using_templates.py
git commit -m "feat(mcp): using_templates core (lark-cli wrapper for feishu templates)"
```

---

## Task 2: 导出 + 全量测试

- [ ] **Step 1: 更新 `mcp/sda_mcp/skills/__init__.py`**

在现有 import 之后追加：

```python
from sda_mcp.skills.using_templates import (
    list_templates, read_template, create_template, update_template, delete_template,
    CreateResult, UpdateResult, DeleteResult,
)
```

并把 `list_templates, read_template, create_template, update_template, delete_template` 加入 `__all__`（dataclass 可不入 `__all__`，但 import 保留）。

- [ ] **Step 2: 全量测试**

```bash
cd mcp && python -m pytest -q
```
Expected: 全绿（1.E 完成后的基线 + using_templates 13）。

- [ ] **Step 3: 铁律校验**

```bash
git diff -- using-templates/ | head
```
Expected: 无输出。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/__init__.py
git commit -m "feat(mcp): export using_templates core APIs"
```

---

## 可选集成对照（env-gated，默认跳过）

仅当 `SDA_INTEGRATION=1` 且本机已装并登录 `lark-cli`、`config.json` 含 `FEISHU_TEMPLATE_FOLDER_TOKEN` 时手动运行：
- `list_templates()` 与 `node using-templates/scripts/templates.js list` 输出的 id/name/category 集合一致。
- `create_template("sda-parity-<ts>", "# 测试")` → `read_template(doc_id)` 内容含 "# 测试" → `delete_template(doc_id, password)` 清理。

默认 `skip`，不计入全量。

---

## 完成标准

- [ ] `using_templates.py`：list/read/create/update/delete，封装 lark-cli 子进程 + 身份回退缓存 + 临时目录 @引用 + 子文件夹并行。
- [ ] 去 CLI/三态/scratch 文件路径参数/`{ok}`；create/update 收 markdown 字符串；失败抛 SkillError 子类。
- [ ] delete 密码门与 Node 一致（配置了才校验）。
- [ ] mock 单元测试 13 全绿；全量测试通过。
- [ ] 原 `using-templates/` 零改动。
