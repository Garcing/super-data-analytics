/**
 * Streamlit 报告发布客户端（streamlit.js）
 * ============================================================================
 * 直连 Vercel Blob（@vercel/blob SDK）管理 streamlit 报告：把报告 .py 源码推到
 * `streamlit-reports/<id>.py`，并维护 `streamlit-reports-index.json` 索引。
 * 线上 app.py 直读 Blob 公开 URL 渲染——不走 serverless 函数，不碰 html 的 api。
 *
 * CLI（从 building-reports/ 目录运行）：
 *   node scripts/report.js streamlit publish --id <id> [--title --summary --tags] [--report "<py>"|@file|-]
 *   node scripts/report.js streamlit list
 *   node scripts/report.js streamlit get <id>
 *   node scripts/report.js streamlit delete <id>
 *
 * 凭证 BLOB_READ_WRITE_TOKEN 来自 ~/.super-data-analytics/config.json 的 env 块；脚本不读 .env。
 *
 * 索引条目（与 html 共用 schema）：
 *   { id, title, created_at, updated_at, summary, tags }
 *   - meta（除时间外）由 flag 提供：--title / --summary / --tags（逗号分隔 → 数组）
 *   - created_at 首次发布取 uploadedAt，重发保留原值；updated_at 每次刷新
 *   - tags 替代旧 group，作为可变长标签列表
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadConfig, ensureProxyEnv, parseInputFlag, readContentSource, withOptimisticLock, sleep } from '../lib/shared.js'

const CREDENTIAL_KEYS = ['BLOB_READ_WRITE_TOKEN']

loadConfig(CREDENTIAL_KEYS)
const proxyOk = ensureProxyEnv()

const { put, head, del } = await import('@vercel/blob')

const INDEX_PATH = 'streamlit-reports-index.json'
const CACHE_MAX_AGE = 60 // 索引/源码 CDN 缓存 60s，保证线上 app 新报告 ~1min 内可见

// ---------------------------- Blob 读写封装 ----------------------------
/** head 在 blob 不存在时抛 BlobNotFoundError；这里吞掉"不存在"返回 null。 */
async function safeHead(pathname) {
  try {
    return await head(pathname)
  } catch (e) {
    const msg = String((e && e.message) || e)
    if (msg.includes('does not exist') || msg.includes('not found')) return null
    throw e
  }
}

/** put 公开、确定性 URL；同 id 重发即覆盖；cacheControlMaxAge 让 CDN 不长期缓存。 */
async function putText(pathname, text, { ifMatch } = {}) {
  return put(pathname, text, {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    cacheControlMaxAge: CACHE_MAX_AGE,
    ...(ifMatch ? { ifMatch } : {}),
  })
}

/** 取某份报告源码的公开 URL；不存在返回 null。 */
async function getSourceUrl(id) {
  const blob = await safeHead(`streamlit-reports/${id}.py`)
  return blob && blob.url ? blob.url : null
}

// 把 "--tags 销售,区域" 解析成 ["销售","区域"]。
function parseTags(raw) {
  if (!raw) return []
  return raw.split(',').map((t) => t.trim()).filter(Boolean)
}

// ---------------------------- 索引（单文件 + 乐观锁；head 强一致 + 公开读对比校验） ----------------------------
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
        try { data = JSON.parse(text) } catch { /* 索引损坏，当空 */ }
      }
      return { data, etag: headEtag }
    }
    if (i < 11) await sleep(1000 * (i + 1))
  }
  throw new Error('索引读取一直陈旧（CDN 缓存未刷新）。请稍后重试——新报告约 1 分钟可见。')
}

function upsertEntry(index, entry) {
  const reports = Array.isArray(index.reports) ? [...index.reports] : []
  const i = reports.findIndex((r) => r.id === entry.id)
  if (i >= 0) {
    // 重发保留 created_at（创建时间稳定），其余字段以本次为准
    reports[i] = { ...entry, created_at: reports[i].created_at || entry.created_at }
  } else {
    reports.unshift(entry)
  }
  return { reports }
}

async function writeIndexEntry(entry) {
  return withOptimisticLock({
    read: readIndexWithEtag,
    modify: (index) => upsertEntry(index, entry),
    write: (next, etag) => putText(INDEX_PATH, JSON.stringify(next, null, 2), { ifMatch: etag }),
  })
}

async function removeIndexEntry(id) {
  return withOptimisticLock({
    read: readIndexWithEtag,
    modify: (index) => ({ reports: (index.reports || []).filter((r) => r.id !== id) }),
    write: (next, etag) => putText(INDEX_PATH, JSON.stringify(next, null, 2), { ifMatch: etag }),
  })
}

// ---------------------------- 业务操作 ----------------------------
async function publish({ id, title, summary, tags, options }) {
  if (!id) throw new Error('publish 需要 --id <reportId>')
  if (options.source === 'stdin' && process.stdin.isTTY) {
    throw new Error('未提供 --report 且 stdin 是终端。请用 --report "<py>"、--report @<文件> 或管道传入')
  }
  const source = await readContentSource(options, process.stdin, { label: '报告 .py 源码' })

  const blob = await putText(`streamlit-reports/${id}.py`, source)
  // put() 不返回 uploadedAt，补一次 head() 拿时间戳
  const info = await safeHead(`streamlit-reports/${id}.py`)
  const uploadedAt = info?.uploadedAt || null
  const entry = {
    id,
    title: title || id,
    created_at: uploadedAt,
    updated_at: uploadedAt,
    summary: summary || '',
    tags,
  }
  await writeIndexEntry(entry)
  return { ...entry, url: blob.url }
}

async function listReports() {
  const { data } = await readIndexWithEtag()
  return data.reports || []
}

async function getReport(id) {
  const url = await getSourceUrl(id)
  if (!url) throw new Error(`找不到报告: ${id}`)
  const res = await fetch(url)
  return await res.text()
}

async function deleteReport(id) {
  const srcUrl = await getSourceUrl(id)
  if (srcUrl) await del(srcUrl)
  await removeIndexEntry(id)
  return { id, removed: true }
}

// ---------------------------- CLI ----------------------------
const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase()
  } catch {
    return false
  }
})()

const USAGE = `用法（从 building-reports/ 目录运行）:
  发布（--report 三种来源，同 querying-data 的 --sql / --payload）:
    node scripts/report.js streamlit publish --id <id> [--title --summary --tags] [--report "<py>"|@file|-]
    node scripts/report.js streamlit publish --id <id> --report @<file>     # 文件（建议 <工作区>/.super-data-analytics/scratch/）
    node scripts/report.js streamlit publish --id <id> --report -           # stdin（管道）
  其它:
    node scripts/report.js streamlit list                                   # 列出全部报告
    node scripts/report.js streamlit get <id>                               # 打印某份报告源码
    node scripts/report.js streamlit delete <id>                            # 删除

meta flag（除时间外由 agent 填）:
  --title   报告标题（默认 = id；同时是 URL 路径，直达链接 = 线上/<title>，避免空格/斜杠，全库唯一）
  --summary 一句话摘要
  --tags    逗号分隔标签，如 --tags "销售,区域,GMV"
时间（created_at/updated_at）由 CLI 自动写，不让 agent 填。
报告 .py 顶层 st.* 调用 + from lib import ...，不需要 META dict。`

function parsePublishArgs(args) {
  const known = new Set(['--id', '--title', '--summary', '--tags', '--report'])
  const out = { id: null, title: null, summary: null, tagsRaw: null, reportRaw: null }
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    switch (a) {
      case '--id': out.id = readVal(args, ++i, '--id', known); break
      case '--title': out.title = readVal(args, ++i, '--title', known); break
      case '--summary': out.summary = readVal(args, ++i, '--summary', known); break
      case '--tags': out.tagsRaw = readVal(args, ++i, '--tags', known); break
      case '--report': out.reportRaw = readVal(args, ++i, '--report', known); break
      default: throw new Error(`未知参数: ${a}`)
    }
  }
  return out
}

function readVal(args, i, name, known) {
  const v = args[i]
  if (v === undefined || known.has(v)) throw new Error(`${name} 需要指定值`)
  return v
}

export async function runCli(argv = process.argv.slice(2)) {
  const [cmd, ...rest] = argv
  let exitCode = 0
  try {
    switch (cmd) {
      case 'publish': {
        const a = parsePublishArgs(rest)
        if (!a.id) throw new Error(USAGE)
        const options = parseInputFlag(a.reportRaw)
        const entry = await publish({
          id: a.id,
          title: a.title,
          summary: a.summary,
          tags: parseTags(a.tagsRaw),
          options,
        })
        console.log(entry.url)
        console.error(`已发布: id=${entry.id} title=${entry.title} tags=[${entry.tags.join(',')}]`)
        break
      }
      case 'list': {
        const reports = await listReports()
        if (!reports.length) { console.log('(暂无报告)'); break }
        console.log(['id', 'updated_at', 'title'].join('\t'))
        for (const r of reports) console.log([r.id, r.updated_at || r.created_at || '', r.title || ''].join('\t'))
        break
      }
      case 'get': {
        const [id] = rest
        if (!id) throw new Error('用法: streamlit.js get <id>')
        console.log(await getReport(id))
        break
      }
      case 'delete': {
        const [id] = rest
        if (!id) throw new Error('用法: streamlit.js delete <id>')
        const r = await deleteReport(id)
        console.log(r.removed ? `已删除: ${r.id}` : `索引中无此报告: ${r.id}（已尝试删 Blob）`)
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
  if (exitCode !== 0) process.exitCode = exitCode
}

if (isMain && proxyOk) {
  await runCli()
}
