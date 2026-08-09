"""sda-mcp 统一异常体系。

所有内核失败时抛这些异常（不返回 {ok:false}）。
MCP 工具层捕获后映射为 MCP isError + 可操作错误信息。
"""


class SkillError(Exception):
    """所有 skill 内核失败的基类。"""


class ConfigError(SkillError):
    """凭证/配置缺失或无效（如 config.json 缺 key）。"""


class ValidationError(SkillError):
    """输入校验失败（字段缺失、类型错、越界）。"""


class DataSourceError(SkillError):
    """外部数据源错误（Hologres/Power BI/Neo4j 连接或查询失败）。"""


class ExternalAPIError(SkillError):
    """外部 API 调用失败（apimart/Vercel Blob/Fabric）。"""


class SkillTimeoutError(SkillError):
    """内核调用超时。"""
