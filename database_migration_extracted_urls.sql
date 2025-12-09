-- Migration: Add extracted_urls table for selective URL scraping workflow
-- This table tracks restaurant URLs extracted from listing pages and their scrape status

CREATE TABLE IF NOT EXISTS extracted_urls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES scrape_jobs(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'scraping', 'scraped', 'failed')),
  scraped_at TIMESTAMP,
  data JSONB,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(job_id, url)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_extracted_urls_job_id ON extracted_urls(job_id);
CREATE INDEX IF NOT EXISTS idx_extracted_urls_status ON extracted_urls(status);
CREATE INDEX IF NOT EXISTS idx_extracted_urls_url ON extracted_urls(url);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_extracted_urls_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
CREATE TRIGGER update_extracted_urls_timestamp
  BEFORE UPDATE ON extracted_urls
  FOR EACH ROW
  EXECUTE FUNCTION update_extracted_urls_updated_at();

-- Comments for documentation
COMMENT ON TABLE extracted_urls IS 'Tracks restaurant URLs extracted from listing pages with their scrape status';
COMMENT ON COLUMN extracted_urls.job_id IS 'Foreign key to scrape_jobs table';
COMMENT ON COLUMN extracted_urls.url IS 'Restaurant URL extracted from listing page';
COMMENT ON COLUMN extracted_urls.status IS 'Scrape status: pending, scraping, scraped, or failed';
COMMENT ON COLUMN extracted_urls.data IS 'Scraped data stored as JSON';
COMMENT ON COLUMN extracted_urls.scraped_at IS 'Timestamp when URL was successfully scraped';

