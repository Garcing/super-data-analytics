"""P1-a 回归:sql_schema 对不存在的表必须报可操作错误,不得静默空列。

QA 实测(2026-08-26):public.no_such_table_xyz 与逻辑语义表
semantic.fact_user_period_lifecycle 均静默返回 columns:[],误导调用方得出
"表存在但没结构"的错误结论;querying-data Skill 原描述的 relation does not
exist 报错从未发生。修复:空列时查 information_schema.tables 确认存在性,
不存在则抛 ValidationError 并提示逻辑表应读 SQL 文档。
"""
import pytest

from sda_mcp.errors import ValidationError
from sda_mcp.skills import querying_data as q


class _D:
    def __init__(self, name):
        self.name = name


class _Step:
    """一次 execute 的预设返回:description + rows。"""

    def __init__(self, names, rows):
        self.description = [_D(n) for n in names]
        self.rows = rows


class _SeqCursor:
    def __init__(self, steps):
        self._steps = list(steps)
        self._cur = None
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, statement, *a, **k):
        self.calls.append(statement)
        self._cur = self._steps.pop(0)

    @property
    def description(self):
        return self._cur.description if self._cur else None

    def fetchall(self):
        return self._cur.rows

    def fetchone(self):
        return self._cur.rows[0] if self._cur.rows else None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cursor


def _client(monkeypatch, steps):
    monkeypatch.setattr(q.HologresClient, "__init__", lambda self: None)
    client = q.HologresClient()
    cursor = _SeqCursor(steps)
    monkeypatch.setattr(client, "_connect", lambda: _FakeConn(cursor))
    return client, cursor


def test_missing_table_raises_with_hint(monkeypatch):
    """模板查询空列 + information_schema 确认不存在 → ValidationError 带指引。"""
    client, cursor = _client(monkeypatch, [
        _Step(["字段名", "数据类型"], []),        # 模板查询:无列
        _Step(["exists"], []),                   # 存在性检查:不存在
    ])
    with pytest.raises(ValidationError) as ei:
        client.get_table_schema("no_such_table_xyz", "public")
    msg = str(ei.value)
    assert "不存在" in msg
    assert "SQL 文档" in msg          # 逻辑表指引
    assert len(cursor.calls) == 2     # 确认做了存在性检查


def test_existing_table_returns_columns_without_existence_probe(monkeypatch):
    client, cursor = _client(monkeypatch, [
        _Step(["字段名", "数据类型"], [("id", "integer")]),
    ])
    cols = client.get_table_schema("orders", "public")
    assert cols == [{"字段名": "id", "数据类型": "integer"}]
    assert len(cursor.calls) == 1     # 有列时不多查


def test_table_exists_but_zero_columns_does_not_raise(monkeypatch):
    """存在但零列(极端情形)不误报,保持原样返回。"""
    client, _ = _client(monkeypatch, [
        _Step(["字段名", "数据类型"], []),
        _Step(["exists"], [(1,)]),
    ])
    assert client.get_table_schema("edge", "public") == []
