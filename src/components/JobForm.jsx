import React, { useState } from 'react'
import './JobForm.css'

function JobForm({ onJobCreated, apiUrl, setLoading }) {
  const [mode, setMode] = useState('html') // 'html', 'url', 'crawl', 'osm' - HTML first (most reliable free option)
  const [url, setUrl] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [rawHtml, setRawHtml] = useState('')
  const [aiPrompt, setAiPrompt] = useState('')
  const [exportFormat, setExportFormat] = useState('json')
  const [useJavascript, setUseJavascript] = useState(false)
  const [extractIndividualPages, setExtractIndividualPages] = useState(true)
  const [maxPages, setMaxPages] = useState(10)
  const [maxDepth, setMaxDepth] = useState(2)
  const [sameDomain, setSameDomain] = useState(true)
  const [osmLocation, setOsmLocation] = useState('')
  const [osmLimit, setOsmLimit] = useState(50)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    setLoading(true)

    try {
      if (mode === 'html') {
        // Parse HTML directly
        const response = await fetch(`${apiUrl}/parse-html`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            html: rawHtml,
            source_url: 'pasted-html',
            ai_prompt: aiPrompt || null,
            extract_individual_pages: extractIndividualPages,
          }),
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `Request failed (${response.status})`)
        }

        const result = await response.json()
        
        const fakeJob = {
          id: `html-${Date.now()}`,
          url: 'Pasted HTML',
          status: 'completed',
          created_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          ai_prompt: aiPrompt,
        }
        
        onJobCreated(fakeJob, {
          job_id: fakeJob.id,
          data: result.results || [result.data],
          total_items: result.total_items || 1,
          filtered_items: result.total_items || 1,
        })
        
        setRawHtml('')
        setAiPrompt('')
        setLoading(false)
        return
      }

      // OSM-only mode
      if (mode === 'osm') {
        const response = await fetch(`${apiUrl}/jobs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            osm_only: true,
            osm_location: osmLocation,
            osm_limit: osmLimit,
            export_format: exportFormat,
            ai_prompt: aiPrompt || null,
          }),
        })

        if (!response.ok) {
          let errorMessage = `Request failed (${response.status})`
          try {
            const contentType = response.headers.get('content-type')
            if (contentType && contentType.includes('application/json')) {
              const errorData = await response.json()
              errorMessage = errorData.detail || errorMessage
            }
          } catch {}
          throw new Error(errorMessage)
        }

        const job = await response.json()
        onJobCreated(job)

        setOsmLocation('')
        setOsmLimit(50)
        setAiPrompt('')
        return
      }

      // Regular URL or Crawl mode
      const response = await fetch(`${apiUrl}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: mode === 'url' ? url : null,
          search_query: mode === 'crawl' ? searchQuery : null,
          crawl_mode: mode === 'crawl',
          max_pages: mode === 'crawl' ? maxPages : null,
          max_depth: mode === 'crawl' ? maxDepth : null,
          same_domain: mode === 'crawl' ? sameDomain : null,
          ai_prompt: aiPrompt || null,
          export_format: exportFormat,
          use_javascript: useJavascript,
          extract_individual_pages: extractIndividualPages,
        }),
      })

      if (!response.ok) {
        let errorMessage = `Request failed (${response.status})`
        try {
          const contentType = response.headers.get('content-type')
          if (contentType && contentType.includes('application/json')) {
            const errorData = await response.json()
            errorMessage = errorData.detail || errorMessage
          }
        } catch {}
        throw new Error(errorMessage)
      }

      const job = await response.json()
      onJobCreated(job)

      setUrl('')
      setSearchQuery('')
      setAiPrompt('')
    } catch (err) {
      setError(err.message)
      setLoading(false)
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit = () => {
    if (submitting) return false
    if (mode === 'html') return rawHtml.length > 100
    if (mode === 'url') return !!url
    if (mode === 'crawl') return !!searchQuery
    if (mode === 'osm') return !!osmLocation
    return false
  }

  return (
    <div className="job-form">
      <h2>New Scraping Job</h2>
      
      <div className="mode-tabs">
        <button 
          type="button"
          className={`mode-tab recommended ${mode === 'html' ? 'active' : ''}`}
          onClick={() => setMode('html')}
          title="Most reliable - bypasses all anti-bot protection"
        >
          Paste HTML
        </button>
        <button 
          type="button"
          className={`mode-tab ${mode === 'url' ? 'active' : ''}`}
          onClick={() => setMode('url')}
          title="Direct URL scraping"
        >
          URL
        </button>
        <button 
          type="button"
          className={`mode-tab ${mode === 'crawl' ? 'active' : ''}`}
          onClick={() => setMode('crawl')}
          title="Multi-page crawling"
        >
          Crawl
        </button>
        <button 
          type="button"
          className={`mode-tab ${mode === 'osm' ? 'active' : ''}`}
          onClick={() => setMode('osm')}
          title="OpenStreetMap - Fast, free, no web scraping"
        >
          <span>OSM</span>
          <span style={{fontSize: '0.65em', marginLeft: '4px', color: mode === 'osm' ? '#fff' : '#4CAF50', fontWeight: '600'}}>FREE</span>
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        {mode === 'url' && (
          <div className="form-group">
            <label>Website URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              required
              disabled={submitting}
            />
          </div>
        )}

        {mode === 'osm' && (
          <>
            <div className="form-group">
              <label>Location <span style={{color: '#4CAF50'}}>(FREE - No API key needed)</span></label>
              <input
                type="text"
                value={osmLocation}
                onChange={(e) => setOsmLocation(e.target.value)}
                placeholder="Houston, TX or 29.7604,-95.3698"
                required
                disabled={submitting}
              />
              <small>City name, coordinates, or bounding box. Uses OpenStreetMap data only.</small>
            </div>

            <div className="form-group">
              <label>Max Results</label>
              <input
                type="number"
                value={osmLimit}
                onChange={(e) => setOsmLimit(parseInt(e.target.value) || 50)}
                min="1"
                max="200"
                disabled={submitting}
              />
              <small>Maximum number of steakhouses to retrieve (1-200)</small>
            </div>
          </>
        )}

        {mode === 'crawl' && (
          <>
            <div className="form-group">
              <label>Search Query or URL</label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="steakhouses in Houston, TX"
                required
                disabled={submitting}
              />
              <small>Enter a search term or starting URL</small>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Max Pages</label>
                <input
                  type="number"
                  value={maxPages}
                  onChange={(e) => setMaxPages(parseInt(e.target.value) || 10)}
                  min="1"
                  max="50"
                  disabled={submitting}
                />
              </div>
              <div className="form-group">
                <label>Max Depth</label>
                <input
                  type="number"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(parseInt(e.target.value) || 2)}
                  min="1"
                  max="5"
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="checkbox-group">
                <input
                  type="checkbox"
                  checked={sameDomain}
                  onChange={(e) => setSameDomain(e.target.checked)}
                  disabled={submitting}
                />
                <span>Same domain only</span>
              </label>
            </div>
          </>
        )}

        {mode === 'html' && (
          <div className="form-group">
            <label>Paste HTML Content</label>
            <div className="html-instructions">
              <div className="instruction-step">
                <span className="step-number">1</span>
                <span>Open the website in your browser (Yelp, OpenTable, Google Maps, etc.)</span>
              </div>
              <div className="instruction-step">
                <span className="step-number">2</span>
                <span>Press <kbd>Ctrl</kbd>+<kbd>U</kbd> (or right-click → View Page Source)</span>
              </div>
              <div className="instruction-step">
                <span className="step-number">3</span>
                <span>Press <kbd>Ctrl</kbd>+<kbd>A</kbd> to select all, then <kbd>Ctrl</kbd>+<kbd>C</kbd> to copy</span>
              </div>
              <div className="instruction-step">
                <span className="step-number">4</span>
                <span>Paste below and add an AI prompt to extract specific data</span>
              </div>
            </div>
            <textarea
              value={rawHtml}
              onChange={(e) => setRawHtml(e.target.value)}
              placeholder="Paste the HTML source code here..."
              disabled={submitting}
              className="html-input"
              rows={8}
            />
            <small className={rawHtml.length > 100 ? 'success' : ''}>
              {rawHtml.length > 0 
                ? `${rawHtml.length.toLocaleString()} characters ${rawHtml.length > 100 ? '- Ready to extract!' : '- Need more content'}` 
                : 'Works on ANY website - no bot detection possible'}
            </small>
          </div>
        )}

        {mode !== 'osm' && (
          <div className="form-group">
            <label>AI Extraction Prompt {mode === 'html' ? '(recommended)' : '(optional)'}</label>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder={mode === 'html' 
                ? "Extract all restaurant names, addresses, phone numbers, ratings, and prices as a list"
                : "Extract restaurant names, addresses, ratings..."
              }
              disabled={submitting}
            />
            <small>
              {mode === 'html' 
                ? 'Describe what data you want - AI will find and structure it for you'
                : 'Describe what data you want to extract'
              }
            </small>
          </div>
        )}

        {(mode === 'url' || mode === 'crawl' || mode === 'osm') && (
          <div className="form-row">
            <div className="form-group">
              <label>Export Format</label>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value)}
                disabled={submitting}
              >
                <option value="json">JSON</option>
                <option value="csv">CSV</option>
                <option value="excel">Excel</option>
              </select>
            </div>
            <div className="form-group">
              <label>&nbsp;</label>
              <label className="checkbox-group" style={{ height: '42px', display: 'flex' }}>
                <input
                  type="checkbox"
                  checked={useJavascript}
                  onChange={(e) => setUseJavascript(e.target.checked)}
                  disabled={submitting}
                />
                <span>JavaScript rendering</span>
              </label>
            </div>
          </div>
        )}

        {error && <div className="form-error">{error}</div>}

        {/* Extract from Individual Pages Option - Made More Visible */}
        {(mode === 'url' || mode === 'crawl' || mode === 'html') && (
          <div className="form-group extract-individual-pages-option">
            <div className="checkbox-highlight">
              <label className="checkbox-group">
                <input
                  type="checkbox"
                  checked={extractIndividualPages}
                  onChange={(e) => setExtractIndividualPages(e.target.checked)}
                  disabled={submitting}
                />
                <span>
                  <strong>🎯 Extract from individual pages</strong>
                  {mode === 'html' && ' (for restaurant listing pages)'}
                </span>
              </label>
              <small>
                {mode === 'html' 
                  ? '✅ DEFAULT: Visits each restaurant\'s individual page to get complete data (full addresses, all menu URLs, amenities, hours, etc.). Takes longer but gets everything. Uncheck to disable.'
                  : '✅ DEFAULT: Automatically extracts restaurant URLs from listing pages, then visits each individual page to get complete data (full addresses, all menu URLs, amenities, etc.). Uncheck to disable.'}
              </small>
            </div>
          </div>
        )}

        <button 
          type="submit" 
          className="submit-btn"
          disabled={!canSubmit()}
        >
          {submitting ? (
            <span className="spinner" />
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {mode === 'html' ? (
                  <path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>
                ) : mode === 'crawl' ? (
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                ) : (
                  <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9"/>
                )}
              </svg>
              {mode === 'html' ? 'Extract Data' : 
               mode === 'crawl' ? 'Start Crawling' :
               mode === 'osm' ? 'Search OSM' : 'Start Scraping'}
            </>
          )}
        </button>
      </form>
    </div>
  )
}

export default JobForm
