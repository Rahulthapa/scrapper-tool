# Troubleshooting: Scraper Not Visiting Individual Pages

## Problem

The scraper is not visiting individual restaurant pages from OpenTable listing pages. The log shows:
- `Is listing page: False` for `https://www.opentable.com/metro/houston-restaurants`
- Only scraping the listing page itself, not individual restaurant pages

## Root Cause

The listing page detection is failing because the URL pattern matching isn't working correctly.

## Solution Applied

### 1. Fixed Listing Page Detection

Updated `_is_restaurant_listing_page()` in `app/worker.py` to:
- Use simple string matching for OpenTable URLs (more reliable than regex)
- Check for `/metro/`, `/region/`, `/neighborhood/` patterns
- Default to treating OpenTable URLs as listings if they don't have `/r/` (restaurant page indicator)

### 2. Enhanced URL Extraction

Improved `extract_restaurant_urls_from_listing()` in `app/scraper.py` to:
- Better extract OpenTable restaurant URLs from metro/region pages
- Use multiple methods: BeautifulSoup, JavaScript evaluation, data attributes
- Look for restaurant cards and links in OpenTable-specific structures

### 3. Added Comprehensive Logging

Added detailed logging to track:
- Listing page detection results
- URL extraction process
- Each individual page visit
- Section extraction from each page

## How to Verify It's Working

### Check the Logs

After running a scraping job, check the log file for:

1. **Listing Detection**:
   ```
   [RESTAURANT] URL: ... | Step: PAGE_TYPE | Is listing page: True
   ```

2. **URL Extraction**:
   ```
   [LISTING] URL: ... | Found X restaurant URLs
   [LISTING]   1. https://www.opentable.com/r/restaurant-1
   [LISTING]   2. https://www.opentable.com/r/restaurant-2
   ```

3. **Individual Page Visits**:
   ```
   [URL VISIT] STARTED | Method: GET | URL: https://www.opentable.com/r/restaurant-1
   [SECTION] STARTED | URL: ... | Section: OVERVIEW
   [SECTION] STARTED | URL: ... | Section: DETAILS
   ```

### Test Detection

Use the debug endpoint:
```bash
GET /debug/listing-detection?url=https://www.opentable.com/metro/houston-restaurants
```

This will show:
- Whether the URL is detected as a listing page
- Detection logic details
- Recommendation

## Expected Behavior

When you provide an OpenTable listing URL like:
- `https://www.opentable.com/metro/houston-restaurants`
- `https://www.opentable.com/region/houston/houston-restaurants`

The scraper should:

1. **Detect it as a listing page** ✅
2. **Extract all restaurant URLs** from the page ✅
3. **Visit each individual restaurant page** ✅
4. **Extract all sections** from each page:
   - Overview
   - Details
   - Experiences
   - Offers
   - Popular Dishes
   - Menu
   - Reviews
   - FAQs
   - Photos

## If It's Still Not Working

### Check 1: Detection
```bash
GET /debug/listing-detection?url=YOUR_URL
```

If it returns `is_listing_page: false`, the detection needs adjustment.

### Check 2: URL Extraction
Look in logs for:
```
[LISTING] Found X restaurant URLs
```

If it shows `Found 0 restaurant URLs`, the URL extraction needs improvement.

### Check 3: Individual Page Visits
Look in logs for:
```
[URL VISIT] STARTED | URL: https://www.opentable.com/r/...
```

If you don't see these, individual pages aren't being visited.

## Manual Testing

You can test the detection function directly:

```python
from app.worker import ScraperWorker

worker = ScraperWorker()
url = "https://www.opentable.com/metro/houston-restaurants"
is_listing = worker._is_restaurant_listing_page(url)
print(f"Is listing: {is_listing}")  # Should be True
```

## Next Steps

1. Run a new scraping job with an OpenTable metro URL
2. Check the log file for the entries mentioned above
3. Verify that individual pages are being visited
4. If still not working, check the debug endpoint output

