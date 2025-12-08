-- Migration: Add web crawling columns to scrape_jobs table
-- Run this in your Supabase SQL Editor

-- Step 1: Add new columns for web crawling functionality
ALTER TABLE scrape_jobs 
ADD COLUMN IF NOT EXISTS crawl_mode BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS search_query TEXT,
ADD COLUMN IF NOT EXISTS max_pages INTEGER DEFAULT 10,
ADD COLUMN IF NOT EXISTS max_depth INTEGER DEFAULT 2,
ADD COLUMN IF NOT EXISTS same_domain BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS use_javascript BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS extract_individual_pages BOOLEAN DEFAULT TRUE;

-- Step 2: Make url nullable since it's optional in crawl mode
-- Check if column exists and is NOT NULL first
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

-- Step 3: Refresh PostgREST schema cache (if you have permissions)
-- Note: This might not work on managed Supabase - use dashboard instead
-- NOTIFY pgrst, 'reload schema';

-- Step 4: Verify columns were added
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns
WHERE table_name = 'scrape_jobs'
AND column_name IN ('crawl_mode', 'search_query', 'max_pages', 'max_depth', 'same_domain', 'use_javascript', 'extract_individual_pages')
ORDER BY column_name;

-- Add comments for documentation
COMMENT ON COLUMN scrape_jobs.crawl_mode IS 'Enable web crawling mode to discover and scrape multiple pages';
COMMENT ON COLUMN scrape_jobs.search_query IS 'Search query for finding pages to crawl (also used for Google Maps searches)';
COMMENT ON COLUMN scrape_jobs.max_pages IS 'Maximum number of pages to crawl';
COMMENT ON COLUMN scrape_jobs.max_depth IS 'Maximum depth of links to follow';
COMMENT ON COLUMN scrape_jobs.same_domain IS 'Only crawl pages on the same domain';
COMMENT ON COLUMN scrape_jobs.use_javascript IS 'Use Playwright for JavaScript-rendered pages';
COMMENT ON COLUMN scrape_jobs.extract_individual_pages IS 'Extract data from individual restaurant pages (default: true for restaurant listings)';

