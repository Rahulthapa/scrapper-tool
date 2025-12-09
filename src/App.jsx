import React, { useState } from 'react'
import JobForm from './components/JobForm'
import JobList from './components/JobList'
import ResultsView from './components/ResultsView'
import UrlExtractionView from './components/UrlExtractionView'
import UrlList from './components/UrlList'
import './App.css'

function App() {
  const [mode, setMode] = useState('standard') // 'standard' or 'selective'
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [urlExtractionJobId, setUrlExtractionJobId] = useState(null)
  const [extractedUrls, setExtractedUrls] = useState([])

  const API_BASE_URL = import.meta.env.VITE_API_URL || 
    (import.meta.env.PROD ? '' : 'http://localhost:8000')

  const handleJobCreated = (newJob, directResults = null) => {
    setJobs([newJob, ...jobs])
    setSelectedJob(newJob)
    
    if (directResults) {
      // HTML parsing returns results directly
      setResults(directResults)
      setLoading(false)
    } else {
      setResults(null)
      pollJobStatus(newJob.id)
    }
  }

  const pollJobStatus = async (jobId) => {
    const maxAttempts = 120
    let attempts = 0

    const poll = async () => {
      if (attempts >= maxAttempts) {
        setLoading(false)
        setJobs(prev => prev.map(j => 
          j.id === jobId ? { ...j, status: 'timeout', error: 'Job timed out' } : j
        ))
        return
      }

      try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const job = await response.json()

        setJobs(prev => prev.map(j => j.id === jobId ? job : j))
        setSelectedJob(job)

        if (job.status === 'completed') {
          await fetchResults(jobId)
        } else if (job.status === 'failed') {
          setLoading(false)
        } else {
          attempts++
          setTimeout(poll, 3000)
        }
      } catch (error) {
        attempts++
        if (attempts < maxAttempts) {
          setTimeout(poll, 5000)
        } else {
          setLoading(false)
        }
      }
    }

    poll()
  }

  const fetchResults = async (jobId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/results`)
      if (response.ok) {
        const data = await response.json()
        setResults(data)
      }
    } catch (error) {
      console.error('Error fetching results:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleJobSelect = async (job) => {
    setSelectedJob(job)
    setResults(null)

    if (job.status === 'completed') {
      setLoading(true)
      await fetchResults(job.id)
    } else if (job.status === 'pending' || job.status === 'running') {
      setLoading(true)
      pollJobStatus(job.id)
    }
  }

  const handleExport = async (format) => {
    if (!selectedJob) return

    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${selectedJob.id}/export?format=${format}`)
      if (!response.ok) {
        throw new Error('Export failed')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `scrape_results_${selectedJob.id}.${format === 'excel' ? 'xlsx' : format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Export error:', error)
      alert('Failed to export results')
    }
  }

  const handleUrlsExtracted = (jobId, urls) => {
    setUrlExtractionJobId(jobId)
    setExtractedUrls(urls)
    // Create a fake job for the job list
    const fakeJob = {
      id: jobId,
      url: 'URL Extraction',
      status: 'completed',
      created_at: new Date().toISOString(),
    }
    setJobs([fakeJob, ...jobs])
    setSelectedJob(fakeJob)
  }

  const handleUrlScraped = (result) => {
    // Update extracted URLs state
    setExtractedUrls(prev =>
      prev.map(u =>
        u.url === result.url
          ? { ...u, status: result.status }
          : u
      )
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-brand">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2a10 10 0 0 1 10 10"/>
            <path d="M12 2a10 10 0 0 0-10 10"/>
            <circle cx="12" cy="12" r="4"/>
          </svg>
          <h1>Web Scraper</h1>
        </div>
        <span className="header-tagline">AI-powered data extraction</span>
      </header>

      <div className="mode-switcher">
        <button
          className={mode === 'standard' ? 'active' : ''}
          onClick={() => setMode('standard')}
        >
          Standard Scraping
        </button>
        <button
          className={mode === 'selective' ? 'active' : ''}
          onClick={() => setMode('selective')}
        >
          Selective URL Scraping
        </button>
      </div>

      <div className="app-content">
        {mode === 'selective' ? (
          <>
            <div className="left-panel">
              <UrlExtractionView
                onUrlsExtracted={handleUrlsExtracted}
                API_BASE_URL={API_BASE_URL}
              />
            </div>
            <div className="right-panel">
              {urlExtractionJobId && extractedUrls.length > 0 ? (
                <UrlList
                  jobId={urlExtractionJobId}
                  urls={extractedUrls}
                  API_BASE_URL={API_BASE_URL}
                  onScraped={handleUrlScraped}
                />
              ) : (
                <div className="empty-state-container">
                  <div className="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/>
                      <rect x="9" y="3" width="6" height="4" rx="1"/>
                      <path d="M9 12h6M9 16h6"/>
                    </svg>
                    <p>Extract URLs from a listing page to get started</p>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="left-panel">
              <JobForm 
                onJobCreated={handleJobCreated}
                apiUrl={API_BASE_URL}
                setLoading={setLoading}
              />
              <JobList
                jobs={jobs}
                selectedJob={selectedJob}
                onJobSelect={handleJobSelect}
              />
            </div>

            <div className="right-panel">
              {selectedJob ? (
                <ResultsView
                  job={selectedJob}
                  results={results}
                  loading={loading}
                  onExport={handleExport}
                />
              ) : (
                <div className="empty-state-container">
                  <div className="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/>
                      <rect x="9" y="3" width="6" height="4" rx="1"/>
                      <path d="M9 12h6M9 16h6"/>
                    </svg>
                    <p>Create a scraping job to get started</p>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default App
