# Detailed Logging Setup

## Overview

The scraper now includes comprehensive logging that tracks every step of the scraping process. All logs are saved to a separate file for easy debugging and monitoring.

## Log File Location

Logs are automatically saved to:
```
scraper_logs/scraper_YYYYMMDD_HHMMSS.log
```

The `scraper_logs/` directory is created automatically if it doesn't exist.

## What Gets Logged

### 1. URL Visits
- When a URL is being visited
- HTTP method used
- Status of the visit (STARTED, COMPLETE, ERROR)
- Response status codes
- HTML content length
- Processing duration

### 2. Listing Page Processing
- Restaurant URLs found from listing pages
- Number of URLs extracted
- First 10 URLs (with option to see all)

### 3. Individual Restaurant Page Processing
- Each restaurant URL being visited
- Processing steps (INITIALIZED, FETCHING_HTML, PARSING, etc.)
- Type detection (OpenTable, Yelp, etc.)
- HTML fetch method (Playwright vs httpx)
- HTML content size

### 4. Section Extraction
- Each section being extracted:
  - OVERVIEW
  - ABOUT
  - DETAILS
  - EXPERIENCES
  - OFFERS
  - POPULAR_DISHES
  - MENU
  - REVIEWS
  - FAQs
  - PHOTOS
  - BOOKING_INFO
- Status of each section (STARTED, COMPLETE)
- Number of items found in each section
- Sample data extracted

### 5. Data Summary
- Complete summary of all extracted data
- Field names and values
- Count of items in arrays/objects

### 6. Errors
- All errors encountered
- Error messages
- Stack traces (in debug mode)
- URLs where errors occurred

## Log Format

Each log entry follows this format:
```
YYYY-MM-DD HH:MM:SS | LEVEL     | [CATEGORY] Message | Additional Info
```

### Categories

- `[URL VISIT]` - URL being visited
- `[URL COMPLETE]` - URL visit completed
- `[URL ERROR]` - URL visit error
- `[LISTING]` - Listing page processing
- `[RESTAURANT]` - Restaurant page processing
- `[SECTION]` - Section extraction
- `[SECTION DATA]` - Data extracted from section
- `[FIELD]` - Individual field extraction
- `[DATA SUMMARY]` - Complete data summary
- `[WARNING]` - Warnings
- `[ERROR]` - Errors

## Example Log Output

```
2025-12-08 14:30:15 | INFO     | ================================================================================
2025-12-08 14:30:15 | INFO     |   Scraper logging started - Log file: scraper_logs/scraper_20251208_143015.log
2025-12-08 14:30:15 | INFO     | ================================================================================
2025-12-08 14:30:16 | INFO     | [LISTING] URL: https://www.opentable.com/s?... | Found 20 restaurant URLs
2025-12-08 14:30:16 | INFO     | [LISTING]   1. https://www.opentable.com/r/restaurant-1
2025-12-08 14:30:16 | INFO     | [LISTING]   2. https://www.opentable.com/r/restaurant-2
...
2025-12-08 14:30:17 | INFO     | ================================================================================
2025-12-08 14:30:17 | INFO     |   VISITING 20 INDIVIDUAL RESTAURANT PAGES
2025-12-08 14:30:17 | INFO     | ================================================================================
2025-12-08 14:30:17 | INFO     | ================================================================================
2025-12-08 14:30:17 | INFO     |   PROCESSING RESTAURANT PAGE
2025-12-08 14:30:17 | INFO     | ================================================================================
2025-12-08 14:30:17 | INFO     | [URL VISIT] STARTED | Method: GET | URL: https://www.opentable.com/r/restaurant-1
2025-12-08 14:30:17 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: INITIALIZED
2025-12-08 14:30:17 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: DETECTED_TYPE | OpenTable: True
2025-12-08 14:30:17 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: FETCHING_HTML | Using Playwright
2025-12-08 14:30:20 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: HTML_FETCHED | Playwright - Length: 245,678 bytes
2025-12-08 14:30:20 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: PARSING | Using OpenTable parser
2025-12-08 14:30:20 | INFO     | ================================================================================
2025-12-08 14:30:20 | INFO     |   PARSING OPENTABLE PAGE: https://www.opentable.com/r/restaurant-1
2025-12-08 14:30:20 | INFO     | ================================================================================
2025-12-08 14:30:20 | INFO     | [SECTION] STARTED | URL: https://www.opentable.com/r/restaurant-1 | Section: OVERVIEW
2025-12-08 14:30:20 | INFO     | [SECTION DATA] URL: https://www.opentable.com/r/restaurant-1 | Section: OVERVIEW | Data: {'name': 'Restaurant Name', 'rating': 4.8, ...}
2025-12-08 14:30:20 | INFO     | [SECTION] STARTED | URL: https://www.opentable.com/r/restaurant-1 | Section: DETAILS
2025-12-08 14:30:20 | INFO     | [SECTION DATA] URL: https://www.opentable.com/r/restaurant-1 | Section: DETAILS | Items Found: 15
2025-12-08 14:30:20 | INFO     | [SECTION] STARTED | URL: https://www.opentable.com/r/restaurant-1 | Section: EXPERIENCES
2025-12-08 14:30:20 | INFO     | [SECTION DATA] URL: https://www.opentable.com/r/restaurant-1 | Section: EXPERIENCES | Items Found: 2
...
2025-12-08 14:30:22 | INFO     | [RESTAURANT] URL: https://www.opentable.com/r/restaurant-1 | Step: PARSING_COMPLETE | Sections found: Overview, Details, Experiences (2), Offers (1), Popular Dishes (3), Menu, Reviews, FAQs (25), Photos (5)
2025-12-08 14:30:22 | INFO     | [DATA SUMMARY] URL: https://www.opentable.com/r/restaurant-1
2025-12-08 14:30:22 | INFO     | [DATA SUMMARY]   name: Restaurant Name
2025-12-08 14:30:22 | INFO     | [DATA SUMMARY]   rating: 4.8
2025-12-08 14:30:22 | INFO     | [DATA SUMMARY]   details: 15 items
2025-12-12 14:30:22 | INFO     | [URL COMPLETE] URL: https://www.opentable.com/r/restaurant-1 | Status: 200 | HTML Length: 245,678 bytes | Duration: 5.23s
2025-12-08 14:30:22 | INFO     | --------------------------------------------------------------------------------
```

## How to Use

The logger is automatically initialized when the application starts. No additional configuration is needed.

### Viewing Logs

1. **During Development**: Logs are written to the console and file simultaneously
2. **In Production**: Check the log file in `scraper_logs/` directory
3. **Real-time Monitoring**: Use `tail -f scraper_logs/scraper_*.log` to watch logs in real-time

### Log Levels

- **DEBUG**: Detailed field-level extraction (very verbose)
- **INFO**: Standard operations, section extraction, data summaries
- **WARNING**: Non-critical issues
- **ERROR**: Errors and exceptions

## Troubleshooting

### If logs aren't appearing:

1. Check that `scraper_logs/` directory exists and is writable
2. Verify the logger is initialized (check application startup logs)
3. Check file permissions

### If you want to disable logging:

Comment out the logger initialization in `app/main.py`:
```python
# detail_logger = get_scraper_logger()
```

### If you want a custom log file location:

Pass the path when initializing:
```python
detail_logger = get_scraper_logger("custom/path/to/logs.log")
```

## Benefits

1. **Debugging**: See exactly what URLs are being visited and what data is found
2. **Monitoring**: Track scraping progress and identify bottlenecks
3. **Verification**: Confirm that internal pages are being scraped
4. **Troubleshooting**: Identify which sections are failing to extract
5. **Audit Trail**: Complete record of all scraping operations

