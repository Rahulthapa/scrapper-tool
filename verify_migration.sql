-- Verification Script: Check if migration was successful
-- Run this FIRST to see what columns exist

-- Check all columns in scrape_jobs table
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'scrape_jobs'
ORDER BY ordinal_position;

-- Specifically check for new columns
SELECT 
    CASE 
        WHEN COUNT(*) = 7 THEN '✅ All new columns exist'
        ELSE '❌ Missing columns: ' || (7 - COUNT(*))::text || ' columns missing'
    END as migration_status
FROM information_schema.columns
WHERE table_name = 'scrape_jobs'
AND column_name IN ('crawl_mode', 'search_query', 'max_pages', 'max_depth', 'same_domain', 'use_javascript', 'extract_individual_pages');

-- Check each column individually (simple approach)
SELECT 'crawl_mode' as column_name, 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'crawl_mode') 
            THEN '✅ Exists' ELSE '❌ Missing' END as status
UNION ALL
SELECT 'search_query', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'search_query') 
            THEN '✅ Exists' ELSE '❌ Missing' END
UNION ALL
SELECT 'max_pages', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'max_pages') 
            THEN '✅ Exists' ELSE '❌ Missing' END
UNION ALL
SELECT 'max_depth', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'max_depth') 
            THEN '✅ Exists' ELSE '❌ Missing' END
UNION ALL
SELECT 'same_domain', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'same_domain') 
            THEN '✅ Exists' ELSE '❌ Missing' END
UNION ALL
SELECT 'use_javascript', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'use_javascript') 
            THEN '✅ Exists' ELSE '❌ Missing' END
UNION ALL
SELECT 'extract_individual_pages', 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'scrape_jobs' AND column_name = 'extract_individual_pages') 
            THEN '✅ Exists' ELSE '❌ Missing' END;

