import React, { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import Header from '../components/Header'
import InsightCard from '../components/InsightCard'
import KpiStrip from '../components/KpiStrip'
import ExportButton from '../components/ExportButton'
import DataSourceBadge from '../components/DataSourceBadge'
import { exportToPDF, generateFilename } from '../utils/pdfExporter'
import { reportUrl } from '../utils/blob'

export default function Report() {
  const { id } = useParams()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const reportRef = useRef(null)

  useEffect(() => {
    setLoading(true)
    setNotFound(false)

    fetch(reportUrl(id))
      .then(res => {
        if (!res.ok) throw new Error('Not found')
        return res.json()
      })
      .then(data => {
        setReport(data)
      })
      .catch(() => {
        setNotFound(true)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [id])

  const handleExport = async () => {
    if (!reportRef.current || !report) return
    const filename = generateFilename(reportTitle || 'report')
    await exportToPDF(reportRef.current, filename)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div
          style={{
            width: '36px',
            height: '36px',
            border: '3px solid var(--border-subtle)',
            borderTopColor: 'var(--accent-forest)',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite'
          }}
        />
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6">
        <h2 className="heading-2" style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
          报告不存在
        </h2>
        <p className="body-base" style={{ marginBottom: '24px', color: 'var(--text-muted)' }}>
          未找到对应的报告，请检查链接是否正确。
        </p>
        <Link to="/" className="btn-primary">
          返回首页
        </Link>
      </div>
    )
  }

  if (!report) return null

  const meta = report.meta || {}
  const summary = report.summary || {}
  const conclusions = report.conclusions || []
  const overallSummary = summary.overall || report.overall_summary || ''
  const reportTitle = report.title || meta.title || '未命名报告'
  const createdAt = report.created_at || meta.generated_at
  const modelName = report.model_name || meta.model

  return (
    <div className="min-h-screen" style={{ position: 'relative' }}>
      <Header />

      {/* Dot pattern background overlay */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: 'radial-gradient(circle, rgba(61, 54, 48, 0.06) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          pointerEvents: 'none',
          zIndex: 0
        }}
      />

      <div ref={reportRef} style={{ position: 'relative', zIndex: 1 }}>
        {/* Spacer for fixed header */}
        <div className="no-print" style={{ height: '100px' }} />

        {/* Action bar */}
        <div className="max-w-6xl mx-auto px-6 lg:px-8 no-print" style={{ marginBottom: '8px' }}>
          <div className="flex items-center justify-between">
            <Link
              to="/"
              className="btn-ghost"
              style={{ color: 'var(--accent-forest)' }}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                style={{ marginRight: '6px' }}
              >
                <path
                  d="M10 3L5 8l5 5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              返回列表
            </Link>
            <ExportButton onClick={handleExport} />
          </div>
        </div>

        {/* Report title header */}
        <header className="max-w-6xl mx-auto px-6" style={{ paddingTop: '40px', paddingBottom: '8px' }}>
          <h1 className="heading-1 animate-fade-in-up" style={{ marginBottom: '8px' }}>
            {reportTitle}
          </h1>
          {createdAt && (
            <p className="caption animate-fade-in-up" style={{ animationDelay: '0.1s', animationFillMode: 'both' }}>
              {new Date(createdAt).toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
              })}
            </p>
          )}
        </header>

        <section className="max-w-6xl mx-auto px-6" style={{ paddingTop: '32px', paddingBottom: '8px' }}>
          <KpiStrip kpis={summary.kpis || []} />
        </section>

        {/* Summary section */}
        <section className="max-w-6xl mx-auto px-6" style={{ paddingTop: '16px', paddingBottom: '16px' }}>
          <div
            className="card animate-fade-in-up"
            style={{
              padding: '28px 32px',
              borderTop: '3px solid transparent',
              borderImage: 'linear-gradient(to right, var(--accent-forest), var(--accent-gold), var(--accent-terracotta)) 1',
              animationDelay: (summary.kpis || []).length > 0 ? '0.35s' : '0.15s',
              animationFillMode: 'both'
            }}
          >
            {/* Overall summary */}
            {overallSummary && (
              <p
                className="body-large"
                style={{
                  lineHeight: '1.8',
                  color: 'var(--text-secondary)',
                  marginBottom: '16px'
                }}
              >
                {overallSummary}
              </p>
            )}

            {/* Data source badge */}
            {modelName && (
              <div>
                <DataSourceBadge model={modelName} />
              </div>
            )}
          </div>
        </section>

        {/* Insights section */}
        <section className="max-w-6xl mx-auto px-6" style={{ paddingTop: '16px', paddingBottom: '48px' }}>
          <h2
            className="heading-2 animate-fade-in-up"
            style={{ marginBottom: '24px', animationDelay: '0.2s', animationFillMode: 'both' }}
          >
            详细发现
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {conclusions.map((conclusion, index) => (
              <InsightCard
                key={conclusion.id || index}
                conclusion={conclusion}
                index={index}
              />
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer
          className="print-footer"
          style={{
            borderTop: '1px solid var(--border-subtle)',
            padding: '24px',
            textAlign: 'center'
          }}
        >
          <Link
            to="/"
            className="text-sm font-display"
            style={{ color: 'var(--text-muted)', textDecoration: 'none' }}
          >
            Power BI Reports
          </Link>
          {createdAt && (
            <p
              className="caption"
              style={{ marginTop: '6px', fontSize: '12px' }}
            >
              报告生成于 {new Date(createdAt).toLocaleString('zh-CN')}
            </p>
          )}
        </footer>
      </div>

      {/* Spinner keyframe */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
