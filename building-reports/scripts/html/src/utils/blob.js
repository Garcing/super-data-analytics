// HTML 报告数据直连 Vercel Blob 公开 URL（不再经 serverless 函数）。
// 报告 JSON 由 skill 侧 scripts/report.js html 写入；前端只读公开 URL。
const BLOB_BASE = 'https://o2v8qrfoxqnbqwk4.public.blob.vercel-storage.com'

export const indexUrl = () => `${BLOB_BASE}/html-reports-index.json`
export const reportUrl = (id) => `${BLOB_BASE}/html-reports/${encodeURIComponent(id)}.json`
