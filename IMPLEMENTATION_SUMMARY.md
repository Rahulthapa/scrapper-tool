# Implementation Summary - Scraper Architecture

## Changes Implemented

### 1. Removed Hardcoded Behavior ✅

**Location**: `app/worker.py` lines 280-286

**Before**:
- Hardcoded `skip_listing_page=True`
- Hardcoded `max_restaurants=1`
- Always scraped only 1 restaurant (second one, after skipping first)

**After**:
- Uses `max_restaurants` from job parameters
- `skip_listing_page=True` by default (only scrape individual pages, not listing page)
- If `max_restaurants=None`: Scrapes ALL extracted restaurant URLs
- If `max_restaurants=N`: Scrapes first N restaurant URLs

### 2. Improved URL Filtering Logic ✅

**Location**: `app/worker.py` lines 433-442

**Before**:
- Skipped first extracted URL when `skip_listing_page=True`
- Then limited to `max_restaurants`

**After**:
- Removed logic that skips first URL
- Simply limits to `max_restaurants` if specified
- If `max_restaurants=None`, processes all URLs

### 3. Enhanced Logging ✅

**Location**: `app/scraper.py` - Multiple locations

**Added Logging**:
- Browser instance creation: `"✅ Created shared browser instance for all pages"`
- Page creation: `"📄 Creating new page from shared browser context"`
- Navigation: `"🌐 Navigating to restaurant page: {url}"`
- Page load: `"✅ Page loaded: {url}"`
- HTML extraction: `"📄 Extracting HTML content"` and `"✅ HTML extracted: X bytes"`
- Parser usage: `"🔍 Using OpenTable-specific parser"`
- Parser results: `"✅ OpenTable parser returned X data fields"`

### 4. Better Error Handling ✅

**Location**: `app/scraper.py` lines 2391-2395

**Added**:
- Check if browser context exists before creating page
- Clear error message if browser context not available
- Prevents silent failures

## Current Behavior

### For Listing Pages:

1. **URL Extraction**:
   - Extracts ALL restaurant URLs from listing page
   - Uses JavaScript rendering with Playwright
   - Multiple extraction methods (JSON, HTML, JS)

2. **URL Filtering**:
   - If `max_restaurants=None` (default): Processes ALL extracted URLs
   - If `max_restaurants=N`: Processes first N URLs
   - Always skips listing page itself (`skip_listing_page=True`)

3. **Individual Page Visits**:
   - Creates shared browser instance (memory efficient)
   - Visits each restaurant URL sequentially (one at a time)
   - For each URL:
     - Creates new page from shared browser context
     - Navigates to restaurant page
     - Extracts HTML content
     - Parses with OpenTable-specific parser (if OpenTable)
     - Saves result immediately to database
     - Closes page (frees memory)
   - Moves to next URL

### For Individual Pages:

- Scrapes page directly
- Extracts all available data
- Returns result

## Configuration Options

### Job Parameters:

- `extract_individual_pages`: `True` (default) - Enable individual page extraction
- `max_restaurants`: `None` (default) - Scrape all restaurants, or `N` to limit
- `use_javascript`: `False` (default) - Auto-enabled for listing pages

### Example Usage:

```json
{
  "url": "https://www.opentable.com/metro/houston-restaurants",
  "extract_individual_pages": true,
  "max_restaurants": null,  // Scrape all
  "use_javascript": false   // Auto-enabled for listing pages
}
```

```json
{
  "url": "https://www.opentable.com/metro/houston-restaurants",
  "extract_individual_pages": true,
  "max_restaurants": 10,  // Scrape first 10 only
  "use_javascript": false
}
```

## Memory Optimization

- **Sequential Processing**: One page at a time
- **Shared Browser**: Single browser instance reused
- **Immediate Cleanup**: Pages closed after use
- **Incremental Saving**: Data saved after each page

## Expected Log Flow

```
1. Scraper logging started
2. PROCESSING JOB: <job_id>
3. PROCESSING SINGLE URL: <listing_url>
4. PAGE_TYPE | Is listing page: True
5. EXTRACTING RESTAURANT URLS FROM LISTING PAGE
6. [LISTING] Found X restaurant URLs
7. Will scrape ALL X extracted restaurant URLs (or "Limiting to N")
8. VISITING X INDIVIDUAL RESTAURANT PAGES
9. ✅ Created shared browser instance for all pages
10. Processing X restaurant pages SEQUENTIALLY
11. VISITING INDIVIDUAL RESTAURANT PAGE: <url>
12. Creating new page from shared browser context
13. Navigating to restaurant page: <url>
14. Page loaded: <url>
15. Extracting HTML content
16. HTML extracted: X bytes
17. Using OpenTable-specific parser
18. OpenTable parser returned X data fields
19. Saved result immediately
20. Repeat for next URL...
```

## Verification

To verify individual pages are being visited, check the log file for:

1. `"VISITING INDIVIDUAL RESTAURANT PAGE: <url>"` - Confirms URL is being processed
2. `"Creating new page from shared browser context"` - Confirms page creation
3. `"Navigating to restaurant page: <url>"` - Confirms navigation
4. `"Page loaded: <url>"` - Confirms page loaded
5. `"HTML extracted: X bytes"` - Confirms content extracted
6. `"OpenTable parser returned X data fields"` - Confirms data parsed

If any of these are missing, it indicates where the flow is breaking.

