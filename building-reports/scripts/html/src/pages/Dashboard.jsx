import React, { useState, useEffect } from 'react'
import Header from '../components/Header'
import ReportCard from '../components/ReportCard'
import StatsOverview from '../components/StatsOverview'
import EmptyState from '../components/EmptyState'

export default function Dashboard() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/reports')
      .then(res => res.json())
      .then(data => {
        const sorted = (Array.isArray(data) ? data : data.reports || []).sort(
          (a, b) => new Date(b.created_at || b.date) - new Date(a.created_at || a.date)
        )
        setReports(sorted)
      })
      .catch(() => {
        setReports([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return (
    <div className="min-h-screen">
      <Header />

      <main className="max-w-6xl mx-auto px-6 lg:px-8 py-12 lg:py-16">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div
              style={{
                width: '24px',
                height: '24px',
                border: '2px solid var(--text-muted)',
                borderTopColor: 'transparent',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }}
            />
          </div>
        ) : reports.length > 0 ? (
          <>
            <div className="mb-12 opacity-0 animate-fade-in-up">
              <h2
                className="font-display font-light text-text-primary"
                style={{ fontSize: 'clamp(2.25rem, 5vw, 3rem)', marginBottom: '16px' }}
              >
                分析存档
              </h2>
              <p className="text-text-secondary" style={{ maxWidth: '36rem' }}>
                所有数据分析报告与洞察结论的归档。
              </p>
            </div>

            <StatsOverview reports={reports} />

            <section>
              <div className="mb-8 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                <h3 className="font-mono text-xs text-text-muted uppercase" style={{ letterSpacing: '0.05em' }}>
                  全部报告
                </h3>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 lg:pl-6">
                {reports.map((report, index) => (
                  <ReportCard key={report.id || index} report={report} index={index} />
                ))}
              </div>
            </section>
          </>
        ) : (
          <EmptyState />
        )}
      </main>

      <footer style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-8">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <p className="font-mono text-xs text-text-muted">PowerBI Report</p>
            <p className="text-xs text-text-muted">
              运行 <code className="font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-secondary)' }}>powerbi-analysis</code> 创建新分析
            </p>
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
