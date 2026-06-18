---
title: 图片报告生成（report → image）设计
status: draft
date: 2026-06-14
---

# 图片报告生成（report → image）

## 1. 目标与范围

在 `generating-insights-report/scripts/image/` 下实现一个 Node.js CLI，调用 apimart 的 gpt-image-2 异步生成图片，下载到本地并打印公网 URL。形态与 `scripts/html/report.js` 一致（单文件、自动加载 `.env`、代理感知、编程式 + CLI 双接口）。

### 范围内

- 文生图（text-to-image）CLI：`node scripts/image/image.js "<提示词>" [flags]`
- 支持两个模型：`gpt-image-2`（默认，平台中转渠道）/ `gpt-image-2-official`（OpenAI 官方渠道），按 `--model` 切换
- 异步三步：提交 → 轮询 → 下载
- 下载图片到本地 + 打印公网 URL
- 代理感知（undici）
- `--dry-run`：构造并打印请求体，不调用 API、不计费
- 文档：`references/report_to_image.md`（agent 使用指引）、SKILL.md、根 CLAUDE.md

### 范围外（明确不做）

- CLI 层不做图生图 / inpainting 入口。API 客户端层（`buildRequestBody`）支持透传 `image_urls` / `mask_url`，供编程式进阶调用，但 CLI 默认只走文生图。
- 不把生成的图片再上传到 Vercel Blob。apimart 返回的 URL 已是稳定公网链接，且我们要下载到本地，不依赖它的时效。
- 不引入测试框架（项目无现成 test 体系）。靠纯函数可测性 + `--dry-run` + 一次真实 smoke test 验证。

---

## 2. 两个模型的差异（关键正确性依据）

apimart 在同一 `POST /v1/images/generations` 端点上通过 `model` 字段区分两个渠道，支持的字段不同。构造请求体时必须按 `model` 白名单过滤，否则中转渠道会对官方字段报错。

| 字段 | `gpt-image-2`（默认） | `gpt-image-2-official` |
|------|:---:|:---:|
| prompt / model | ✅ | ✅ |
| size / resolution | ✅ | ✅ |
| quality（auto/low/medium/high） | ❌ 不发 | ✅ |
| output_format（png/jpeg/webp）/ output_compression | ❌ 不发 | ✅ |
| background / moderation / mask_url | ❌ 不发 | ✅ |
| n（张数） | 仅 1 | 1–4 |
| image_urls（参考图） | ✅（支持 URL 与 base64 data URI 混填） | ✅（仅 URL） |
| official_fallback（bool，失败时升级到官方渠道） | ✅ | — |

**默认选 `gpt-image-2`**：更便宜、支持 base64 输入、有 `official_fallback` 兜底；需要最高画质时 `--model gpt-image-2-official`。

`size`：传比例（如 `16:9`）或像素串（如 `3840x2160`），或 `auto`。
`resolution`：`1k`（默认）/ `2k` / `4k`。`size × resolution` 由服务端映射到具体像素，客户端不计算。

---

## 3. API 调用流程（异步）

```
POST /v1/images/generations            提交，拿 task_id
  Header: Authorization: Bearer $APIMART_API_KEY
  Body:   { model, prompt, size, ...（按 model 裁剪） }
  ← 200 { code, data: { status:"submitted", task_id } }
        │
        ▼  首次等 12s，之后每 4s 轮询一次，总超时 180s
GET /v1/tasks/{task_id}?language=zh    查状态
  ← { code, data: { status, progress, result:{ images:[{ url:[...], expires_at }] } } }
        │  status ∈ {submitted/pending, processing/in_progress, completed, failed, cancelled}
        ▼  status === "completed"
data.result.images[0].url[0]           取图 URL（稳定公网链接，但 expires_at ≈ completed+24h）
        │
        ▼
fetch(url) → 写本地文件                下载到 scripts/image/output/
```

### 轮询参数（常量，不暴露到 CLI）

- `POLL_INITIAL_DELAY_MS = 12000`
- `POLL_INTERVAL_MS = 4000`
- `POLL_TIMEOUT_MS = 180000`（官方文档：high + 2k/4k 可达 130s，客户端超时建议 ≥180s）

### 端点路径

- `IMAGES_PATH = "/v1/images/generations"`（基于 apimart "OpenAI compatible" 推断；命名常量，smoke test 第一次实调确认，错了改一处）
- `BASE_URL` 默认 `https://api.apimart.ai/v1`，可由 `APIMART_BASE_URL` 覆盖

状态终态判定：`completed` / `failed` / `cancelled` 视为终态；`submitted` / `pending` / `processing` / `in_progress` 视为进行中、继续轮询。取图：`data.result.images[i].url[0]`（`url` 是数组）。

---

## 4. 文件结构

```
generating-insights-report/scripts/image/
├── image.js          # 主脚本（单文件，镜像 report.js）
├── package.json      # { type:"module", dependencies:{ undici } }
├── output/           # 下载的图片落地
│   └── .gitignore    # 忽略 *.png *.jpeg *.webp（保留目录）
└── README.md         # （可选）极简使用说明，或直接指向 references/report_to_image.md
```

`image.js` 内部分四段（注释分隔）：

1. **config + env + 代理**：`findEnvFile` / `loadEnvFile` / undici `ProxyAgent`（全部抄 report.js 的成熟实现）
2. **API client**：`submitImageTask(body)` / `getTaskStatus(taskId)` / `downloadImage(url, destPath)`
3. **orchestrator**：`generateImage(prompt, opts)` —— 提交 → 轮询 → 下载 → 返回 `{ results: [{ url, localPath }], taskId, cost }`；纯函数 `buildRequestBody(prompt, opts)` / `parseArgs(argv)`
4. **CLI 入口**：`if (isMain)` 分发

**为什么单文件**：`report.js`（~227 行）就是单文件、config+API+CLI 全包，已被认可。`image.js` 体量相当，内部分段清晰即可，不拆多文件增加心智负担。若后续图生图/批量需求增长再拆。

**依赖**：仅 `undici`（代理感知必须——本机走 7897 代理，原生 fetch 忽略 `HTTPS_PROXY`，是已知坑）。其余用 Node 内置（`fs`/`path`/`fetch`）。

---

## 5. CLI 契约

```bash
# 最简
node scripts/image/image.js "星空下的古老城堡"

# 进阶（flags 全有默认值）
node scripts/image/image.js "赛博朋克海报" \
  --model gpt-image-2-official \
  --size 16:9 --resolution 2k --quality high \
  --format jpeg --n 2 \
  -o ./my-poster

# 零成本自检
node scripts/image/image.js "测试" --dry-run
```

**位置参数**：`<prompt>`（唯一必填；缺失打印 usage 并 `exit 1`）。

**flags**（`--flag value` 与 `--flag=value` 两种写法都支持；纯 argv 手解析，不引第三方）：

| flag | 默认 | 说明 |
|------|------|------|
| `--model` | `gpt-image-2` | `gpt-image-2` \| `gpt-image-2-official` |
| `--size` | `1:1` | 比例 / 像素串 / `auto` |
| `--resolution` | `1k` | `1k` \| `2k` \| `4k` |
| `--quality` | `auto` | 仅 official 生效 |
| `--format` | `png` | png \| jpeg \| webp，仅 official 生效 |
| `--n` | `1` | 张数；official 允许 1–4，generation 强制 1 |
| `-o` / `--output` | 无 | 自定义输出路径（不带时间戳后缀） |
| `--dry-run` | — | 只打印请求体，不调 API |

非法值（如 `--model` 传了未知值、`generation` 模式下 `--n 3`）→ 友好报错 + `exit 1`。

### 终端输出（成功时）

```
URL:   https://upload.apimart.ai/f/image/xxxxx.png
本地:  scripts/image/output/20260614-103045-0.png
```

多张（`--n 2`）则每个文件打印两行。

---

## 6. 配置（.env）

在 `generating-insights-report/.env`（`scripts/image/` 向上找到的最近 `.env`，与 report.js 同款自动发现）追加：

```bash
# --- APIMart 图像生成 (generating-insights-report/scripts/image) ---
APIMART_API_KEY=sk-pVx9sulMElzFppd57fiJyjsQtlFQxgFS0BZgf8fRnMIvXkSl
APIMART_BASE_URL=https://api.apimart.ai/v1   # 可选，有默认值
```

- shell 已设的同名变量优先（与 report.js 一致）
- `.env` 不入库（确认根 `.gitignore` 覆盖 `.env`，若未覆盖需补）

---

## 7. 输出文件命名

- 默认：`scripts/image/output/<YYYYMMDD-HHMMSS>-<index>.<ext>`
  - `ext` 由 `--format` 决定（png/jpeg/webp），默认 `png`
  - `index` 从 0 起，对应 `images[]` 顺序（多张时区分）
- `-o path`：直接用给定路径（单张）；多张时追加 `-<index>` 后缀防覆盖
- `output/` 加 `.gitignore`（忽略图片、保留目录）

---

## 8. 错误处理

| 情况 | 行为 |
|------|------|
| 缺 `APIMART_API_KEY` | 友好提示去 `.env` 配置 |
| 检测到代理但未装 `undici` | 提示 `cd scripts/image && npm install undici`（抄 report.js） |
| 提交失败 / 内容审核拒绝 | 透传服务端 `code` + `error.message` + 响应体片段 |
| 轮询 180s 超时 | 报错并打印 `task_id`，提示可手动 `GET /v1/tasks/{task_id}` 复查 |
| task `failed` / `cancelled` | 透传上游 `error.message` |
| 下载失败 | **仍打印 URL** 兜底（用户可手动取图），整体不视为成功、`exit 1` |

---

## 9. 编程式接口（导出）

```js
import { generateImage, buildRequestBody, submitImageTask, getTaskStatus } from './scripts/image/image.js'

// 高层：一步到位，返回 URL + 本地路径
await generateImage('星空下的古老城堡', { size: '16:9', resolution: '2k' })
// => { results: [{ url, localPath }], taskId, cost }

// 低层：自己控流程
const body = buildRequestBody('prompt', { model: 'gpt-image-2-official', quality: 'high' })
const { task_id } = await submitImageTask(body)
const status = await getTaskStatus(task_id)
```

`buildRequestBody` 与 `parseArgs` 是纯函数，结构上随时可单测。

---

## 10. 验证策略（替代完整单测）

付费外部 API 不便自动化测试，采取三层：

1. **纯函数可测**：`buildRequestBody`（按 model 裁剪字段）、`parseArgs`、终态判定，导出后可独立断言。
2. **`--dry-run`**：打印将发送的 body，人工核对参数裁剪 / 映射正确，零成本。
3. **一次真实 smoke test**：实跑 `node scripts/image/image.js "一只橘猫坐在窗台上看夕阳，水彩画风格"`，确认端点路径、轮询、下载全链路通（成本约 $0.05）。成功后即在 `report_to_image.md` 记录实测耗时。

---

## 11. 文档更新

### A. 新建 `generating-insights-report/references/report_to_image.md`（agent 使用指引）

对标 `references/report_to_html.md` 的结构：frontmatter（`name: report-to-image`）+ 架构图 + 可调接口（CLI / 编程式）+ 输入格式（prompt + opts + model 字段矩阵）+ 环境变量 + 依赖/代理说明 + 示例。面向 agent：什么时候该生成图片报告、怎么组装提示词、怎么选 model/size/quality。

### B. 更新 `generating-insights-report/SKILL.md`

填 Image 行：

| 格式 | 输入 | 输出 |
|------|------|------|
| Image | 文本提示词（+ 可选 size/quality/model 等） | 本地图片文件 + 公网 URL |

参考文档加一行：`Image：scripts/image/，接口与用法见 references/report_to_image.md`。

### C. 更新根 `CLAUDE.md`

架构块订正 `image/` → `scripts/image/`，标注实现方式（apimart gpt-image-2）与调用入口。

---

## 12. 实现顺序（给后续 plan 参考）

1. 建目录 + `package.json`（`type: module`，dep `undici`）+ `npm install`
2. 写 `image.js`：config/env/代理段（移植 report.js）→ API client → `buildRequestBody`（含 model 字段矩阵）→ `generateImage` orchestrator → CLI
3. `--dry-run` 自检参数裁剪
4. 配 `.env`（加 `APIMART_API_KEY`）
5. 一次真实 smoke test，确认端点 + 轮询 + 下载
6. 写 `references/report_to_image.md`
7. 更新 SKILL.md + 根 CLAUDE.md
8. `output/.gitignore` + 确认 `.env` 已被忽略

---

## 13. 风险与待验证

- **POST 端点路径**：`/v1/images/generations` 基于推断。做成常量，smoke test 第一次实调确认。若 404，查 apimart `llms.txt` 修正。
- **status 枚举差异**：两份文档对轮询状态命名不完全一致（`processing` vs `in_progress`、`submitted` vs `pending`）。终态判定用集合 `{completed, failed, cancelled}`，其余一律视为进行中，兼容两种命名。
- **取图字段**：`data.result.images[i].url` 是**数组**，取 `[0]`。
- **URL 时效**：约 24h 过期，所以必须下载本地（已在范围内）。
