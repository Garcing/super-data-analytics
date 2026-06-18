import React from 'react'

const trendConfig = {
  up:      { arrow: '↗', color: 'var(--accent-forest)' },
  down:    { arrow: '↘', color: 'var(--accent-terracotta)' },
  neutral: { arrow: '→', color: 'var(--text-muted)' },
}

export default function KpiStrip({ kpis }) {
  if (!kpis || kpis.length === 0) return null

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {kpis.map((kpi, i) => {
        const trend = trendConfig[kpi.trend] || trendConfig.neutral
        return (
          <div
            key={i}
            className="kpi-metric-card animate-fade-in-up"
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <div className="kpi-metric-label">{kpi.label}</div>
            <div className="kpi-metric-value">{kpi.value}</div>
            {kpi.trend_value && (
              <div className="kpi-metric-trend" style={{ color: trend.color }}>
                {trend.arrow} {kpi.trend_value}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
