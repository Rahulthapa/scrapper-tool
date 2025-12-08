# Fix: URLs Not Appearing in CSV

## Issues Identified

1. **Only 1 URL being scraped** instead of all individual restaurant URLs
2. **URLs in logs but not in CSV** - URLs are extracted but not making it to the CSV export

## Root Causes

### Issue 1: Individual Pages Not Being Visited
- The `extract_from_individual_pages` function might be failing silently
- Results might not be properly collected
- Only the listing page data is being saved

### Issue 2: CSV Export Not Handling Data Structure
- Nested data structures might not be flattened correctly
- URLs might be in nested objects that aren't being extracted
- The exporter might not be handling all data formats

## Fixes Applied

### 1. Enhanced Result Collection
- Added better error handling in `extract_from_individual_pages`
- Ensured URLs are always included even if scraping fails
- Added validation to ensure all results have URLs

### 2. Improved CSV Export
- Enhanced `_prepare_data_for_csv` to handle nested restaurant lists
- Added support for `extracted_url` field
- Better handling of missing URLs

### 3. Data Flattening in Export Endpoint
- Added logic to flatten nested structures before CSV export
- Handles cases where results are wrapped in `restaurants` arrays
- Extracts data from nested `data` fields

### 4. Better Logging
- Added debug logs to track:
  - How many results are being saved
  - How many have URLs
  - Data structure being exported

## Expected Behavior After Fix

1. **All 109 URLs extracted** from listing page
2. **All URLs included in CSV** even if scraping failed
3. **Data from each URL** included in CSV rows
4. **Proper flattening** of nested structures

## CSV Structure

Each row will have:
- `url` - The restaurant URL (always first column)
- All extracted data flattened into columns
- `source_listing_url` - Where the URL came from
- `scraping_status` - "success" or "failed" (if scraping failed)

## Debugging

If URLs still don't appear:

1. **Check logs** for:
   - "Saving X results for job"
   - "Results with URLs: X/Y"
   - "Items with URLs in export: X/Y"

2. **Check job results**:
   ```bash
   GET /jobs/{job_id}/results
   ```

3. **Check extracted URLs**:
   ```bash
   GET /jobs/{job_id}/extracted-urls
   ```

4. **Verify data structure**:
   - Each result should have a `url` field
   - Results should be a flat list, not nested

## Next Steps

After deployment, test with:
1. Create a new scraping job
2. Wait for completion
3. Export to CSV
4. Verify all URLs are present
5. Check that data from each URL is included

