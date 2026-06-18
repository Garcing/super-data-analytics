import React from 'react'
import ChartContainer from './ChartContainer'

const importanceMap = {
  high: { label: '关键', badgeClass: 'badge-importance-high' },
  medium: { label: '重要', badgeClass: 'badge-importance-medium' },
  low: { label: '一般', badgeClass: 'badge-importance-low' }
}

export default function InsightCard({ conclusion, index }) {
  if (!conclusion) return null

  const importance = conclusion.importance || 'low'
  const { label: importanceLabel, badgeClass } = importanceMap[importance] || importanceMap.low

  return (
    <div
      className="card animate-fade-in-up"
      style={{
        padding: '24px',
        animationDelay: `${index * 0.05}s`,
        animationFillMode: 'both'
      }}
    >
      {/* Header row: number + importance badge */}
      <div className="flex items-center gap-3" style={{ marginBottom: '12px' }}>
        <span
          className="font-display font-bold text-lg"
          style={{ color: '#9e9589', minWidth: '28px' }}
        >
          {String(index + 1).padStart(2, '0')}
        </span>
        <span className={badgeClass}>
          {importanceLabel}
        </span>
      </div>

      {/* Title */}
      <h3 className="heading-3" style={{ marginBottom: '8px' }}>
        {conclusion.title}
      </h3>

      {/* Description */}
      {conclusion.description && (
        <p className="body-base" style={{ marginBottom: '16px' }}>
          {conclusion.description}
        </p>
      )}

      {/* Data support section */}
      {conclusion.data_support && (
        <div
          style={{
            padding: '14px 16px',
            backgroundColor: 'rgba(45, 90, 74, 0.04)',
            borderRadius: '8px',
            borderLeft: '3px solid var(--accent-forest)',
            marginBottom: '16px'
          }}
        >
          <div
            className="text-xs font-medium tracking-wide uppercase"
            style={{ color: 'var(--accent-forest)', marginBottom: '6px' }}
          >
            数据支撑
          </div>
          <p className="body-base" style={{ fontSize: '14px', lineHeight: '1.7' }}>
            {conclusion.data_support}
          </p>
        </div>
      )}

      {/* Chart */}
      {conclusion.chart_data && conclusion.chart_type && (
        <div style={{ marginTop: '8px' }}>
          <ChartContainer type={conclusion.chart_type} data={conclusion.chart_data} />
        </div>
      )}
    </div>
  )
}
