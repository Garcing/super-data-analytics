import React from 'react'
import { Link } from 'react-router-dom'

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const year = d.getFullYear()
  return `${month}月${day}日 ${year}`
}

export default function ReportCard({ report, index }) {
  if (!report) return null

  const stats = report.stats || report.conclusions || []
  const conclusionCount = Array.isArray(stats)
    ? stats.length
    : (stats.total_conclusions || stats.count || 0)
  const highCount = Array.isArray(report.conclusions)
    ? report.conclusions.filter(c => c.importance === 'high').length
    : (report.high_importance_count || 0)

  return (
    <Link
      to={`/report/${encodeURIComponent(report.id)}`}
      className="card animate-fade-in-up block no-underline"
      style={{
        padding: '24px',
        animationDelay: `${index * 0.08}s`,
        animationFillMode: 'both'
      }}
    >
      {/* Date + stats badge */}
      <div className="flex items-center justify-between" style={{ marginBottom: '12px' }}>
        <span className="caption">{formatDate(report.created_at)}</span>
        <span className="badge-muted">
          {conclusionCount} 项发现
        </span>
      </div>

      {/* Title */}
      <h3
        className="heading-3 transition-colors duration-200"
        style={{ marginBottom: '8px' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent-forest)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = '')}
      >
        {report.title || '未命名报告'}
      </h3>

      {/* Summary preview */}
      {report.summary_preview && (
        <p
          className="body-base line-clamp-2"
          style={{ marginBottom: '16px', color: 'var(--text-tertiary)' }}
        >
          {report.summary_preview}
        </p>
      )}

      {/* Footer */}
      <div
        className="flex items-center justify-between"
        style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}
      >
        {highCount > 0 && (
          <span className="badge-importance-high">
            {highCount} 项高重要度
          </span>
        )}
        <span className="text-sm font-medium ml-auto group-hover:text-accent-forest" style={{ color: 'var(--accent-forest)' }}>
          查看
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ marginLeft: '4px', verticalAlign: 'middle' }}
          >
            <path
              d="M5 3l4 4-4 4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </div>
    </Link>
  )
}
