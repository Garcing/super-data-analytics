from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contract import ChartSpec, ContractError, validate
from .io import ChartInputError, load_json, resolve_input_path, resolve_output_path
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
    parser.add_argument("input", nargs="?", help="Path to chart JSON input.")
    parser.add_argument("--out", help="Output file path.")
    parser.add_argument("--out-dir", help="Directory for generated chart output.")
    parser.add_argument("--format", default="png")
    parser.add_argument("--dpi", default="144")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if not args.input:
        raise CliArgumentError("input is required")
    if args.format not in {"png", "svg"}:
        raise CliArgumentError("format must be one of png, svg")
    try:
        dpi = int(args.dpi)
    except (TypeError, ValueError) as exc:
        raise CliArgumentError("dpi must be an integer") from exc
    if dpi <= 0:
        raise CliArgumentError("dpi must be greater than 0")
    args.dpi = dpi
    return args


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
        args = parse_args(argv)
        raw = load_json(resolve_input_path(args.input))
        spec = validate(raw)
        output_path = resolve_output_path(raw, out=args.out, out_dir=args.out_dir, fmt=args.format)
        warnings = render_chart(spec, output_path, args.format, args.dpi)
        ensure_output_exists(output_path)
        ensure_png_nonblank(output_path)
        write_json(_success_payload(spec, output_path, args.format, args.dpi, warnings))
        return 0
    except (CliArgumentError, ChartInputError, ContractError) as exc:
        write_json({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:
        write_json({"ok": False, "error": str(exc)})
        return 1
