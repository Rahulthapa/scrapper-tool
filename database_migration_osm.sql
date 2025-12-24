-- Migration: Add OSM-only mode columns to scrape_jobs table
-- Run this in your Supabase SQL Editor
-- After running, refresh the schema cache in Supabase Dashboard:
-- Settings → API → Schema Cache → "Clear Cache"

-- Step 1: Add new columns for OSM-only functionality
ALTER TABLE scrape_jobs 
ADD COLUMN IF NOT EXISTS osm_only BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS osm_location TEXT,
ADD COLUMN IF NOT EXISTS osm_limit INTEGER DEFAULT 50;

-- Step 2: Verify columns were added
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'scrape_jobs'
AND column_name IN ('osm_only', 'osm_location', 'osm_limit')
ORDER BY column_name;

-- Step 3: Add comments for documentation
COMMENT ON COLUMN scrape_jobs.osm_only IS 'Use only OpenStreetMap Overpass API (no web scraping)';
COMMENT ON COLUMN scrape_jobs.osm_location IS 'Location for OSM search (city name, coordinates, or bounding box)';
COMMENT ON COLUMN scrape_jobs.osm_limit IS 'Maximum number of results from OSM (default: 50, max: 200)';

-- Step 4: Verify the migration
SELECT 
    'OSM columns added successfully' as status,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_name = 'scrape_jobs' 
     AND column_name IN ('osm_only', 'osm_location', 'osm_limit')) as columns_added;

