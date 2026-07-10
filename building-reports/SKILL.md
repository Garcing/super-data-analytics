---
name: building-reports
description: 报告生成板块，按格式（html / image / streamlit / lark）路由；html/image 走 config.json + 三态输入
metadata:
  skill-series: super-data-analytics
  chinese-name: 构建数据报告
---

# 构建数据报告

将分析结果转化为不同格式的数据分析报告。所有命令在 `building-reports/` 目录下执行。

## 格式说明

统一入口为 `node scripts/report.js <html|image|streamlit> <子命令> ...`；`report.js` 只做薄分发，并用动态 import 只加载目标格式模块。各格式模块内部保留同名子命令（如 `image generate`）。

| 格式 | 输入 | 输出 | 入口 |
|------|------|------|------|
| HTML | 报告 JSON（meta + summary + conclusions） | vercel 公网链接 | `node scripts/report.js html ...`，详见 [`references/report_to_html.md`](references/report_to_html.md) |
| Image | 文本提示词（支持 inline / @file / stdin，+ 可选 size/quality/model 等） | 本地图片（`--output` 决定路径，建议 `results/`）+ 公网 URL | `node scripts/report.js image ...`，详见 [`references/report_to_image.md`](references/report_to_image.md) |
| Streamlit | 报告 `.py`（`from lib import ...`，顶层 `st.*`） | 多页 app（本地 / Community Cloud URL） | `node scripts/report.js streamlit ...`，详见 [`references/report_to_streamlit.md`](references/report_to_streamlit.md) |
| 飞书文档 | lark-doc 要求的格式 | 飞书文档 URL | 参考 SKILL `lark-doc` |
| 飞书幻灯片 | lark-slides 要求的格式 | 飞书幻灯片 URL | 参考 SKILL `lark-slides` |

## 运行环境与依赖

- Node.js `>=20.0.0`。
- 报告 CLI：在 `building-reports/scripts/` 执行 `npm ci`，安装共享的 `@vercel/blob` 与 `undici`。HTML/Image/Streamlit 的 Node CLI 都从这里解析共享依赖；`scripts/image/` 不再维护重复的 package/lock。
- HTML 前端：另在 `building-reports/scripts/html/` 执行 `npm ci`，安装 React/Vite/Tailwind/Recharts 前端依赖。
- Streamlit：Python `>=3.10`，执行 `python -m pip install -r scripts/streamlit/requirements.txt`。
- 飞书文档/幻灯片由 `lark-doc` / `lark-slides` 技能及其依赖负责。
- 代理可选读取 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY`；`SDA_STDIN_TIMEOUT_MS` 只调整 stdin 超时。这些不是凭证。

部署 HTML 另需 Vercel CLI；Streamlit 发布脚本另需 Git/Bash。完整安装矩阵见仓库根目录 `DEPENDENCIES.MD`。



## 核心约定（与 querying-data 对齐）

### 凭证：config.json 唯一来源

- html / image / streamlit 的凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块（`VERCEL_REPORTS_URL` / `APIMART_API_KEY` / `APIMART_BASE_URL` / `BLOB_READ_WRITE_TOKEN`）。html/streamlit 直连 Blob 写（token 在客户端），**不需要在 Vercel 项目设置里配环境变量**；`VERCEL_REPORTS_URL` 仅用于拼 html 可分享链接。
- 脚本**不读 `.env`、不依赖环境变量导出**；配置缺失或字段不全时报错指引补全，由 agent 引导用户提供后写回 config.json 再重试。
- 飞书的配置项见各自指引。

### 三态输入（html / streamlit 的 `--report`，image 的 `--prompt`，同 querying-data 的 `--sql` / `--payload`）

html `publish` 的报告 JSON、streamlit `publish` 的报告 `.py` 源码支持 `--report` 三种来源；image 的提示词支持同构的 `--prompt` 三种来源：

- `--report "<内容>"` inline
- `--report @<file>` 文件
- `--report -` 或不传 → stdin（管道）

- `--prompt "<文本>"` inline（image）
- `--prompt @<file>` 文件（image）
- `--prompt -` 或不传 → stdin（image）

### 索引 schema（html / streamlit 共用）

两边索引条目统一为 `{ id, title, created_at, updated_at, summary, tags }`：

- **html**：meta 自然挂在报告 JSON 上（`meta.title` / `meta.generated_at` / `meta.tags` / `summary.overall`），`html.js` 自动提取组装索引，CLI 不传 meta flag。
- **streamlit**：报告是 `.py` 源码没有结构化 meta，所以 `--title` / `--summary` / `--tags` 由 agent 经 flag 填；时间（`created_at` / `updated_at`）两边都由 CLI 自动写。
- `created_at` 首次发布写入后重发保留原值（稳定）；`updated_at` 每次刷新。时间为 ISO 8601 UTC 带 `Z`。
- `tags` 是字符串数组（如 `["销售","区域"]`），替代旧 `group`，作为可变长标签。streamlit 导航按首个 tag 分组。
- **不存 stats**（结论数/高重要度数）——前端要这些指标时实时从报告 JSON 的 `conclusions` 派生，索引保持轻量。

### 工作区产物目录（约定，由 agent 构造路径）

- 临时请求文件（如 `--report @` 指向的报告 JSON 草稿）建议放 `<工作区>/.super-data-analytics/scratch/`。
- 报告结果落盘（如 image 下载的图片，经 `--output` 指定）建议放 `<工作区>/.super-data-analytics/results/`。
- 脚本不强制这两个目录、不假设默认落盘位置——路径由 agent 经各 CLI 的参数（image 的 `--output`）显式决定；裸 `--output` 才兜底到 `~/Downloads`。
- html 的产物是公网 URL（打印到 stdout），一般不落盘；如需留痕，把发布返回的 URL / 报告 JSON 自行写入 `results/`。

## Step 1 选格式

按交付场景选：在线可交互分享 → HTML；一张图讲清结论、要嵌 PPT/微信 → Image；多页可钻取 app → Streamlit；落到飞书生态 → 飞书文档/幻灯片。

## Step 2 读对应格式的 reference

**执行前先读对应 reference**——里面写明 CLI 形态、输入格式、产物路径、代理/依赖等细节：

- HTML → [`references/report_to_html.md`](references/report_to_html.md)
- Image → [`references/report_to_image.md`](references/report_to_image.md)
- Streamlit → [`references/report_to_streamlit.md`](references/report_to_streamlit.md)
