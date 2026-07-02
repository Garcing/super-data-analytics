from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contract import ChartSpec, ContractError, validate
from .io import (
    ChartInputError,
    ensure_save_parent,
    format_from_save_path,
    read_data_source,
)
from .quality import ensure_output_exists, ensure_png_nonblank
from .render import render_chart


class CliArgumentError(ValueError):
    pass


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
        "--save",
        help="输出文件路径（必填）；扩展名 .png / .svg 决定输出格式",
    )
    parser.add_argument("--dpi", default="144")
    return parser


def resolve_data_option(value: str | None) -> dict[str, Any]:
    """把 --data 解析成内部 source（对外只剩一个 --data），对齐 querying-data 的 --query：
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
    if not args.save:
        raise CliArgumentError(
            "--save 是必填项：输出文件路径，扩展名 .png 或 .svg 决定输出格式。"
            "建议落到 <工作区>/.super-data-analytics/results/"
        )
    try:
        dpi = int(args.dpi)
    except (TypeError, ValueError) as exc:
        raise CliArgumentError("dpi 必须是整数") from exc
    if dpi <= 0:
        raise CliArgumentError("dpi 必须大于 0")
    data_option = resolve_data_option(args.data)
    save_path = Path(args.save)
    fmt = format_from_save_path(save_path)  # ChartInputError → exit 2
    return data_option, save_path, fmt, dpi


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
        data_option, save_path, fmt, dpi = parse_args(argv)
        raw = read_data_source(data_option)
        spec = validate(raw)
        ensure_save_parent(save_path)
        warnings = render_chart(spec, save_path, fmt, dpi)
        ensure_output_exists(save_path)
        ensure_png_nonblank(save_path)
        sys.stderr.write(f"结果已保存到: {save_path.resolve()}\n")
        sys.stderr.flush()
        write_json(_success_payload(spec, save_path, fmt, dpi, warnings))
        return 0
    except (CliArgumentError, ChartInputError, ContractError) as exc:
        write_json({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:
        write_json({"ok": False, "error": str(exc)})
        return 1
