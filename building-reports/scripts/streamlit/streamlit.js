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
import { loadConfig, setupProxy, closeProxy, parseInputFlag, readContentSource } from '../lib/shared.js'

const CREDENTIAL_KEYS = ['BLOB_READ_WRITE_TOKEN']

loadConfig(CREDENTIAL_KEYS)
const proxyState = await setupProxy()

const { put, head, del, list } = await import('@vercel/blob')

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

/** put 公开、确定性 URL；同 id 重发即覆盖（allowOverwrite）。 */
async function putText(pathname, text) {
  return put(pathname, text, { access: 'public', addRandomSuffix: false, allowOverwrite: true })
}

/** 取某份报告源码的公开 URL；不存在返回 null。 */
async function getSourceUrl(id) {
  const blob = await safeHead(`streamlit-reports/${id}.py`)
  return blob && blob.url ? blob.url : null
}

// ---------------------------- 索引（每报告 meta 为唯一真相，避免共享文件读写竞争） ----------------------------
// 不再对单一 index 文件做 read-modify-write（CDN/最终一致性下并发发布会互相覆盖）。
// 每份报告的 meta 存到 streamlit-reports/<id>.meta.json；list() 枚举它们重建索引，
// 再写一份合并的 streamlit-reports-index.json 供线上 app 公开读（app 无 token，不能 list）。
async function rebuildIndex() {
  const metas = []
  let cursor
  do {
    const res = await list({ prefix: 'streamlit-reports/', cursor, limit: 1000 })
    const metaBlobs = (res.blobs || []).filter((b) => b.pathname.endsWith('.meta.json'))
    const fetched = await Promise.all(
      metaBlobs.map(async (b) => {
        try {
          const r = await fetch(b.url)
          return await r.json()
        } catch {
          return null
        }
      }),
    )
    metas.push(...fetched.filter(Boolean))
    cursor = res.hasMore ? res.cursor : undefined
  } while (cursor)

  metas.sort(
    (a, b) =>
      (a.group || '').localeCompare(b.group || '') || (a.title || '').localeCompare(b.title || ''),
  )
  await putText('streamlit-reports-index.json', JSON.stringify({ reports: metas }, null, 2))
  return metas
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
  await putText(`streamlit-reports/${id}.meta.json`, JSON.stringify(meta, null, 2))

  await rebuildIndex() // 从权威 meta 重建合并索引（供线上 app 读）
  return { ...meta, url: blob.url }
}

async function listReports() {
  // CLI 侧每次 list 都重建，保证最新
  return await rebuildIndex()
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
  const metaBlob = await safeHead(`streamlit-reports/${id}.meta.json`)
  if (metaBlob && metaBlob.url) await del(metaBlob.url)
  const before = (await rebuildIndex()).length
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
