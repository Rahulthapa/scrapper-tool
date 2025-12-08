import React, { useState, useMemo } from 'react'
import './ResultsView.css'

function ResultsView({ job, results, loading, onExport }) {
  const [viewMode, setViewMode] = useState('table') // 'table' or 'json'

  // Check if this is a local result (from HTML paste)
  const isLocalResult = job?.id?.startsWith('html-')

  // Download functions for local results
  const downloadJSON = () => {
    if (!results?.data) return
    const blob = new Blob([JSON.stringify(results.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `scrape_results_${job.id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadCSV = () => {
    if (!results?.data || results.data.length === 0) return
    
    // Flatten objects for CSV
    const flattenObj = (obj, prefix = '') => {
      const result = {}
      for (const key in obj) {
        const value = obj[key]
        const newKey = prefix ? `${prefix}.${key}` : key
        if (value === null || value === undefined) {
          result[newKey] = ''
        } else if (typeof value === 'object' && !Array.isArray(value)) {
          Object.assign(result, flattenObj(value, newKey))
        } else if (Array.isArray(value)) {
          result[newKey] = value.join('; ')
        } else {
          result[newKey] = String(value)
        }
      }
      return result
    }

    const flatData = results.data.map(item => flattenObj(item))
    const headers = [...new Set(flatData.flatMap(obj => Object.keys(obj)))]
    
    const csvRows = [
      headers.join(','),
      ...flatData.map(row => 
        headers.map(h => {
          const val = row[h] || ''
          // Escape quotes and wrap in quotes if contains comma
          const escaped = String(val).replace(/"/g, '""')
          return escaped.includes(',') || escaped.includes('\n') ? `"${escaped}"` : escaped
        }).join(',')
      )
    ]
    
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `scrape_results_${job.id}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExport = (format) => {
    if (isLocalResult) {
      // Local results - download directly
      if (format === 'json') downloadJSON()
      else if (format === 'csv') downloadCSV()
      else if (format === 'excel') downloadCSV() // Fallback to CSV for Excel
    } else {
      // Server results - use API
      onExport(format)
    }
  }

  const formatDate = (dateString) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleString()
  }

  const getDisplayUrl = (job) => {
    if (job.crawl_mode && job.search_query) {
      return job.search_query
    }
    return job.url || '-'
  }

  // Flatten nested objects for table view
  const flattenObject = (obj, prefix = '') => {
    const result = {}
    for (const key in obj) {
      const value = obj[key]
      const newKey = prefix ? `${prefix}.${key}` : key
      
      if (value === null || value === undefined) {
        result[newKey] = ''
      } else if (typeof value === 'object' && !Array.isArray(value)) {
        Object.assign(result, flattenObject(value, newKey))
      } else if (Array.isArray(value)) {
        result[newKey] = value.length > 0 ? 
          (typeof value[0] === 'object' ? `[${value.length} items]` : value.join(', ')) 
          : ''
      } else {
        result[newKey] = String(value)
      }
    }
    return result
  }

  // Process data for table view
  const tableData = useMemo(() => {
    if (!results?.data || results.data.length === 0) return { headers: [], rows: [] }

    // Flatten all objects
    const flattenedRows = results.data.map(item => flattenObject(item))
    
    // Get all unique keys as headers
    const headerSet = new Set()
    flattenedRows.forEach(row => {
      Object.keys(row).forEach(key => headerSet.add(key))
    })
    
    // Prioritize important columns
    const priorityColumns = ['title', 'name', 'url', 'price', 'address', 'email', 'phone']
    const headers = [...headerSet].sort((a, b) => {
      const aLower = a.toLowerCase()
      const bLower = b.toLowerCase()
      const aIndex = priorityColumns.findIndex(p => aLower.includes(p))
      const bIndex = priorityColumns.findIndex(p => bLower.includes(p))
      if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex
      if (aIndex !== -1) return -1
      if (bIndex !== -1) return 1
      return a.localeCompare(b)
    })

    // Limit to first 15 columns for readability
    const limitedHeaders = headers.slice(0, 15)

    return {
      headers: limitedHeaders,
      rows: flattenedRows,
      totalColumns: headers.length
    }
  }, [results])

  if (loading) {
    return (
      <div className="results-view">
        <div className="results-header">
          <h2>Processing</h2>
        </div>
        <div className="loading-state">
          <div className="loading-spinner" />
          <p>Scraping in progress...</p>
        </div>
      </div>
    )
  }

  const hasData = results?.data && results.data.length > 0

  return (
    <div className="results-view">
      <div className="results-header">
        <h2>Job Results</h2>
        {job.status === 'completed' && hasData && (
          <div className="export-buttons">
            <button className="export-btn" onClick={() => handleExport('json')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              JSON
            </button>
            <button className="export-btn" onClick={() => handleExport('csv')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              CSV
            </button>
            <button className="export-btn" onClick={() => handleExport('excel')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              Excel
            </button>
          </div>
        )}
      </div>

      <div className="results-info">
        <div className="info-item">
          <span className="info-label">Status</span>
          <span className="info-value status">
            <span className={`status-dot ${job.status}`} />
            {job.status}
          </span>
        </div>
        <div className="info-item">
          <span className="info-label">Target</span>
          <span className="info-value">{getDisplayUrl(job)}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Created</span>
          <span className="info-value">{formatDate(job.created_at)}</span>
        </div>
        {job.completed_at && (
          <div className="info-item">
            <span className="info-label">Completed</span>
            <span className="info-value">{formatDate(job.completed_at)}</span>
          </div>
        )}
        {job.ai_prompt && (
          <div className="info-item">
            <span className="info-label">AI Prompt</span>
            <span className="info-value">{job.ai_prompt}</span>
          </div>
        )}
      </div>

      {job.error && (
        <div className="error-banner">
          <strong>Error:</strong> {job.error}
        </div>
      )}

      <div className="results-content">
        {job.status === 'completed' && results ? (
          hasData ? (
            <>
              <div className="view-toggle">
                <button 
                  className={`toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
                  onClick={() => setViewMode('table')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                    <path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>
                  </svg>
                  Table View
                </button>
                <button 
                  className={`toggle-btn ${viewMode === 'json' ? 'active' : ''}`}
                  onClick={() => setViewMode('json')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>
                  </svg>
                  JSON View
                </button>
                <span className="data-count">{results.data.length} items</span>
              </div>

              {viewMode === 'table' ? (
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="row-num">#</th>
                        {tableData.headers.map((header, i) => (
                          <th key={i}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {tableData.rows.map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          <td className="row-num">{rowIndex + 1}</td>
                          {tableData.headers.map((header, colIndex) => (
                            <td key={colIndex} title={row[header] || ''}>
                              {row[header] ? (
                                row[header].length > 100 
                                  ? row[header].substring(0, 100) + '...' 
                                  : row[header]
                              ) : '-'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {tableData.totalColumns > 15 && (
                    <div className="table-note">
                      Showing 15 of {tableData.totalColumns} columns. Download CSV/Excel for full data.
                    </div>
                  )}
                </div>
              ) : (
                <div className="results-data">
                  <pre className="results-json">
                    {JSON.stringify(results.data, null, 2)}
                  </pre>
                </div>
              )}
            </>
          ) : (
            <div className="no-results">No data found</div>
          )
        ) : job.status === 'pending' ? (
          <div className="status-message">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
            <p>Job is queued and will start shortly</p>
          </div>
        ) : job.status === 'running' ? (
          <div className="status-message">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            <p>Scraping in progress...</p>
          </div>
        ) : job.status === 'failed' ? (
          <div className="status-message">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M15 9l-6 6M9 9l6 6"/>
            </svg>
            <p>Job failed - check error message above</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default ResultsView
