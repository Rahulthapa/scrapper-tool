# Final Fix: URLs Not Appearing in CSV

## Problem

URLs are extracted and visible in log files, but they don't appear in the CSV export.

## Root Cause

The issue is that:
1. URLs ARE being extracted correctly (visible in logs: "Found 109 restaurant URLs")
2. But when `extract_from_individual_pages` is called, it might:
   - Return only 1 result (the listing page itself)
   - Fail silently and return empty results
   - Not properly collect all the results

3. Only the successfully scraped pages are saved, not all extracted URLs

## Fix Applied

### 1. Ensure ALL URLs Are Included
Even if individual page scraping fails, ALL extracted URLs are now included in results:

```python
# CRITICAL: Ensure ALL extracted URLs are included, even if scraping failed
existing_urls = {r.get('url', '').lower() for r in detailed_restaurants if r.get('url')}

# Add any missing URLs as entries (even if scraping failed)
for url in restaurant_urls:
    if url.lower() not in existing_urls:
        detailed_restaurants.append({
            'url': url,
            'source_listing_url': listing_url,
            'extracted_url': url,
            'scraping_status': 'not_scraped',
            'note': 'URL extracted from listing page but individual page not scraped'
        })
```

### 2. Enhanced Result Validation
Before saving, we now:
- Ensure all items are dicts
- Ensure all items have URLs
- Log which URLs are being saved
- Clean invalid items

### 3. Better Error Handling
If `extract_from_individual_pages` returns 0 results, we return all the extracted URLs anyway (so they appear in CSV).

## Expected Behavior

After this fix:

1. **All 109 URLs** extracted from listing page
2. **All 109 URLs** included in results (even if scraping failed)
3. **All 109 URLs** appear in CSV file
4. **Data from successfully scraped pages** included
5. **Failed pages** show `scraping_status: 'not_scraped'` or `'failed'`

## CSV Structure

Each row will have:
- `url` - The restaurant URL (always present)
- `source_listing_url` - Where it came from
- `scraping_status` - 'success', 'failed', or 'not_scraped'
- All extracted data (if scraping succeeded)
- `note` - Explanation if scraping failed

## Verification

After deployment, check:

1. **Logs show**: "Final results: 109 restaurants (from 109 extracted URLs)"
2. **CSV has**: 109 rows (one per URL)
3. **Each row has**: `url` column with the restaurant URL
4. **Some rows have**: Full data (if scraping succeeded)
5. **Some rows have**: Just URL + status (if scraping failed)

## Debugging

If URLs still don't appear:

1. Check logs for:
   - "Final results: X restaurants (from Y extracted URLs)"
   - "Results with URLs: X/Y"
   - "First 5 URLs being saved: [...]"

2. Check saved results:
   ```bash
   GET /jobs/{job_id}/results
   ```
   Should show all URLs in the data.

3. Check export:
   ```bash
   GET /jobs/{job_id}/export?format=csv
   ```
   Should download CSV with all URLs.

