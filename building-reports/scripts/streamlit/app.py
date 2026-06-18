"""Streamlit 报告看板入口。

扫描 reports/*.py，用 ast 提取每份报告的 META（不执行报告代码），
按 group 分组，用 st.navigation + st.Page 动态建页。
首个「主页」展示全部报告概览，其余页为各报告。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
# 让报告 .py 里的 `from lib import ...` 可解析
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REPORTS_DIR = _HERE / "reports"

st.set_page_config(page_title="数据分析报告", page_icon="📈", layout="wide")


def extract_meta(path: Path) -> dict:
    """从报告 .py 顶层 META = {...} 字典提取元信息，不执行代码。"""
    defaults = {
        "title": path.stem,
        "icon": "📄",
        "group": "其他",
        "summary": "",
    }
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == "META":
                try:
                    val = ast.literal_eval(node.value)
                    if isinstance(val, dict):
                        defaults.update(val)
                except Exception:
                    pass
                break
    return defaults


def build_entries() -> list[tuple[dict, object]]:
    """扫描 reports/，返回 [(meta, StreamlitPage), ...]。"""
    entries: list[tuple[dict, object]] = []
    for py in sorted(REPORTS_DIR.glob("*.py")):
        if py.name.startswith("_"):
            continue
        meta = extract_meta(py)
        # url_path = 报告标题，使每份报告有固定直达链接 base/<标题>
        page = st.Page(
            str(py),
            title=meta["title"],
            icon=meta.get("icon", "📄"),
            url_path=meta["title"],
        )
        entries.append((meta, page))
    return entries


def main() -> None:
    entries = build_entries()

    if not entries:
        st.title("📈 数据分析报告")
        st.info("暂无报告。把报告 .py 放到 `reports/` 目录（参考 `reports/_template.py`），重启即可。")
        # 占位页：模板（若有）。无模板时 st.info 已渲染，无需空 navigation
        template = REPORTS_DIR / "_template.py"
        if template.exists():
            st.navigation([st.Page(str(template), title="模板", icon="📄")]).run()
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
