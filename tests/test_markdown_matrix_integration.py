"""markdown 格式矩阵往返测试。

- 单元测试（默认跑）：校验 fixtures/markdown_matrix.md 存在且含全部格式段；
  update_doc 会把整份 md 交给 convert（mock）。
- 集成测试（SDA_INTEGRATION=1）：真实 md → docx → md 往返，断言各格式语义存活。
  需 config.json 飞书凭证 + 一个可建临时文档的文件夹（环境变量 SDA_TEST_DOC_FOLDER）。
  get_doc_markdown 读路径为原始块自序列化（2026-08-31 起，不再走官方导出）：
  表格读回为 markdown 管道表格、代码围栏逐字保真、无实体化/样式定界符污染；
  列表编号等仍会规范化，故格式矩阵断言关键文本/结构存在，SQL 围栏断言逐字节一致。
"""
import os
from pathlib import Path

import pytest

from sda_mcp.skills import retrieving_context as r

FIXTURE = Path(__file__).parent / "fixtures" / "markdown_matrix.md"

_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用（需飞书凭证 + SDA_TEST_DOC_FOLDER）",
)


# ---------- 默认跑的单元测试：fixture 完整性 ----------

def test_matrix_fixture_has_all_sections():
    """测试 md 文件覆盖全部格式段（人眼可视检 + 自动校验）。"""
    md = FIXTURE.read_text(encoding="utf-8")
    # 标题三级
    assert "# 一级标题" in md and "## 二级标题" in md and "### 三级标题" in md
    # 行内格式
    assert "**加粗**" in md and "*斜体*" in md and "`行内代码`" in md
    # 列表
    assert "- 指标 A" in md and "1. 第一步" in md
    # 表格、代码块、引用、分隔
    assert "| 维度 |" in md
    assert "```python" in md
    assert "> 这是一段引用" in md
    assert "\n---\n" in md


def test_update_doc_passes_full_md_to_convert(monkeypatch):
    """update_doc 把整份 md（含全部格式）交给 convert，insert 用其返回。"""
    md = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def _convert(self, content):
        captured["content"] = content
        return ([{"block_type": 2}], ["b1"])

    monkeypatch.setattr(r.FeishuClient, "convert_markdown_to_blocks", _convert)
    monkeypatch.setattr(r.FeishuClient, "delete_all_children", lambda self, did: None)
    monkeypatch.setattr(r.FeishuClient, "insert_descendants", lambda *a, **k: None)

    out = r.update_doc("DOCNEW", md)
    assert captured["content"] == md            # 整份 md 原样进 convert
    assert out == {"updated": True, "document_id": "DOCNEW"}


# ---------- 集成测试：真实 md→docx→md 往返 ----------

@_INTEGRATION
def test_matrix_roundtrip_survives_formats():
    """真实往返：建临时文档 → convert+insert → get_doc_markdown → 各格式语义存活。

    读回为原始块自序列化（表格→markdown 管道表格、无实体转义污染），但列表编号、
    语言名映射仍会规范化，故断言关键文本存在而非逐字符一致。
    需 SDA_TEST_DOC_FOLDER 指向一个应用可写的文件夹。"""
    folder = os.environ.get("SDA_TEST_DOC_FOLDER")
    if not folder:
        pytest.skip("设 SDA_TEST_DOC_FOLDER 为可建临时文档的文件夹 token 以跑此往返")

    from sda_mcp.feishu import FeishuClient

    md = FIXTURE.read_text(encoding="utf-8")
    fc = FeishuClient()

    doc_id = fc.create_doc(folder, "MD矩阵往返测试-集成")
    try:
        blocks, first_level = fc.convert_markdown_to_blocks(md)
        assert len(first_level) > 0, "convert 未返回顶层块"
        fc.insert_descendants(doc_id, blocks, first_level)

        back = fc.get_doc_markdown(doc_id)
        # 标题
        assert "一级标题：报告主标题" in back
        assert "二级标题：关键指标" in back
        assert "三级标题：数据表格" in back
        # 行内格式（飞书保留 md 标记）
        assert "加粗" in back and "斜体" in back and "行内代码" in back
        assert "一个链接" in back and "https://example.com" in back
        # 列表
        assert "指标 A：日活" in back and "指标 B" in back and "指标 C" in back
        assert "第一步：取数" in back and "第二步：清洗" in back and "第三步：分析" in back
        # 表格（读回为 HTML <table>，断言全部单元格文本存在）
        for cell in ("维度", "数值", "同比", "移动端", "12000", "PC 端", "8000",
                     "小程序", "5000"):
            assert cell in back, f"表格单元格丢失: {cell}"
        # 代码块
        assert "def hello(name: str)" in back
        # 引用、分隔
        assert "这是一段引用文字" in back
    finally:
        fc.delete_file(doc_id, "docx")


@_INTEGRATION
def test_sql_fence_roundtrip_byte_exact():
    """SQL 围栏字节级往返（2026-08-31 读路径根治回归）。

    围栏内含 *、&、<、>、" 与函数调用——旧官方导出路径会把它们污染成
    ``*round*(``、``\\&\\#34;``、``&gt;=``；块自序列化路径必须逐字节还原。"""
    folder = os.environ.get("SDA_TEST_DOC_FOLDER")
    if not folder:
        pytest.skip("设 SDA_TEST_DOC_FOLDER 为可建临时文档的文件夹 token 以跑此往返")

    from sda_mcp.feishu import FeishuClient

    fence_body = (
        "select * from t\n"
        "where a >= '&' and b < 'x' and c = \"q\"\n"
        "    ,round(extract(epoch from ts) / 3600.0, 2)\n"
    )
    md = f"# SQL围栏往返\n\n```SQL\n{fence_body}```\n"
    fc = FeishuClient()

    doc_id = fc.create_doc(folder, "SQL围栏往返-集成")
    try:
        blocks, first_level = fc.convert_markdown_to_blocks(md)
        fc.insert_descendants(doc_id, blocks, first_level)

        back = fc.get_doc_markdown(doc_id)
        assert f"```SQL\n{fence_body}```" in back
    finally:
        fc.delete_file(doc_id, "docx")
