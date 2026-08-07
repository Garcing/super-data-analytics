/**
 * 图片报告生成（image.js）
 * ============================================================================
 * 调用 apimart gpt-image-2 异步生成图片，下载到本地并打印公网 URL。
 * 异步流程拆成三步，任意一步可断点续跑：
 *   submit   提交任务 → 拿 task_id
 *   status   按 task_id 轮询到终态 → 打印状态 + 图片 URL
 *   download 按 task_id 下载图片到 --output 路径
 *   generate 一键到底：提交 → 轮询 → 下载。
 *
 * CLI（从 building-reports/ 目录运行）：
 *   node scripts/image/image.js generate [--prompt "<提示词>"|@file|-] [选项] --output <路径> # 一键
 *   node scripts/image/image.js submit [--prompt "<提示词>"|@file|-] [选项] [--dry-run] # 只提交
 *   node scripts/image/image.js status <task_id>                        # 只轮询
 *   node scripts/image/image.js download <task_id> --output <路径>       # 只下载
 *
 * 凭证统一来自 ~/.super-data-analytics/config.json 的 env 块（APIMART_API_KEY /
 * APIMART_BASE_URL）；脚本不读 .env、不依赖环境变量导出。
 */
import { writeFile, mkdir } from 'node:fs/promises'
import { dirname, join, resolve, extname } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { loadConfig, ensureProxyEnv, parseInputFlag, readContentSource } from '../lib/shared.js'

const CREDENTIAL_KEYS = ['APIMART_API_KEY', 'APIMART_BASE_URL']

// 模块加载时注入凭证 + 代理（与 querying-data / report.js 同构：config.json 唯一来源）
loadConfig(CREDENTIAL_KEYS)
const proxyOk = ensureProxyEnv()

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

// ---------------------------- 配置 ----------------------------
/** 读取并校验基础配置。 */
function getConfig() {
  const apiKey = process.env.APIMART_API_KEY || ''
  const baseUrl = (process.env.APIMART_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '')
  if (!apiKey) {
    throw new Error('APIMART_API_KEY 未配置。请写入 ~/.super-data-analytics/config.json 的 env 块后重试。')
  }
  return { apiKey, baseUrl }
}

// ---------------------------- 纯函数（内部使用，不对外导出） ----------------------------
/**
 * 按模型白名单构造请求体。纯函数。
 * @param {string} prompt
 * @param {object} [opts] — model/size/resolution/quality/background/moderation/
 *                          output_format/output_compression/n/image_urls/mask_url/official_fallback
 * @returns {object} 请求体（仅含该模型允许的字段）
 */
function buildRequestBody(prompt, opts = {}) {
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
 * 解析 CLI 参数（含子命令识别）。
 * @param {string[]} argv — process.argv.slice(2)
 * @returns {{ sub: string, promptOptions: object|null, taskId: string|null, opts: object, dryRun: boolean, output: {provided: boolean, path: string|null} }}
 */
const SUBCOMMANDS = new Set(['generate', 'submit', 'status', 'download'])

function parseArgs(argv) {
  if (argv.length === 0 || !SUBCOMMANDS.has(argv[0])) {
    throw new Error(USAGE)
  }
  const sub = argv[0]
  const rest = argv.slice(1)

  const opts = {
    model: MODEL_DEFAULT,
    size: '1:1',
    resolution: '1k',
    quality: 'auto',
    output_format: 'png',
    n: 1,
  }
  const positional = []
  let promptRaw = null
  let dryRun = false
  // --output 值可选：裸 --output → path=null（兜底 ~/Downloads）；--output <p> → path=p。
  const output = { provided: false, path: null }

  for (let i = 0; i < rest.length; i++) {
    const a = rest[i]
    if (a === '--dry-run') { dryRun = true; continue }
    if (a === '--output') {
      output.provided = true
      const next = rest[i + 1]
      if (next !== undefined && !next.startsWith('--')) { output.path = next; i++ }
      else { output.path = null }
      continue
    }
    if (a.startsWith('--')) {
      let key, val
      const eq = a.indexOf('=')
      if (eq > -1) { key = a.slice(2, eq); val = a.slice(eq + 1) }
      else { key = a.slice(2); val = rest[++i] }
      switch (key) {
        case 'prompt':
          if (val === undefined || val.startsWith('--')) throw new Error('--prompt 需要指定值（inline 内容 / @文件 / -）')
          promptRaw = val
          break
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

  const taskId = (sub === 'status' || sub === 'download') ? (positional[0] || null) : null
  let promptOptions = null
  if (sub === 'generate' || sub === 'submit') {
    if (positional.length > 0) {
      throw new Error(`${sub} 不接受位置参数提示词，请使用 --prompt "<提示词>"、--prompt @<文件>、--prompt - 或 stdin`)
    }
    promptOptions = parseInputFlag(promptRaw)
  } else if (positional.length > 1) {
    throw new Error(`${sub} 只接受一个 task_id 位置参数`)
  }
  return { sub, promptOptions, taskId, opts, dryRun, output }
}

async function readPrompt(promptOptions) {
  if (promptOptions.source === 'stdin' && process.stdin.isTTY) {
    throw new Error('未提供提示词且 stdin 是终端。请用 --prompt "<提示词>"、--prompt @<文件>、--prompt - 或管道传入')
  }
  return readContentSource(promptOptions, process.stdin, { label: '提示词' })
}

// ---------------------------- API client ----------------------------
/** 提交生成任务，返回 { taskId, raw }。 */
async function submitImageTask(body) {
  const { apiKey, baseUrl } = getConfig()
  const res = await fetch(`${baseUrl}${IMAGES_PATH}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 401) throw new Error('APIMART_API_KEY 无效，请检查 config.json 配置')
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
async function getTaskStatus(taskId) {
  const { apiKey, baseUrl } = getConfig()
  const res = await fetch(`${baseUrl}/tasks/${encodeURIComponent(taskId)}?language=zh`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  })
  if (!res.ok) throw new Error(`查询任务失败 (${res.status}): ${await res.text()}`)
  const data = await res.json()
  return data?.data || data
}

// ---------------------------- orchestrator（内部，不对外导出） ----------------------------
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

/**
 * 计算本地输出路径。
 * - --output <path>：用之（多张追加 -<index>）
 * - 裸 --output：兜底 ~/Downloads/<ts>-<index>.<ext>
 * 落盘根目录由 agent 经 --output 决定；脚本不假设默认工作区目录。
 */
function resolveOutPath(output, index, ext, total) {
  if (output.path) {
    const abs = resolve(output.path)
    if (total > 1) {
      const e = extname(abs)
      return e ? `${abs.slice(0, -e.length)}-${index}${e}` : `${abs}-${index}.${ext}`
    }
    return abs
  }
  return join(homedir(), 'Downloads', `${formatTimestamp(new Date())}-${index}.${ext}`)
}

/** 下载类命令必须显式 --output（裸 --output 兜底 ~/Downloads）；不传则报错。 */
function requireOutput(output) {
  if (!output.provided) {
    throw new Error(
      '需要 --output <路径>（或裸 --output 兜底 ~/Downloads）。' +
      '建议 agent 落到 <工作区>/.super-data-analytics/results/<名字>.<ext>',
    )
  }
}

async function downloadImage(url, destPath) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`下载失败 (${res.status}): ${url}`)
  const buf = Buffer.from(await res.arrayBuffer())
  await mkdir(dirname(destPath), { recursive: true })
  await writeFile(destPath, buf)
  return destPath
}

/** 轮询到终态（completed/failed/cancelled）或超时。返回 { status, taskData }。 */
async function pollUntilTerminal(taskId) {
  await sleep(POLL_INITIAL_DELAY_MS)
  const deadline = Date.now() + POLL_TIMEOUT_MS
  while (true) {
    const taskData = await getTaskStatus(taskId)
    const status = taskData?.status
    if (TERMINAL_STATUSES.has(status)) return { status, taskData }
    if (Date.now() > deadline) {
      throw new Error(`轮询超时 (${POLL_TIMEOUT_MS / 1000}s)，task_id=${taskId}，可手动复查: GET /v1/tasks/${taskId}`)
    }
    await sleep(POLL_INTERVAL_MS)
  }
}

/** 从已完成的 taskData 里下载全部图片。返回 [{ url, localPath, downloadError? }]。 */
async function downloadImagesFromTask(taskData, outputFormat, output) {
  const images = taskData?.result?.images || []
  if (!images.length) throw new Error(`任务完成但无图片: ${JSON.stringify(taskData).slice(0, 300)}`)
  const results = []
  for (let i = 0; i < images.length; i++) {
    const urlArr = images[i].url
    const url = Array.isArray(urlArr) ? urlArr[0] : urlArr
    if (!url) continue
    const ext = extFromUrl(url, outputFormat)
    const entry = { url }
    try {
      entry.localPath = await downloadImage(url, resolveOutPath(output, i, ext, images.length))
    } catch (e) {
      // 下载失败仍保留 URL，CLI 层会打印并 exit 1
      entry.localPath = null
      entry.downloadError = e.message
    }
    results.push(entry)
  }
  return results
}

// ---------------------------- CLI 入口 ----------------------------
const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase()
  } catch { return false }
})()

const USAGE = `用法（从 building-reports/ 目录运行）:
  一键（提交 → 轮询 → 下载）:
    node scripts/image/image.js generate [--prompt "<提示词>"|@file|-] --output <路径> [选项]
  断点续跑（三步任选）:
    node scripts/image/image.js submit   [--prompt "<提示词>"|@file|-] [选项] [--dry-run] # 只提交，打印 task_id
    node scripts/image/image.js status   <task_id>                        # 轮询到终态，打印状态 + 图片 URL
    node scripts/image/image.js download <task_id> --output <路径>         # 下载图片

提示词输入（三态，同 querying-data 的 --sql / --payload）:
  --prompt "<文本>"  inline
  --prompt @<file>   文件
  --prompt -         stdin（管道）
  不传 --prompt 时走 stdin。

--output <路径> 下载落盘路径（下载类命令必填）；裸 --output 兜底 ~/Downloads。
                agent 建议落 <工作区>/.super-data-analytics/results/<名字>.<ext>

选项（生成参数，均有默认值）:
  --model <m>        gpt-image-2（默认，平台中转）/ gpt-image-2-official（OpenAI 官方）
  --size <s>         比例如 16:9、像素如 3840x2160、或 auto（默认 1:1）
  --resolution <r>   1k（默认）/ 2k / 4k
  --quality <q>      auto/low/medium/high（仅 official 生效，默认 auto）
  --format <f>       png/jpeg/webp（仅 official 生效，默认 png）
  --n <num>          张数，official 允许 1-4，generation 仅 1（默认 1）
  --dry-run          只打印请求体，不调用 API（仅 submit / 一键）

示例:
  node scripts/image/image.js generate --prompt "海报" --output ./.super-data-analytics/results/poster.png --size 16:9
  node scripts/image/image.js generate --prompt @./.super-data-analytics/scratch/poster-prompt.txt --output ./.super-data-analytics/results/poster.png --size 16:9
  # 断点续跑：
  node scripts/image/image.js submit --prompt "海报" --size 16:9      # → 拿到 task_id
  node scripts/image/image.js status  <task_id>              # → 等到 completed
  node scripts/image/image.js download <task_id> --output ./.super-data-analytics/results/poster.png`

function printResults(results, taskId, cost) {
  for (const r of results) {
    console.log(`URL:   ${r.url}`)
    console.log(`本地:  ${r.localPath || '(下载失败，请用上方 URL 手动取图)'}`)
    if (r.downloadError) console.log(`       └ ${r.downloadError}`)
  }
  if (taskId) console.log(`task_id=${taskId}`)
  if (cost != null) console.log(`cost=${cost}`)
}

export async function runCli(argv = process.argv.slice(2)) {
  let exitCode = 0
  try {
    const { sub, promptOptions, taskId, opts, dryRun, output } = parseArgs(argv)

    switch (sub) {
      case 'generate': {
        const prompt = await readPrompt(promptOptions)
        if (dryRun) { console.log(JSON.stringify(buildRequestBody(prompt, opts), null, 2)); break }
        requireOutput(output)
        const body = buildRequestBody(prompt, opts)
        const { taskId: tid } = await submitImageTask(body)
        const { status, taskData } = await pollUntilTerminal(tid)
        if (status !== 'completed') {
          const errMsg = taskData?.error?.message || `任务状态 ${status}`
          throw new Error(`图片生成失败: ${errMsg} (task_id=${tid})，可续跑: image.js status ${tid}`)
        }
        const results = await downloadImagesFromTask(taskData, body.output_format, output)
        printResults(results, tid, taskData?.cost)
        if (results.some((r) => !r.localPath)) exitCode = 1
        break
      }
      case 'submit': {
        const prompt = await readPrompt(promptOptions)
        const body = buildRequestBody(prompt, opts)
        if (dryRun) { console.log(JSON.stringify(body, null, 2)); break }
        const { taskId: tid, raw } = await submitImageTask(body)
        const d = raw?.data
        const cost = Array.isArray(d) ? d[0]?.cost : d?.cost
        console.log(JSON.stringify({ task_id: tid, ...(cost != null ? { cost } : {}) }, null, 2))
        break
      }
      case 'status': {
        if (!taskId) throw new Error('用法: image.js status <task_id>')
        const { status, taskData } = await pollUntilTerminal(taskId)
        const out = { task_id: taskId, status }
        if (status === 'completed') {
          out.cost = taskData?.cost ?? null
          out.images = (taskData?.result?.images || []).map((im) => {
            const u = im.url
            return { url: Array.isArray(u) ? u[0] : u }
          })
        } else {
          out.error = taskData?.error?.message || `任务未完成: ${status}`
          exitCode = 1
        }
        console.log(JSON.stringify(out, null, 2))
        break
      }
      case 'download': {
        if (!taskId) throw new Error('用法: image.js download <task_id> --output <路径>')
        requireOutput(output)
        const { status, taskData } = await pollUntilTerminal(taskId)
        if (status !== 'completed') {
          throw new Error(`任务未完成 (${status})，无法下载。先用 status 确认: image.js status ${taskId}`)
        }
        const results = await downloadImagesFromTask(taskData, opts.output_format, output)
        printResults(results, taskId, taskData?.cost)
        if (results.some((r) => !r.localPath)) exitCode = 1
        break
      }
    }
  } catch (err) {
    console.error(err.message || String(err))
    exitCode = 1
  }
  if (exitCode !== 0) process.exitCode = exitCode
}

if (isMain && proxyOk) {
  await runCli()
}
