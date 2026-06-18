import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

export default function Header() {
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()
  const isReportPage = location.pathname.startsWith('/report/')

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handleScroll, { passive: true })
    setScrolled(false)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [location.pathname])

  if (!isReportPage) {
    return (
      <header
        className="sticky top-0 z-50 no-print"
        style={{
          backgroundColor: '#faf7f2',
          borderBottom: '1px solid var(--border-subtle)',
          height: '64px'
        }}
      >
        <div className="max-w-6xl mx-auto px-6 lg:px-8 h-full flex items-center justify-between">
          <h1 className="font-display text-xl text-text-primary">PowerBI Report</h1>
          <span className="font-mono text-xs text-text-muted">PowerBI Report</span>
        </div>
      </header>
    )
  }

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 no-print"
      style={{
        backgroundColor: scrolled ? 'rgba(250, 247, 242, 0.95)' : 'transparent',
        backdropFilter: scrolled ? 'blur(16px)' : 'none',
        WebkitBackdropFilter: scrolled ? 'blur(16px)' : 'none',
        boxShadow: scrolled
          ? '0 1px 2px rgba(61, 54, 48, 0.04), 0 4px 8px rgba(61, 54, 48, 0.04), 0 12px 24px rgba(61, 54, 48, 0.06)'
          : 'none',
        borderBottom: scrolled ? '1px solid var(--border-subtle)' : '1px solid transparent',
        padding: scrolled ? '12px 0' : '20px 0',
        transition: 'all 500ms'
      }}
    >
      <div className="max-w-6xl mx-auto px-6 lg:px-8 flex items-center gap-4">
        <Link
          to="/"
          className="flex items-center gap-4 no-underline"
          style={{ opacity: scrolled ? 1 : 0.9, transition: 'opacity 500ms' }}
        >
          <div
            className="flex items-center justify-center"
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '50%',
              border: '2px solid rgba(45, 90, 74, 0.2)',
              padding: '6px'
            }}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="10" width="3" height="8" rx="0.5" fill="var(--accent-forest)" />
              <rect x="8.5" y="6" width="3" height="12" rx="0.5" fill="var(--accent-forest)" />
              <rect x="15" y="2" width="3" height="16" rx="0.5" fill="var(--accent-forest)" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold text-text-primary" style={{ lineHeight: '1.2' }}>
              PowerBI Report
            </h1>
            <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, letterSpacing: '0.15em', textTransform: 'uppercase', marginTop: '2px' }}>
              分析报告
            </p>
          </div>
        </Link>
      </div>
    </header>
  )
}
