"""markdown 格式矩阵往返测试。

- 单元测试（默认跑）：校验 fixtures/markdown_matrix.md 存在且含全部格式段；
  create_template 会把整份 md 交给 convert（mock）。
- 集成测试（SDA_INTEGRATION=1）：真实 md → docx → md 往返，断言各格式语义存活。
  需 config.json 飞书凭证 + 模板文件夹已授权。Feishu convert/get_doc_markdown 是
  飞书侧解析，读回会规范化（表格→HTML、语言名大写、列表项间多空行），故只断言
  关键文本/结构存在，不断言逐字符一致。
"""
import os
from pathlib import Path

import pytest

from sda_mcp.skills import using_templates as t

FIXTURE = Path(__file__).parent / "fixtures" / "markdown_matrix.md"

_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用（需飞书凭证 + 模板文件夹授权）",
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


def test_create_template_passes_full_md_to_convert(monkeypatch):
    """create_template 把整份 md（含全部格式）交给 convert，insert 用其返回。"""
    md = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def _convert(self, content):
        captured["content"] = content
        return ([{"block_type": 2}], ["b1"])

    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks", _convert)
    monkeypatch.setattr(t.FeishuClient, "create_doc", lambda self, folder, title: "DOCNEW")
    monkeypatch.setattr(t.FeishuClient, "insert_descendants", lambda *a, **k: None)
    monkeypatch.setattr(t, "get_env",
                        lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})

    r = t.create_template("矩阵测试", md)
    assert captured["content"] == md            # 整份 md 原样进 convert
    assert r.document_id == "DOCNEW"


# ---------- 集成测试：真实 md→docx→md 往返 ----------

@_INTEGRATION
def test_matrix_roundtrip_survives_formats():
    """真实往返：create+convert+insert → get_doc_markdown → 各格式语义存活。

    读回会被飞书规范化（表格变 HTML、Python 大写、列表项间多空行、+/- 转义），
    故断言关键文本存在而非逐字符一致。"""
    from sda_mcp.feishu import FeishuClient

    md = FIXTURE.read_text(encoding="utf-8")
    fc = FeishuClient()

    # 用 retrieve_doc 目标文档同账号的模板文件夹；建临时文档
    from sda_mcp.config import get_env
    folder = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
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
