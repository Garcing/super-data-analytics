"""块级 docx→markdown 自序列化回归（2026-08-31 根治 P1-2 遗留）。

背景：官方导出 ``docs/v1/content?content_type=markdown`` 存在三类污染——
HTML 实体化、``&#`` 前反斜杠、代码围栏内把斜体 run 渲染成 ``*`` 定界符
（实测 complaint 表文档 24 个斜体 run → ``select ** *from``、``*round*(``）。
修复：读路径改用原始块自序列化，代码围栏内逐字拼接 run 文本、无视样式。

fixture 结构全部镜像 2026-08-31 真实探针（block_type 与字段名逐一对齐）：
page=1, text=2, heading1..9=3..11, bullet=12, ordered=13, code=14,
quote=15, divider=22, table=31, table_cell=32, quote_container=34,
code.style.language=56(SQL)。
"""
import pytest

import sda_mcp.feishu as f
from sda_mcp.errors import ExternalAPIError, SkillError


def _run(content, **style):
    base = {"bold": False, "inline_code": False, "italic": False,
            "strikethrough": False, "underline": False}
    base.update(style)
    return {"text_run": {"content": content, "text_element_style": base}}


def _text_block(block_id, elements, block_type=2, parent="PAGE"):
    key = {2: "text"}.get(block_type, "text")
    return {"block_id": block_id, "block_type": block_type, "parent_id": parent,
            key: {"elements": elements, "style": {"align": 1, "folded": False}}}


def _doc(children, blocks):
    """组装 page 根 + 子块列表，返回 (blocks, by_id)。"""
    page = {"block_id": "PAGE", "block_type": 1, "children": children}
    return [page] + blocks


# --- 代码围栏：逐字拼接、无视样式（核心回归） ---

def test_code_fence_concatenates_runs_verbatim_ignoring_italic():
    """镜像真实投诉表文档：`select ` + 斜体`* ` + `from (values` 必须逐字还原。"""
    code = {"block_id": "C", "block_type": 14, "parent_id": "PAGE",
            "code": {"elements": [
                _run("    select "),
                _run("* ", italic=True),
                _run("from (values\n"),
                _run("        ,round(extract(epoch from t) / 3600.0, 2)", italic=True),
            ], "style": {"language": 56, "wrap": False}}}
    out = f.blocks_to_markdown(_doc(["C"], [code]), "投诉工单事实表")
    assert out == (
        "# 投诉工单事实表\n\n"
        "```SQL\n"
        "    select * from (values\n"
        "        ,round(extract(epoch from t) / 3600.0, 2)\n"
        "```"
    )


def test_code_fence_unknown_language_emits_bare_fence():
    code = {"block_id": "C", "block_type": 14, "parent_id": "PAGE",
            "code": {"elements": [_run("print(1)\n")],
                     "style": {"language": 9999, "wrap": False}}}
    out = f.blocks_to_markdown(_doc(["C"], [code]), "t")
    assert "```\nprint(1)\n```" in out and "```SQL" not in out


# --- 段落行内样式 ---

def test_paragraph_renders_bold_inline_code_italic_link():
    p = _text_block("P1", [
        _run("表ID：", bold=True),
        _run("complaint", inline_code=True),
        _run("　SQL 方言：", ),
        _run("Hologres", italic=True),
        _run(" 文档", ),
        _run("链接", link={"url": "https://example.com"}),
    ])
    out = f.blocks_to_markdown(_doc(["P1"], [p]), "t")
    assert "**表ID：**`complaint`　SQL 方言：*Hologres* 文档[链接](https://example.com)" in out


def test_link_url_percent_decoded_to_human_readable():
    """实测（2026-08-31 集成往返）：飞书存储层把链接 URL 百分号编码
    （https%3A%2F%2Fexample.com），序列化时解码还原，与旧官方导出行为对齐。"""
    p = _text_block("P1", [_run("链接", link={"url": "https%3A%2F%2Fexample.com%2Fa%20b"})])
    out = f.blocks_to_markdown(_doc(["P1"], [p]), "t")
    assert "[链接](https://example.com/a b)" in out


def test_underline_strikethrough_styles_dropped_but_text_kept():
    p = _text_block("P1", [_run("下划线", underline=True), _run("删除", strikethrough=True)])
    out = f.blocks_to_markdown(_doc(["P1"], [p]), "t")
    assert "下划线删除" in out


def test_unsupported_inline_element_raises():
    p = _text_block("P1", [{"mention_user": {"user_id": "ou_x"}}])
    with pytest.raises(SkillError, match="mention"):
        f.blocks_to_markdown(_doc(["P1"], [p]), "t")


# --- 标题 / 列表 / 引用 / 分隔线 ---

def test_heading_bullet_ordered_quote_divider():
    blocks = [
        {"block_id": "H1", "block_type": 3, "parent_id": "PAGE",
         "heading1": {"elements": [_run("一级")], "style": {}}},
        {"block_id": "H2", "block_type": 5, "parent_id": "PAGE",
         "heading3": {"elements": [_run("三级")], "style": {}}},
        {"block_id": "B1", "block_type": 12, "parent_id": "PAGE",
         "bullet": {"elements": [_run("项目A")], "style": {}}},
        {"block_id": "O1", "block_type": 13, "parent_id": "PAGE",
         "ordered": {"elements": [_run("第一步")], "style": {}}},
        {"block_id": "Q1", "block_type": 15, "parent_id": "PAGE",
         "quote": {"elements": [_run("引用一行")], "style": {}}},
        {"block_id": "D1", "block_type": 22, "parent_id": "PAGE", "divider": {}},
    ]
    out = f.blocks_to_markdown(_doc(["H1", "H2", "B1", "O1", "Q1", "D1"], blocks), "")
    assert "# 一级" in out and "### 三级" in out
    assert "- 项目A" in out and "1. 第一步" in out
    assert "> 引用一行" in out and "\n\n---" in out and out.endswith("---")


def test_quote_container_prefixes_children():
    inner = _text_block("QT", [_run("容器内引用")], parent="QC")
    qc = {"block_id": "QC", "block_type": 34, "parent_id": "PAGE",
          "children": ["QT"], "quote_container": {}}
    out = f.blocks_to_markdown(_doc(["QC"], [qc, inner]), "t")
    assert "> 容器内引用" in out


# --- 表格（行优先扁平 cells + column_size，实测 28 cells / 4 列 = 7 行） ---

def _table_doc():
    cells, blocks = [], []
    for i, txt in enumerate(["维度", "数值", "移动端", "12000"]):
        cid, tid = f"cell{i}", f"txt{i}"
        cells.append(cid)
        blocks.append({"block_id": cid, "block_type": 32, "parent_id": "TB",
                       "children": [tid], "table_cell": {}})
        blocks.append(_text_block(tid, [_run(txt)], parent=cid))
    tb = {"block_id": "TB", "block_type": 31, "parent_id": "PAGE", "children": cells,
          "table": {"cells": cells,
                    "property": {"column_size": 2, "column_width": [220, 138],
                                 "header_row": True,
                                 "merge_info": [{"col_span": 1, "row_span": 1}] * 4}}}
    return _doc(["TB"], [tb] + blocks)


def test_table_renders_pipe_rows_with_header_separator():
    out = f.blocks_to_markdown(_table_doc(), "t")
    assert "| 维度 | 数值 |" in out
    assert "| --- | --- |" in out
    assert "| 移动端 | 12000 |" in out


def test_table_cell_paragraphs_joined_by_space():
    blocks = []
    cells = ["c0", "c1"]
    blocks.append({"block_id": "c0", "block_type": 32, "parent_id": "TB",
                   "children": ["t0", "t1"], "table_cell": {}})
    blocks.append(_text_block("t0", [_run("第一段")], parent="c0"))
    blocks.append(_text_block("t1", [_run("第二段")], parent="c0"))
    blocks.append({"block_id": "c1", "block_type": 32, "parent_id": "TB",
                   "children": ["t2"], "table_cell": {}})
    blocks.append(_text_block("t2", [_run("值")], parent="c1"))
    tb = {"block_id": "TB", "block_type": 31, "parent_id": "PAGE", "children": cells,
          "table": {"cells": cells, "property": {"column_size": 1}}}
    out = f.blocks_to_markdown(_doc(["TB"], [tb] + blocks), "t")
    assert "| 第一段 第二段 |" in out and "| 值 |" in out


# --- 不支持的块类型：硬报错不静默丢 ---

def test_unsupported_block_type_raises_skill_error():
    img = {"block_id": "IMG", "block_type": 27, "parent_id": "PAGE", "image": {}}
    with pytest.raises(SkillError, match="27"):
        f.blocks_to_markdown(_doc(["IMG"], [img]), "t")


# --- 标题元数据 ---

def test_empty_title_omits_heading_line():
    p = _text_block("P1", [_run("正文")])
    out = f.blocks_to_markdown(_doc(["P1"], [p]), "")
    assert out == "正文"


def test_missing_page_root_raises_external():
    with pytest.raises(ExternalAPIError):
        f.blocks_to_markdown([_text_block("P1", [_run("x")])], "t")


# --- get_doc_markdown 新读路径 ---

class _ClientForDoc:
    """绕过 httpx，直接桩 _request，捕获端点序列。"""

    def __init__(self, monkeypatch, meta, blocks_pages):
        self.paths = []
        pages = list(blocks_pages)

        def fake(_self, method, path, *, params=None, json_body=None):
            self.paths.append(path)
            if path.endswith("/blocks"):
                return pages.pop(0)
            return {"code": 0, "data": {"document": meta}}

        monkeypatch.setattr(f.FeishuClient, "_request", fake)
        monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")


def test_get_doc_markdown_reads_meta_then_blocks(monkeypatch):
    blocks = _doc(["P1"], [_text_block("P1", [_run("正文")])])
    c = _ClientForDoc(monkeypatch,
                      meta={"document_id": "D1", "title": "标题", "revision_id": 3},
                      blocks_pages=[{"code": 0, "data": {"items": blocks, "has_more": False}}])
    out = f.FeishuClient().get_doc_markdown("D1")
    assert out == "# 标题\n\n正文"
    assert c.paths[0] == "/open-apis/docx/v1/documents/D1"
    assert c.paths[1] == "/open-apis/docx/v1/documents/D1/blocks"
    assert not any("/docs/v1/content" in p for p in c.paths)  # 旧导出端点已弃用


def test_get_doc_markdown_paginates_blocks(monkeypatch):
    # 真实分页形态：根块（含全部 children id）与 P1 在第一页，P2 在第二页
    page1_blocks = [{"block_id": "PAGE", "block_type": 1, "children": ["P1", "P2"]},
                    _text_block("P1", [_run("A")])]
    page2_blocks = [_text_block("P2", [_run("B")])]
    c = _ClientForDoc(monkeypatch,
                      meta={"title": "t"},
                      blocks_pages=[
                          {"code": 0, "data": {"items": page1_blocks, "has_more": True,
                                               "page_token": "PG2"}},
                          {"code": 0, "data": {"items": page2_blocks, "has_more": False}},
                      ])
    out = f.FeishuClient().get_doc_markdown("D1")
    assert "A" in out and "B" in out
    assert c.paths.count("/open-apis/docx/v1/documents/D1/blocks") == 2


def test_get_doc_markdown_blocks_missing_page_root(monkeypatch):
    c = _ClientForDoc(monkeypatch,
                      meta={"title": "t"},
                      blocks_pages=[{"code": 0, "data": {"items": [], "has_more": False}}])
    with pytest.raises(ExternalAPIError):
        f.FeishuClient().get_doc_markdown("D1")
