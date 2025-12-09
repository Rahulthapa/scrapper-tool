# Code Flow Analysis - Individual Page Visits

## Current Flow

### Step 1: Listing Page Detection
**Location**: `app/worker.py` - `_process_single_url_job()`
- Checks if URL is a restaurant listing page
- For OpenTable: Checks for `/metro/`, `/region/`, `/neighborhood/` patterns
- Logs: `"Is listing page: True/False"`

### Step 2: URL Extraction
**Location**: `app/worker.py` - `_process_restaurant_listing_with_individual_pages()`
- Calls `extract_restaurant_urls_from_listing()`
- Extracts restaurant URLs from listing page
- Logs: `"Found X restaurant URLs"`

### Step 3: URL Filtering
**Location**: `app/worker.py` - `_process_restaurant_listing_with_individual_pages()`
- If `skip_listing_page=True`: Skips first extracted URL
- If `max_restaurants=1`: Limits to 1 URL
- Logs: `"Will scrape second URL instead: <URL>"`

### Step 4: Individual Page Visits
**Location**: `app/scraper.py` - `extract_from_individual_pages()`
- Creates shared browser instance
- Loops through each restaurant URL sequentially
- For each URL:
  - Calls `extract_single_restaurant()`
  - Logs: `"Processing: <URL>"`
  - Logs: `"VISITING INDIVIDUAL RESTAURANT PAGE: <URL>"`
  - Visits page with Playwright
  - Extracts data
  - Saves immediately

## Potential Issues

### Issue 1: Listing Page Not Detected
**Symptom**: Log shows `"Is listing page: False"`
**Check**: URL pattern matching in `_is_restaurant_listing_page()`

### Issue 2: No URLs Extracted
**Symptom**: Log shows `"Found 0 restaurant URLs"`
**Check**: 
- JavaScript extraction working?
- URL filtering too strict?
- Page not loading correctly?

### Issue 3: Individual Pages Not Visited
**Symptom**: Log shows URL extraction but no "VISITING INDIVIDUAL RESTAURANT PAGE" messages
**Check**:
- Is `extract_from_individual_pages()` being called?
- Are there any errors in the loop?
- Is browser context created successfully?

### Issue 4: Browser Context Not Created
**Symptom**: Log shows "Failed to create shared browser instance"
**Check**:
- Playwright installed?
- Browser dependencies available?
- Memory issues?

## Diagnostic Logging Added

### Enhanced Logging Points:

1. **URL Extraction**:
   - `"Found X restaurant URLs"`
   - `"URLs to visit: [list]"`

2. **Individual Page Visits**:
   - `"VISITING INDIVIDUAL RESTAURANT PAGE: <URL>"`
   - `"Opening restaurant page: <URL>"`
   - `"Extracting detailed data from: <URL>"`

3. **Browser Operations**:
   - `"Created shared browser instance"`
   - `"Using Playwright (shared browser)"`
   - `"HTML_FETCHED"`

4. **Progress Tracking**:
   - `"[X/Y] Processing: <URL>"`
   - `"Progress: X/Y (Z%)"`

## How to Verify Individual Pages Are Visited

### Check Log File For:

1. **URL Extraction Success**:
   ```
   [LISTING] Found X restaurant URLs
   [LISTING] 1. https://www.opentable.com/r/restaurant-name
   ```

2. **Individual Page Visit Start**:
   ```
   VISITING INDIVIDUAL RESTAURANT PAGE: https://www.opentable.com/r/restaurant-name
   PROCESSING RESTAURANT PAGE
   [URL VISIT] STARTED | Method: GET | URL: https://www.opentable.com/r/restaurant-name
   ```

3. **Page Content Fetching**:
   ```
   FETCHING_HTML | Using Playwright (shared browser)
   HTML_FETCHED | Playwright - Length: X bytes
   ```

4. **Data Extraction**:
   ```
   PARSING | Using OpenTable parser
   PARSING_COMPLETE | Sections found: Overview, Details, ...
   ```

## Expected Log Flow

```
1. Scraper logging started
2. PROCESSING JOB: <job_id>
3. PROCESSING SINGLE URL: <listing_url>
4. PAGE_TYPE | Is listing page: True
5. EXTRACTING RESTAURANT URLS FROM LISTING
6. [LISTING] Found X restaurant URLs
7. VISITING X INDIVIDUAL RESTAURANT PAGES
8. VISITING INDIVIDUAL RESTAURANT PAGE: <restaurant_url>
9. PROCESSING RESTAURANT PAGE
10. FETCHING_HTML | Using Playwright
11. HTML_FETCHED | Length: X bytes
12. PARSING | Using OpenTable parser
13. PARSING_COMPLETE | Sections found: ...
14. ✅ Extracted data for: <restaurant_name>
```

## Next Steps

1. **Run a test scrape** and check the log file
2. **Look for the log messages** listed above
3. **Identify where the flow stops** (if it does)
4. **Check for error messages** that might indicate the issue

