"""从 Vercel Blob 拉取 streamlit 报告索引 / 源码，并 exec 渲染。

报告 .py 不在仓库里——它们存在 Blob，app.py 运行时按索引拉取源码 exec。
这里只读公开 URL（无需 token）；写入由 skill 侧的 streamlit.js CLI 完成。
urllib 默认认 HTTP(S)_PROXY 环境变量（与 Node fetch 不同，无需额外接管）。
"""
from __future__ import annotations

import json
import urllib.request

import streamlit as st

# Blob store 公开域名（一次性常量；首次 publish 后从返回 URL 提取）。
BLOB_BASE = "https://o2v8qrfoxqnbqwk4.public.blob.vercel-storage.com"
INDEX_URL = f"{BLOB_BASE}/streamlit-reports-index.json"
SOURCE_URL = f"{BLOB_BASE}/streamlit-reports/{{id}}.py"


def _get_text(url: str, timeout: int = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (公开读 URL)
        return r.read().decode("utf-8")


@st.cache_data(show_spinner=False, ttl=30)
def fetch_index() -> list[dict]:
    """返回索引里的报告条目数组；取不到返回 []。"""
    try:
        data = json.loads(_get_text(INDEX_URL))
    except Exception:
        return []
    if isinstance(data, dict):
        return data.get("reports", [])
    return data or []


@st.cache_data(show_spinner=False, ttl=30)
def fetch_source(report_id: str) -> str:
    """取某份报告 .py 源码。"""
    return _get_text(SOURCE_URL.format(id=report_id))


def make_runner(report_id: str):
    """返回一个无参 callable，供 st.Page 使用：被调用时 fetch 源码并 exec。

    exec 注入 __name__="__main__"，与本地 `streamlit run 报告.py` 行为一致；
    报告里的 `from lib import ...` 靠 app.py 把 streamlit 目录插进 sys.path 解析。
    """

    def run() -> None:
        src = fetch_source(report_id)
        exec(compile(src, f"<blob:{report_id}>", "exec"), {"__name__": "__main__"})  # noqa: S102

    return run
