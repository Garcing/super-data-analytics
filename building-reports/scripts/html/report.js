/**
 * HTML 报告客户端（report.js）
 * ============================================================================
 * 封装与 Vercel 报告 API 的全部交互：发布 / 列出 / 读取 / 删除。只暴露 CLI，
 * 不导出 JS 编程接口——发布/读取逻辑为内部函数。
 *
 * CLI（从 building-reports/ 目录运行）：
 *   node scripts/html/report.js publish --id <reportId> [--report "<json>" | --report @<file> | --report -]
 *   node scripts/html/report.js list
 *   node scripts/html/report.js get <reportId>
 *   node scripts/html/report.js delete <reportId>
 *
 * 凭证统一来自 ~/.super-data-analytics/config.json 的 env 块（VERCEL_REPORTS_URL /
 * VERCEL_API_SECRET）；脚本不读 .env、不依赖环境变量导出。
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  loadConfig,
  setupProxy,
  parseInputFlag,
  readContentSource,
} from '../lib/shared.js'

const CREDENTIAL_KEYS = ['VERCEL_REPORTS_URL', 'VERCEL_API_SECRET']

// 模块加载时注入凭证 + 代理（与 querying-data 同构：config.json 唯一来源）
loadConfig(CREDENTIAL_KEYS)
const proxyState = await setupProxy()

/** 读取并校验基础配置（URL + 密钥 + 代理）。 */
function getConfig() {
  if (proxyState.proxyUrl && !proxyState.proxyConfigured) {
    throw new Error(
      `检测到代理 ${proxyState.proxyUrl}，但 undici 未安装，无法走代理。请在 scripts/html 下运行: npm install undici`,
    )
  }
  const vercelUrl = (process.env.VERCEL_REPORTS_URL || '').replace(/\/+$/, '')
  const apiSecret = process.env.VERCEL_API_SECRET || ''
  if (!vercelUrl) {
    throw new Error('VERCEL_REPORTS_URL 未配置。请写入 ~/.super-data-analytics/config.json 的 env 块后重试。')
  }
  if (!apiSecret) {
    throw new Error('VERCEL_API_SECRET 未配置。请写入 ~/.super-data-analytics/config.json 的 env 块后重试。')
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
  if (res.status === 401) throw new Error('API Secret 无效，请检查 config.json 里的 VERCEL_API_SECRET')
  if (!res.ok) throw new Error(`请求失败 (${res.status}): ${await res.text()}`)
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

/**
 * 发布一份报告，返回公网 URL。
 * @param {object} reportData — 报告 JSON（meta + summary + conclusions，格式见 references/report_to_html.md）
 * @param {string} reportId   — 报告唯一标识，如 'report-20260415-流失分析'
 * @returns {Promise<string>} 公网 URL
 */
async function publishReport(reportData, reportId) {
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
async function listReports() {
  const data = await request('/api/reports')
  return Array.isArray(data) ? data : (data.reports || [])
}

/**
 * 读取单份报告（公开）。
 * @param {string} id — 报告 id
 * @returns {Promise<object>} 完整报告 JSON
 */
async function getReport(id) {
  if (!id) throw new Error('缺少 reportId')
  return request(`/api/reports/${encodeURIComponent(id)}`)
}

/**
 * 删除一份报告（需鉴权，同步更新索引）。
 * @param {string} id — 报告 id
 * @returns {Promise<{success: boolean}>}
 */
async function deleteReport(id) {
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

const USAGE = `用法（从 building-reports/ 目录运行）:
  发布（--report 三种来源，同 querying-data 的 --query）:
    node scripts/html/report.js publish --id <reportId> --report "<json>"     # inline
    node scripts/html/report.js publish --id <reportId> --report @<file>      # 文件（建议放 <工作区>/.super-data-analytics/scratch/）
    node scripts/html/report.js publish --id <reportId> --report -            # stdin（管道）
    node scripts/html/report.js publish --id <reportId>                       # 不传 --report 等同 stdin
  其它:
    node scripts/html/report.js list                                          # 列出全部报告
    node scripts/html/report.js get <reportId>                                # 打印某份报告 JSON
    node scripts/html/report.js delete <reportId>                             # 删除某份报告`

// publish 专属参数：位置无关，--id / --report 各取所需。
function parsePublishArgs(args) {
  const known = new Set(['--id', '--report'])
  let id = null
  let report = null
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    if (a === '--id') {
      const v = args[++i]
      if (!v || known.has(v)) throw new Error('--id 需要指定值')
      id = v
    } else if (a === '--report') {
      const v = args[++i]
      if (v === undefined || known.has(v)) throw new Error('--report 需要指定值（inline 内容 / @文件 / -）')
      report = v
    } else {
      throw new Error(`未知参数: ${a}`)
    }
  }
  return { id, report }
}

if (isMain) {
  const [, , cmd, ...rest] = process.argv
  let exitCode = 0
  try {
    switch (cmd) {
      case 'publish': {
        const { id, report } = parsePublishArgs(rest)
        if (!id) throw new Error(USAGE)
        const options = parseInputFlag(report)
        if (options.source === 'stdin' && process.stdin.isTTY) {
          throw new Error('未提供 --report 且 stdin 是终端。请用 --report "<json>"、--report @<文件> 或管道传入')
        }
        const text = await readContentSource(options, process.stdin, { label: '报告 JSON' })
        let data
        try {
          data = JSON.parse(text)
        } catch (e) {
          throw new Error(`报告 JSON 解析失败: ${e.message}`)
        }
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
        exitCode = 1
    }
  } catch (err) {
    console.error(cmd && !['publish', 'list', 'get', 'delete'].includes(cmd) ? USAGE : (err.message || String(err)))
    exitCode = 1
  }
  process.exitCode = exitCode
}
