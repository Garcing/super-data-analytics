"""各 skill 的干净 Python 内核。"""

from sda_mcp.skills.diagnosing import contribute, ContributionResult
from sda_mcp.skills.predicting import forecast, ForecastResult, ForecastError
from sda_mcp.skills.evaluating import evaluate
from sda_mcp.skills.visualizing import render as render_chart, ChartResult
from sda_mcp.skills.querying_data import (
    sql_query, sql_schema, sql_test_connection, SqlResult,
    powerbi_list_models, powerbi_list_tools, powerbi_schema, powerbi_query,
)
from sda_mcp.skills.retrieving_context import (
    search as retrieve_search, cypher as retrieve_cypher,
    schema as retrieve_schema, doc as retrieve_doc,
)

__all__ = [
    "contribute", "ContributionResult",
    "forecast", "ForecastResult", "ForecastError",
    "evaluate",
    "render_chart", "ChartResult",
    "sql_query", "sql_schema", "sql_test_connection", "SqlResult",
    "powerbi_list_models", "powerbi_list_tools", "powerbi_schema", "powerbi_query",
    "retrieve_search", "retrieve_cypher", "retrieve_schema", "retrieve_doc",
]
