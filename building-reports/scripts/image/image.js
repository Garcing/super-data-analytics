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
  // data 可能是数组（提交响应: [{status,task_id}]）或对象（兼容），两种都取 task_id
  const d = data?.data
  const taskId = Array.isArray(d) ? d[0]?.task_id : d?.task_id
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
  let exitCode = 0
  try {
    const { prompt, opts, dryRun } = parseArgs(process.argv.slice(2))
    if (!prompt) {
      console.error(USAGE)
      exitCode = 1
    } else if (dryRun) {
      console.log(JSON.stringify(buildRequestBody(prompt, opts), null, 2))
    } else {
      const { results, taskId, cost } = await generateImage(prompt, opts)
      for (const r of results) {
        console.log(`URL:   ${r.url}`)
        console.log(`本地:  ${r.localPath || '(下载失败，请用上方 URL 手动取图)'}`)
        if (r.downloadError) console.log(`       └ ${r.downloadError}`)
      }
      if (cost != null) console.log(`task_id=${taskId} cost=${cost}`)
      if (results.some((r) => !r.localPath)) exitCode = 1
    }
  } catch (err) {
    console.error(err.message || String(err))
    exitCode = 1
  }
  // 干净关闭代理连接池，避免 Windows 下 process.exit 时 undici 句柄未关闭触发 libuv 断言崩溃
  if (proxyConfigured) {
    try {
      const { getGlobalDispatcher } = await import('undici')
      await getGlobalDispatcher().close()
    } catch { /* ignore */ }
  }
  process.exitCode = exitCode
}
