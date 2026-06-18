# 图片报告生成（report → image）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `generating-insights-report/scripts/image/` 实现一个 Node.js CLI，调用 apimart gpt-image-2 异步生成图片、下载到本地、打印公网 URL。

**Architecture:** 单文件 `image.js`，镜像 `scripts/html/report.js` 的成熟范式（ESM、`.env` 向上自动发现、undici 代理感知、编程式 + CLI 双接口）。异步三步：`POST /images/generations` 提交拿 `task_id` → 轮询 `GET /tasks/{id}` → 下载 `result.images[].url[0]`。两个模型（默认 `gpt-image-2` 平台中转 / `gpt-image-2-official` 官方）共享端点，按字段白名单裁剪请求体。

**Tech Stack:** Node.js v24（内置 `fetch`、ESM top-level await）、`undici`（代理感知，本机走 7897 代理）。无第三方 CLI 解析库、无测试框架——纯函数靠 `node -e` 断言 + `--dry-run` + 一次真实 smoke test 验证（依据 spec §10）。

**Spec:** `docs/superpowers/specs/2026-06-14-image-report-generation-design.md`

**运行目录约定：** 所有 CLI 命令从仓库根 `super-data-analyst/` 运行（脚本内部用 `__dirname` 定位，路径自洽）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `generating-insights-report/scripts/image/image.js` | 主脚本：config/env/代理 + 纯函数 + API client + orchestrator + CLI | 新建 |
| `generating-insights-report/scripts/image/package.json` | `{type:module}` + 依赖 `undici` | 新建 |
| `generating-insights-report/scripts/image/output/.gitignore` | 忽略生成的图片，保留目录 | 新建 |
| `generating-insights-report/.env` | 追加 `APIMART_API_KEY` / `APIMART_BASE_URL` | 修改（不入库） |
| `generating-insights-report/references/report_to_image.md` | agent 使用指引 | 新建 |
| `generating-insights-report/SKILL.md` | 填 Image 行 + 参考文档 | 修改 |
| `CLAUDE.md`（根） | 订正 `image/` 路径 | 修改 |

---

## Task 1: 脚手架（package.json + output/ + 依赖）

**Files:**
- Create: `generating-insights-report/scripts/image/package.json`
- Create: `generating-insights-report/scripts/image/output/.gitignore`

- [ ] **Step 1: 建 `package.json`**

`generating-insights-report/scripts/image/package.json`：

```json
{
  "name": "image-report",
  "private": true,
  "type": "module",
  "description": "调用 apimart gpt-image-2 生成图片报告，下载到本地并返回公网 URL",
  "dependencies": {
    "undici": "^8.4.1"
  }
}
```

- [ ] **Step 2: 建 `output/.gitignore`**

根 `.gitignore` 的 `output/*.png` 仅对仓库根生效，不覆盖本目录，故本地建一个。`generating-insights-report/scripts/image/output/.gitignore`：

```
*
!.gitignore
```

（忽略目录内所有文件，保留 `.gitignore` 自身，使空目录可入库。）

- [ ] **Step 3: 安装 undici**

Run:
```bash
cd generating-insights-report/scripts/image && npm install
```
Expected: 生成 `node_modules/` 与 `package-lock.json`；无报错。

- [ ] **Step 4: 确认 node_modules 不入库**

根 `.gitignore` 第 10 行已含 `node_modules/`（对子目录也生效，因为模式无前导斜杠）。确认：
```bash
git check-ignore generating-insights-report/scripts/image/node_modules
```
Expected: 打印该路径（表示已被忽略）。

- [ ] **Step 5: 提交脚手架**

```bash
git add generating-insights-report/scripts/image/package.json generating-insights-report/scripts/image/package-lock.json generating-insights-report/scripts/image/output/.gitignore
git commit -m "feat(image): scaffold scripts/image (package.json + undici)"
```

---

## Task 2: 实现 image.js（完整单文件）

**Files:**
- Create: `generating-insights-report/scripts/image/image.js`

本任务写出完整 `image.js`（config/env/代理 → 纯函数 → API client → orchestrator → CLI），分步验证纯函数与 `--dry-run`。Node v24 支持 top-level await 与全局 `fetch`。

- [ ] **Step 1: 写出完整 `image.js`**

`generating-insights-report/scripts/image/image.js`：

```js
/**
 * 图片报告生成（image.js）
 * ============================================================================
 * 调用 apimart gpt-image-2 异步生成图片，下载到本地并打印公网 URL。
 * 形态与 scripts/html/report.js 一致：单文件、自动加载 .env、代理感知、
 * 编程式 + CLI 双接口。
 *
 * 编程式（从 generating-insights-report/ 目录）：
 *   import { generateImage, buildRequestBody } from './scripts/image/image.js'
 *   await generateImage('提示词', { size: '16:9', resolution: '2k' })
 *
 * CLI（从仓库根）：
 *   node generating-insights-report/scripts/image/image.js "<提示词>" [--model ...] [--dry-run]
 *
 * 环境变量（自动从最近的 .env 加载，shell 已设置的优先）：
 *   APIMART_API_KEY   — apimart 中转接口密钥（必填）
 *   APIMART_BASE_URL  — 接口基址，默认 https://api.apimart.ai/v1
 */
import { writeFile, mkdir } from 'node:fs/promises'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

// ---------------------------- 常量 ----------------------------
const DEFAULT_BASE_URL = 'https://api.apimart.ai/v1'
const IMAGES_PATH = '/images/generations'
const POLL_INITIAL_DELAY_MS = 12_000
const POLL_INTERVAL_MS = 4_000
const POLL_TIMEOUT_MS = 180_000
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

const MODEL_DEFAULT = 'gpt-image-2'
const VALID_MODELS = new Set(['gpt-image-2', 'gpt-image-2-official'])

/** 各模型允许发送的字段白名单（其它字段会被裁掉，避免中转渠道报错）。 */
const PARAM_MATRIX = {
  'gpt-image-2': ['prompt', 'model', 'size', 'resolution', 'n', 'image_urls', 'official_fallback'],
  'gpt-image-2-official': [
    'prompt', 'model', 'size', 'resolution', 'quality', 'background',
    'moderation', 'output_format', 'output_compression', 'n', 'image_urls', 'mask_url',
  ],
}

// ---------- .env 自动发现 + 代理感知（移植自 scripts/html/report.js） ----------
function findEnvFile(startDir, maxUp = 6) {
  let current = resolve(startDir)
  for (let i = 0; i < maxUp; i++) {
    const candidate = join(current, '.env')
    if (existsSync(candidate)) return candidate
    const parent = dirname(current)
    if (parent === current) break // 已到文件系统根
    current = parent
  }
  return null
}

function loadEnvFile(envPath) {
  const text = readFileSync(envPath, 'utf8')
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    let value = line.slice(eq + 1).trim()
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1)
    }
    if (!(key in process.env)) process.env[key] = value
  }
}

// 模块加载时自动注入最近的 .env（shell 环境优先）
const envPath = findEnvFile(__dirname)
if (envPath) loadEnvFile(envPath)

// 代理感知：原生 fetch 默认忽略 HTTPS_PROXY，检测到代理时经 undici 接管。
const proxyUrl =
  process.env.HTTPS_PROXY || process.env.https_proxy ||
  process.env.HTTP_PROXY || process.env.http_proxy ||
  process.env.ALL_PROXY || process.env.all_proxy
let proxyConfigured = false
if (proxyUrl) {
  try {
    const { ProxyAgent, setGlobalDispatcher } = await import('undici')
    setGlobalDispatcher(new ProxyAgent(proxyUrl))
    proxyConfigured = true
  } catch {
    proxyConfigured = false // undici 未安装时留给 getConfig 给出明确提示
  }
}

/** 读取并校验基础配置。 */
function getConfig() {
  if (proxyUrl && !proxyConfigured) {
    throw new Error(`检测到代理 ${proxyUrl}，但 undici 未安装，无法走代理。请在 scripts/image 下运行: npm install undici`)
  }
  const apiKey = process.env.APIMART_API_KEY || ''
  const baseUrl = (process.env.APIMART_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '')
  if (!apiKey) {
    throw new Error('APIMART_API_KEY 未配置。请设置 APIMART_API_KEY 环境变量，或在 .env 文件中配置。')
  }
  return { apiKey, baseUrl }
}

// ---------------------------- 纯函数 ----------------------------
/**
 * 按模型白名单构造请求体。纯函数，可独立测试。
 * @param {string} prompt
 * @param {object} [opts] — model/size/resolution/quality/background/moderation/
 *                          output_format/output_compression/n/image_urls/mask_url/official_fallback
 * @returns {object} 请求体（仅含该模型允许的字段）
 */
export function buildRequestBody(prompt, opts = {}) {
  const model = opts.model || MODEL_DEFAULT
  if (!VALID_MODELS.has(model)) {
    throw new Error(`不支持的 model: ${model}，可选: ${[...VALID_MODELS].join(' / ')}`)
  }
  if (!prompt || typeof prompt !== 'string') {
    throw new Error('prompt 必填且为字符串')
  }
  const candidates = {
    prompt,
    model,
    size: opts.size ?? '1:1',
    resolution: opts.resolution ?? '1k',
    quality: opts.quality ?? 'auto',
    background: opts.background ?? 'auto',
    moderation: opts.moderation ?? 'auto',
    output_format: opts.output_format ?? 'png',
    output_compression: opts.output_compression,
    n: opts.n ?? 1,
    image_urls: opts.image_urls,
    mask_url: opts.mask_url,
    official_fallback: opts.official_fallback,
  }
  if (model === 'gpt-image-2' && candidates.n !== 1) {
    throw new Error('gpt-image-2 模型只支持 n=1；如需多张请用 --model gpt-image-2-official')
  }
  const body = {}
  for (const key of PARAM_MATRIX[model]) {
    const v = candidates[key]
    if (v !== undefined && v !== null) body[key] = v
  }
  return body
}

/**
 * 解析 CLI 参数。纯函数。
 * @param {string[]} argv — process.argv.slice(2)
 * @returns {{ prompt: string|null, opts: object, dryRun: boolean }}
 */
export function parseArgs(argv) {
  const opts = {
    model: MODEL_DEFAULT,
    size: '1:1',
    resolution: '1k',
    quality: 'auto',
    output_format: 'png',
    n: 1,
  }
  const positional = []
  let dryRun = false
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--dry-run') { dryRun = true; continue }
    if (a === '-o' || a === '--output') { opts.output = argv[++i]; continue }
    if (a.startsWith('--')) {
      let key, val
      const eq = a.indexOf('=')
      if (eq > -1) { key = a.slice(2, eq); val = a.slice(eq + 1) }
      else { key = a.slice(2); val = argv[++i] }
      switch (key) {
        case 'model': opts.model = val; break
        case 'size': opts.size = val; break
        case 'resolution': opts.resolution = val; break
        case 'quality': opts.quality = val; break
        case 'format': opts.output_format = val; break
        case 'n': {
          const n = parseInt(val, 10)
          if (Number.isNaN(n)) throw new Error(`--n 需为整数: ${val}`)
          opts.n = n
          break
        }
        default: throw new Error(`未知参数: --${key}`)
      }
      continue
    }
    positional.push(a)
  }
  const prompt = positional.join(' ').trim() || null
  return { prompt, opts, dryRun }
}

// ---------------------------- API client ----------------------------
/** 提交生成任务，返回 { taskId, raw }。 */
export async function submitImageTask(body) {
  const { apiKey, baseUrl } = getConfig()
  const res = await fetch(`${baseUrl}${IMAGES_PATH}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 401) throw new Error('APIMART_API_KEY 无效，请检查 .env 配置')
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : {} }
  catch { throw new Error(`提交失败：响应非 JSON (${res.status}): ${text.slice(0, 500)}`) }
  if (!res.ok) throw new Error(`提交失败 (${res.status}): ${JSON.stringify(data).slice(0, 500)}`)
  const taskId = data?.data?.task_id
  if (!taskId) throw new Error(`未返回 task_id: ${JSON.stringify(data).slice(0, 500)}`)
  return { taskId, raw: data }
}

/** 查询任务状态，返回 data 对象。 */
export async function getTaskStatus(taskId) {
  const { apiKey, baseUrl } = getConfig()
  const res = await fetch(`${baseUrl}/tasks/${encodeURIComponent(taskId)}?language=zh`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  })
  if (!res.ok) throw new Error(`查询任务失败 (${res.status}): ${await res.text()}`)
  const data = await res.json()
  return data?.data || data
}

// ---------------------------- orchestrator ----------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 从图片 URL 推断扩展名，失败回退到请求格式或 png。 */
function extFromUrl(url, fallback) {
  try {
    const m = new URL(url).pathname.match(/\.(png|jpe?g|webp)$/i)
    if (m) return m[1].toLowerCase()
  } catch { /* ignore */ }
  return (fallback || 'png').toLowerCase()
}

function formatTimestamp(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

/** 计算本地输出路径：-o 指定则用之（多张追加 -<index>），否则 output/<ts>-<index>.<ext>。 */
function resolveOutPath(outputOpt, index, ext, total) {
  if (outputOpt) {
    const abs = resolve(outputOpt)
    if (total > 1) {
      const e = extname(abs)
      return e ? `${abs.slice(0, -e.length)}-${index}${e}` : `${abs}-${index}.${ext}`
    }
    return abs
  }
  return join(__dirname, 'output', `${formatTimestamp(new Date())}-${index}.${ext}`)
}

async function downloadImage(url, destPath) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`下载失败 (${res.status}): ${url}`)
  const buf = Buffer.from(await res.arrayBuffer())
  await mkdir(dirname(destPath), { recursive: true })
  await writeFile(destPath, buf)
  return destPath
}

/**
 * 一步到位：提交 → 轮询 → 下载。
 * @returns {Promise<{ results: Array<{url, localPath, downloadError?}>, taskId, cost }>}
 */
export async function generateImage(prompt, opts = {}) {
  const body = buildRequestBody(prompt, opts)
  const { taskId } = await submitImageTask(body)

  // 首次延迟，之后按间隔轮询，直到终态或超时。
  await sleep(POLL_INITIAL_DELAY_MS)
  const deadline = Date.now() + POLL_TIMEOUT_MS
  let status, taskData
  while (true) {
    taskData = await getTaskStatus(taskId)
    status = taskData?.status
    if (TERMINAL_STATUSES.has(status)) break
    if (Date.now() > deadline) {
      throw new Error(`轮询超时 (${POLL_TIMEOUT_MS / 1000}s)，task_id=${taskId}，可手动复查: GET /v1/tasks/${taskId}`)
    }
    await sleep(POLL_INTERVAL_MS)
  }

  if (status !== 'completed') {
    const errMsg = taskData?.error?.message || `任务状态 ${status}`
    throw new Error(`图片生成失败: ${errMsg} (task_id=${taskId})`)
  }

  const images = taskData?.result?.images || []
  if (!images.length) throw new Error(`任务完成但无图片: ${JSON.stringify(taskData).slice(0, 300)}`)

  const results = []
  for (let i = 0; i < images.length; i++) {
    const urlArr = images[i].url
    const url = Array.isArray(urlArr) ? urlArr[0] : urlArr
    if (!url) continue
    const ext = extFromUrl(url, body.output_format)
    const entry = { url }
    try {
      entry.localPath = await downloadImage(url, resolveOutPath(opts.output, i, ext, images.length))
    } catch (e) {
      // 下载失败仍保留 URL，CLI 层会打印并 exit 1
      entry.localPath = null
      entry.downloadError = e.message
    }
    results.push(entry)
  }
  return { results, taskId, cost: taskData?.cost }
}

// ---------------------------- CLI 入口 ----------------------------
const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase()
  } catch { return false }
})()

const USAGE = `用法:
  node generating-insights-report/scripts/image/image.js "<提示词>" [选项]

选项（均有默认值）:
  --model <m>        gpt-image-2（默认，平台中转）/ gpt-image-2-official（OpenAI 官方）
  --size <s>         比例如 16:9、像素如 3840x2160、或 auto（默认 1:1）
  --resolution <r>   1k（默认）/ 2k / 4k
  --quality <q>      auto/low/medium/high（仅 official 生效，默认 auto）
  --format <f>       png/jpeg/webp（仅 official 生效，默认 png）
  --n <num>          张数，official 允许 1-4，generation 仅 1（默认 1）
  -o, --output <p>   自定义输出路径
  --dry-run          只打印请求体，不调用 API

示例:
  node generating-insights-report/scripts/image/image.js "星空下的古老城堡"
  node generating-insights-report/scripts/image/image.js "海报" --model gpt-image-2-official --size 16:9 --quality high`

if (isMain) {
  const { prompt, opts, dryRun } = parseArgs(process.argv.slice(2))
  try {
    if (!prompt) {
      console.error(USAGE)
      process.exit(1)
    }
    if (dryRun) {
      console.log(JSON.stringify(buildRequestBody(prompt, opts), null, 2))
      process.exit(0)
    }
    const { results, taskId, cost } = await generateImage(prompt, opts)
    for (const r of results) {
      console.log(`URL:   ${r.url}`)
      console.log(`本地:  ${r.localPath || '(下载失败，请用上方 URL 手动取图)'}`)
      if (r.downloadError) console.log(`       └ ${r.downloadError}`)
    }
    if (cost != null) console.log(`task_id=${taskId} cost=${cost}`)
    if (results.some((r) => !r.localPath)) process.exit(1)
  } catch (err) {
    console.error(err.message || String(err))
    process.exit(1)
  }
}
```

- [ ] **Step 2: 用 `node -e` 断言纯函数（buildRequestBody / parseArgs）**

不需要真实 API、不花钱。导入模块会触发 `.env` 加载与 undici 初始化，均无副作用。

Run（在仓库根，用 heredoc 避免转义）:
```bash
node --input-type=module <<'EOF'
import { buildRequestBody, parseArgs } from './generating-insights-report/scripts/image/image.js'
import assert from 'node:assert'

// generation 默认：仅白名单字段（含显式 n:1）
const g = buildRequestBody('测试', { size: '16:9' })
assert.deepEqual(Object.keys(g).sort(), ['model', 'n', 'prompt', 'resolution', 'size'])
assert.equal(g.model, 'gpt-image-2')
assert.equal(g.size, '16:9')
assert.equal(g.n, 1)

// official：quality/format/background/moderation 进白名单
const o = buildRequestBody('测试', { model: 'gpt-image-2-official', quality: 'high', output_format: 'jpeg' })
assert.equal(o.quality, 'high')
assert.equal(o.output_format, 'jpeg')
assert.equal(o.background, 'auto')

// generation 拒绝 n>1
assert.throws(() => buildRequestBody('t', { n: 2 }), /n=1/)

// 未知 model 报错
assert.throws(() => buildRequestBody('t', { model: 'foo' }), /不支持的 model/)

// parseArgs：位置参数 + flags + dry-run
const p = parseArgs(['提示词', '--model', 'gpt-image-2-official', '--size', '16:9', '--n', '2', '--dry-run'])
assert.equal(p.prompt, '提示词')
assert.equal(p.opts.model, 'gpt-image-2-official')
assert.equal(p.opts.size, '16:9')
assert.equal(p.opts.n, 2)
assert.equal(p.dryRun, true)

// --format 映射到 output_format
const p2 = parseArgs(['x', '--format', 'webp'])
assert.equal(p2.opts.output_format, 'webp')

// 无 prompt
assert.equal(parseArgs([]).prompt, null)

console.log('OK: pure functions pass')
EOF
```
Expected: 打印 `OK: pure functions pass`，无 AssertionError。若失败，按报错修正对应函数后重跑。

- [ ] **Step 3: 用 `--dry-run` 验证 CLI 装配 + 参数裁剪**

dry-run 不调 `getConfig`，故即便 `.env` 还没配 APIMART key 也能跑。

Run:
```bash
node generating-insights-report/scripts/image/image.js "星空下的古老城堡" --dry-run
```
Expected（generation 默认）:
```json
{
  "prompt": "星空下的古老城堡",
  "model": "gpt-image-2",
  "size": "1:1",
  "resolution": "1k",
  "n": 1
}
```

Run（official + 进阶参数）:
```bash
node generating-insights-report/scripts/image/image.js "海报" --model gpt-image-2-official --size 16:9 --quality high --format jpeg --dry-run
```
Expected: body 含 `quality:"high"`、`output_format:"jpeg"`、`background:"auto"`、`moderation:"auto"`，且**不含** `mask_url`/`image_urls`（未传则不出现）。

Run（无 prompt → 打印 usage + exit 1）:
```bash
node generating-insights-report/scripts/image/image.js --dry-run; echo "exit=$?"
```
Expected: 打印 USAGE，`exit=1`。

- [ ] **Step 4: 提交**

```bash
git add generating-insights-report/scripts/image/image.js
git commit -m "feat(image): implement image.js CLI (submit/poll/download, model param matrix)"
```

---

## Task 3: 配置 .env

**Files:**
- Modify: `generating-insights-report/.env`（不入库）

- [ ] **Step 1: 追加 APIMART 配置段**

在 `generating-insights-report/.env` 末尾追加（保留现有内容）：

```bash

# --- APIMart 图像生成 (generating-insights-report/scripts/image) ---
APIMART_API_KEY=sk-pVx9sulMElzFppd57fiJyjsQtlFQxgFS0BZgf8fRnMIvXkSl
APIMART_BASE_URL=https://api.apimart.ai/v1
```

- [ ] **Step 2: 确认 .env 未被 git 追踪**

Run:
```bash
git check-ignore generating-insights-report/.env && echo "ignored: OK"
```
Expected: 打印该路径 + `ignored: OK`。若未忽略，**不得** `git add` 此文件。

- [ ] **Step 3: 无需提交（.env 不入库）**

本任务不产生提交。进入 Task 4 的 smoke test 时脚本会自动读到该 key。

---

## Task 4: 真实 smoke test（端点 + 轮询 + 下载全链路）

**Files:** 无代码改动（除非发现端点路径需修正）

> 成本约 $0.05；失败不计费。本任务验证 spec §3 的端点路径与取图字段。若 `POST /images/generations` 返回 404，按 spec §13 查 apimart `llms.txt` 修正 `IMAGES_PATH` 常量后重跑。

- [ ] **Step 1: 跑一次默认（generation）生成**

Run（本机走 7897 代理，脚本经 undici 自动走代理；首次轮询约 12s 起、单张通常 30–60s）:
```bash
node generating-insights-report/scripts/image/image.js "一只橘猫坐在窗台上看夕阳，水彩画风格"
```
Expected: 约 30–60s 后打印两行：
```
URL:   https://upload.apimart.ai/f/image/xxxxx.png
本地:  generating-insights-report/scripts/image/output/20260614-HHMMSS-0.png
```
且 `output/` 下确有该 png 文件（用 `ls generating-insights-report/scripts/image/output/` 确认）。

- [ ] **Step 2: 若端点 404，修正路径常量**

若 Step 1 报 `提交失败 (404)`：拉取 apimart 文档索引确认正确路径：
```bash
curl -s https://docs.apimart.ai/llms.txt | grep -i image
```
把 `image.js` 顶部 `const IMAGES_PATH = '/images/generations'` 改为正确值，重跑 Step 1。修正后：
```bash
git add generating-insights-report/scripts/image/image.js
git commit -m "fix(image): correct images endpoint path"
```

- [ ] **Step 3: 记录实测耗时到 report_to_image.md（Task 5 会用到）**

记下本次 `actual_time`（若终端未打印 cost 行，可从轮询耗时估算），供 Task 5 写文档时引用。无需提交。

---

## Task 5: 写 references/report_to_image.md（agent 使用指引）

**Files:**
- Create: `generating-insights-report/references/report_to_image.md`

对标 `references/report_to_html.md` 的结构：frontmatter + 架构图 + 可调接口 + 输入格式 + 环境变量 + 依赖/代理 + 示例。面向 agent：何时用图片报告、怎么组装 prompt、怎么选 model/size/quality。

- [ ] **Step 1: 写出 `report_to_image.md`**

`generating-insights-report/references/report_to_image.md`：

````markdown
---
name: report-to-image
description: 用 apimart gpt-image-2 生成图片（封面/配图/海报），下载到本地并返回公网 URL
---

# 图片报告（report → image）

把一段文本描述生成为图片，落地到本地文件，并返回 apimart 的稳定公网 URL。适合为分析报告生成封面图、关键结论的示意配图、海报。

## 架构一瞥

```
调用方 ──POST /images/generations + Bearer key──▶ apimart ──task_id──▶ 调用方
                                                          │
调用方 ──GET /tasks/{task_id}（轮询）─────────────────────┘
                       │ status=completed
                       ▼
            result.images[0].url[0]  ──fetch──▶ 下载到 scripts/image/output/
```

- **异步**：提交返回 `task_id`，需轮询 `/v1/tasks/{task_id}` 直到 `completed`，单张通常 30–60s。
- **取图**：`data.result.images[i].url` 是**数组**，取 `[0]`。
- **URL 时效**：约 24h 过期（`expires_at ≈ completed + 24h`），脚本会下载到本地，请以本地文件为准。

---

## 可调用的接口

### A. CLI（最常用，从仓库根运行）

```bash
node generating-insights-report/scripts/image/image.js "<提示词>" [选项]
```

| 选项 | 默认 | 说明 |
|------|------|------|
| `--model` | `gpt-image-2` | `gpt-image-2`（平台中转，便宜）/ `gpt-image-2-official`（OpenAI 官方，画质/参数最全） |
| `--size` | `1:1` | 比例（`16:9`/`9:16`/`4:3` …）、像素串（`3840x2160`）、或 `auto` |
| `--resolution` | `1k` | `1k`/`2k`/`4k` |
| `--quality` | `auto` | auto/low/medium/high（**仅 official**） |
| `--format` | `png` | png/jpeg/webp（**仅 official**） |
| `--n` | `1` | 张数，official 允许 1–4，generation 仅 1 |
| `-o, --output` | 自动 | 自定义输出路径 |
| `--dry-run` | — | 只打印请求体，不调用 API、不计费 |

成功输出两行：公网 `URL:` 与 `本地:` 路径（多张则逐张打印）。

### B. JS 便捷接口（`image.js`）

封装了上面的流程，自动处理 `.env` 加载、代理、轮询。导出：`generateImage` / `buildRequestBody` / `submitImageTask` / `getTaskStatus`。

```js
import { generateImage, buildRequestBody } from './scripts/image/image.js'

// 高层：一步到位
const { results, taskId, cost } = await generateImage('星空下的古老城堡', {
  size: '16:9', resolution: '2k',
})
// results: [{ url, localPath }]

// 低层：自己控流程（如仅想拿 task_id 后续手动查）
const body = buildRequestBody('prompt', { model: 'gpt-image-2-official', quality: 'high' })
const { taskId } = await submitImageTask(body)
```

### C. 两个模型的字段差异（关键）

同一端点，靠 `model` 区分渠道，**支持字段不同**，`buildRequestBody` 会按白名单自动裁剪：

| 字段 | `gpt-image-2`（默认） | `gpt-image-2-official` |
|------|:---:|:---:|
| prompt / size / resolution | ✅ | ✅ |
| quality / format / background / moderation / mask | ❌ | ✅ |
| n | 仅 1 | 1–4 |
| image_urls（base64 也行） | ✅ | ✅（仅 URL） |
| official_fallback（失败升级官方） | ✅ | — |

> 选型：日常用默认 `gpt-image-2`（便宜 + base64 输入 + 官方兜底）；要最高画质/多张/指定格式用 `--model gpt-image-2-official`。

---

## 何时用图片报告

- 给一份分析报告配**封面图 / 关键结论示意图**（HTML 报告里嵌入）
- 生成**数据海报**（`--size 2:3` / `9:16` + `--resolution 2k`）
- 批量出**候选图**供挑选（`--model gpt-image-2-official --n 4`）

提示词建议：主体 + 场景 + 风格 + 构图，例如「一只橘猫坐在窗台上看夕阳，水彩画风格，暖色调，居中构图」。比例只通过 `--size` 传，不要在 prompt 里重复写比例（避免上游理解冲突）。

---

## 环境变量

从最近的 `.env` 自动加载（`generating-insights-report/.env`）：

| 变量 | 用途 |
|------|------|
| `APIMART_API_KEY` | apimart 中转接口密钥（必填） |
| `APIMART_BASE_URL` | 接口基址，默认 `https://api.apimart.ai/v1` |

### 依赖与代理

- **依赖**：首次使用前在 `scripts/image` 下 `npm install`（装 `undici`）。
- **代理**：自动检测 `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`，经 `undici` 的 `ProxyAgent` 走代理（与 Python `requests` 行为一致）。代理下未装 `undici` 会明确报错。
- Node 自带 `fetch`（Node 18+），除 `undici` 外无其它外部依赖。

---

## 示例

```bash
# 最简
node generating-insights-report/scripts/image/image.js "星空下的古老城堡"

# 2K 横版海报（官方画质）
node generating-insights-report/scripts/image/image.js "赛博朋克夜景" \
  --model gpt-image-2-official --size 16:9 --resolution 2k --quality high --format jpeg

# 零成本自检请求体
node generating-insights-report/scripts/image/image.js "测试" --dry-run
```

> 实测：默认 `gpt-image-2` + 1k 单张约 `_XX_s` 完成（Task 4 smoke test 记录值，填入实际耗时）。
````

- [ ] **Step 2: 回填 Task 4 实测耗时**

把上一行 `> 实测：…约 `_XX_s` 完成` 中的 `_XX_` 替换为 Task 4 记录的实际秒数。

- [ ] **Step 3: 提交**

```bash
git add generating-insights-report/references/report_to_image.md
git commit -m "docs(image): add references/report_to_image.md agent guide"
```

---

## Task 6: 更新 SKILL.md 与根 CLAUDE.md

**Files:**
- Modify: `generating-insights-report/SKILL.md`
- Modify: `CLAUDE.md`（根）

- [ ] **Step 1: 更新 SKILL.md 的 Image 行与参考文档**

把 `generating-insights-report/SKILL.md` 中：

```markdown
| Image |  |  |
```

改为：

```markdown
| Image | 文本提示词（+ 可选 size/quality/model 等） | 本地图片文件 + 公网 URL |
```

并把参考文档区：

```markdown
- Image
```

改为：

```markdown
- Image：`scripts/image/`，接口与用法见 `references/report_to_image.md`
```

- [ ] **Step 2: 更新根 CLAUDE.md 架构块**

把根 `CLAUDE.md` 架构块里的：

```
    image/                          图片报告（已实现）
```

改为：

```
    scripts/image/                  图片报告（apimart gpt-image-2，CLI + 编程式）
```

- [ ] **Step 3: 提交**

```bash
git add generating-insights-report/SKILL.md CLAUDE.md
git commit -m "docs(image): wire image skill into SKILL.md and root CLAUDE.md"
```

---

## 完成标准（Definition of Done）

- [ ] `node .../image.js "<prompt>"` 端到端跑通：打印 URL + 落地本地文件
- [ ] `--dry-run` 对两个 model 都正确裁剪字段（Task 2 Step 3 验证）
- [ ] 纯函数 `node -e` 断言全过（Task 2 Step 2）
- [ ] `.env` 含 `APIMART_API_KEY` 且不入库
- [ ] `references/report_to_image.md` 写好、实测耗时回填
- [ ] SKILL.md + 根 CLAUDE.md 订正
- [ ] 全部任务各自提交，工作区无遗留无关改动
