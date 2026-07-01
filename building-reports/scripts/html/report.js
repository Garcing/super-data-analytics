/**
 * HTML 报告客户端（report.js）
 * ============================================================================
 * 直连 Vercel Blob（@vercel/blob SDK）管理 HTML 报告：把报告 JSON 推到
 * `html-reports/<id>.json`，并维护 `html-reports-index.json` 索引（ifMatch 乐观锁）。
 * 不走 serverless 函数；线上前端直读 Blob 公开 URL。与 streamlit.js 完全对称。
 *
 * CLI（从 building-reports/ 目录运行）：
 *   node scripts/html/report.js publish --id <reportId> [--report "<json>" | --report @<file> | --report -]
 *   node scripts/html/report.js list
 *   node scripts/html/report.js get <reportId>
 *   node scripts/html/report.js delete <reportId>
 *
 * 凭证 BLOB_READ_WRITE_TOKEN 来自 ~/.super-data-analytics/config.json 的 env 块；
 * VERCEL_REPORTS_URL 仅用于拼"可分享的前端链接"。脚本不读 .env。
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  loadConfig,
  setupProxy,
  parseInputFlag,
  readContentSource,
  withOptimisticLock,
  sleep,
} from '../lib/shared.js'

const CREDENTIAL_KEYS = ['BLOB_READ_WRITE_TOKEN', 'VERCEL_REPORTS_URL']
const INDEX_PATH = 'html-reports-index.json'
const CACHE_MAX_AGE = 60 // CDN 缓存 60s，保证新报告 ~1min 内对前端可见

loadConfig(CREDENTIAL_KEYS)
const proxyState = await setupProxy()

const { put, head, del } = await import('@vercel/blob')

// ---------------------------- Blob 读写封装 ----------------------------
function getConfig() {
  if (proxyState.proxyUrl && !proxyState.proxyConfigured) {
    throw new Error(
      `检测到代理 ${proxyState.proxyUrl}，但 undici 未安装。请在 scripts 下运行: npm install undici`,
    )
  }
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    throw new Error('BLOB_READ_WRITE_TOKEN 未配置。请写入 ~/.super-data-analytics/config.json 的 env 块后重试。')
  }
  return {
    frontendUrl: (process.env.VERCEL_REPORTS_URL || '').replace(/\/+$/, ''),
  }
}

async function safeHead(pathname) {
  try {
    return await head(pathname)
  } catch (e) {
    const msg = String((e && e.message) || e)
    if (msg.includes('does not exist') || msg.includes('not found')) return null
    throw e
  }
}

async function putJson(pathname, obj, { ifMatch } = {}) {
  return put(pathname, JSON.stringify(obj, null, 2), {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    cacheControlMaxAge: CACHE_MAX_AGE,
    contentType: 'application/json',
    ...(ifMatch ? { ifMatch } : {}),
  })
}

// ---------------------------- 索引（单文件 + 乐观锁；head 强一致 + 公开读对比校验） ----------------------------
// head() — SDK 带 token，返回当前强 etag（强一致，不经 CDN）。
// fetch(public_url) — 公开读，可能走 CDN 缓存（cacheControlMaxAge=60，最多 60s 陈旧）。
// 读到内容后对比 fetch 响应的 etag 与 head 的强 etag：一致 → 内容就是当前版本，可用；
// 不一致 → CDN 陈旧，退避重读直到一致（最多 10 次，覆盖 60s 刷新窗口）。
async function readIndexWithEtag() {
  for (let i = 0; i < 12; i++) {
    const blob = await safeHead(INDEX_PATH)
    if (!blob || !blob.url) return { data: { reports: [] }, etag: undefined }
    const headEtag = (blob.etag || '').replace(/^W\//, '')
    const res = await fetch(blob.url)
    if (!res.ok) return { data: { reports: [] }, etag: undefined }
    const fetchEtag = (res.headers.get('etag') || '').replace(/^W\//, '')

    if (fetchEtag === headEtag) {
      const text = await res.text()
      let data = { reports: [] }
      if (text) {
        try { data = JSON.parse(text) } catch { /* 损坏当空 */ }
      }
      return { data, etag: headEtag }
    }
    // CDN 还没回源，退避等刷新
    if (i < 11) await sleep(1000 * (i + 1))
  }
  throw new Error('索引读取一直陈旧（CDN 缓存未刷新）。请稍后重试——新报告约 1 分钟可见。')
}

function buildIndexEntry(id, body, uploadedAt) {
  const overall = body?.summary?.overall || ''
  const summaryPreview = overall.slice(0, 100) + (overall.length > 100 ? '...' : '')
  return {
    id,
    title: body?.meta?.title || id,
    created_at: body?.meta?.generated_at || uploadedAt || null,
    summary_preview: summaryPreview,
    stats: {
      total_conclusions: body?.summary?.total_conclusions || 0,
      high_importance: body?.summary?.high_importance_count || 0,
    },
  }
}

function upsertEntry(index, entry) {
  const reports = Array.isArray(index.reports) ? [...index.reports] : []
  const i = reports.findIndex((r) => r.id === entry.id)
  if (i >= 0) reports[i] = entry
  else reports.unshift(entry)
  return { reports }
}

async function writeIndexEntry(entry) {
  return withOptimisticLock({
    read: readIndexWithEtag,
    modify: (index) => upsertEntry(index, entry),
    write: (next, etag) => putJson(INDEX_PATH, next, { ifMatch: etag }),
  })
}

async function removeIndexEntry(id) {
  return withOptimisticLock({
    read: readIndexWithEtag,
    modify: (index) => ({ reports: (index.reports || []).filter((r) => r.id !== id) }),
    write: (next, etag) => putJson(INDEX_PATH, next, { ifMatch: etag }),
  })
}

// ---------------------------- 业务操作 ----------------------------
async function publishReport(reportData, reportId) {
  if (!reportId || !reportData?.meta?.title) {
    throw new Error('缺少必要字段: reportId 与 reportData.meta.title')
  }
  const { frontendUrl } = getConfig()
  const body = { ...reportData, id: reportId }
  const blob = await putJson(`html-reports/${reportId}.json`, body)
  await writeIndexEntry(buildIndexEntry(reportId, body, blob.uploadedAt))
  return `${frontendUrl}/report/${reportId}`
}

async function listReports() {
  const { data } = await readIndexWithEtag()
  return data.reports || []
}

async function getReport(id) {
  if (!id) throw new Error('缺少 reportId')
  const blob = await safeHead(`html-reports/${id}.json`)
  if (!blob || !blob.url) throw new Error(`找不到报告: ${id}`)
  const res = await fetch(blob.url)
  return await res.json()
}

async function deleteReport(id) {
  if (!id) throw new Error('缺少 reportId')
  const blob = await safeHead(`html-reports/${id}.json`)
  if (blob && blob.url) await del(blob.url)
  await removeIndexEntry(id)
  return { success: true }
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
    node scripts/html/report.js delete <reportId>                             # 删除`

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
