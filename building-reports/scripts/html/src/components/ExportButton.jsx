import React from 'react'

export default function ExportButton({ onClick }) {
  return (
    <button className="btn-primary no-print" onClick={onClick}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ marginRight: '8px' }}
      >
        <path
          d="M8 2v8M8 10l-2.5-2.5M8 10l2.5-2.5M3 12v1.5h10V12"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      导出 PDF
    </button>
  )
}
