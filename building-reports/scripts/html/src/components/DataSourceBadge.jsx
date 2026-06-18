import React from 'react'

export default function DataSourceBadge({ model }) {
  if (!model) return null

  return (
    <span className="badge-accent">
      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ marginRight: '4px' }}
      >
        <ellipse cx="6" cy="3" rx="4" ry="1.5" stroke="currentColor" strokeWidth="1.2" fill="none" />
        <path d="M2 3v3c0 .83 1.79 1.5 4 1.5s4-.67 4-1.5V3" stroke="currentColor" strokeWidth="1.2" fill="none" />
        <path d="M2 6v3c0 .83 1.79 1.5 4 1.5s4-.67 4-1.5V6" stroke="currentColor" strokeWidth="1.2" fill="none" />
      </svg>
      {model}
    </span>
  )
}
