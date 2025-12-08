import React from 'react'
import './JobList.css'

function JobList({ jobs, selectedJob, onJobSelect }) {
  const formatDate = (dateString) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const getDisplayUrl = (job) => {
    if (job.crawl_mode && job.search_query) {
      return job.search_query
    }
    if (job.url) {
      try {
        const url = new URL(job.url)
        return url.hostname + (url.pathname !== '/' ? url.pathname : '')
      } catch {
        return job.url
      }
    }
    return 'Unknown'
  }

  return (
    <div className="job-list">
      <div className="job-list-header">
        <h2>Jobs</h2>
        <span>{jobs.length} total</span>
      </div>
      
      {jobs.length === 0 ? (
        <div className="job-list-empty">
          <p>No jobs yet</p>
        </div>
      ) : (
        <div className="job-list-items">
          {jobs.map((job) => (
            <div
              key={job.id}
              className={`job-item ${selectedJob?.id === job.id ? 'selected' : ''}`}
              onClick={() => onJobSelect(job)}
            >
              <div className="job-item-header">
                <span className="job-item-url">{getDisplayUrl(job)}</span>
                <span className={`job-status ${job.status}`}>{job.status}</span>
              </div>
              <div className="job-item-meta">
                <span>{formatDate(job.created_at)}</span>
                {job.crawl_mode && <span className="job-item-badge">Crawl</span>}
                {job.ai_prompt && <span className="job-item-badge">AI</span>}
              </div>
              {job.error && (
                <div className="job-item-error">
                  {job.error.length > 80 ? job.error.substring(0, 80) + '...' : job.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default JobList
