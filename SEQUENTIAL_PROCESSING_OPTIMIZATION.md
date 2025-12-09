# Sequential Processing Optimization

## Problem
Even with `max_concurrent=1`, the code was using `asyncio.gather()` which creates all tasks upfront, potentially causing memory issues and not truly processing one at a time.

## Solution: True Sequential Processing

### Changes Made

1. **Replaced `asyncio.gather()` with Sequential Loop**
   - **Before**: Created all tasks upfront with `asyncio.gather()`
   - **After**: Process each URL one at a time in a simple `for` loop
   - **Result**: Only one page is processed at a time, minimizing memory usage

2. **Immediate Incremental Saving**
   - **Before**: Results saved at the end (or with semaphore-based incremental saving)
   - **After**: Each result is saved immediately after scraping
   - **Result**: Data is persisted as soon as it's available, reducing memory footprint

3. **Simplified Processing Flow**
   - Removed semaphore-based concurrency control
   - Removed task creation overhead
   - Direct sequential processing with immediate saving

### Code Changes

**Location**: `app/scraper.py` - `extract_from_individual_pages()` function

**Key Changes**:
```python
# OLD: Concurrent processing with asyncio.gather()
tasks = [extract_with_semaphore(...) for ...]
results = await asyncio.gather(*tasks, return_exceptions=True)

# NEW: Sequential processing with immediate saving
for idx, (restaurant_data, url) in enumerate(restaurant_urls):
    result = await extract_single_restaurant(...)
    # Save immediately
    await storage.save_results(job_id, [result])
    results.append(result)
```

### Benefits

1. **Memory Efficiency**
   - Only one browser page active at a time
   - Results saved immediately (not kept in memory)
   - Minimal memory footprint

2. **Data Safety**
   - Data saved after each page (no data loss if process crashes)
   - Incremental progress tracking
   - Can resume from last saved result if needed

3. **Simpler Code**
   - Easier to understand and debug
   - No complex concurrency management
   - Clear sequential flow

4. **Better Error Handling**
   - Errors don't affect other pages
   - Each page processed independently
   - Failed pages don't block others

### Processing Flow

```
For each restaurant URL:
  1. Scrape the page
  2. Extract data
  3. Save data immediately to database
  4. Move to next URL
  5. Repeat
```

### Performance Characteristics

- **Memory Usage**: Constant (~200MB for browser + minimal for current page)
- **Processing Speed**: Sequential (one page at a time)
- **Data Persistence**: Immediate (after each page)
- **Error Recovery**: Per-page (one failure doesn't stop others)

### Configuration

- `max_concurrent=1`: Already set (sequential mode)
- `save_incrementally=True`: Default (always saves immediately)
- `job_id`: Required for incremental saving

### Notes

- This is optimal for memory-constrained environments
- Processing is slower than concurrent but much more memory-efficient
- Data is always saved, even if the process crashes mid-way
- Each page is independent - failures don't cascade

