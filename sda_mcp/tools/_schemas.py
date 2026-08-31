"""Stable structured-output contracts advertised by ``tools/list``.

Only fields controlled by SDA are modeled here. Provider-owned payloads such
as Power BI's nested ``result`` remain intentionally open dictionaries because
Microsoft's Preview response can evolve independently of this server.
"""
from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class SqlColumn(TypedDict):
    name: str
    dataTypeID: int


class SqlQueryOutput(TypedDict):
    columns: list[SqlColumn]
    rows: list[dict[str, Any]]
    row_count: int


class TableSchema(TypedDict):
    schema: str
    table: str
    columns: list[dict[str, Any]]


class SqlSchemaOutput(TypedDict):
    tables: list[TableSchema]


class RetrieveSearchOutput(TypedDict):
    question: str
    strategy: str
    results: list[dict[str, Any]]


class RetrieveCypherOutput(TypedDict):
    cypher: str
    rows: list[dict[str, Any]]


class NodeSchema(TypedDict):
    properties: dict[str, str]
    unique: list[str]


class RetrieveSchemaOutput(TypedDict):
    nodes: dict[str, NodeSchema]
    relationships: list[str]


class DocReadOutput(TypedDict):
    content: str
    document_id: str


class ChartOutput(TypedDict):
    format: str
    width: int
    height: int
    url: str | None


class DocUpdateOutput(TypedDict):
    updated: bool
    document_id: str


class ContributionOutput(TypedDict):
    method: str
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    checks: dict[str, Any]


class ForecastOutput(TypedDict):
    metric: str
    model: str
    model_reason: str
    forecast: list[dict[str, Any]]
    summary: dict[str, Any]
    backtest: dict[str, Any]
    confidence: str
    assumptions: list[str]
    warnings: list[str]


class ReportPublishOutput(TypedDict):
    url: str
    report_id: str
    blob_url: str


class ReportListOutput(TypedDict):
    reports: list[dict[str, Any]]


class ReportDeleteOutput(TypedDict):
    success: bool
    report_id: str
