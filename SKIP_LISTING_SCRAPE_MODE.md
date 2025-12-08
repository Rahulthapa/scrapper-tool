# Skip Listing Page - Scrape First Extracted URL Only

## What This Does

When you provide a listing URL like:
```
https://www.opentable.com/metro/houston-restaurants
```

The scraper will:
1. ✅ **Extract restaurant URLs** from the listing page (109 URLs found)
2. ⏭️ **SKIP scraping the listing page itself**
3. 🎯 **Scrape ONLY the first extracted URL** (e.g., `https://www.opentable.com/r/restaurant-1`)
4. 💾 **Save the result immediately**

## Why This Helps

- **Faster testing**: Only scrapes 1 page instead of 109
- **Isolates issues**: Tests if individual page scraping works
- **No listing page noise**: Focuses on restaurant page data
- **Quick verification**: See if data extraction works

## Expected Flow

```
1. User provides: https://www.opentable.com/metro/houston-restaurants
2. Extract URLs: Found 109 restaurant URLs
3. Skip listing page: ⏭️ SKIPPING listing page scraping
4. Select first URL: https://www.opentable.com/r/restaurant-1
5. Scrape first URL: 🌐 Loading page...
6. Extract data: ✅ Page loaded: 125,432 bytes
7. Save result: 💾 Incrementally saved result 1/1
8. Return: 1 restaurant with full data
```

## Logs You'll See

```
Step 1: Extracting restaurant URLs from listing page...
Step 1 Complete: Found 109 restaurant URLs
⏭️ SKIPPING listing page scraping - will only scrape extracted restaurant URLs
📋 First extracted URL to scrape: https://www.opentable.com/r/restaurant-1
⚠️ TEST MODE: Limiting to 1 restaurants (out of 109 found)
Step 2: Visiting 1 individual restaurant pages...
📊 Processing 1 restaurant pages concurrently...
🌐 Loading page: https://www.opentable.com/r/restaurant-1
✅ Page loaded: 125,432 bytes
✅ [1/1] (100.0%) | https://www.opentable.com/r/restaurant-1...
💾 Incrementally saved result 1/1 for https://www.opentable.com/r/restaurant-1...
Step 2 Complete: Extracted data from 1 individual pages
```

## What Gets Saved

- **1 restaurant** with full data from the first extracted URL
- **All sections** extracted (Overview, Details, Menu, Reviews, etc.)
- **URL included** in the result
- **Source listing URL** tracked

## CSV Output

The CSV will have:
- **1 row** (the first restaurant)
- **All extracted data** in flattened columns
- **URL** in first column
- **Complete data** from that restaurant page

## Next Steps After Testing

Once you verify this works:

1. **Remove the limit** to scrape all URLs:
   - Remove `max_restaurants: 1` or set to `null`
   - Will scrape all 109 restaurants sequentially

2. **Or increase gradually**:
   - `max_restaurants: 5` - Test with 5
   - `max_restaurants: 10` - Test with 10
   - Then remove limit for full scrape

## Benefits

✅ **Fast**: Only 1 page to scrape (~5 seconds)
✅ **Focused**: Tests individual page scraping only
✅ **Clean**: No listing page data mixed in
✅ **Debuggable**: Easy to see what's happening
✅ **Incremental**: Result saved immediately

