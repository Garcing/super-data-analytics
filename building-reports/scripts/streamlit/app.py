"""Streamlit 报告看板入口。

从 Vercel Blob 读报告索引（streamlit-reports-index.json），用 st.Page(callable)
动态建页：每个 page 的 callable 在被访问时 fetch 对应 .py 源码并 exec 渲染。

框架（本文件 + lib/ + store.py）部署一次；报告推到 Blob 即生效，无需重新部署。
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from store import fetch_index, make_runner

_HERE = Path(__file__).resolve().parent
# 让报告 .py 里的 `from lib import ...` 可解析（exec 报告源码时用到）
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

st.set_page_config(page_title="数据分析报告", page_icon="📈", layout="wide")


def build_entries() -> list[tuple[dict, object]]:
    """读 Blob 索引，返回 [(meta, StreamlitPage), ...]。"""
    entries: list[tuple[dict, object]] = []
    for meta in fetch_index():
        rid = meta.get("id")
        if not rid:
            continue
        title = meta.get("title", rid)
        page = st.Page(
            make_runner(rid),
            title=title,
            icon=meta.get("icon", "📄"),
            # url_path = 报告标题，使每份报告有固定直达链接 base/<标题>
            url_path=title,
        )
        entries.append((meta, page))
    return entries


def main() -> None:
    entries = build_entries()

    if not entries:
        st.title("📈 数据分析报告")
        st.info("暂无报告。用 `streamlit.js publish` 把报告 .py 推到 Blob 即可生效。")
        return

    # 按 group 聚合，供导航与主页使用
    groups = sorted({meta.get("group", "其他") for meta, _ in entries})
    pages_by_group: dict[str, list] = {}
    for meta, page in entries:
        pages_by_group.setdefault(meta.get("group", "其他"), []).append(page)

    def home() -> None:
        """主页：报告概览。"""
        st.header("📊 报告概览")
        st.caption(f"共 {len(entries)} 份报告 · {len(groups)} 个分组")
        for group in groups:
            st.subheader(group)
            for meta, page in entries:
                if meta.get("group", "其他") != group:
                    continue
                with st.container(border=True):
                    icon_col, body_col = st.columns([1, 9])
                    icon_col.markdown(f"## {meta.get('icon', '📄')}")
                    body_col.markdown(f"**{meta['title']}**")
                    if meta.get("summary"):
                        body_col.caption(meta["summary"])
                    st.page_link(page, label="打开报告 →", icon="➡️")

    home_page = st.Page(home, title="主页", icon="🏠", default=True)
    # "" 分组让主页排在最前、无分组标题
    nav = {"": [home_page], **pages_by_group}
    st.navigation(nav).run()


if __name__ == "__main__":
    main()
