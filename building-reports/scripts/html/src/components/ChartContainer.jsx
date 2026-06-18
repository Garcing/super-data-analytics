import React from 'react'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { CHART_COLORS } from '../utils/chartConfig'

const axisStyle = {
  tick: { fontSize: 11, fill: '#8c8377' },
  stroke: 'rgba(61, 54, 48, 0.08)'
}

const gridStyle = {
  strokeDasharray: '4 4',
  stroke: 'rgba(61, 54, 48, 0.08)'
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  return (
    <div style={{
      background: 'rgba(250, 247, 242, 0.95)',
      border: '1px solid rgba(61, 54, 48, 0.15)',
      borderRadius: '8px',
      padding: '10px 14px',
      boxShadow: '0 4px 12px rgba(61, 54, 48, 0.1)',
      fontSize: '13px',
      color: '#3d3630',
      lineHeight: '1.6'
    }}>
      {label && (
        <div style={{
          fontWeight: 600,
          marginBottom: '4px',
          color: '#5c544b'
        }}>
          {label}
        </div>
      )}
      {payload.map((entry, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: entry.color
          }} />
          <span style={{ color: '#7a7067' }}>{entry.name || entry.dataKey}:</span>
          <span style={{ fontWeight: 600 }}>{typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}</span>
        </div>
      ))}
    </div>
  )
}

function CustomPieTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0]
  return (
    <div style={{
      background: 'rgba(250, 247, 242, 0.95)',
      border: '1px solid rgba(61, 54, 48, 0.15)',
      borderRadius: '8px',
      padding: '10px 14px',
      boxShadow: '0 4px 12px rgba(61, 54, 48, 0.1)',
      fontSize: '13px',
      color: '#3d3630'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{
          display: 'inline-block',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: d.payload.fill || d.color
        }} />
        <span style={{ color: '#7a7067' }}>{d.name}:</span>
        <span style={{ fontWeight: 600 }}>{typeof d.value === 'number' ? d.value.toLocaleString() : d.value}</span>
      </div>
    </div>
  )
}

function BarChartView({ data }) {
  let chartData = []
  let seriesKeys = []

  if (data.xKey && data.yKey) {
    chartData = data.data.map(item => ({
      name: String(item[data.xKey]),
      ...item
    }))
    seriesKeys = [data.yKey]
  } else if (data.x_labels && data.series) {
    chartData = data.x_labels.map((label, i) => {
      const point = { name: String(label) }
      Object.entries(data.series).forEach(([key, values]) => {
        point[key] = values[i]
      })
      return point
    })
    seriesKeys = Object.keys(data.series)
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis dataKey="name" {...axisStyle} />
        <YAxis {...axisStyle} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: '12px', color: '#7a7067' }} />
        {seriesKeys.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            radius={[3, 3, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

function LineChartView({ data }) {
  const chartData = data.x_labels.map((label, i) => {
    const point = { name: String(label) }
    Object.entries(data.series).forEach(([key, values]) => {
      point[key] = values[i]
    })
    return point
  })
  const seriesKeys = Object.keys(data.series)

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis dataKey="name" {...axisStyle} />
        <YAxis {...axisStyle} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: '12px', color: '#7a7067' }} />
        {seriesKeys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            strokeWidth={2}
            dot={{ r: 3, fill: CHART_COLORS[i % CHART_COLORS.length] }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

function PieChartView({ data }) {
  let chartData = []

  if (data.labels && data.values) {
    chartData = data.labels.map((label, i) => ({
      name: String(label),
      value: data.values[i],
      fill: CHART_COLORS[i % CHART_COLORS.length]
    }))
  } else if (data.data && data.nameKey && data.valueKey) {
    chartData = data.data.map((item, i) => ({
      name: String(item[data.nameKey]),
      value: item[data.valueKey],
      fill: CHART_COLORS[i % CHART_COLORS.length]
    }))
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          labelLine={{ stroke: '#9e9589', strokeWidth: 1 }}
        >
          {chartData.map((entry, i) => (
            <Cell key={i} fill={entry.fill} />
          ))}
        </Pie>
        <Tooltip content={<CustomPieTooltip />} />
      </PieChart>
    </ResponsiveContainer>
  )
}

function ScatterChartView({ data }) {
  const chartData = data.x.map((xVal, i) => ({
    x: xVal,
    y: data.y[i],
    label: data.labels ? data.labels[i] : `Point ${i + 1}`
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis
          type="number"
          dataKey="x"
          name={data.x_title || 'X'}
          {...axisStyle}
        />
        <YAxis
          type="number"
          dataKey="y"
          name={data.y_title || 'Y'}
          {...axisStyle}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload || !payload.length) return null
            const d = payload[0].payload
            return (
              <div style={{
                background: 'rgba(250, 247, 242, 0.95)',
                border: '1px solid rgba(61, 54, 48, 0.15)',
                borderRadius: '8px',
                padding: '10px 14px',
                boxShadow: '0 4px 12px rgba(61, 54, 48, 0.1)',
                fontSize: '13px',
                color: '#3d3630'
              }}>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: '#5c544b' }}>{d.label}</div>
                <div>{data.x_title || 'X'}: {typeof d.x === 'number' ? d.x.toLocaleString() : d.x}</div>
                <div>{data.y_title || 'Y'}: {typeof d.y === 'number' ? d.y.toLocaleString() : d.y}</div>
              </div>
            )
          }}
        />
        <Scatter
          data={chartData}
          fill={CHART_COLORS[0]}
          r={5}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}

export default function ChartContainer({ type, data }) {
  if (!type || !data) return null

  return (
    <div style={{ width: '100%' }}>
      {type === 'bar' && <BarChartView data={data} />}
      {type === 'line' && <LineChartView data={data} />}
      {type === 'pie' && <PieChartView data={data} />}
      {type === 'scatter' && <ScatterChartView data={data} />}
    </div>
  )
}
