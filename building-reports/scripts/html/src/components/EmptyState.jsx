import React from 'react'

export default function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6">
      <svg
        width="64"
        height="64"
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ opacity: 0.3, marginBottom: '20px' }}
      >
        <rect x="8" y="16" width="48" height="36" rx="4" stroke="#9e9589" strokeWidth="2" fill="none" />
        <path d="M8 24h48" stroke="#9e9589" strokeWidth="2" />
        <circle cx="14" cy="20" r="2" fill="#9e9589" />
        <circle cx="20" cy="20" r="2" fill="#9e9589" />
        <circle cx="26" cy="20" r="2" fill="#9e9589" />
        <rect x="16" y="32" width="12" height="12" rx="2" stroke="#9e9589" strokeWidth="1.5" fill="none" />
        <path d="M34 34h14M34 40h10M34 46h6" stroke="#9e9589" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <h2 className="heading-3 text-text-muted" style={{ marginBottom: '8px' }}>
        暂无报告
      </h2>
      <p className="body-base text-text-muted text-center" style={{ maxWidth: '320px' }}>
        还没有生成分析报告。完成 Power BI 数据分析后，报告将自动出现在这里。
      </p>
    </div>
  )
}
