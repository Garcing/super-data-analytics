#!/usr/bin/env node
/**
 * building-reports 统一薄入口。
 *
 * 只负责按报告格式动态加载对应模块；具体命令、参数、配置和清理逻辑
 * 仍由各格式模块自己维护，避免跨格式依赖被无谓加载。
 */

import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const FORMATS = {
  html: './html/html.js',
  streamlit: './streamlit/streamlit.js',
  image: './image/image.js',
}

const USAGE = `用法（从 building-reports/ 目录运行）:
  node scripts/report.js html <publish|list|get|delete> [参数]
  node scripts/report.js streamlit <publish|list|get|delete> [参数]
  node scripts/report.js image <generate|submit|status|download> [参数]`

export async function runCli(argv = process.argv.slice(2)) {
  const [format, ...rest] = argv
  if (!format || !FORMATS[format]) {
    throw new Error(USAGE)
  }
  const mod = await import(FORMATS[format])
  if (typeof mod.runCli !== 'function') {
    throw new Error(`报告格式 ${format} 未导出 runCli(argv)`)
  }
  await mod.runCli(rest)
}

const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase()
  } catch {
    return false
  }
})()

if (isMain) {
  runCli().catch((err) => {
    console.error(err.message || String(err))
    process.exitCode = 1
  })
}
