# Sequential Scraping Implementation Guide

## Changes Made

### 1. **Sequential Processing (One Browser at a Time)**
- Changed `max_concurrent` from 10 to **1**
- Processes one restaurant URL at a time
- Much more memory efficient (~150MB vs ~1.5GB)
- More reliable, avoids resource exhaustion

### 2. **Incremental Saving**
- Results are saved to database **as each page is scraped**
- If process fails, you don't lose all progress
- Each successful scrape is immediately saved
- Logs show: `💾 Incrementally saved result X/Y`

### 3. **Test Mode: Scrape Just One URL**
- Added `max_restaurants` parameter
- Set to `1` to test with just one restaurant
- Helps debug issues before running full scrape

## Usage

### Test with One Restaurant
```json
POST /jobs
{
  "url": "https://www.opentable.com/metro/houston-restaurants",
  "use_javascript": true,
  "extract_individual_pages": true,
  "max_restaurants": 1
}
```

This will:
1. Extract all 109 URLs from listing page
2. **Only scrape the first 1 URL** (for testing)
3. Save result immediately
4. Return 1 restaurant with full data

### Full Sequential Scraping
```json
POST /jobs
{
  "url": "https://www.opentable.com/metro/houston-restaurants",
  "use_javascript": true,
  "extract_individual_pages": true
  // max_restaurants not set = scrape all
}
```

This will:
1. Extract all 109 URLs
2. Scrape **one at a time** (sequential)
3. Save each result as it's scraped
4. Return all 109 restaurants

## Benefits

### Memory Efficiency
- **Before**: 10 browsers × 150MB = 1.5GB RAM
- **After**: 1 browser × 150MB = 150MB RAM
- **90% memory reduction**

### Reliability
- Less likely to hit resource limits
- More stable on limited servers
- Easier to debug (one at a time)

### Progress Preservation
- Results saved incrementally
- If process fails at restaurant 50, you still have 49 results
- Can resume from where it left off

### Better Error Handling
- One failure doesn't affect others
- Can see exactly which URL failed
- Easier to retry specific URLs

## Expected Behavior

### Logs Will Show:
```
Step 1 Complete: Found 109 restaurant URLs
⚠️ TEST MODE: Limiting to 1 restaurants (out of 109 found)
Step 2: Visiting 1 individual restaurant pages...
📊 Processing 1 restaurant pages concurrently...
🌐 Loading page: https://www.opentable.com/r/restaurant-1
✅ Page loaded: 125,432 bytes
✅ [1/1] (100.0%) | https://www.opentable.com/r/restaurant-1... | Rate: 0.2/s
💾 Incrementally saved result 1/1 for https://www.opentable.com/r/restaurant-1...
Step 2 Complete: Extracted data from 1 individual pages
```

### For Full Scrape (109 restaurants):
```
Step 1 Complete: Found 109 restaurant URLs
Step 2: Visiting 109 individual restaurant pages...
📊 Processing 109 restaurant pages concurrently...
🌐 Loading page: https://www.opentable.com/r/restaurant-1
✅ Page loaded: 125,432 bytes
✅ [1/109] (0.9%) | https://www.opentable.com/r/restaurant-1... | Rate: 0.2/s | ETA: 545s
💾 Incrementally saved result 1/109 for https://www.opentable.com/r/restaurant-1...
🌐 Loading page: https://www.opentable.com/r/restaurant-2
✅ Page loaded: 118,234 bytes
✅ [2/109] (1.8%) | https://www.opentable.com/r/restaurant-2... | Rate: 0.2/s | ETA: 535s
💾 Incrementally saved result 2/109 for https://www.opentable.com/r/restaurant-2...
...
```

## Performance

### Speed
- **Sequential**: ~5 seconds per page = 109 × 5 = **545 seconds (~9 minutes)**
- **Concurrent (10)**: ~5 seconds per batch = 11 batches × 5 = **55 seconds**
- **Trade-off**: Slower but much more reliable

### Memory
- **Sequential**: ~150MB constant
- **Concurrent (10)**: ~1.5GB peak
- **Trade-off**: Much lower memory usage

## Testing Strategy

### Step 1: Test with 1 Restaurant
```json
{
  "url": "https://www.opentable.com/metro/houston-restaurants",
  "use_javascript": true,
  "extract_individual_pages": true,
  "max_restaurants": 1
}
```

**Verify:**
- ✅ One restaurant URL extracted
- ✅ One page scraped successfully
- ✅ Data extracted correctly
- ✅ Result saved to database
- ✅ Appears in CSV export

### Step 2: Test with 5 Restaurants
```json
{
  "max_restaurants": 5
}
```

**Verify:**
- ✅ 5 restaurants scraped sequentially
- ✅ All 5 saved incrementally
- ✅ All 5 appear in CSV

### Step 3: Full Scrape
```json
{
  // Remove max_restaurants or set to null
}
```

**Verify:**
- ✅ All 109 restaurants scraped
- ✅ Progress visible in logs
- ✅ All results saved
- ✅ All appear in CSV

## Troubleshooting

### If Still Only 1 Result:

1. **Check logs for errors:**
   - Look for "❌ Failed" messages
   - Check for timeout errors
   - Check for memory errors

2. **Verify browser is working:**
   - Check "🌐 Loading page" messages
   - Check "✅ Page loaded" messages
   - Check HTML content length

3. **Check incremental saving:**
   - Look for "💾 Incrementally saved" messages
   - Verify results in database
   - Check if results are being collected

4. **Test with single URL:**
   - Use `max_restaurants: 1`
   - See if that works
   - If yes, it's a concurrency/collection issue
   - If no, it's a page loading/parsing issue

## Next Steps

1. **Deploy the changes**
2. **Test with 1 restaurant first** (`max_restaurants: 1`)
3. **Check logs** to see what's happening
4. **Verify result** appears in database and CSV
5. **If successful, try 5 restaurants**
6. **Then try full scrape**

This approach is much more reliable and will help us identify exactly where the issue is!

