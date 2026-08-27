"""P1-2 回归：飞书 docx 导出 markdown 的实体污染必须在读取侧解码。

背景（2026-08-26 QA + 探针实证）：docx 存储层干净（list_blocks 文本原样），
``docs/v1/content?content_type=markdown`` 导出时先把 ``" & < >`` 实体化
（``&#34; &amp; &lt; &gt;``）再做 markdown 反斜杠转义 → 读取方看到
``\\&\\#34;引号\\&\\#34;`` 乱码样残留，且整篇写回会让残留累积进存储。
修复：get_doc_markdown 导出后解码——先剥 ``&``/``#`` 前的反斜杠，再 html.unescape。
"""


def _patch_request(monkeypatch, content):
    def fake_request(self, method, path, *, params=None, json_body=None):
        return {"code": 0, "data": {"content": content}}
    from sda_mcp.feishu import FeishuClient
    monkeypatch.setattr(FeishuClient, "_request", fake_request)


def test_get_doc_markdown_decodes_entities(monkeypatch):
    from sda_mcp.feishu import FeishuClient
    raw = r'\&\#34;引号\&\#34; \&amp; \&lt;大于\&gt; \+20\.96%'
    _patch_request(monkeypatch, raw)

    out = FeishuClient().get_doc_markdown("DOC1")

    # 实体还原为原始字符；\+20\.96% 等 markdown 装饰性转义保留（渲染等价）
    assert out == r'"引号" & <大于> \+20\.96%'


def test_get_doc_markdown_decodes_legacy_stored_entities(monkeypatch):
    """防御性语义:若实体文本以字面量存在(极端情形),单遍解码只剥一层。
    实测(2026-08-27 探针)所有文档存储层干净,该情形未出现——锁定
    html.unescape 单遍行为,避免有人误改成递归解码。"""
    from sda_mcp.feishu import FeishuClient
    raw = r'按\&amp;\#34;训练营类型\&amp;\#34;（体验营 / 正式营）'
    _patch_request(monkeypatch, raw)

    out = FeishuClient().get_doc_markdown("DOC1")

    assert out == '按&#34;训练营类型&#34;（体验营 / 正式营）'
