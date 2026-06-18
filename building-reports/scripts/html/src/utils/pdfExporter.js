export async function exportToPDF(element, filename = 'report.pdf') {
  if (!element) throw new Error('导出元素不存在')
  document.body.classList.add('pdf-exporting')
  const originalTitle = document.title
  document.title = filename.replace('.pdf', '')
  await new Promise(resolve => setTimeout(resolve, 100))
  window.print()
  setTimeout(() => {
    document.title = originalTitle
    document.body.classList.remove('pdf-exporting')
  }, 1000)
  return true
}

export function generateFilename(prefix = 'report') {
  const now = new Date()
  const timestamp = now.toISOString().slice(0, 10).replace(/-/g, '')
  const cleanPrefix = prefix.replace(/[^\w\u4e00-\u9fa5-]/g, '_').slice(0, 30)
  return `${cleanPrefix}_${timestamp}.pdf`
}
