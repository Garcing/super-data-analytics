# SDA MCP 项目约定

本仓库独立维护 Super Data Analytics MCP 服务。历史 CLI Skill 套件位于 `Garcing/super-data-analytics-old`，不要把旧实现重新复制回来。

## 目录

- `sda_mcp/tools/`：FastMCP 工具注册、输入模型与面向模型的工具说明。
- `sda_mcp/skills/`：可测试的确定性 Python 执行内核。
- `skills/`：与 MCP 工具配套、供 agent 阅读的工作流技能。
- `tests/`：单元测试和按环境变量启用的集成测试。
- `docs/`：当前架构和调研记录。

## 开发规则

- Python 要求 `>=3.10`，依赖和 pytest 配置以 `pyproject.toml` 为准。
- MCP 工具保持薄层：参数校验、错误映射和内容块组装放在工具层，业务计算放在 `sda_mcp/skills/`。
- 修改工具名、输入/输出 schema 或行为时，同步更新对应 `skills/*/SKILL.md`、references、README 和测试。
- 工具说明应清楚说明功能、关键约束、参数和返回结构；“何时用”保持简洁，由配套 skill 负责流程编排。
- 配置和凭证只从环境变量或 `~/.super-data-analytics/config.json` 读取，禁止提交 `.env`、token 或真实 secret。
- `sync(dry_run=false)` 会全量重建 Neo4j；维护和验证时先执行 `dry_run=true`。

## 验证

```bash
python -m pytest -q
```

需要真实外部服务的集成测试默认跳过；仅在配置完备时设置 `SDA_INTEGRATION=1`。
