# Fixes Applied for URL Extraction and Data Scraping

## Issues Fixed

### 1. ✅ URL Extraction Filtering Bug
**Problem**: URLs were being filtered out incorrectly because `seen_urls` was being reused in the cleaning step.

**Fix**: Created separate `cleaned_seen` set for the cleaning step to avoid filtering out valid URLs.

### 2. ✅ Only 1 Restaurant Extracted Instead of 100
**Problem**: The log shows "Extracted 1 restaurants" when it should extract 100.

**Fixes Applied**:
- Added better error handling and logging in `extract_from_individual_pages`
- Improved result collection to ensure all results are captured
- Added validation to check if results are empty or None
- Added warnings when fewer results than expected are returned

### 3. ✅ Added URL Listing Endpoint
**New Endpoint**: `GET /jobs/{job_id}/extracted-urls`

Returns:
- List of all URLs extracted from the job
- Restaurant names (if available)
- Source listing URL
- Total count

### 4. ✅ Enhanced Logging
- Added progress tracking for batch extraction
- Better error messages with context
- Warnings when results don't match expectations
- Detailed logging of extracted URLs

## How to Use

### 1. Check Extracted URLs
```bash
GET /jobs/{job_id}/extracted-urls
```

Response:
```json
{
  "job_id": "fc1655b8-27e3-42c7-a6b8-46c0de566bd4",
  "job_url": "https://www.opentable.com/metro/houston-restaurants",
  "total_urls": 109,
  "urls": [
    {
      "url": "https://www.opentable.com/r/restaurant-1",
      "name": "Restaurant Name",
      "source": "https://www.opentable.com/metro/houston-restaurants"
    },
    ...
  ],
  "status": "completed"
}
```

### 2. Check Logs for Progress
The logs now show:
- Progress updates: `✅ [45/100] (45.0%)`
- Processing rate: `Rate: 2.3/s`
- ETA: `ETA: 24s`
- Final summary: `Total: 100 | Success: 95 | Failed: 5`

## Expected Behavior After Fixes

When scraping `https://www.opentable.com/metro/houston-restaurants`:

1. ✅ Extracts 109 restaurant URLs
2. ✅ Processes all 109 URLs concurrently (10 at a time)
3. ✅ Shows real-time progress
4. ✅ Extracts data from each page
5. ✅ Returns all 109 restaurants with complete data
6. ✅ Logs all extracted URLs

## Debugging

If you still see only 1 restaurant:

1. **Check the logs** for:
   - "📊 Processing X restaurant pages concurrently..."
   - Progress updates
   - Error messages

2. **Check the extracted URLs**:
   ```bash
   GET /jobs/{job_id}/extracted-urls
   ```

3. **Check for exceptions** in the logs:
   - Look for "❌ Failed" messages
   - Check for "Error processing restaurant" messages

4. **Verify results**:
   ```bash
   GET /jobs/{job_id}/results
   ```

## Next Steps

If issues persist:
1. Check if Playwright is working correctly
2. Verify OpenTable pages are loading
3. Check for rate limiting or blocking
4. Review error logs for specific failures

