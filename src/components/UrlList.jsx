import React, { useState, useEffect } from 'react'
import './UrlList.css'

function UrlList({ jobId, urls: initialUrls, API_BASE_URL, onScraped }) {
  const [urls, setUrls] = useState(initialUrls || [])
  const [selectedUrls, setSelectedUrls] = useState(new Set())
  const [scrapingUrls, setScrapingUrls] = useState(new Set())
  const [error, setError] = useState(null)

  // Update URLs when initialUrls changes
  useEffect(() => {
    if (initialUrls) {
      setUrls(initialUrls)
    }
  }, [initialUrls])

  // Poll for URL status updates
  useEffect(() => {
    if (!jobId) return

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/urls`)
        if (response.ok) {
          const data = await response.json()
          setUrls(data.urls)
        }
      } catch (err) {
        console.error('Error polling URLs:', err)
      }
    }, 3000) // Poll every 3 seconds

    return () => clearInterval(pollInterval)
  }, [jobId, API_BASE_URL])

  const handleSelectUrl = (url) => {
    const newSelected = new Set(selectedUrls)
    if (newSelected.has(url)) {
      newSelected.delete(url)
    } else {
      newSelected.add(url)
    }
    setSelectedUrls(newSelected)
  }

  const handleSelectAll = () => {
    const pendingUrls = urls.filter(u => u.status === 'pending').map(u => u.url)
    if (pendingUrls.every(url => selectedUrls.has(url))) {
      setSelectedUrls(new Set())
    } else {
      setSelectedUrls(new Set(pendingUrls))
    }
  }

  const handleScrapeSingle = async (url) => {
    if (scrapingUrls.has(url)) return

    setScrapingUrls(prev => new Set(prev).add(url))
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/scrape-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to scrape URL')
      }

      const result = await response.json()
      
      // Update local state
      setUrls(prevUrls =>
        prevUrls.map(u =>
          u.url === url
            ? { ...u, status: result.status, error_message: result.error_message }
            : u
        )
      )

      if (result.status === 'scraped' && onScraped) {
        onScraped(result)
      }
    } catch (err) {
      setError(err.message)
      setUrls(prevUrls =>
        prevUrls.map(u =>
          u.url === url
            ? { ...u, status: 'failed', error_message: err.message }
            : u
        )
      )
    } finally {
      setScrapingUrls(prev => {
        const newSet = new Set(prev)
        newSet.delete(url)
        return newSet
      })
    }
  }

  const handleScrapeSelected = async () => {
    if (selectedUrls.size === 0) return

    const urlsToScrape = Array.from(selectedUrls)
    setScrapingUrls(new Set(urlsToScrape))
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/scrape-urls`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ urls: urlsToScrape }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to scrape URLs')
      }

      const result = await response.json()
      
      // Update local state
      const scrapedUrls = new Set(result.scraped.map(r => r.url))
      const failedUrls = new Set(result.failed.map(r => r.url))
      
      setUrls(prevUrls =>
        prevUrls.map(u => {
          if (scrapedUrls.has(u.url)) {
            return { ...u, status: 'scraped' }
          } else if (failedUrls.has(u.url)) {
            const failed = result.failed.find(r => r.url === u.url)
            return { ...u, status: 'failed', error_message: failed?.error_message }
          }
          return u
        })
      )

      if (onScraped && result.scraped.length > 0) {
        result.scraped.forEach(scraped => onScraped(scraped))
      }

      setSelectedUrls(new Set())
    } catch (err) {
      setError(err.message)
    } finally {
      setScrapingUrls(new Set())
    }
  }

  const handleScrapeAll = async () => {
    const pendingUrls = urls.filter(u => u.status === 'pending').map(u => u.url)
    if (pendingUrls.length === 0) return

    setSelectedUrls(new Set(pendingUrls))
    await handleScrapeSelected()
  }

  const handleExport = async (format) => {
    if (!jobId || scrapedCount === 0) return

    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/export?format=${format}`)
      if (!response.ok) {
        throw new Error('Export failed')
      }
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `scraped_restaurants_${jobId}.${format === 'excel' ? 'xlsx' : format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Export error:', error)
      setError(`Failed to export: ${error.message}`)
    }
  }

  const getStatusBadge = (status) => {
    const badges = {
      pending: { text: 'Pending', class: 'badge-pending' },
      scraping: { text: 'Scraping...', class: 'badge-scraping' },
      scraped: { text: 'Scraped', class: 'badge-scraped' },
      failed: { text: 'Failed', class: 'badge-failed' },
    }
    const badge = badges[status] || badges.pending
    return <span className={`status-badge ${badge.class}`}>{badge.text}</span>
  }

  const pendingCount = urls.filter(u => u.status === 'pending').length
  const scrapedCount = urls.filter(u => u.status === 'scraped').length
  const failedCount = urls.filter(u => u.status === 'failed').length

  return (
    <div className="url-list">
      <div className="url-list-header">
        <h2>Extracted Restaurant URLs</h2>
        <div className="stats">
          <span className="stat">Total: {urls.length}</span>
          <span className="stat pending">Pending: {pendingCount}</span>
          <span className="stat scraped">Scraped: {scrapedCount}</span>
          {failedCount > 0 && <span className="stat failed">Failed: {failedCount}</span>}
        </div>
      </div>

      {scrapedCount > 0 && (
        <div className="export-section">
          <h3>Export Scraped Data ({scrapedCount} restaurants)</h3>
          <div className="export-buttons">
            <button 
              className="export-btn" 
              onClick={() => handleExport('json')}
              title="Export as JSON"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              JSON
            </button>
            <button 
              className="export-btn" 
              onClick={() => handleExport('csv')}
              title="Export as CSV"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              CSV
            </button>
            <button 
              className="export-btn" 
              onClick={() => handleExport('excel')}
              title="Export as Excel"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              Excel
            </button>
          </div>
        </div>
      )}

      <div className="url-list-actions">
        <button
          onClick={handleScrapeAll}
          disabled={pendingCount === 0 || scrapingUrls.size > 0}
          className="action-button scrape-all"
        >
          Scrape All ({pendingCount})
        </button>
        <button
          onClick={handleScrapeSelected}
          disabled={selectedUrls.size === 0 || scrapingUrls.size > 0}
          className="action-button scrape-selected"
        >
          Scrape Selected ({selectedUrls.size})
        </button>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <div className="urls-table-container">
        <table className="urls-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={pendingCount > 0 && urls.filter(u => u.status === 'pending').every(u => selectedUrls.has(u.url))}
                  onChange={handleSelectAll}
                  disabled={pendingCount === 0}
                />
              </th>
              <th>URL</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {urls.map((urlItem, index) => (
              <tr key={index} className={urlItem.status === 'scraped' ? 'row-scraped' : ''}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedUrls.has(urlItem.url)}
                    onChange={() => handleSelectUrl(urlItem.url)}
                    disabled={urlItem.status !== 'pending'}
                  />
                </td>
                <td className="url-cell">
                  <a href={urlItem.url} target="_blank" rel="noopener noreferrer">
                    {urlItem.url}
                  </a>
                </td>
                <td>
                  {getStatusBadge(urlItem.status)}
                  {urlItem.error_message && (
                    <div className="error-tooltip" title={urlItem.error_message}>
                      ⚠️
                    </div>
                  )}
                </td>
                <td>
                  {urlItem.status === 'pending' && (
                    <button
                      onClick={() => handleScrapeSingle(urlItem.url)}
                      disabled={scrapingUrls.has(urlItem.url)}
                      className="scrape-button"
                    >
                      {scrapingUrls.has(urlItem.url) ? 'Scraping...' : 'Scrape'}
                    </button>
                  )}
                  {urlItem.status === 'scraped' && (
                    <button disabled className="scrape-button scraped">
                      Scraped
                    </button>
                  )}
                  {urlItem.status === 'failed' && (
                    <button
                      onClick={() => handleScrapeSingle(urlItem.url)}
                      disabled={scrapingUrls.has(urlItem.url)}
                      className="scrape-button retry"
                    >
                      {scrapingUrls.has(urlItem.url) ? 'Retrying...' : 'Retry'}
                    </button>
                  )}
                  {urlItem.status === 'scraping' && (
                    <button disabled className="scrape-button">
                      Scraping...
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {urls.length === 0 && (
        <div className="empty-state">
          <p>No URLs extracted yet. Please extract URLs from a listing page first.</p>
        </div>
      )}
    </div>
  )
}

export default UrlList

