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

  const tags = Array.isArray(report.tags) ? report.tags : []

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
      {/* Date */}
      <div style={{ marginBottom: '12px' }}>
        <span className="caption">{formatDate(report.created_at)}</span>
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

      {/* Summary */}
      {report.summary && (
        <p
          className="body-base line-clamp-2"
          style={{ marginBottom: '16px', color: 'var(--text-tertiary)' }}
        >
          {report.summary}
        </p>
      )}

      {/* Footer: tags + 查看 */}
      <div
        className="flex items-center justify-between gap-2"
        style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}
      >
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="font-mono"
              style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-muted)',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
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
