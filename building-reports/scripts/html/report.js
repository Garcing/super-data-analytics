/**
 * HTML 报告客户端（report.js）
 * ============================================================================
 * 封装与 Vercel 报告 API 的全部交互：发布 / 列出 / 读取 / 删除。
 * 原 publishReport.mjs 的演进版，统一管理四种操作。
 *
 * 编程式：
 *   import { publishReport, listReports, getReport, deleteReport } from './report.js'
 *
 * CLI（从 generating-insights-report/ 目录运行）：
 *   node scripts/html/report.js publish <report.json> [reportId]
 *   node scripts/html/report.js list
 *   node scripts/html/report.js get <reportId>
 *   node scripts/html/report.js delete <reportId>
 *
 * 环境变量（自动从最近的 .env 加载，shell 已设置的优先）：
 *   VERCEL_REPORTS_URL  — Vercel 项目 URL，如 https://project-6hzz6.vercel.app
 *   VERCEL_API_SECRET   — POST/DELETE 鉴权密钥
 */
import { readFile } from 'node:fs/promises'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

/**
 * 从 startDir 向上逐级查找最近的 .env 文件（最多 maxUp 层）。
 * 避免项目结构变动后路径错位。
 */
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

/**
 * 解析 .env 并注入 process.env（仅在尚未设置时注入，shell 环境优先）。
 */
function loadEnvFile(envPath) {
  const text = readFileSync(envPath, 'utf8')
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    let value = line.slice(eq + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    if (!(key in process.env)) process.env[key] = value
  }
}

// 模块加载时自动注入最近的 .env
const envPath = findEnvFile(__dirname)
if (envPath) loadEnvFile(envPath)

// 代理感知：原生 fetch 默认忽略 HTTPS_PROXY/HTTP_PROXY（与 Python requests 不同），
// 检测到代理环境变量时，通过 undici 的 ProxyAgent 显式接管，保证代理网络下也能访问。
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

/** 读取并校验基础配置（URL + 密钥 + 代理）。 */
function getConfig() {
  if (proxyUrl && !proxyConfigured) {
    throw new Error(
      `检测到代理 ${proxyUrl}，但 undici 未安装，无法走代理。请在 scripts/html 下运行: npm install undici`
    )
  }
  const vercelUrl = (process.env.VERCEL_REPORTS_URL || '').replace(/\/+$/, '')
  const apiSecret = process.env.VERCEL_API_SECRET || ''
  if (!vercelUrl) {
    throw new Error('Vercel URL 未配置。请设置 VERCEL_REPORTS_URL 环境变量，或在 .env 文件中配置。')
  }
  if (!apiSecret) {
    throw new Error('API Secret 未配置。请设置 VERCEL_API_SECRET 环境变量，或在 .env 文件中配置。')
  }
  return { vercelUrl, apiSecret }
}

/** 统一请求：GET 公开，POST/DELETE 带 Bearer 鉴权。返回解析后的 JSON。 */
async function request(path, { method = 'GET', body } = {}) {
  const { vercelUrl, apiSecret } = getConfig()
  const res = await fetch(`${vercelUrl}${path}`, {
    method,
    headers: {
      ...(method !== 'GET' ? { Authorization: `Bearer ${apiSecret}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) throw new Error('API Secret 无效，请检查 VERCEL_API_SECRET 配置')
  if (!res.ok) throw new Error(`请求失败 (${res.status}): ${await res.text()}`)
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

/**
 * 发布一份报告，返回公网 URL。
 * @param {object} reportData — 报告 JSON（meta + summary + conclusions，格式见 references/report_to_html.md，位于 generating-insights-report 根目录）
 * @param {string} reportId   — 报告唯一标识，如 'report-20260415-流失分析'
 * @returns {Promise<string>} 公网 URL
 */
export async function publishReport(reportData, reportId) {
  if (!reportId || !reportData?.meta?.title) {
    throw new Error('缺少必要字段: reportId 与 reportData.meta.title')
  }
  const { vercelUrl } = getConfig()
  const result = await request('/api/reports', { method: 'POST', body: { ...reportData, id: reportId } })
  return `${vercelUrl}${result.url}`
}

/**
 * 列出全部报告（读索引，公开）。
 * @returns {Promise<Array>} 索引条目数组（id / title / created_at / summary_preview / stats）
 */
export async function listReports() {
  const data = await request('/api/reports')
  return Array.isArray(data) ? data : (data.reports || [])
}

/**
 * 读取单份报告（公开）。
 * @param {string} id — 报告 id
 * @returns {Promise<object>} 完整报告 JSON
 */
export async function getReport(id) {
  if (!id) throw new Error('缺少 reportId')
  return request(`/api/reports/${encodeURIComponent(id)}`)
}

/**
 * 删除一份报告（需鉴权，同步更新索引）。
 * @param {string} id — 报告 id
 * @returns {Promise<{success: boolean}>}
 */
export async function deleteReport(id) {
  if (!id) throw new Error('缺少 reportId')
  return request(`/api/reports/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// ---------------------------- CLI 入口 ----------------------------
const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase()
  } catch {
    return false
  }
})()

const USAGE = `用法（从 generating-insights-report/ 目录运行）:
  node scripts/html/report.js publish <reportId>                 发布 cache/<reportId>.json，打印公网链接
  node scripts/html/report.js list                               列出全部报告
  node scripts/html/report.js get <reportId>                     打印某份报告 JSON
  node scripts/html/report.js delete <reportId>                  删除某份报告`

if (isMain) {
  const [, , cmd, ...rest] = process.argv
  try {
    switch (cmd) {
      case 'publish': {
        const [id] = rest
        if (!id) throw new Error('用法: node scripts/html/report.js publish <reportId>  (读取 cache/<reportId>.json)')
        const jsonPath = join(__dirname, 'cache', `${id}.json`)
        if (!existsSync(jsonPath)) {
          throw new Error(`找不到报告文件: ${jsonPath}\n请把报告 JSON 放到 scripts/html/cache/<reportId>.json`)
        }
        const data = JSON.parse(await readFile(jsonPath, 'utf8'))
        console.log(await publishReport(data, id))
        break
      }
      case 'list': {
        const reports = await listReports()
        if (!reports.length) { console.log('(暂无报告)'); break }
        console.log(['id', 'created_at', 'title'].join('\t'))
        for (const r of reports) {
          console.log([r.id, r.created_at || '', r.title || ''].join('\t'))
        }
        break
      }
      case 'get': {
        const [id] = rest
        if (!id) throw new Error('用法: node scripts/html/report.js get <reportId>')
        console.log(JSON.stringify(await getReport(id), null, 2))
        break
      }
      case 'delete': {
        const [id] = rest
        if (!id) throw new Error('用法: node scripts/html/report.js delete <reportId>')
        await deleteReport(id)
        console.log(`已删除: ${id}`)
        break
      }
      default:
        console.error(USAGE)
        process.exit(1)
    }
  } catch (err) {
    console.error(cmd && !['publish', 'list', 'get', 'delete'].includes(cmd) ? USAGE : (err.message || String(err)))
    process.exit(1)
  }
}
