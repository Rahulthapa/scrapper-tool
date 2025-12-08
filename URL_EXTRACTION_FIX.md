# URL Extraction Fix for OpenTable Metro Pages

## Problem

The scraper was correctly detecting listing pages but **only extracting the listing page URL itself** instead of individual restaurant URLs. The log showed:
```
[LISTING] Found 1 restaurant URLs
[LISTING]   1. https://www.opentable.com/metro/east-texas-restaurants
```

This meant the scraper was visiting the same listing page twice instead of visiting individual restaurant pages.

## Root Causes

1. **Dynamic Content Loading**: OpenTable uses JavaScript to dynamically load restaurant listings. The initial page load doesn't contain all restaurant URLs.

2. **Infinite Scroll**: OpenTable uses infinite scroll - restaurants load as you scroll down the page.

3. **Insufficient Wait Time**: The scraper wasn't waiting long enough for content to load.

4. **No Scrolling**: The scraper wasn't scrolling to trigger lazy loading of more restaurants.

5. **Missing Filter**: The extraction wasn't filtering out the listing page URL itself from results.

## Fixes Applied

### 1. Enhanced Page Loading & Scrolling
- Increased wait time from 3 seconds to 5 seconds for initial load
- Added **3 scroll operations** to trigger lazy loading
- Wait 2 seconds between each scroll
- Total wait time: ~11 seconds to ensure content loads

### 2. Improved URL Extraction Selectors
Added multiple selectors to find restaurant links:
- `a[href*="/r/"]` - Direct links
- `[data-test*="restaurant"]` - Data attributes
- `[class*="restaurantCard"]` - Card components
- `article a[href*="/r/"]` - Article links
- `div[class*="card"] a[href*="/r/"]` - Card divs

### 3. Better JavaScript Extraction
- Added console logging to track extraction progress
- Extract from multiple sources:
  - DOM links
  - Restaurant cards
  - Restaurant name links
  - All links with `/r/` pattern
  - Window variables (__PRELOADED_STATE__, etc.)

### 4. Critical Filtering
Added filtering to **exclude the listing page URL itself**:
```python
# CRITICAL: Filter out the listing page URL itself
if url.lower() == listing_url.lower():
    continue

# For OpenTable, only keep URLs with /r/ (restaurant pages)
if 'opentable.com' in listing_url.lower():
    if '/r/' not in url.lower():
        continue
    # Ensure it's not a metro/region/neighborhood page
    if any(pattern in url.lower() for pattern in ['/metro/', '/region/', '/neighborhood/', '/s?']):
        continue
```

### 5. Enhanced Logging
- Log how many URLs found at each step
- Log first 10 URLs found
- Warn if no restaurant URLs extracted
- Debug logging for JavaScript extraction

## Expected Behavior After Fix

When scraping `https://www.opentable.com/metro/east-texas-restaurants`:

1. ✅ **Detects as listing page**
2. ✅ **Loads page with Playwright**
3. ✅ **Scrolls to load content** (3 scrolls)
4. ✅ **Extracts restaurant URLs** like:
   - `https://www.opentable.com/r/restaurant-name-1`
   - `https://www.opentable.com/r/restaurant-name-2`
   - etc.
5. ✅ **Filters out listing page URL**
6. ✅ **Visits each individual restaurant page**
7. ✅ **Extracts all sections** from each page

## Log Output After Fix

You should see:
```
[LISTING] URL: https://www.opentable.com/metro/east-texas-restaurants | Found 25 restaurant URLs
[LISTING]   1. https://www.opentable.com/r/restaurant-1
[LISTING]   2. https://www.opentable.com/r/restaurant-2
[LISTING]   3. https://www.opentable.com/r/restaurant-3
...
[URL VISIT] STARTED | URL: https://www.opentable.com/r/restaurant-1
[URL VISIT] STARTED | URL: https://www.opentable.com/r/restaurant-2
...
```

## Testing

After deploying, test with:
```
POST /api/scrape
{
  "url": "https://www.opentable.com/metro/east-texas-restaurants",
  "use_javascript": true,
  "extract_individual_pages": true
}
```

Check the logs to verify:
1. Multiple restaurant URLs are extracted (not just 1)
2. Individual restaurant pages are visited
3. Data is extracted from each page

## If Still Not Working

If you still see only 1 URL extracted:

1. **Check browser console logs** - The JavaScript extraction logs to console
2. **Increase scroll count** - Try 5 scrolls instead of 3
3. **Increase wait time** - Try 10 seconds instead of 5
4. **Check for anti-bot measures** - OpenTable might be blocking automated access
5. **Verify page structure** - OpenTable might have changed their HTML structure

