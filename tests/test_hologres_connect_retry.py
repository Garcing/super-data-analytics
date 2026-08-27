"""P1-3 回归：Hologres 连接建立失败自动重试一次。

背景：sda-vpn 转发器随 openvpn 隧道微重置间歇断连（容器仍 healthy），
psycopg 建连期 ``OperationalError: server closed the connection unexpectedly``
造成 ~11% sql_query 抖动（2026-08-26 QA）。查询为只读、无连接池（每次新建），
建连失败重试一次安全且能吸收绝大多数瞬断。
"""
import pytest

from sda_mcp.errors import DataSourceError
from sda_mcp.skills import querying_data as q


class _FakeDescr:
    def __init__(self, name, type_code):
        self.name = name
        self.type_code = type_code


class _FakeCursor:
    def __init__(self):
        self.description = [_FakeDescr("one", 23)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, statement, *a, **k):
        pass

    def fetchall(self):
        return [(1,)]


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _FakeCursor()


def _make_client(monkeypatch, connect_fn):
    monkeypatch.setattr(q.HologresClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.psycopg, "connect", connect_fn)
    monkeypatch.setattr(q.time, "sleep", lambda s: None)
    client = q.HologresClient()
    client._dsn = "host=fake"
    return client


def test_query_retries_transient_connect_failure(monkeypatch):
    attempts = []

    def connect(dsn):
        attempts.append(1)
        if len(attempts) == 1:
            raise q.psycopg.OperationalError(
                "server closed the connection unexpectedly")
        return _FakeConn()

    client = _make_client(monkeypatch, connect)
    result = client.query("SELECT 1")
    assert result.row_count == 1
    assert len(attempts) == 2          # 重试一次后成功


def test_query_raises_datasource_after_retry_exhausted(monkeypatch):
    attempts = []

    def connect(dsn):
        attempts.append(1)
        raise q.psycopg.OperationalError("server closed the connection unexpectedly")

    client = _make_client(monkeypatch, connect)
    with pytest.raises(DataSourceError) as ei:
        client.query("SELECT 1")
    assert "Hologres" in str(ei.value)  # 可操作提示保留
    assert len(attempts) == 2
