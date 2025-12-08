-- =====================================================
-- Complete Supabase Database Setup for Web Scraper
-- Run this entire script in Supabase SQL Editor
-- =====================================================

-- Step 1: Create scrape_jobs table (if it doesn't exist)
CREATE TABLE IF NOT EXISTS scrape_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT,  -- Nullable for keyword search mode
  status TEXT NOT NULL DEFAULT 'pending',
  filters JSONB,
  ai_prompt TEXT,
  export_format TEXT DEFAULT 'json',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE,
  error TEXT
);

-- Step 2: Create scrape_results table (if it doesn't exist)
CREATE TABLE IF NOT EXISTS scrape_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES scrape_jobs(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Step 3: Add new columns for web crawling functionality (if they don't exist)
DO $$ 
BEGIN
    -- Add crawl_mode
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'crawl_mode'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN crawl_mode BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Add search_query
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'search_query'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN search_query TEXT;
    END IF;
    
    -- Add max_pages
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'max_pages'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN max_pages INTEGER DEFAULT 10;
    END IF;
    
    -- Add max_depth
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'max_depth'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN max_depth INTEGER DEFAULT 2;
    END IF;
    
    -- Add same_domain
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'same_domain'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN same_domain BOOLEAN DEFAULT TRUE;
    END IF;
    
    -- Add use_javascript
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' AND column_name = 'use_javascript'
    ) THEN
        ALTER TABLE scrape_jobs ADD COLUMN use_javascript BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Step 4: Make url nullable (if it's currently NOT NULL)
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'scrape_jobs' 
        AND column_name = 'url' 
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE scrape_jobs ALTER COLUMN url DROP NOT NULL;
    END IF;
END $$;

-- Step 5: Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_scrape_results_job_id ON scrape_results(job_id);
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status ON scrape_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_created_at ON scrape_jobs(created_at);

-- Step 6: Add column comments for documentation
COMMENT ON COLUMN scrape_jobs.crawl_mode IS 'Enable web crawling mode to discover and scrape multiple pages';
COMMENT ON COLUMN scrape_jobs.search_query IS 'Search query for finding pages to crawl or keyword-based searches';
COMMENT ON COLUMN scrape_jobs.max_pages IS 'Maximum number of pages to crawl or scrape';
COMMENT ON COLUMN scrape_jobs.max_depth IS 'Maximum depth of links to follow (for crawl mode)';
COMMENT ON COLUMN scrape_jobs.same_domain IS 'Only crawl pages on the same domain (for crawl mode)';
COMMENT ON COLUMN scrape_jobs.use_javascript IS 'Use Playwright for JavaScript-rendered pages';

-- Step 7: Verify the setup
SELECT 
    'Tables created successfully' as status,
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scrape_jobs') as scrape_jobs_exists,
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scrape_results') as scrape_results_exists;

-- Step 8: Show all columns in scrape_jobs table
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'scrape_jobs'
ORDER BY ordinal_position;

-- =====================================================
-- IMPORTANT: After running this script, refresh the 
-- PostgREST schema cache in Supabase Dashboard:
-- Settings → API → Schema Cache → "Clear Cache"
-- Wait 30-60 seconds for the cache to refresh
-- =====================================================

