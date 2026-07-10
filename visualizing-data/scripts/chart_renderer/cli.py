from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any

from .contract import ChartSpec, ContractError, validate
from .render import ensure_output_exists, ensure_png_nonblank, render_chart


# --- 常量 ---------------------------------------------------------------------

SUPPORTED_FORMATS = {"png", "svg"}
STDIN_READ_TIMEOUT_SECONDS = 15.0


# --- 错误类型 ----------------------------------------------------------------

class ChartInputError(ValueError):
    """输入读取 / 格式推断类错误，映射到 exit code 2。"""


class CliArgumentError(ValueError):
    """CLI 参数错误，映射到 exit code 2。"""


# --- 输入读取（三态：inline / @file / stdin）---------------------------------

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
    """按三态路由读取图表 JSON，对齐 querying-data 的 --sql / --payload 路由。"""
    source = options["data_source"]
    if source == "stdin":
        return read_data_from_stdin()
    if source == "file":
        return read_data_from_file(options["data_path"])
    return read_data_inline(options["data_inline"])


# --- 输出路径 / 格式 ----------------------------------------------------------

def format_from_output_path(output_path: Path) -> str:
    """--output 的扩展名决定输出格式（删掉了 --format）。非法或缺扩展名直接报错。"""
    ext = output_path.suffix.lower()
    fmt = ext.lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ChartInputError(
            f"--output 扩展名必须是 .png 或 .svg（决定输出格式），收到: {ext or '(无扩展名)'}"
        )
    return fmt


def ensure_output_parent(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)


# --- 参数解析 ----------------------------------------------------------------

class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise CliArgumentError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if status == 0:
            raise SystemExit(0)
        raise CliArgumentError(message or f"argument parsing failed with status {status}")


def write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Render a chart image from JSON.")
    parser.add_argument(
        "--data",
        help=(
            "chart JSON 输入，三态：inline JSON 字符串、@<file-path> 文件、"
            "- 或不传走 stdin"
        ),
    )
    parser.add_argument(
        "--output",
        help="输出文件路径（必填）；扩展名 .png / .svg 决定输出格式",
    )
    parser.add_argument("--dpi", default="144")
    return parser


def resolve_data_option(value: str | None) -> dict[str, Any]:
    """把 --data 解析成内部 source（对外只剩一个 --data），对齐 querying-data 的 --sql / --payload：
    不传 或 -  → stdin（从管道读；- 是 Unix 惯用的"显式 stdin"）
    @<path>    → file
    其他       → inline（直接 JSON）
    """
    if value is None or value == "-":
        return {"data_source": "stdin"}
    if value.startswith("@"):
        path = value[1:]
        if not path:
            raise CliArgumentError("--data @ 后需提供文件路径")
        return {"data_source": "file", "data_path": path}
    return {"data_source": "inline", "data_inline": value}


def parse_args(argv: list[str] | None = None):
    args = build_parser().parse_args(argv)
    if not args.output:
        raise CliArgumentError(
            "--output 是必填项：输出文件路径，扩展名 .png 或 .svg 决定输出格式。"
            "建议落到 <工作区>/.super-data-analytics/results/"
        )
    try:
        dpi = int(args.dpi)
    except (TypeError, ValueError) as exc:
        raise CliArgumentError("dpi 必须是整数") from exc
    if dpi <= 0:
        raise CliArgumentError("dpi 必须大于 0")
    data_option = resolve_data_option(args.data)
    output_path = Path(args.output)
    fmt = format_from_output_path(output_path)  # ChartInputError → exit 2
    return data_option, output_path, fmt, dpi


# --- 主流程 ------------------------------------------------------------------

def _success_payload(spec: ChartSpec, output_path: Path, fmt: str, dpi: int, warnings: list[str]) -> dict[str, Any]:
    return {
        "ok": True,
        "path": str(output_path.resolve()),
        "format": fmt,
        "dpi": dpi,
        "width": int(spec.options.get("width", 1200)),
        "height": int(spec.options.get("height", 720)),
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        data_option, output_path, fmt, dpi = parse_args(argv)
        raw = read_data_source(data_option)
        spec = validate(raw)
        ensure_output_parent(output_path)
        warnings = render_chart(spec, output_path, fmt, dpi)
        ensure_output_exists(output_path)
        ensure_png_nonblank(output_path)
        sys.stderr.write(f"结果已保存到: {output_path.resolve()}\n")
        sys.stderr.flush()
        write_json(_success_payload(spec, output_path, fmt, dpi, warnings))
        return 0
    except (CliArgumentError, ChartInputError, ContractError) as exc:
        write_json({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:
        write_json({"ok": False, "error": str(exc)})
        return 1
