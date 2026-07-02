from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any


class ChartInputError(ValueError):
    pass


SUPPORTED_FORMATS = {"png", "svg"}
STDIN_READ_TIMEOUT_SECONDS = 15.0


def parse_json_text(text: str, *, origin: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        raise ChartInputError(f"{origin} 为空")
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ChartInputError(f"{origin} 不是合法 JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ChartInputError(f"{origin} JSON 必须是对象")
    return value


def read_data_from_file(path: str) -> dict[str, Any]:
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ChartInputError(f"输入文件不存在: {path}") from exc
    except OSError as exc:
        raise ChartInputError(f"无法读取输入文件 {path}: {exc}") from exc
    return parse_json_text(text, origin=f"文件 {path}")


def read_data_from_stdin(stream: Any = None) -> dict[str, Any]:
    stream = stream or sys.stdin
    # TTY（交互终端）下没有管道可读，直接报错，避免阻塞。
    if getattr(stream, "isatty", lambda: False)():
        raise ChartInputError(
            "未提供 --data 且 stdin 是终端。请用 --data \"<JSON>\"、--data @<文件> 或管道传入"
        )

    # 非交互环境（脚本/管道/agent 子进程）里，若调用方忘了带 --data 且 stdin 没关闭，
    # read() 会永久挂起。用后台线程 + 超时兜底：到点没收完就主动报错退出。
    holder: dict[str, Any] = {}

    def _read() -> None:
        try:
            holder["text"] = stream.read()
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    reader.join(STDIN_READ_TIMEOUT_SECONDS)
    if reader.is_alive():
        raise ChartInputError(
            f"等待 stdin 超时（{int(STDIN_READ_TIMEOUT_SECONDS)}s 内未收到 JSON）。\n"
            "常见原因：在非交互环境（脚本/管道/agent）里既没传 --data \"<JSON>\" / --data @<文件>，"
            "stdin 也没关闭。\n解决：用 --data 显式传入，或确保管道写完后关闭 stdin。"
        )
    if "error" in holder:
        raise ChartInputError(f"读取 stdin 失败: {holder['error']}")

    return parse_json_text(holder.get("text", ""), origin="stdin")


def read_data_inline(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise ChartInputError("--data 不能为空")
    return parse_json_text(raw, origin="inline --data")


def read_data_source(options: dict[str, Any]) -> dict[str, Any]:
    """按三态路由读取图表 JSON，对齐 querying-data 的 --query 路由。"""
    source = options["data_source"]
    if source == "stdin":
        return read_data_from_stdin()
    if source == "file":
        return read_data_from_file(options["data_path"])
    return read_data_inline(options["data_inline"])


def format_from_save_path(save_path: Path) -> str:
    """--save 的扩展名决定输出格式（删掉了 --format）。非法或缺扩展名直接报错。"""
    ext = save_path.suffix.lower()
    fmt = ext.lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ChartInputError(
            f"--save 扩展名必须是 .png 或 .svg（决定输出格式），收到: {ext or '(无扩展名)'}"
        )
    return fmt


def ensure_save_parent(save_path: Path) -> None:
    save_path.parent.mkdir(parents=True, exist_ok=True)
