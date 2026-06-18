from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ChartInputError(ValueError):
    pass


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = SCRIPTS_DIR / "input"
DEFAULT_OUTPUT_DIR = SCRIPTS_DIR / "output"


def resolve_input_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or path.parent != Path("."):
        return path
    return DEFAULT_INPUT_DIR / path


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChartInputError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ChartInputError(f"input file is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ChartInputError("input JSON must be an object")
    return value


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip()).strip("-")
    return cleaned[:80] or "chart"


def resolve_output_path(spec: dict[str, Any], *, out: str | None, out_dir: str | None, fmt: str) -> Path:
    if fmt not in {"png", "svg"}:
        raise ChartInputError("format must be png or svg")
    if out:
        path = Path(out)
        if path.suffix.lower() != f".{fmt}":
            path = path.with_suffix(f".{fmt}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    directory = Path(out_dir) if out_dir else DEFAULT_OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    title = str(spec.get("title", "chart"))
    return directory / f"{slugify(title)}.{fmt}"
