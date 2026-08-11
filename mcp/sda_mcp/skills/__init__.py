"""各 skill 的干净 Python 内核。"""

from sda_mcp.skills.diagnosing import contribute, ContributionResult
from sda_mcp.skills.predicting import forecast, ForecastResult, ForecastError
from sda_mcp.skills.evaluating import evaluate
from sda_mcp.skills.visualizing import render as render_chart, ChartResult
from sda_mcp.skills.querying_data import (
    sql_query, sql_schema, sql_test_connection, SqlResult,
    powerbi_list_tools, powerbi_schema, powerbi_query,
)
from sda_mcp.skills.retrieving_context import (
    search as retrieve_search, cypher as retrieve_cypher,
    schema as retrieve_schema, doc as retrieve_doc,
)
from sda_mcp.skills.retrieving_context_sync import sync_graph
from sda_mcp.skills.building_reports import (
    publish_report, list_reports, get_report, delete_report,
    submit_image, get_image_status, generate_image,
)
from sda_mcp.skills.using_templates import (
    list_templates, read_template, create_template, update_template, delete_template,
    CreateResult, UpdateResult, DeleteResult,
)

__all__ = [
    "contribute", "ContributionResult",
    "forecast", "ForecastResult", "ForecastError",
    "evaluate",
    "render_chart", "ChartResult",
    "sql_query", "sql_schema", "sql_test_connection", "SqlResult",
    "powerbi_list_tools", "powerbi_schema", "powerbi_query",
    "retrieve_search", "retrieve_cypher", "retrieve_schema", "retrieve_doc", "sync_graph",
    "publish_report", "list_reports", "get_report", "delete_report",
    "submit_image", "get_image_status", "generate_image",
    "list_templates", "read_template", "create_template", "update_template", "delete_template",
]
