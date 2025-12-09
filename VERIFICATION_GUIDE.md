# Verification Guide - Individual Page Visits

## How to Verify the Scraper Visits Individual Pages

### Step 1: Check Log File

After running a scrape job, check the log file for these key messages:

#### Phase 1: Listing Page Detection
```
[LISTING] Found X restaurant URLs
```
✅ **If you see this**: URL extraction is working

#### Phase 2: Individual Page Processing
```
📊 Processing X restaurant pages SEQUENTIALLY (one at a time)...
📋 Restaurant URLs to visit: [list of URLs]
```
✅ **If you see this**: Individual page processing has started

#### Phase 3: Page Visits (CRITICAL)
```
🔄 [1/X] Processing: <restaurant_url>...
🌐 VISITING INDIVIDUAL RESTAURANT PAGE: <restaurant_url>
📄 Creating new page from shared browser context for: <restaurant_url>
✅ Page created successfully for: <restaurant_url>
🌐 Navigating to restaurant page: <restaurant_url>
✅ Page loaded: <restaurant_url>
📄 Extracting HTML content from: <restaurant_url>
✅ HTML extracted: X bytes from <restaurant_url>
```
✅ **If you see all of these**: Individual pages ARE being visited

#### Phase 4: Data Extraction
```
🔍 Using OpenTable-specific parser for detailed extraction: <restaurant_url>
✅ OpenTable parser returned X data fields from <restaurant_url>
💾 Saved result X/Y immediately for <restaurant_url>...
```
✅ **If you see these**: Data is being extracted and saved

### Step 2: Check Database/Results

1. **Check job results** via API: `GET /jobs/{job_id}`
2. **Verify URLs in results**: Each result should have a `url` field with the individual restaurant URL
3. **Check data completeness**: Results should have detailed fields (name, address, phone, etc.)

### Step 3: Common Issues and Solutions

#### Issue: Log stops after "Found X restaurant URLs"
**Possible Causes**:
- Browser context creation failed
- `extract_from_individual_pages()` not being called
- Exception during processing

**Check For**:
- `"Failed to create shared browser instance"` in logs
- `"About to call extract_from_individual_pages"` message
- Any error messages

#### Issue: Log shows "Processing X pages" but no individual page visits
**Possible Causes**:
- Browser context is None
- Loop not executing
- Exception in loop

**Check For**:
- `"✅ Created shared browser instance"` message
- `"VISITING INDIVIDUAL RESTAURANT PAGE"` messages
- Error messages in loop

#### Issue: Pages visited but no data extracted
**Possible Causes**:
- HTML extraction failed
- Parser failed
- Page content not loading

**Check For**:
- `"HTML extracted: X bytes"` messages
- `"OpenTable parser returned X data fields"` messages
- Error messages from parser

## Expected Complete Log Sequence

```
2025-12-09 XX:XX:XX | INFO | Scraper logging started
2025-12-09 XX:XX:XX | INFO | PROCESSING JOB: <job_id>
2025-12-09 XX:XX:XX | INFO | PROCESSING SINGLE URL: <listing_url>
2025-12-09 XX:XX:XX | INFO | PAGE_TYPE | Is listing page: True
2025-12-09 XX:XX:XX | INFO | EXTRACTING RESTAURANT URLS FROM LISTING
2025-12-09 XX:XX:XX | INFO | [LISTING] Found X restaurant URLs
2025-12-09 XX:XX:XX | INFO | Will scrape ALL X extracted restaurant URLs
2025-12-09 XX:XX:XX | INFO | VISITING X INDIVIDUAL RESTAURANT PAGES
2025-12-09 XX:XX:XX | INFO | ✅ Created shared browser instance for all pages
2025-12-09 XX:XX:XX | INFO | 📊 Processing X restaurant pages SEQUENTIALLY
2025-12-09 XX:XX:XX | INFO | 🔄 [1/X] Processing: <restaurant_url>...
2025-12-09 XX:XX:XX | INFO | 🌐 VISITING INDIVIDUAL RESTAURANT PAGE: <restaurant_url>
2025-12-09 XX:XX:XX | INFO | 📄 Creating new page from shared browser context
2025-12-09 XX:XX:XX | INFO | ✅ Page created successfully
2025-12-09 XX:XX:XX | INFO | 🌐 Navigating to restaurant page: <restaurant_url>
2025-12-09 XX:XX:XX | INFO | ✅ Page loaded: <restaurant_url>
2025-12-09 XX:XX:XX | INFO | 📄 Extracting HTML content
2025-12-09 XX:XX:XX | INFO | ✅ HTML extracted: X bytes
2025-12-09 XX:XX:XX | INFO | 🔍 Using OpenTable-specific parser
2025-12-09 XX:XX:XX | INFO | ✅ OpenTable parser returned X data fields
2025-12-09 XX:XX:XX | INFO | 💾 Saved result 1/X immediately
2025-12-09 XX:XX:XX | INFO | 🔄 [2/X] Processing: <next_restaurant_url>...
... (repeats for each restaurant)
```

## Testing Checklist

- [ ] Log shows "Found X restaurant URLs"
- [ ] Log shows "Will scrape ALL X extracted restaurant URLs" (or "Limiting to N")
- [ ] Log shows "VISITING X INDIVIDUAL RESTAURANT PAGES"
- [ ] Log shows "✅ Created shared browser instance"
- [ ] Log shows "VISITING INDIVIDUAL RESTAURANT PAGE" for each URL
- [ ] Log shows "Navigating to restaurant page" for each URL
- [ ] Log shows "HTML extracted: X bytes" for each URL
- [ ] Log shows "OpenTable parser returned X data fields" for each URL
- [ ] Log shows "Saved result X/Y immediately" for each URL
- [ ] Database/API shows results with individual restaurant URLs
- [ ] Results contain detailed data (name, address, etc.)

## Next Steps

1. Run a test scrape with a listing page URL
2. Check the log file for the messages above
3. Verify results in database/API
4. If any step is missing, check error messages in log

