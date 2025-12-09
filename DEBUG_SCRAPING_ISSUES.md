# Debug: URLs and Data Not Showing

## Enhanced Logging Added

I've added comprehensive logging to track exactly what's happening:

### 1. **OpenTable Parser Logging**
- Logs when parser is called
- Logs how many fields were extracted
- Logs restaurant name and URL
- Logs all extracted field names
- Logs errors if parser fails

### 2. **Result Collection Logging**
- Logs each result being processed
- Logs URL, name, and number of keys
- Logs when results are added to detailed_restaurants
- Logs warnings if URL is missing

### 3. **Error Handling**
- All errors are logged with full traceback
- Errors don't silently fail
- Returns data with URL even if parsing fails

## What to Check in Logs

After running a scrape, look for these log messages:

### ✅ Success Indicators:
```
✅ Extracted X fields: name, rating, price_range, ...
✅ Restaurant name: Restaurant Name
✅ Restaurant URL: https://www.opentable.com/r/restaurant-name
📝 Result 1: URL=https://... | Name=Restaurant Name | Keys=25
✅ Added result 1 to detailed_restaurants (total: 1)
```

### ❌ Error Indicators:
```
❌ OpenTable parser failed for URL: [error message]
❌ Failed to extract detailed data from URL: [error message]
⚠️ Result X has no URL: [...]
```

## Common Issues and Solutions

### Issue 1: Parser Returns Empty Data
**Symptoms:**
- "OpenTable parser returned 0 data fields"
- Result has URL but no other data

**Possible Causes:**
- HTML structure changed
- Selectors not matching
- Page not fully loaded

**Solution:**
- Check HTML content length in logs
- Verify page loaded correctly
- Check if selectors need updating

### Issue 2: Results Not Being Collected
**Symptoms:**
- "Result X: URL=..." but not added
- "detailed_restaurants" count stays at 0

**Possible Causes:**
- Result is None or empty
- Result doesn't have URL
- Exception in result processing

**Solution:**
- Check for exceptions in logs
- Verify URL is in result
- Check result structure

### Issue 3: Data Not Saved
**Symptoms:**
- Results collected but not in database
- CSV export shows empty

**Possible Causes:**
- Save function failing silently
- Data structure issue
- Database connection issue

**Solution:**
- Check "💾 Incrementally saved" messages
- Verify save_results is called
- Check database connection

## Debugging Steps

1. **Check if page loads:**
   ```
   Look for: "🌐 Loading page: ..."
   Look for: "✅ Page loaded: X bytes"
   ```

2. **Check if parser runs:**
   ```
   Look for: "Using OpenTable-specific parser"
   Look for: "OpenTable parser returned X data fields"
   ```

3. **Check if data extracted:**
   ```
   Look for: "✅ Extracted X fields: ..."
   Look for: "✅ Restaurant name: ..."
   ```

4. **Check if result collected:**
   ```
   Look for: "📝 Result 1: URL=... | Name=... | Keys=..."
   Look for: "✅ Added result 1 to detailed_restaurants"
   ```

5. **Check if saved:**
   ```
   Look for: "💾 Incrementally saved result 1/1"
   Look for: "Saving X results for job"
   ```

## Next Steps

1. **Run a scrape** with the enhanced logging
2. **Check the logs** for the messages above
3. **Identify where it fails**:
   - Page loading?
   - Parsing?
   - Collection?
   - Saving?
4. **Share the logs** so we can see exactly what's happening

The enhanced logging will show us exactly where the data is being lost!


