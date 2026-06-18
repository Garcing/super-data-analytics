import { useState, useEffect } from 'react'

function AnimatedNumber({ value, duration = 800 }) {
  const [displayValue, setDisplayValue] = useState(0)
  useEffect(() => {
    let startTime, animationFrame
    const animate = (timestamp) => {
      if (!startTime) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / duration, 1)
      setDisplayValue(Math.floor((1 - Math.pow(1 - progress, 3)) * value))
      if (progress < 1) animationFrame = requestAnimationFrame(animate)
    }
    animationFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animationFrame)
  }, [value, duration])
  return <span>{displayValue}</span>
}

export default function StatsOverview({ reports = [] }) {
  const totalReports = reports.length
  const now = new Date()
  const thisMonthReports = reports.filter(r => {
    const d = new Date(r.created_at || r.date)
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  }).length
  const totalHighImportance = reports.reduce((sum, r) => {
    if (r.conclusions) {
      return sum + r.conclusions.filter(c => c.importance === 'high').length
    }
    return sum + (r.stats?.high_importance || 0)
  }, 0)

  return (
    <div className="mb-16 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <div
        className="flex flex-wrap items-baseline gap-x-12 gap-y-4"
        style={{ padding: '24px 0', borderTop: '1px solid var(--border-subtle)', borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="flex items-baseline gap-3">
          <span className="font-display font-light text-text-primary" style={{ fontSize: 'clamp(3rem, 5vw, 3.75rem)' }}>
            <AnimatedNumber value={totalReports} />
          </span>
          <span className="text-sm text-text-muted font-medium">份报告</span>
        </div>
        <div className="hidden sm:block" style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-subtle)' }} />
        <div className="flex items-baseline gap-3">
          <span className="font-display font-light text-text-primary" style={{ fontSize: 'clamp(3rem, 5vw, 3.75rem)' }}>
            <AnimatedNumber value={thisMonthReports} />
          </span>
          <span className="text-sm text-text-muted font-medium">本月新增</span>
        </div>
        <div className="hidden sm:block" style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-subtle)' }} />
        <div className="flex items-baseline gap-3">
          <span className="font-display font-light text-text-primary" style={{ fontSize: 'clamp(3rem, 5vw, 3.75rem)' }}>
            <AnimatedNumber value={totalHighImportance} />
          </span>
          <span className="text-sm text-text-muted font-medium">关键发现</span>
        </div>
      </div>
    </div>
  )
}
