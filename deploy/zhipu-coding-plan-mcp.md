---
name: zhipu-official-mcp-setup
description: Configure and verify Zhipu AI (BigModel / GLM Coding Plan) official Vision, Web Search, and Web Reader MCP servers for an MCP-compatible coding client, with Claude Code as the primary path. Reuse one API key, avoid duplicate registrations, preserve existing MCP configuration, and verify each server after setup.
---

# 智谱官方 MCP 接入 Skill

## 目标

在不破坏现有 MCP 配置的前提下，为当前编码客户端接入智谱官方提供的以下能力：

1. 视觉理解 MCP：`zai-mcp-server`
2. 联网搜索 MCP：`web-search-prime`
3. 网页读取 MCP：`web-reader`

官方文档：

- 视觉理解：https://docs.bigmodel.cn/cn/coding-plan/mcp/vision-mcp-server
- 联网搜索：https://docs.bigmodel.cn/cn/coding-plan/mcp/search-mcp-server
- 网页读取：https://docs.bigmodel.cn/cn/coding-plan/mcp/reader-mcp-server

## 必须先理解的配置关系

这三个能力不是同一个 MCP Server 的三个开关，而是 **3 个独立 MCP Server**。

- `zai-mcp-server`：本地 MCP，`stdio` 方式运行，依赖 Node.js / npx。
- `web-search-prime`：智谱托管的远程 HTTP MCP，无需本地安装。
- `web-reader`：智谱托管的远程 HTTP MCP，无需本地安装。

因此：

- API Key：通常只需要获取 **1 个**，三个 MCP 可以复用同一个适用的 GLM Coding Plan API Key。
- MCP 注册：如果需要三个能力都显式接入，则需要存在 **3 条独立 Server 配置**。
- 配置动作：可以一次编辑配置文件并同时加入三个 Server，也可以分别执行三条 CLI 命令；逻辑上仍是三个 MCP。
- Claude Code 使用 `-s user` 时，每个 MCP 只需在当前用户范围注册一次，不需要每个项目重复配置。

### GLM Coding Plan 的特殊情况

如果 Claude Code 当前直接使用 GLM Coding Plan：

- 联网搜索 MCP 已由模型服务端内置，通常无需另装 `web-search-prime`。
- 网页读取 MCP 已由模型服务端内置，通常无需另装 `web-reader`。
- 基础 `image_analysis` 已内置；只有需要完整视觉工具集（OCR、报错截图诊断、技术图解读、图表分析、UI diff、视频分析等）时，再安装 `zai-mcp-server`。

如果 Claude Code 中还会调用非智谱模型，并希望这些模型也能使用上述 MCP，则应显式配置相应 Server。

## 执行原则

执行本 Skill 时必须遵守：

1. 先检查，后修改。不要直接覆盖现有 MCP 配置。
2. 不得删除或重写与本任务无关的 MCP Server。
3. 同名 Server 已存在时，先检查其 URL / command / headers / env 是否正确；正确则跳过，错误才修复。
4. API Key 只询问或读取一次，然后复用于需要的 Server。
5. 不要把真实 API Key 写入本 Skill 文件、README、Git 仓库、日志或最终总结。
6. 不要在回复中完整回显 API Key。
7. 优先采用用户级配置，使其对所有项目生效；除非用户明确要求 project/local scope。
8. Windows 环境下优先兼容 PowerShell 与 CMD；若 `npx -y` 在 PowerShell 下出现参数问题，改用 CMD。
9. 视觉 MCP 使用最新版包，避免命中旧 npx 缓存。
10. 完成后必须验证三个 Server 的实际状态，而不是只确认“配置文件写入成功”。

## Step 1：识别环境

先确认：

- 当前客户端是否为 Claude Code、Cline、OpenCode、Roo Code、Kilo Code 或其它 MCP 客户端。
- 当前操作系统。
- 是否正在使用 GLM Coding Plan。
- 用户是否希望三个 MCP 对所有模型可用，还是仅使用 GLM Coding Plan 的内置能力。

若是 Claude Code，优先执行：

```bash
claude mcp list
```

检查以下三个名称是否已经存在：

```text
zai-mcp-server
web-search-prime
web-reader
```

不要因为某个名称已存在就重复注册。

## Step 2：检查 API Key

需要使用 GLM Coding Plan 对应的 API Key。

注意：

- 个人 Coding Plan：从个人编程套餐中创建 / 获取 Key。
- 团队 Coding Plan：必须使用团队套餐提供的 Key；团队套餐 Key 与平台其它 API Key 不通用。

若 Key 未提供，只向用户索取一次。

在任何输出中，将其显示为：

```text
YOUR_API_KEY
```

或掩码形式，不完整回显真实 Key。

## Step 3：Claude Code 推荐配置

### 3.1 视觉理解 MCP

只有在以下任一情况下显式安装：

- 用户需要完整视觉工具集；
- 当前并非依赖 GLM Coding Plan 的内置 `image_analysis`；
- 用户明确要求三个官方 MCP 都注册到 Claude Code。

前置检查：

```bash
node -v
npx -v
```

Node.js 需要 18 或更高版本。

推荐用户级安装：

```bash
claude mcp add -s user zai-mcp-server --env Z_AI_API_KEY=YOUR_API_KEY -- npx -y "@z_ai/mcp-server@latest"
```

等价核心配置：

```json
{
  "mcpServers": {
    "zai-mcp-server": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@z_ai/mcp-server@latest"
      ],
      "env": {
        "Z_AI_API_KEY": "YOUR_API_KEY",
        "Z_AI_MODE": "ZHIPU"
      }
    }
  }
}
```

视觉 MCP 当前可提供的主要工具包括：

- `ui_to_artifact`
- `extract_text_from_screenshot`
- `diagnose_error_screenshot`
- `understand_technical_diagram`
- `analyze_data_visualization`
- `ui_diff_check`
- `image_analysis`
- `video_analysis`

### 3.2 联网搜索 MCP

若 GLM Coding Plan 内置搜索已经满足需求，可跳过显式安装。

若希望其它模型也能调用，则注册：

```bash
claude mcp add -s user -t http web-search-prime https://open.bigmodel.cn/api/mcp/web_search_prime/mcp --header "Authorization: Bearer YOUR_API_KEY"
```

对应配置：

```json
{
  "mcpServers": {
    "web-search-prime": {
      "type": "http",
      "url": "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

核心工具：

```text
webSearchPrime
```

### 3.3 网页读取 MCP

若 GLM Coding Plan 内置网页读取已经满足需求，可跳过显式安装。

若希望其它模型也能调用，则注册：

```bash
claude mcp add -s user -t http web-reader https://open.bigmodel.cn/api/mcp/web_reader/mcp --header "Authorization: Bearer YOUR_API_KEY"
```

对应配置：

```json
{
  "mcpServers": {
    "web-reader": {
      "type": "http",
      "url": "https://open.bigmodel.cn/api/mcp/web_reader/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

核心工具：

```text
webReader
```

## Step 4：一次性手动配置三个 MCP（Claude Code）

如果用户更希望只修改一次 `.claude.json`，则应在现有 `mcpServers` 对象中 **合并** 以下三个条目，而不是覆盖整个文件：

```json
{
  "mcpServers": {
    "zai-mcp-server": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@z_ai/mcp-server@latest"
      ],
      "env": {
        "Z_AI_API_KEY": "YOUR_API_KEY",
        "Z_AI_MODE": "ZHIPU"
      }
    },
    "web-search-prime": {
      "type": "http",
      "url": "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    },
    "web-reader": {
      "type": "http",
      "url": "https://open.bigmodel.cn/api/mcp/web_reader/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

重要：实际执行时必须先读取现有 `.claude.json`，只合并缺失条目；不得用上面的示例覆盖用户原有文件。

## Step 5：Windows 注意事项

### PowerShell 检查版本

```powershell
node -v
npx -v
claude mcp list
```

### 直接测试视觉 MCP

```powershell
$env:Z_AI_API_KEY="YOUR_API_KEY"; npx -y @z_ai/mcp-server@latest
```

若 PowerShell 对 `-y` 或命令包装出现异常，改用 CMD：

```cmd
set Z_AI_API_KEY=YOUR_API_KEY && npx -y @z_ai/mcp-server@latest
```

出现 Windows requires `cmd /c` wrapper to execute npx 一类提示时，按照智谱官方说明通常可以忽略该告警；若 Server 实际无法启动，再进一步处理。

## Step 6：验证

配置完成后执行：

```bash
claude mcp list
```

期望结果：需要显式安装的 Server 均能被 Claude Code 识别，且没有 Failed / disconnected 一类状态。

然后分别做功能验证。

### 搜索验证

向客户端提出：

```text
使用 web-search-prime 搜索智谱 GLM Coding Plan 最新官方文档，并返回来源链接。
```

### 网页读取验证

向客户端提出：

```text
使用 web-reader 读取 https://docs.bigmodel.cn/cn/coding-plan/mcp/reader-mcp-server ，概括该页面提供的 MCP 工具名称。
```

期望能够调用：

```text
webReader
```

### 视觉验证

准备一张本地图片，例如 `demo.png`，然后提出：

```text
使用智谱视觉 MCP 分析当前目录中的 demo.png。
```

如需验证专项工具，可要求它执行 OCR、错误截图诊断、技术图解读或图表分析。

## Step 7：故障排查

### A. `zai-mcp-server` 无法启动

依次检查：

```bash
node -v
npx -v
```

确认 Node.js >= 18。

再测试：

```bash
npx -y @z_ai/mcp-server@latest
```

如果旧缓存导致版本异常，继续使用 `@latest`，必要时再清理 npx/npm 缓存。

### B. API Key 无效

检查：

- Key 是否复制完整。
- Key 是否已经激活。
- 是否拿错了普通开放平台 Key 与 Coding Plan Key。
- 团队套餐用户是否使用了团队套餐 Key。
- 视觉 MCP 的 `Z_AI_MODE` 是否与平台匹配；中国智谱平台通常使用 `ZHIPU`。
- Remote MCP Header 是否严格为：

```text
Authorization: Bearer YOUR_API_KEY
```

### C. 搜索 / Reader 连接超时

检查：

- URL 是否完全正确。
- 网络代理、防火墙、企业网络策略是否阻断 `open.bigmodel.cn`。
- Header 是否正确传递。
- 当前 MCP 客户端是否支持 HTTP / Streamable HTTP。

### D. 已有同名 MCP 但配置错误

不要直接重复添加。

先检查现有 Server，然后只更新错误项。若必须重建，先删除对应的单个 Server，再重新注册；不要清空所有 MCP。

视觉 MCP 例：

```bash
claude mcp remove zai-mcp-server
```

仅在确认它配置错误时执行。

## 针对其它 MCP 客户端

如果不是 Claude Code，不要照抄 Claude Code 的 CLI 命令；应按照官方文档选择对应客户端的配置格式。

原则保持不变：

- Vision：本地 `stdio`，执行 `npx -y @z_ai/mcp-server@latest`，传入 `Z_AI_API_KEY` 与 `Z_AI_MODE=ZHIPU`。
- Search：远程 MCP，URL 为 `https://open.bigmodel.cn/api/mcp/web_search_prime/mcp`。
- Reader：远程 MCP，URL 为 `https://open.bigmodel.cn/api/mcp/web_reader/mcp`。
- Search / Reader 的鉴权 Header 为 `Authorization: Bearer YOUR_API_KEY`。

不同客户端对于 `http`、`streamableHttp`、`streamable-http` 等类型名称可能不同，必须使用该客户端官方支持的字段，不得凭经验猜字段名。

## 完成标准

只有同时满足以下条件，才可以报告任务完成：

1. 已判断用户是否真的需要显式安装三个 MCP，尤其考虑 GLM Coding Plan 的内置能力。
2. 需要的 MCP Server 均已注册，且没有创建重复条目。
3. 原有 MCP 配置未被破坏。
4. API Key 未被泄露到 Skill / Git / 日志 / 回复正文。
5. `claude mcp list` 或对应客户端状态检查正常。
6. 至少完成一次实际工具调用验证，确认不是“配置存在但不可用”。

## 最终汇报格式

完成后只需简洁汇报：

```text
智谱官方 MCP 已检查/配置：
- Vision: 已启用 / 已内置无需安装 / 未启用（原因）
- Web Search: 已启用 / 已内置无需安装 / 未启用（原因）
- Web Reader: 已启用 / 已内置无需安装 / 未启用（原因）
- Scope: user / project / local
- 验证结果: 正常 / 异常（给出具体错误）
```

不要在最终汇报中输出完整 API Key。
