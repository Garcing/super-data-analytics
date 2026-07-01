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

| 格式 | 输入 | 输出 | 入口 |
|------|------|------|------|
| HTML | 报告 JSON（meta + summary + conclusions） | vercel 公网链接 | `node scripts/html/report.js`，详见 [`references/report_to_html.md`](references/report_to_html.md) |
| Image | 文本提示词（+ 可选 size/quality/model 等） | 本地图片（`--save` 决定路径，建议 `results/`）+ 公网 URL | `node scripts/image/image.js`，详见 [`references/report_to_image.md`](references/report_to_image.md) |
| Streamlit | 报告 `.py`（`from lib import ...`，顶层 `st.*`） | 多页 app（本地 / Community Cloud URL） | `node scripts/streamlit/streamlit.js`，详见 [`references/report_to_streamlit.md`](references/report_to_streamlit.md) |
| 飞书文档 | lark-doc 要求的格式 | 飞书文档 URL | 参考 SKILL `lark-doc` |
| 飞书幻灯片 | lark-slides 要求的格式 | 飞书幻灯片 URL | 参考 SKILL `lark-slides` |

## 核心约定（与 querying-data 对齐）

### 凭证：config.json 唯一来源

- html / image / streamlit 的凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块（`VERCEL_REPORTS_URL` / `APIMART_API_KEY` / `APIMART_BASE_URL` / `BLOB_READ_WRITE_TOKEN`）。html/streamlit 直连 Blob 写（token 在客户端），**不需要在 Vercel 项目设置里配环境变量**；`VERCEL_REPORTS_URL` 仅用于拼 html 可分享链接。
- 脚本**不读 `.env`、不依赖环境变量导出**；配置缺失或字段不全时报错指引补全，由 agent 引导用户提供后写回 config.json 再重试。
- 飞书的配置项见各自指引。

### 三态输入（html 的 `--report`、streamlit 的 `--source`，同 querying-data 的 `--query`）

html `publish` 的报告 JSON、streamlit `publish` 的报告 `.py` 源码都支持三种来源：

- `--report "<json>"` / `--source "<py>"` inline
- `--report @<file>` / `--source @<file>` 文件
- `--report -` / `--source -` 或不传 → stdin（管道）

> Image 是提示词驱动，直接走 CLI 位置参数（`"<提示词>"`），无需三态输入。

### 工作区产物目录（约定，由 agent 构造路径）

- 临时请求文件（如 `--report @` 指向的报告 JSON 草稿）建议放 `<工作区>/.super-data-analytics/scratch/`。
- 报告结果落盘（如 image 下载的图片，经 `--save` 指定）建议放 `<工作区>/.super-data-analytics/results/`。
- 脚本不强制这两个目录、不假设默认落盘位置——路径由 agent 经各 CLI 的参数（image 的 `--save`）显式决定；裸 `--save` 才兜底到 `~/Downloads`。
- html 的产物是公网 URL（打印到 stdout），一般不落盘；如需留痕，把发布返回的 URL / 报告 JSON 自行写入 `results/`。

## Step 1 选格式

按交付场景选：在线可交互分享 → HTML；一张图讲清结论、要嵌 PPT/微信 → Image；多页可钻取 app → Streamlit；落到飞书生态 → 飞书文档/幻灯片。

## Step 2 读对应格式的 reference

**执行前先读对应 reference**——里面写明 CLI 形态、输入格式、产物路径、代理/依赖等细节：

- HTML → [`references/report_to_html.md`](references/report_to_html.md)
- Image → [`references/report_to_image.md`](references/report_to_image.md)
- Streamlit → [`references/report_to_streamlit.md`](references/report_to_streamlit.md)
