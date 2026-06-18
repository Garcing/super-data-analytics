"""
feishu_reader.py — Read Feishu Base data via lark-cli.

Functions:
    fetch_table_fields(app_token, table_id) -> list[dict]
    fetch_table_records(app_token, table_id, fields=None) -> list[dict]
"""
from __future__ import annotations

import json
import subprocess


def _run_lark_cli(*args: str) -> dict:
    """Call lark-cli and return parsed JSON output."""
    cmd = ["lark-cli", *args, "--as", "bot"]
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        raise RuntimeError(f"lark-cli failed: {result.stderr}")
    lines = result.stdout.strip().split("\n")
    # lark-cli may output pretty-printed JSON spanning many lines;
    # collect everything from the first '{' to the end.
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            start = i
            break
    if start is None:
        raise RuntimeError(f"No JSON output from lark-cli: {result.stdout[:500]}")
    json_text = "\n".join(lines[start:])
    return json.loads(json_text)


def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """Fetch field definitions for a table. Filters out auto_number fields."""
    data = _run_lark_cli(
        "base", "+field-list",
        "--base-token", app_token,
        "--table-id", table_id,
    )
    fields = data.get("data", {}).get("fields", [])
    return [
        {"name": f["name"], "type": f["type"], "id": f["id"]}
        for f in fields
        if f["type"] != "auto_number"
    ]


def _extract_cell_value(field_type: str, cell: object) -> object:
    """Extract readable value from a lark-cli record-list cell."""
    if cell is None:
        return None
    # lark-cli returns select fields as lists like ["value"]
    # and multi_select as ["opt1", "opt2"].
    if field_type in ("select", "multi_select") and isinstance(cell, list):
        if field_type == "select" and len(cell) == 1:
            return cell[0]
        return cell
    if isinstance(cell, str):
        return cell.strip() or None
    return cell


def fetch_table_records(
    app_token: str,
    table_id: str,
    fields: list[dict] | None = None,
) -> list[dict]:
    """Fetch all records from a Feishu table.

    lark-cli with --format json returns columnar data:
      data.data  -> list of row arrays (each row is a list of cell values)
      data.fields -> list of column names
    """
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)
    field_map = {f["name"]: f["type"] for f in fields}
    field_names = {f["name"] for f in fields}

    all_rows: list[list] = []
    offset = 0
    page_size = 200
    while True:
        resp = _run_lark_cli(
            "base", "+record-list",
            "--base-token", app_token,
            "--table-id", table_id,
            "--format", "json",
            "--limit", str(page_size),
            "--offset", str(offset),
        )
        payload = resp.get("data", {})
        rows = payload.get("data", [])
        col_names = payload.get("fields", [])
        # Build column index for this page
        col_index = {name: idx for idx, name in enumerate(col_names)}
        all_rows.extend(rows)
        has_more = payload.get("has_more", False)
        if not has_more or len(rows) < page_size:
            break
        offset += len(rows)

    records: list[dict] = []
    for row in all_rows:
        record: dict = {}
        for name in field_names:
            if name not in col_index:
                continue
            raw = row[col_index[name]]
            ftype = field_map[name]
            value = _extract_cell_value(ftype, raw)
            if value is not None:
                record[name] = value
        records.append(record)
    return records
