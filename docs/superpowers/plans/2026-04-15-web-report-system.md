# Web Report System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Vercel-hosted React web report system to the powerbi-analysis skill, enabling publicly accessible analysis reports with interactive charts and a report dashboard.

**Architecture:** React + Vite + Tailwind + Recharts frontend deployed to Vercel with Serverless API Routes backed by Vercel Blob storage. Python script uploads report JSON via API, returns a public URL. Supports upsert semantics for iterative report updates.

**Tech Stack:** React 18, Vite 6, Tailwind CSS 3, Recharts 2, React Router 7, Vercel Blob (@vercel/blob), Python requests, TypeScript (API routes only)

---

## File Structure

### New files (web-report/ Vercel project)
| File | Responsibility |
|------|---------------|
| `web-report/package.json` | NPM dependencies and scripts |
| `web-report/vite.config.js` | Vite build config with React plugin |
| `web-report/tailwind.config.js` | Tailwind theme with Data Dive CSS variables |
| `web-report/postcss.config.js` | PostCSS for Tailwind |
| `web-report/vercel.json` | Vercel deployment config |
| `web-report/index.html` | HTML entry point |
| `web-report/.env.example` | Environment variable template |
| `web-report/tsconfig.json` | TypeScript config for API routes |
| `web-report/src/main.jsx` | React entry point |
| `web-report/src/App.jsx` | Router: `/` → Dashboard, `/report/:id` → Report |
| `web-report/src/index.css` | Tailwind directives + CSS variables + animations |
| `web-report/src/pages/Dashboard.jsx` | Report list page, fetches GET /api/reports |
| `web-report/src/pages/Report.jsx` | Report detail page, fetches GET /api/reports/:id |
| `web-report/src/components/Header.jsx` | Top nav bar with scroll effects |
| `web-report/src/components/InsightCard.jsx` | Conclusion card with importance badge + chart |
| `web-report/src/components/ChartContainer.jsx` | Recharts wrapper (bar/line/pie/scatter) |
| `web-report/src/components/ReportCard.jsx` | Report list card for Dashboard |
| `web-report/src/components/StatsOverview.jsx` | Animated statistics summary |
| `web-report/src/components/ExportButton.jsx` | PDF export button |
| `web-report/src/components/EmptyState.jsx` | Empty dashboard placeholder |
| `web-report/src/utils/pdfExporter.js` | Print-based PDF export |
| `web-report/src/utils/chartConfig.js` | Chart color palette and formatting |
| `web-report/lib/blob.ts` | Vercel Blob read/write/delete wrapper |
| `web-report/api/reports/index.ts` | GET (list) + POST (upsert) |
| `web-report/api/reports/[id].ts` | GET (single) + DELETE |

### New files (skill integration)
| File | Responsibility |
|------|---------------|
| `scripts/web_report_builder.py` | Python client: upload report JSON → get URL |
| `.gitignore` | Ignore .env, node_modules, build artifacts |

### Modified files
| File | Change |
|------|--------|
| `requirements.txt` | Add `requests>=2.31.0` and `python-dotenv>=1.0.0` |
| `SKILL.md` | Add Phase 5 web report section, update Phase 6 delivery |

---

## Task 1: Scaffold web-report project and config files

**Files:**
- Create: `web-report/package.json`
- Create: `web-report/vite.config.js`
- Create: `web-report/tailwind.config.js`
- Create: `web-report/postcss.config.js`
- Create: `web-report/vercel.json`
- Create: `web-report/index.html`
- Create: `web-report/.env.example`
- Create: `web-report/tsconfig.json`
- Create: `web-report/public/favicon.svg`

- [ ] **Step 1: Create web-report directory**

```bash
mkdir -p web-report/{src/{pages,components,utils},api/reports,lib,public}
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "powerbi-web-reports",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@vercel/blob": "^0.27.0",
    "html2pdf.js": "^0.10.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.11.0",
    "recharts": "^2.15.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.18",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.5.1",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.0",
    "vite": "^6.0.7"
  }
}
```

- [ ] **Step 3: Create vite.config.js**

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': 'http://localhost:3000'
    }
  },
  publicDir: 'public',
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  }
})
```

- [ ] **Step 4: Create tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          card: 'var(--bg-card)',
          'card-hover': 'var(--bg-card-hover)',
        },
        accent: {
          terracotta: 'var(--accent-terracotta)',
          forest: 'var(--accent-forest)',
          gold: 'var(--accent-gold)',
          sage: 'var(--accent-sage)',
          rust: 'var(--accent-rust)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
          muted: 'var(--text-muted)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          medium: 'var(--border-medium)',
          strong: 'var(--border-strong)',
        },
        importance: {
          high: 'var(--importance-high)',
          medium: 'var(--importance-medium)',
          low: 'var(--importance-low)',
        },
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
          6: 'var(--chart-6)',
          7: 'var(--chart-7)',
        },
      },
      fontFamily: {
        sans: ['Source Sans 3', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['Cormorant Garamond', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards',
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
      boxShadow: {
        'editorial': '0 1px 2px rgba(61, 54, 48, 0.04), 0 4px 8px rgba(61, 54, 48, 0.04), 0 12px 24px rgba(61, 54, 48, 0.06)',
        'editorial-hover': '0 2px 4px rgba(61, 54, 48, 0.04), 0 8px 16px rgba(61, 54, 48, 0.06), 0 24px 48px rgba(61, 54, 48, 0.08)',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 5: Create postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 6: Create vercel.json**

```json
{
  "framework": "vite",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    { "source": "/report/:id", "destination": "/index.html" }
  ]
}
```

- [ ] **Step 7: Create index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Power BI Reports</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Create .env.example**

```
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_xxx
API_SECRET=your-secret-key-here
```

- [ ] **Step 9: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "."
  },
  "include": ["api/**/*.ts", "lib/**/*.ts"]
}
```

- [ ] **Step 10: Create public/favicon.svg**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2d5a4a" stroke-width="1.5">
  <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
</svg>
```

- [ ] **Step 11: Commit**

```bash
git add web-report/
git commit -m "feat: scaffold web-report Vercel project with config files"
```

---

## Task 2: CSS and entry point

**Files:**
- Create: `web-report/src/index.css`
- Create: `web-report/src/main.jsx`
- Create: `web-report/src/App.jsx`

- [ ] **Step 1: Create src/index.css**

```css
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Source+Sans+3:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg-primary: #faf7f2;
  --bg-secondary: #f5f0e8;
  --bg-tertiary: #ebe5da;
  --bg-card: #ffffff;
  --bg-card-hover: #fffcf8;

  --accent-terracotta: #c45c3c;
  --accent-forest: #2d5a4a;
  --accent-gold: #d4a853;
  --accent-sage: #8ba888;
  --accent-rust: #a0522d;

  --text-primary: #3d3630;
  --text-secondary: #6b635a;
  --text-tertiary: #8c8377;
  --text-muted: #a9a095;

  --border-subtle: rgba(61, 54, 48, 0.08);
  --border-medium: rgba(61, 54, 48, 0.12);
  --border-strong: rgba(61, 54, 48, 0.18);

  --importance-high: #c45c3c;
  --importance-medium: #d4a853;
  --importance-low: #2d5a4a;

  --chart-1: #2d5a4a;
  --chart-2: #c45c3c;
  --chart-3: #d4a853;
  --chart-4: #8ba888;
  --chart-5: #a0522d;
  --chart-6: #6b8e7d;
  --chart-7: #d98a5c;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }

body {
  font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  margin: 0;
  padding: 0;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

.font-display { font-family: 'Cormorant Garamond', Georgia, serif; }
.font-mono { font-family: 'IBM Plex Mono', 'Fira Code', monospace; }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.animate-fade-in-up { animation: fadeInUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards; }
.animate-fade-in { animation: fadeIn 0.5s ease-out forwards; }
.animate-pulse-soft { animation: pulse-soft 2s ease-in-out infinite; }

.dot-pattern {
  background-image: radial-gradient(circle, var(--border-subtle) 1px, transparent 1px);
  background-size: 24px 24px;
}

.shadow-editorial {
  box-shadow: 0 1px 2px rgba(61, 54, 48, 0.04), 0 4px 8px rgba(61, 54, 48, 0.04), 0 12px 24px rgba(61, 54, 48, 0.06);
}

.badge-high { background: rgba(196, 92, 60, 0.1); color: var(--accent-terracotta); border: 1px solid rgba(196, 92, 60, 0.2); }
.badge-medium { background: rgba(212, 168, 83, 0.1); color: #b8923a; border: 1px solid rgba(212, 168, 83, 0.2); }
.badge-low { background: rgba(45, 90, 74, 0.1); color: var(--accent-forest); border: 1px solid rgba(45, 90, 74, 0.2); }

.btn-primary {
  background: var(--accent-forest);
  color: #ffffff;
  transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}
.btn-primary:hover {
  background: #245548;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(45, 90, 74, 0.3);
}

.divider-ornament { display: flex; align-items: center; gap: 16px; }
.divider-ornament::before,
.divider-ornament::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-medium), transparent);
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.recharts-cartesian-grid-horizontal line,
.recharts-cartesian-grid-vertical line {
  stroke: var(--border-subtle) !important;
}

.recharts-text {
  fill: var(--text-tertiary) !important;
  font-family: 'Source Sans 3', sans-serif !important;
}

@media print {
  body { background: #ffffff !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  header, nav button, .dot-pattern { display: none !important; }
  [class*="animate-"] { animation: none !important; opacity: 1 !important; }
}
```

- [ ] **Step 2: Create src/main.jsx**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 3: Create src/App.jsx**

```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Report from './pages/Report'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/report/:id" element={<Report />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
```

- [ ] **Step 4: Commit**

```bash
git add web-report/src/
git commit -m "feat: add React entry point, router, and CSS theme"
```

---

## Task 3: Shared utility modules

**Files:**
- Create: `web-report/src/utils/chartConfig.js`
- Create: `web-report/src/utils/pdfExporter.js`

- [ ] **Step 1: Create src/utils/chartConfig.js**

```javascript
export const CHART_COLORS = [
  '#2d5a4a', '#c45c3c', '#d4a853', '#8ba888', '#a0522d', '#6b8e7d', '#d98a5c'
]

export function formatNumber(num) {
  if (num >= 10000) return (num / 10000).toFixed(1) + '万'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toString()
}
```

- [ ] **Step 2: Create src/utils/pdfExporter.js**

```javascript
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
```

- [ ] **Step 3: Commit**

```bash
git add web-report/src/utils/
git commit -m "feat: add chartConfig and pdfExporter utilities"
```

---

## Task 4: ChartContainer component

**Files:**
- Create: `web-report/src/components/ChartContainer.jsx`

- [ ] **Step 1: Create ChartContainer.jsx**

```jsx
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { CHART_COLORS } from '../utils/chartConfig'

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[var(--bg-card)] border border-[var(--border-medium)] rounded-xl px-4 py-3 shadow-editorial">
        <p className="text-[var(--text-primary)] font-display font-semibold text-sm mb-2">{label}</p>
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-[var(--text-secondary)]">{entry.name}:</span>
            <span className="text-[var(--text-primary)] font-mono font-semibold">
              {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
            </span>
          </div>
        ))}
      </div>
    )
  }
  return null
}

function ChartContainer({ type, data }) {
  if (!data) return null

  const axisStyle = { tick: { fontSize: 11, fill: '#8c8377' }, stroke: 'rgba(61, 54, 48, 0.08)' }
  const gridStyle = { strokeDasharray: '4 4', stroke: 'rgba(61, 54, 48, 0.08)' }

  if (type === 'bar') {
    let chartData = [], seriesKeys = []
    const xKey = data.xKey || 'name'
    if (data.data && Array.isArray(data.data)) {
      chartData = data.data
      seriesKeys = [data.yKey || 'value']
    } else if (data.x_labels && data.series) {
      chartData = data.x_labels.map((label, i) => {
        const point = { name: label }
        Object.entries(data.series).forEach(([key, values]) => { point[key] = values[i] })
        return point
      })
      seriesKeys = Object.keys(data.series)
    }
    return (
      <div className="mt-6 pt-6 border-t border-[var(--border-subtle)]">
        <div className="bg-[var(--bg-secondary)]/50 rounded-xl p-4 -mx-2" style={{ minHeight: '300px' }}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid {...gridStyle} vertical={false} />
              <XAxis dataKey={xKey} {...axisStyle} axisLine={false} tickLine={false} />
              <YAxis {...axisStyle} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              {seriesKeys.length > 1 && <Legend />}
              {seriesKeys.map((key, i) => (
                <Bar key={key} dataKey={key} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[6, 6, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    )
  }

  if (type === 'line') {
    let chartData = [], seriesKeys = []
    if (data.x_labels && data.series) {
      chartData = data.x_labels.map((label, i) => {
        const point = { name: label }
        Object.entries(data.series).forEach(([key, values]) => { point[key] = values[i] })
        return point
      })
      seriesKeys = Object.keys(data.series)
    }
    return (
      <div className="mt-6 pt-6 border-t border-[var(--border-subtle)]">
        <div className="bg-[var(--bg-secondary)]/50 rounded-xl p-4 -mx-2" style={{ minHeight: '300px' }}>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid {...gridStyle} vertical={false} />
              <XAxis dataKey="name" {...axisStyle} axisLine={false} tickLine={false} />
              <YAxis {...axisStyle} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {seriesKeys.map((key, i) => (
                <Line key={key} type="monotone" dataKey={key} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2.5} dot={{ r: 4 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    )
  }

  if (type === 'pie') {
    let chartData = []
    if (data.labels && data.values) {
      chartData = data.labels.map((label, i) => ({ name: label, value: data.values[i] }))
    } else if (data.data) {
      chartData = data.data.map(item => ({ name: item[data.nameKey || 'name'], value: item[data.valueKey || 'value'] }))
    }
    return (
      <div className="mt-6 pt-6 border-t border-[var(--border-subtle)]">
        <div className="bg-[var(--bg-secondary)]/50 rounded-xl p-4 -mx-2" style={{ minHeight: '300px' }}>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={chartData} cx="50%" cy="50%" innerRadius={60} outerRadius={95} paddingAngle={3} dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {chartData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} stroke="#ffffff" strokeWidth={2} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    )
  }

  if (type === 'scatter') {
    const chartData = data.x?.map((x, i) => ({ x, y: data.y[i], name: data.labels?.[i] || `Point ${i + 1}` })) || []
    return (
      <div className="mt-6 pt-6 border-t border-[var(--border-subtle)]">
        <div className="bg-[var(--bg-secondary)]/50 rounded-xl p-4 -mx-2" style={{ minHeight: '300px' }}>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart margin={{ top: 20, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid {...gridStyle} />
              <XAxis type="number" dataKey="x" name={data.x_title || 'X'} {...axisStyle} axisLine={false} />
              <YAxis type="number" dataKey="y" name={data.y_title || 'Y'} {...axisStyle} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Scatter name="Data Points" data={chartData} fill={CHART_COLORS[0]} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    )
  }

  return <p className="text-[var(--text-muted)] text-sm">Unsupported chart type: {type}</p>
}

export default ChartContainer
```

- [ ] **Step 2: Commit**

```bash
git add web-report/src/components/ChartContainer.jsx
git commit -m "feat: add ChartContainer with Recharts (bar/line/pie/scatter)"
```

---

## Task 5: Small display components

**Files:**
- Create: `web-report/src/components/Header.jsx`
- Create: `web-report/src/components/ExportButton.jsx`
- Create: `web-report/src/components/EmptyState.jsx`
- Create: `web-report/src/components/DataSourceBadge.jsx`

- [ ] **Step 1: Create Header.jsx**

```jsx
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

function Header({ title }) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${scrolled ? 'py-3 bg-[var(--bg-primary)]/95 backdrop-blur-md shadow-editorial border-b border-[var(--border-subtle)]' : 'py-5 bg-transparent'}`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-4 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <div className="relative w-12 h-12 group">
              <div className="absolute inset-0 rounded-full border-2 border-[var(--accent-forest)]/20" />
              <div className="absolute inset-1.5 bg-[var(--bg-card)] rounded-full shadow-sm flex items-center justify-center">
                <svg className="w-5 h-5 text-[var(--accent-forest)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-[var(--accent-terracotta)] rounded-full opacity-80" />
            </div>
            <div>
              <h1 className="font-display text-2xl font-semibold text-[var(--text-primary)]">{title || 'Power BI Reports'}</h1>
              <p className="text-[11px] text-[var(--text-tertiary)] font-medium tracking-[0.15em] uppercase mt-0.5">分析报告</p>
            </div>
          </Link>
        </div>
      </div>
    </header>
  )
}

export default Header
```

- [ ] **Step 2: Create ExportButton.jsx**

```jsx
function ExportButton({ onClick }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-2.5 px-6 py-3 rounded-full font-semibold text-sm btn-primary">
      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      <span>导出 PDF</span>
    </button>
  )
}

export default ExportButton
```

- [ ] **Step 3: Create EmptyState.jsx**

```jsx
function EmptyState() {
  return (
    <div className="py-24 opacity-0 animate-fade-in-up">
      <div className="max-w-md">
        <h2 className="font-display text-3xl lg:text-4xl font-light text-[var(--text-primary)] mb-4">暂无报告</h2>
        <p className="text-[var(--text-secondary)] mb-8 leading-relaxed">
          在 OpenClaw 中使用 Power BI 分析技能，生成第一份 Web 分析报告。
        </p>
      </div>
    </div>
  )
}

export default EmptyState
```

- [ ] **Step 4: Create DataSourceBadge.jsx**

```jsx
function DataSourceBadge({ model }) {
  if (!model) return null
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider">数据源</span>
      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border text-[var(--accent-forest)] bg-[var(--accent-forest)]/8 border-[var(--accent-forest)]/15">
        {model}
      </span>
    </div>
  )
}

export default DataSourceBadge
```

- [ ] **Step 5: Commit**

```bash
git add web-report/src/components/{Header,ExportButton,EmptyState,DataSourceBadge}.jsx
git commit -m "feat: add Header, ExportButton, EmptyState, DataSourceBadge components"
```

---

## Task 6: InsightCard and StatsOverview components

**Files:**
- Create: `web-report/src/components/InsightCard.jsx`
- Create: `web-report/src/components/StatsOverview.jsx`

- [ ] **Step 1: Create InsightCard.jsx**

```jsx
import ChartContainer from './ChartContainer'

const IMPORTANCE_LABELS = { high: '关键', medium: '重要', low: '一般' }

function InsightCard({ conclusion, index = 0 }) {
  const { title, description, data_support, importance = 'medium', chart_type, chart_data } = conclusion

  return (
    <article className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] transition-all duration-300 hover:border-[var(--border-medium)] opacity-0 animate-fade-in-up" style={{ animationDelay: `${0.15 + index * 0.1}s` }}>
      <div className="p-6 lg:p-8">
        <div className="flex items-start justify-between gap-4 mb-4">
          <span className="font-mono text-xs text-[var(--text-muted)] mt-1">{String(index + 1).padStart(2, '0')}</span>
          <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider badge-${importance}`}>{IMPORTANCE_LABELS[importance]}</span>
        </div>
        <h3 className="font-display text-xl lg:text-2xl font-normal text-[var(--text-primary)] leading-snug mb-4">{title}</h3>
        <p className="text-[var(--text-secondary)] text-sm leading-relaxed mb-6">{description}</p>
        {data_support && (
          <div className="mb-6 py-4 border-y border-[var(--border-subtle)]">
            <span className="font-mono text-[10px] text-[var(--text-muted)] uppercase tracking-wider block mb-3">数据支撑</span>
            <p className="text-[var(--text-primary)] text-sm font-mono leading-relaxed">{data_support}</p>
          </div>
        )}
        {chart_type && chart_type !== 'none' && chart_data && (
          <div className="mt-6">
            <ChartContainer type={chart_type} data={chart_data} />
          </div>
        )}
      </div>
    </article>
  )
}

export default InsightCard
```

- [ ] **Step 2: Create StatsOverview.jsx**

```jsx
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

function StatsOverview({ reports = [] }) {
  const totalReports = reports.length
  const now = new Date()
  const thisMonthReports = reports.filter(r => {
    const d = new Date(r.created_at)
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  }).length
  const totalHighImportance = reports.reduce((sum, r) => sum + (r.stats?.high_importance || 0), 0)

  return (
    <div className="mb-16 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <div className="flex flex-wrap items-baseline gap-x-12 gap-y-4 py-6 border-y border-[var(--border-subtle)]">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-5xl lg:text-6xl font-light text-[var(--text-primary)]"><AnimatedNumber value={totalReports} /></span>
          <span className="text-sm text-[var(--text-muted)] font-medium">份报告</span>
        </div>
        <div className="hidden sm:block w-px h-8 bg-[var(--border-subtle)]" />
        <div className="flex items-baseline gap-3">
          <span className="font-display text-5xl lg:text-6xl font-light text-[var(--text-primary)]"><AnimatedNumber value={thisMonthReports} /></span>
          <span className="text-sm text-[var(--text-muted)] font-medium">本月新增</span>
        </div>
        <div className="hidden sm:block w-px h-8 bg-[var(--border-subtle)]" />
        <div className="flex items-baseline gap-3">
          <span className="font-display text-5xl lg:text-6xl font-light text-[var(--text-primary)]"><AnimatedNumber value={totalHighImportance} /></span>
          <span className="text-sm text-[var(--text-muted)] font-medium">关键发现</span>
        </div>
      </div>
    </div>
  )
}

export default StatsOverview
```

- [ ] **Step 3: Commit**

```bash
git add web-report/src/components/{InsightCard,StatsOverview}.jsx
git commit -m "feat: add InsightCard and StatsOverview components"
```

---

## Task 7: ReportCard and Dashboard page

**Files:**
- Create: `web-report/src/components/ReportCard.jsx`
- Create: `web-report/src/pages/Dashboard.jsx`

- [ ] **Step 1: Create ReportCard.jsx**

```jsx
import { Link } from 'react-router-dom'

function ReportCard({ report, index = 0 }) {
  const { id, title, created_at, summary_preview, stats } = report

  const formatDate = (isoString) => {
    try {
      const date = new Date(isoString)
      return { month: (date.getMonth() + 1) + '月', day: date.getDate(), year: date.getFullYear() }
    } catch { return { month: '1月', day: '01', year: '2025' } }
  }

  const { month, day, year } = formatDate(created_at)

  return (
    <Link to={`/report/${id}`} className="group relative block opacity-0 animate-fade-in-up no-underline" style={{ animationDelay: `${0.1 + index * 0.08}s` }}>
      <article className="relative h-full">
        <div className="relative h-full bg-[var(--bg-card)] border border-[var(--border-subtle)] transition-all duration-500 group-hover:border-[var(--border-medium)] group-hover:shadow-lg">
          <div className="p-6 lg:p-8">
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-baseline gap-1 text-[var(--text-muted)]">
                <span className="font-mono text-xs">{month}</span>
                <span className="font-display text-2xl font-light text-[var(--text-primary)]">{day}</span>
                <span className="font-mono text-xs">{year}</span>
              </div>
              <div className="flex items-center gap-4 text-[var(--text-muted)]">
                <span className="font-mono text-xs">{stats?.total_conclusions || 0} 项发现</span>
              </div>
            </div>
            <h3 className="font-display text-2xl lg:text-3xl font-normal text-[var(--text-primary)] leading-snug mb-4 group-hover:text-[var(--accent-forest)] transition-colors">{title}</h3>
            <p className="text-[var(--text-secondary)] text-sm leading-relaxed line-clamp-2 mb-6">{summary_preview}</p>
            <div className="flex items-center justify-between pt-5 border-t border-[var(--border-subtle)]">
              <div className="text-xs text-[var(--text-muted)]">{stats?.high_importance || 0} 项关键发现</div>
              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] group-hover:text-[var(--accent-forest)] transition-colors">
                <span className="font-medium opacity-0 group-hover:opacity-100 transition-opacity">查看</span>
                <svg className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </article>
    </Link>
  )
}

export default ReportCard
```

- [ ] **Step 2: Create Dashboard.jsx**

```jsx
import { useState, useEffect } from 'react'
import ReportCard from '../components/ReportCard'
import StatsOverview from '../components/StatsOverview'
import EmptyState from '../components/EmptyState'

function Dashboard() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadReports()
  }, [])

  const loadReports = async () => {
    try {
      const response = await fetch('/api/reports')
      if (response.ok) {
        const data = await response.json()
        setReports(data.reports || [])
      } else {
        setReports([])
      }
    } catch (err) {
      console.log('Failed to load reports:', err)
      setReports([])
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="text-center">
          <div className="w-6 h-6 border-2 border-[var(--text-muted)] border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="mt-4 text-[var(--text-muted)] text-sm">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="border-b border-[var(--border-subtle)] sticky top-0 z-50 bg-[var(--bg-primary)]">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="opacity-0 animate-fade-in-up">
              <h1 className="font-display text-xl text-[var(--text-primary)]">Power BI Reports</h1>
            </div>
            <div className="opacity-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
              <span className="font-mono text-xs text-[var(--text-muted)]">{reports.length} 份报告</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 lg:px-8 py-12 lg:py-16">
        {reports.length > 0 ? (
          <>
            <div className="mb-12 opacity-0 animate-fade-in-up">
              <h2 className="font-display text-4xl lg:text-5xl font-light text-[var(--text-primary)] mb-4">分析存档</h2>
              <p className="text-[var(--text-secondary)] max-w-xl">所有 Power BI 数据分析报告与洞察结论的归档。</p>
            </div>

            <StatsOverview reports={reports} />

            <section>
              <div className="mb-8 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                <h3 className="font-mono text-xs text-[var(--text-muted)] uppercase tracking-wider">全部报告</h3>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 lg:pl-6">
                {reports.map((report, index) => (
                  <ReportCard key={report.id} report={report} index={index} />
                ))}
              </div>
            </section>
          </>
        ) : (
          <EmptyState />
        )}
      </main>

      <footer className="border-t border-[var(--border-subtle)]">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-8">
          <p className="font-mono text-xs text-[var(--text-muted)]">Power BI Reports</p>
        </div>
      </footer>
    </div>
  )
}

export default Dashboard
```

- [ ] **Step 3: Commit**

```bash
git add web-report/src/components/ReportCard.jsx web-report/src/pages/Dashboard.jsx
git commit -m "feat: add ReportCard and Dashboard page"
```

---

## Task 8: Report page

**Files:**
- Create: `web-report/src/pages/Report.jsx`

- [ ] **Step 1: Create Report.jsx**

```jsx
import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import Header from '../components/Header'
import InsightCard from '../components/InsightCard'
import ExportButton from '../components/ExportButton'
import DataSourceBadge from '../components/DataSourceBadge'
import { exportToPDF, generateFilename } from '../utils/pdfExporter'

function Report() {
  const { id } = useParams()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const reportRef = useRef(null)

  const handleExportPDF = async () => {
    const filename = generateFilename(report?.meta?.title?.slice(0, 20) || 'report')
    await exportToPDF(reportRef.current, filename)
  }

  useEffect(() => {
    loadReport()
  }, [id])

  const loadReport = async () => {
    setLoading(true)
    try {
      const response = await fetch(`/api/reports/${encodeURIComponent(id)}`)
      if (response.ok) {
        const data = await response.json()
        setReport(data)
      }
    } catch (err) {
      console.log('Error loading report:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto relative">
            <div className="absolute inset-0 rounded-full border-2 border-[var(--border-subtle)]" />
            <div className="absolute inset-0 rounded-full border-2 border-[var(--accent-forest)] border-t-transparent animate-spin" />
          </div>
          <p className="mt-6 text-[var(--text-secondary)] text-sm">加载报告中...</p>
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="text-center">
          <p className="text-[var(--text-secondary)] font-display text-xl mb-4">报告不存在</p>
          <Link to="/" className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--accent-forest)] text-white rounded-lg">
            返回存档
          </Link>
        </div>
      </div>
    )
  }

  const formatDate = (isoString) => {
    try {
      return new Date(isoString).toLocaleString('zh-CN', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
      })
    } catch { return isoString }
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] relative">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 dot-pattern opacity-40" />
      </div>

      <Header title={report.meta?.title} />

      <main ref={reportRef} className="relative max-w-6xl mx-auto px-6 lg:px-8 pt-32 pb-24">
        <nav className="mb-8 opacity-0 animate-fade-in-up flex items-center justify-between">
          <Link to="/" className="group inline-flex items-center gap-2 px-4 py-2 bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-full text-sm">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span>存档</span>
          </Link>
          <ExportButton onClick={handleExportPDF} />
        </nav>

        <section className="mb-20 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center gap-4 mb-8">
            <span className="text-[11px] font-bold text-[var(--accent-terracotta)] uppercase tracking-[0.2em]">摘要概览</span>
            <div className="flex-1 h-px bg-gradient-to-r from-[var(--accent-terracotta)]/30 to-transparent" />
          </div>
          <div className="relative bg-[var(--bg-card)] rounded-3xl border border-[var(--border-subtle)] shadow-editorial overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-[var(--accent-forest)] via-[var(--accent-gold)] to-[var(--accent-terracotta)]" />
            <div className="relative p-8 lg:p-12">
              <div className="flex flex-wrap gap-8 mb-10">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 rounded-2xl bg-[var(--accent-forest)]/10 flex items-center justify-center">
                    <svg className="w-7 h-7 text-[var(--accent-forest)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-display text-4xl font-bold text-[var(--text-primary)]">{report.summary?.total_conclusions || 0}</p>
                    <p className="text-xs text-[var(--text-tertiary)] font-semibold uppercase tracking-wider mt-1">核心发现</p>
                  </div>
                </div>
              </div>
              <div className="divider-ornament mb-8">
                <svg className="w-6 h-6 text-[var(--accent-gold)]" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2L9.5 8.5 3 9.5l5 4.5-1.5 6.5 5.5-3.5 5.5 3.5-1.5-6.5 5-4.5-6.5-1z"/>
                </svg>
              </div>
              <p className="text-[var(--text-primary)] text-xl lg:text-2xl leading-relaxed font-display">{report.summary?.overall}</p>
              {report.meta?.model && (
                <div className="mt-6">
                  <DataSourceBadge model={report.meta.model} />
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="mb-10 opacity-0 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <div className="flex items-center gap-4">
            <span className="text-[11px] font-bold text-[var(--accent-forest)] uppercase tracking-[0.2em]">详细发现</span>
            <div className="flex-1 h-px bg-gradient-to-r from-[var(--accent-forest)]/30 to-transparent" />
          </div>
          <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold text-[var(--text-primary)]">关键洞察</h2>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {report.conclusions?.map((conclusion, index) => (
            <InsightCard key={conclusion.id} conclusion={conclusion} index={index} />
          ))}
        </section>
      </main>

      <footer className="relative border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-10">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <Link to="/" className="flex items-center gap-4">
              <p className="text-sm font-semibold text-[var(--text-primary)]">Power BI Reports</p>
            </Link>
            <p className="text-sm text-[var(--text-secondary)]">生成时间：{formatDate(report.meta?.generated_at)}</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Report
```

- [ ] **Step 2: Commit**

```bash
git add web-report/src/pages/Report.jsx
git commit -m "feat: add Report page with insights and chart rendering"
```

---

## Task 9: Vercel Blob library and API Routes

**Files:**
- Create: `web-report/lib/blob.ts`
- Create: `web-report/api/reports/index.ts`
- Create: `web-report/api/reports/[id].ts`

- [ ] **Step 1: Create lib/blob.ts**

```typescript
import { put, get, del, list, head } from '@vercel/blob';

export interface IndexEntry {
  id: string;
  title: string;
  created_at: string;
  summary_preview: string;
  stats: {
    total_conclusions: number;
    high_importance: number;
  };
}

export interface ReportIndex {
  reports: IndexEntry[];
}

const INDEX_KEY = 'reports-index.json';

export async function getIndex(): Promise<ReportIndex> {
  try {
    const { body } = await get(INDEX_KEY);
    const text = await body.text();
    return JSON.parse(text);
  } catch {
    return { reports: [] };
  }
}

export async function putIndex(index: ReportIndex): Promise<void> {
  await put(INDEX_KEY, JSON.stringify(index, null, 2), {
    access: 'public',
    addRandomSuffix: false,
    type: 'application/json',
  });
}

export async function getReport(id: string): Promise<object | null> {
  try {
    const { body } = await get(`reports/${id}.json`);
    const text = await body.text();
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function putReport(id: string, data: object): Promise<void> {
  await put(`reports/${id}.json`, JSON.stringify(data, null, 2), {
    access: 'public',
    addRandomSuffix: false,
    type: 'application/json',
  });
}

export async function deleteReport(id: string): Promise<void> {
  await del(`reports/${id}.json`);
}
```

- [ ] **Step 2: Create api/reports/index.ts**

> **Note:** Vercel Edge Runtime uses Web API `Request`/`Response`, NOT `next/server`. This project is Vite-based, not Next.js.

```typescript
import { getIndex, putIndex, putReport } from '../../lib/blob';

export const config = { runtime: 'edge' };

function getApiSecret(): string {
  return process.env.API_SECRET || '';
}

function validateAuth(request: Request): boolean {
  const auth = request.headers.get('authorization');
  const secret = getApiSecret();
  if (!secret) return false;
  return auth === `Bearer ${secret}`;
}

function json(data: object, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// GET /api/reports — list all reports (public)
export async function GET() {
  try {
    const index = await getIndex();
    return json(index);
  } catch {
    return json({ error: 'Failed to load reports' }, 500);
  }
}

// POST /api/reports — upsert a report (auth required)
export async function POST(request: Request) {
  if (!validateAuth(request)) {
    return json({ error: 'Unauthorized' }, 401);
  }

  try {
    const body = await request.json();
    const { id } = body;

    if (!id || !body.meta?.title) {
      return json({ error: 'Missing required fields: id, meta.title' }, 400);
    }

    // Store the full report
    await putReport(id, body);

    // Update the index (with dedup for upsert)
    const index = await getIndex();
    const overallText = body.summary?.overall || '';
    const summaryPreview = overallText.slice(0, 100) + (overallText.length > 100 ? '...' : '');
    const newEntry = {
      id,
      title: body.meta.title,
      created_at: body.meta.generated_at || new Date().toISOString(),
      summary_preview: summaryPreview,
      stats: {
        total_conclusions: body.summary?.total_conclusions || 0,
        high_importance: body.summary?.high_importance_count || 0,
      },
    };

    const existingIdx = index.reports.findIndex((r) => r.id === id);
    let updated = false;
    if (existingIdx >= 0) {
      // Upsert: update existing entry and move to head
      index.reports.splice(existingIdx, 1);
      index.reports.unshift(newEntry);
      updated = true;
    } else {
      // New: insert at head
      index.reports.unshift(newEntry);
    }

    await putIndex(index);

    return json({ url: `/report/${id}`, updated });
  } catch {
    return json({ error: 'Failed to save report' }, 500);
  }
}
```

- [ ] **Step 3: Create api/reports/[id].ts**

```typescript
import { getIndex, putIndex, getReport, deleteReport } from '../../lib/blob';

export const config = { runtime: 'edge' };

function getApiSecret(): string {
  return process.env.API_SECRET || '';
}

function validateAuth(request: Request): boolean {
  const auth = request.headers.get('authorization');
  const secret = getApiSecret();
  if (!secret) return false;
  return auth === `Bearer ${secret}`;
}

function json(data: object, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// GET /api/reports/[id] — get single report (public)
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const report = await getReport(id);
    if (!report) {
      return json({ error: 'Report not found' }, 404);
    }
    return json(report);
  } catch {
    return json({ error: 'Failed to load report' }, 500);
  }
}

// DELETE /api/reports/[id] — delete a report (auth required)
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  if (!validateAuth(request)) {
    return json({ error: 'Unauthorized' }, 401);
  }

  const { id } = await params;
  try {
    await deleteReport(id);

    // Update index: remove the entry
    const index = await getIndex();
    index.reports = index.reports.filter((r) => r.id !== id);
    await putIndex(index);

    return json({ success: true });
  } catch {
    return json({ error: 'Failed to delete report' }, 500);
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add web-report/lib/ web-report/api/
git commit -m "feat: add Vercel Blob library and API routes (CRUD with upsert)"
```

---

## Task 10: Python upload script

**Files:**
- Create: `scripts/web_report_builder.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Create scripts/web_report_builder.py**

```python
"""
Web Report Builder — 上传报告 JSON 到 Vercel Blob，返回公网 URL
"""
import os
import json
import requests
from typing import Optional


class WebReportBuilder:
    def __init__(self, vercel_url: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Args:
            vercel_url: Vercel 项目 URL，如 https://pbi-reports.vercel.app
            api_secret: API 密钥，用于 POST 鉴权
        """
        self.vercel_url = (vercel_url or os.environ.get(
            'VERCEL_REPORTS_URL', ''
        )).rstrip('/')
        self.api_secret = api_secret or os.environ.get('VERCEL_API_SECRET', '')

        if not self.vercel_url:
            raise ValueError(
                'Vercel URL 未配置。请设置 VERCEL_REPORTS_URL 环境变量，'
                '或在 .env 文件中配置。'
            )
        if not self.api_secret:
            raise ValueError(
                'API Secret 未配置。请设置 VERCEL_API_SECRET 环境变量，'
                '或在 .env 文件中配置。'
            )

    def publish_report(self, report_data: dict, report_id: str) -> str:
        """
        上传报告到 Vercel，返回公网 URL。

        Args:
            report_data: 完整的报告 JSON（含 meta, summary, conclusions）
            report_id: 报告唯一标识，如 report-20260415-流失分析

        Returns:
            公网 URL

        Raises:
            requests.exceptions.RequestException: 上传失败
            ValueError: API 返回错误
        """
        # 注入 id 到 body
        payload = {**report_data, 'id': report_id}

        response = requests.post(
            f'{self.vercel_url}/api/reports',
            headers={
                'Authorization': f'Bearer {self.api_secret}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=15,
        )

        if response.status_code == 401:
            raise ValueError('API Secret 无效，请检查 VERCEL_API_SECRET 配置')

        if response.status_code != 200:
            raise ValueError(
                f'上传失败 ({response.status_code}): {response.text}'
            )

        result = response.json()
        return f'{self.vercel_url}{result["url"]}'


# 模块级便捷实例（延迟加载配置）
_builder: Optional[WebReportBuilder] = None


def get_builder() -> WebReportBuilder:
    """获取全局 WebReportBuilder 实例"""
    global _builder
    if _builder is None:
        # 尝试加载 .env 文件
        try:
            from dotenv import load_dotenv
            skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_path = os.path.join(skill_dir, '.env')
            if os.path.exists(env_path):
                load_dotenv(env_path)
        except ImportError:
            pass
        _builder = WebReportBuilder()
    return _builder


def publish_report(report_data: dict, report_id: str) -> str:
    """
    便捷函数：上传报告并返回公网 URL。

    用法:
        from scripts.web_report_builder import publish_report
        url = publish_report(report_json, 'report-20260415-分析')
    """
    return get_builder().publish_report(report_data, report_id)
```

- [ ] **Step 2: Update requirements.txt — add requests and python-dotenv**

Append these lines to `requirements.txt`:

```
# Web 报告上传
requests>=2.31.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: Commit**

```bash
git add scripts/web_report_builder.py requirements.txt
git commit -m "feat: add WebReportBuilder Python client for Vercel upload"
```

---

## Task 11: .gitignore and .env template

**Files:**
- Create: `.gitignore`
- Create: `.env` (with placeholder values, user fills in)

- [ ] **Step 1: Create .gitignore in skill root**

```gitignore
# Python
__pycache__/
*.pyc
venv/

# Environment
.env

# Node
web-report/node_modules/
web-report/dist/
web-report/.vercel/

# Output
output/*.png
output/*.py

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Create .env with placeholder values**

```
# Vercel Web Reports 配置
# 部署 web-report 项目后填写
VERCEL_REPORTS_URL=https://your-project.vercel.app
VERCEL_API_SECRET=your-secret-key
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env
git commit -m "feat: add .gitignore and .env template"
```

---

## Task 12: Update SKILL.md

**Files:**
- Modify: `SKILL.md` — add web report section to Phase 5, update Phase 6

- [ ] **Step 1: Add Web Report section after the existing Phase 5**

Insert the following block after the existing `## 🎨画图引擎调用说明` section (after line ~264, before `## ✍️ DAX编写强制检查清单`):

```markdown



## 🌐 Web分析报告生成说明

当用户需要生成可分享的 Web 分析报告时触发（如要求"出报告"、"复盘分析"等）。

**触发条件**：
- 用户明确要求生成报告或可视化分析
- 出现"分析走势"、"对比数据"、"复盘"等需要强可视化的场景
- 用户需要将分析结果分享给他人

**报告JSON格式**：

```json
{
  "meta": {
    "title": "报告标题",
    "generated_at": "ISO 8601 时间戳",
    "model": "语义模型名称"
  },
  "summary": {
    "overall": "整体结论概述",
    "total_conclusions": 5,
    "high_importance_count": 2
  },
  "conclusions": [
    {
      "id": 1,
      "title": "结论标题",
      "description": "详细描述",
      "data_support": "数据支撑文本",
      "importance": "high | medium | low",
      "chart_type": "bar | line | pie | scatter",
      "chart_data": {
        "bar 格式": { "xKey": "name", "yKey": "value", "data": [{"name":"A","value":100}] },
        "line 格式": { "x_labels": ["1月","2月"], "series": {"指标A":[100,200]} },
        "pie 格式": { "labels": ["A","B"], "values": [60,40] },
        "scatter 格式": { "x":[1,2], "y":[3,4], "x_title":"X轴", "y_title":"Y轴" }
      }
    }
  ]
}
```

**调用方法**：

```python
from scripts.web_report_builder import publish_report

url = publish_report(report_data, report_id)
# 返回公网 URL，如 https://xxx.vercel.app/report/report-20260415-流失分析
```

**report_id 命名规则**：`report-{YYYYMMDD}-{主题关键词}`

**覆写机制**：相同 report_id 的报告会覆盖旧版本，适用于追问同一主题时迭代更新。
```

- [ ] **Step 2: Update Phase 5 description**

Replace the existing Phase 5 block:

```
### Phase 5：生成可视化图表 (可选)
当用户明确表示要求"画图"，或出现"分析走势"、"对比数据"等需要强可视化的场景时触发；执行方式参考 `画图引擎调用说明`
```

With:

```
### Phase 5：生成可视化内容 (可选)

**两种模式可选**：

1. **Web分析报告**（推荐，可分享）：执行方式参考 `Web分析报告生成说明`
2. **本地图表**（快速出图）：当用户仅要求简单画图时，执行方式参考 `画图引擎调用说明`

选择依据：需要分享 → Web报告；快速查看 → 本地图表
```

- [ ] **Step 3: Update Phase 6 description**

Replace the existing Phase 6 block:

```
### Phase 6：交付内容

包含图表内容和数据结果的洞察分析，必须基于现有数据得到结论，不能臆想猜测
```

With:

```
### Phase 6：交付内容

包含分析洞察结论，必须基于现有数据得到结论，不能臆想猜测。

- 若生成了 Web 报告，交付内容中需包含报告链接，如：`📊 Web分析报告: https://xxx.vercel.app/report/report-xxx`
- 若生成了本地图表，交付内容中需包含图片路径
```

- [ ] **Step 4: Commit**

```bash
git add SKILL.md
git commit -m "docs: update SKILL.md with web report generation section"
```

---

## Task 13: Install dependencies and verify build

- [ ] **Step 1: Install npm dependencies**

```bash
cd web-report && npm install
```

Expected: Dependencies installed, no errors.

- [ ] **Step 2: Verify Vite build succeeds**

```bash
cd web-report && npm run build
```

Expected: Build completes with `dist/` output, no errors.

- [ ] **Step 3: Install Python dependencies**

```bash
pip install requests python-dotenv
```

Expected: `requests` and `python-dotenv` installed.

- [ ] **Step 4: Verify Python module imports**

```bash
python -c "from scripts.web_report_builder import WebReportBuilder; print('OK')"
```

Expected: Prints `OK` (will error on missing .env, which is expected — the module loads).

- [ ] **Step 5: Commit (if any lockfile changes)**

```bash
git add web-report/package-lock.json
git commit -m "chore: add package-lock.json"
```

---

## Task 14: End-to-end test (manual, requires Vercel setup)

This task requires the user to have completed the one-time Vercel setup (Section 10 of the spec). It cannot be automated until credentials are configured.

- [ ] **Step 1: Configure .env with real values**

Fill in `.env` with actual Vercel URL and API secret.

- [ ] **Step 2: Deploy to Vercel**

```bash
cd web-report && vercel deploy --prod
```

- [ ] **Step 3: Upload a test report via Python**

```python
from scripts.web_report_builder import publish_report

test_report = {
    "meta": {
        "title": "测试报告",
        "generated_at": "2026-04-15T12:00:00",
        "model": "测试模型",
        "version": "1.0"
    },
    "summary": {
        "overall": "这是一份测试报告，用于验证端到端流程。",
        "total_conclusions": 1,
        "high_importance_count": 1
    },
    "conclusions": [
        {
            "id": 1,
            "title": "测试结论",
            "description": "验证系统是否正常工作。",
            "data_support": "无实际数据",
            "importance": "high",
            "chart_type": "bar",
            "chart_data": {
                "xKey": "name",
                "yKey": "value",
                "data": [
                    {"name": "A", "value": 100},
                    {"name": "B", "value": 200},
                    {"name": "C", "value": 150}
                ]
            }
        }
    ]
}

url = publish_report(test_report, "report-20260415-测试")
print(f"报告URL: {url}")
```

Expected: Prints a valid `https://xxx.vercel.app/report/report-20260415-测试` URL.

- [ ] **Step 4: Open URL in browser and verify**

Verify:
- Dashboard at root URL shows the test report
- Report page loads with chart, insight card, and header
- PDF export button works
- Report card links to report detail

- [ ] **Step 5: Test upsert — upload same ID with updated data**

Change the test report title and conclusions count, upload with the same ID. Verify the report page reflects the update (not a duplicate).

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "chore: final state after e2e verification"
```
