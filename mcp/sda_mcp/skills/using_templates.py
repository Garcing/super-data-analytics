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
