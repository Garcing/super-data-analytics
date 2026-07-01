/**
 * Streamlit 报告发布客户端（streamlit.js）
 * ============================================================================
 * 直连 Vercel Blob（@vercel/blob SDK）管理 streamlit 报告：把报告 .py 源码推到
 * `streamlit-reports/<id>.py`，并维护 `streamlit-reports-index.json` 索引。
 * 线上 app.py 直读 Blob 公开 URL 渲染——不走 serverless 函数，不碰 html 的 api。
 *
 * CLI（从 building-reports/ 目录运行）：
 *   node scripts/streamlit/streamlit.js publish --id <id> [--title --icon --group --summary] [--source "<py>"|@file|-]
 *   node scripts/streamlit/streamlit.js list
 *   node scripts/streamlit/streamlit.js get <id>
 *   node scripts/streamlit/streamlit.js delete <id>
 *
 * 凭证 BLOB_READ_WRITE_TOKEN 来自 ~/.super-data-analytics/config.json 的 env 块；
 * 脚本不读 .env。token = 整个 Blob store 的写权限，注意保管。
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadConfig, setupProxy, closeProxy, parseInputFlag, readContentSource, withOptimisticLock, sleep } from '../lib/shared.js'

const CREDENTIAL_KEYS = ['BLOB_READ_WRITE_TOKEN']

loadConfig(CREDENTIAL_KEYS)
const proxyState = await setupProxy()

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

// ---------------------------- 索引（单文件 + 乐观锁；head 强一致 + 公开读对比校验） ----------------------------
// head() — SDK 带 token，返回当前强 etag（强一致，不经 CDN）。
// fetch(public_url) — 公开读，可能走 CDN 缓存（cacheControlMaxAge=60，最多 60s 陈旧）。
// 读到内容后对比 fetch 响应的 etag 与 head 的强 etag：一致 → 内容就是当前版本，可用；
// 不一致 → CDN 陈旧，退避重读直到一致（最多 12 次，覆盖 60s 刷新窗口）。
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
    // CDN 还没回源，退避等刷新
    if (i < 11) await sleep(1000 * (i + 1))
  }
  throw new Error('索引读取一直陈旧（CDN 缓存未刷新）。请稍后重试——新报告约 1 分钟可见。')
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
async function publish({ id, title, icon, group, summary, options }) {
  if (!id) throw new Error('publish 需要 --id <reportId>')
  if (options.source === 'stdin' && process.stdin.isTTY) {
    throw new Error('未提供 --source 且 stdin 是终端。请用 --source "<py>"、--source @<文件> 或管道传入')
  }
  const source = await readContentSource(options, process.stdin, { label: '报告 .py 源码' })

  const blob = await putText(`streamlit-reports/${id}.py`, source)
  const meta = {
    id,
    title: title || id,
    icon: icon || '📄',
    group: group || '其他',
    summary: summary || '',
    // 不用 Date.now()（某些运行环境受限）；用 Blob 返回的 uploadedAt
    updated_at: blob.uploadedAt || null,
  }
  await writeIndexEntry(meta)
  return { ...meta, url: blob.url }
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
  const next = await removeIndexEntry(id)
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
  发布（--source 三种来源，同 querying-data 的 --query）:
    node scripts/streamlit/streamlit.js publish --id <id> [--title --icon --group --summary] [--source "<py>"|@file|-]
    node scripts/streamlit/streamlit.js publish --id <id> --source @<file>     # 文件（建议 <工作区>/.super-data-analytics/scratch/）
    node scripts/streamlit/streamlit.js publish --id <id> --source -           # stdin（管道）
  其它:
    node scripts/streamlit/streamlit.js list                                   # 列出全部报告
    node scripts/streamlit/streamlit.js get <id>                               # 打印某份报告源码
    node scripts/streamlit/streamlit.js delete <id>                            # 删除

meta 全部由 flag 提供（默认 title=id、icon=📄、group=其他、summary=""）；
报告 .py 源码顶层 st.* 调用 + from lib import ...，不需要 META dict。`

function parsePublishArgs(args) {
  const known = new Set(['--id', '--title', '--icon', '--group', '--summary', '--source'])
  const out = { id: null, title: null, icon: null, group: null, summary: null, sourceRaw: null }
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    switch (a) {
      case '--id': out.id = readVal(args, ++i, '--id', known); break
      case '--title': out.title = readVal(args, ++i, '--title', known); break
      case '--icon': out.icon = readVal(args, ++i, '--icon', known); break
      case '--group': out.group = readVal(args, ++i, '--group', known); break
      case '--summary': out.summary = readVal(args, ++i, '--summary', known); break
      case '--source': out.sourceRaw = readVal(args, ++i, '--source', known); break
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

if (isMain) {
  const [, , cmd, ...rest] = process.argv
  let exitCode = 0
  try {
    switch (cmd) {
      case 'publish': {
        const a = parsePublishArgs(rest)
        if (!a.id) throw new Error(USAGE)
        const options = parseInputFlag(a.sourceRaw)
        const entry = await publish({ ...a, options })
        console.log(entry.url)
        console.error(`已发布: id=${entry.id} title=${entry.title} group=${entry.group}`)
        break
      }
      case 'list': {
        const reports = await listReports()
        if (!reports.length) { console.log('(暂无报告)'); break }
        console.log(['id', 'group', 'title'].join('\t'))
        for (const r of reports) console.log([r.id, r.group || '', r.title || ''].join('\t'))
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
  if (proxyState.proxyConfigured) await closeProxy()
  process.exitCode = exitCode
}
