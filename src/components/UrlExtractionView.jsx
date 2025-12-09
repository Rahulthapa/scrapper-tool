import React, { useState } from 'react'
import './UrlExtractionView.css'

function UrlExtractionView({ onUrlsExtracted, API_BASE_URL }) {
  const [listingUrl, setListingUrl] = useState('')
  const [useJavascript, setUseJavascript] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [jobId, setJobId] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setJobId(null)

    try {
      const response = await fetch(`${API_BASE_URL}/jobs/extract-urls`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          listing_url: listingUrl,
          use_javascript: useJavascript,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to extract URLs')
      }

      const data = await response.json()
      setJobId(data.job_id)
      
      // Poll for URLs
      pollForUrls(data.job_id)
      
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const pollForUrls = async (jobId) => {
    const maxAttempts = 60
    let attempts = 0

    const poll = async () => {
      if (attempts >= maxAttempts) {
        setError('URL extraction timed out')
        setLoading(false)
        return
      }

      try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/urls`)
        if (!response.ok) {
          throw new Error('Failed to fetch URLs')
        }

        const data = await response.json()
        
        // Check if extraction is complete (job status)
        const jobResponse = await fetch(`${API_BASE_URL}/jobs/${jobId}`)
        if (jobResponse.ok) {
          const job = await jobResponse.json()
          
          if (job.status === 'completed' && data.urls.length > 0) {
            // Extraction complete
            setLoading(false)
            if (onUrlsExtracted) {
              onUrlsExtracted(jobId, data.urls)
            }
            return
          } else if (job.status === 'failed') {
            setError(job.error || 'URL extraction failed')
            setLoading(false)
            return
          }
        }

        // Continue polling
        attempts++
        setTimeout(poll, 2000) // Poll every 2 seconds
        
      } catch (err) {
        setError(err.message)
        setLoading(false)
      }
    }

    poll()
  }

  return (
    <div className="url-extraction-view">
      <h2>Extract Restaurant URLs</h2>
      <p className="description">
        Enter a listing page URL (e.g., OpenTable metro/region page) to extract all restaurant URLs.
        The URLs will be displayed for you to select which ones to scrape.
      </p>

      <form onSubmit={handleSubmit} className="extraction-form">
        <div className="form-group">
          <label htmlFor="listingUrl">Listing Page URL</label>
          <input
            type="url"
            id="listingUrl"
            value={listingUrl}
            onChange={(e) => setListingUrl(e.target.value)}
            placeholder="https://www.opentable.com/metro/chicago-restaurants"
            required
            disabled={loading}
          />
        </div>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={useJavascript}
              onChange={(e) => setUseJavascript(e.target.checked)}
              disabled={loading}
            />
            Use JavaScript (Playwright) - Recommended for dynamic pages
          </label>
        </div>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        {loading && (
          <div className="loading-message">
            <div className="spinner"></div>
            <p>Extracting URLs from listing page... This may take a minute.</p>
            {jobId && <p className="job-id">Job ID: {jobId}</p>}
          </div>
        )}

        <button type="submit" disabled={loading || !listingUrl} className="submit-button">
          {loading ? 'Extracting...' : 'Extract URLs'}
        </button>
      </form>
    </div>
  )
}

export default UrlExtractionView

