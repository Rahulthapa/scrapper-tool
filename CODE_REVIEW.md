# Code Review: Web Scraper Tool

## Executive Summary

This is a comprehensive web scraping tool with FastAPI backend, React frontend, and AI-powered data extraction. The codebase is well-structured but has several areas for improvement in terms of error handling, security, testing, and code organization.

---

## 🎯 Strengths

1. **Well-organized architecture**: Clear separation between scraper, worker, storage, and API layers
2. **Comprehensive features**: Supports multiple scraping modes, AI filtering, and restaurant-specific extraction
3. **Good use of async/await**: Proper async patterns throughout
4. **Multiple AI providers**: Fallback support for Gemini and OpenAI
5. **Robust extraction**: Handles embedded JSON, JavaScript rendering, and network interception

---

## 🔴 Critical Issues

### 1. Security Vulnerabilities

#### CORS Configuration (app/main.py:28-34)
```python
allow_origins=["*"]  # ⚠️ SECURITY RISK
```
**Issue**: Allows all origins, exposing API to any website  
**Fix**: Restrict to specific domains in production
```python
allow_origins=[
    "https://yourdomain.com",
    "https://www.yourdomain.com"
] if os.getenv("ENVIRONMENT") == "production" else ["*"]
```

#### API Keys in Environment
**Issue**: No validation that API keys are properly secured  
**Recommendation**: Add validation and use secrets management (AWS Secrets Manager, HashiCorp Vault)

### 2. Error Handling

#### Missing Exception Handling in Background Tasks (app/main.py:903-918)
```python
async def process_job_wrapper():
    try:
        await worker_instance.process_job(job_id)
    except Exception as e:
        logger.error(...)
        # Error is logged but job status update might fail silently
```
**Issue**: If storage update fails, error is lost  
**Fix**: Add retry logic and better error propagation

#### Database Connection Errors (app/storage.py)
**Issue**: No connection pooling or retry logic for Supabase  
**Recommendation**: Implement connection retry with exponential backoff

### 3. Resource Management

#### Playwright Browser Not Properly Closed (app/scraper.py:421-584)
**Issue**: Multiple Playwright instances created without proper cleanup in error cases  
**Fix**: Use context managers consistently:
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(...)
    try:
        # ... scraping logic
    finally:
        await browser.close()
```

---

## ⚠️ High Priority Issues

### 4. Code Duplication

#### Repeated URL Normalization Logic
- `app/scraper.py:1352-1362` (extract_restaurant_urls_from_listing)
- `app/crawler.py:354-385` (_normalize_url)
- `app/main.py:249-281` (collect_restaurant_links)

**Recommendation**: Create a shared utility module:
```python
# app/utils.py
def normalize_url(url: str) -> Optional[str]:
    # Single implementation
```

### 5. Hardcoded Values

#### Magic Numbers Throughout Codebase
- `max_concurrent=5` (app/scraper.py:1371, app/worker.py:252)
- `wait_time=5` (app/main.py:527)
- `limit=100` (app/scraper.py:1365)

**Fix**: Move to configuration:
```python
# app/config.py
class ScraperConfig:
    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT", 5))
    DEFAULT_WAIT_TIME = int(os.getenv("DEFAULT_WAIT_TIME", 5))
```

### 6. Data Validation

#### Missing Input Validation (app/main.py:227-457)
**Issue**: `parse_html` endpoint accepts any HTML without size limits  
**Risk**: Memory exhaustion, DoS attacks  
**Fix**:
```python
if len(request.html) > 10_000_000:  # 10MB limit
    raise HTTPException(status_code=413, detail="HTML too large")
```

### 7. Type Safety

#### Inconsistent Type Hints
- `app/scraper.py:26` - `use_javascript: bool = False` but sometimes passed as string
- Missing return type hints in several async functions

**Recommendation**: Add strict type checking with mypy:
```bash
pip install mypy
mypy app/
```

---

## 📋 Medium Priority Issues

### 8. Logging

#### Inconsistent Log Levels
- Some errors use `logger.error()`, others use `logger.warning()`
- Missing structured logging for production

**Recommendation**: Use structured logging:
```python
logger.info("job_created", extra={
    "job_id": job_id,
    "url": url,
    "user_id": user_id
})
```

### 9. Testing

#### Minimal Test Coverage (tests/test_scraper.py)
**Issue**: Only one placeholder test  
**Recommendation**: Add comprehensive tests:
- Unit tests for scraper methods
- Integration tests for API endpoints
- Mock tests for AI providers
- Error handling tests

### 10. Configuration Management

#### Environment Variables Scattered
**Issue**: No centralized config validation  
**Recommendation**: Create config class:
```python
# app/config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
```

### 11. Database Schema

#### Missing Migration Versioning
**Issue**: `database_migration.sql` exists but no version tracking  
**Recommendation**: Use Alembic or similar for migration management

### 12. Rate Limiting

#### No Rate Limiting on API Endpoints
**Issue**: Endpoints can be abused  
**Recommendation**: Add rate limiting:
```python
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/parse-html")
@limiter.limit("10/minute")
async def parse_html(...):
    ...
```

---

## 🔧 Code Quality Improvements

### 13. Function Length

#### Very Long Functions
- `app/main.py:get_job()` - 200+ lines (941-1206)
- `app/scraper.py:_extract_internal_data()` - 200+ lines (586-803)

**Recommendation**: Break into smaller, focused functions

### 14. Naming Conventions

#### Inconsistent Naming
- `_is_restaurant_listing_page()` vs `_is_local_business_search()`
- Mix of snake_case and inconsistent abbreviations

**Recommendation**: Follow PEP 8 consistently

### 15. Documentation

#### Missing Docstrings
- Many functions lack comprehensive docstrings
- No API documentation beyond FastAPI auto-generated docs

**Recommendation**: Add docstrings with examples:
```python
async def scrape(self, url: str, use_javascript: bool = False) -> Dict[str, Any]:
    """
    General-purpose web scraper that works on any website.
    
    Args:
        url: The URL to scrape
        use_javascript: Whether to use Playwright for JavaScript-rendered pages
        
    Returns:
        Dictionary containing structured data from the page
        
    Example:
        >>> scraper = WebScraper()
        >>> data = await scraper.scrape("https://example.com", use_javascript=True)
        >>> print(data['title'])
    """
```

---

## 🚀 Performance Optimizations

### 16. Caching

#### No Caching for Repeated Requests
**Recommendation**: Add caching for:
- AI API responses (with TTL)
- Scraped page content (with invalidation)
- Database queries

```python
from functools import lru_cache
from cachetools import TTLCache

cache = TTLCache(maxsize=100, ttl=3600)
```

### 17. Database Queries

#### N+1 Query Problem Potential
**Issue**: `get_results()` might fetch results one by one  
**Recommendation**: Batch queries and use pagination

### 18. Memory Usage

#### Large Data Structures in Memory
- `app/scraper.py:784` - `all_restaurants[:100]` stored in memory
- No streaming for large exports

**Recommendation**: Use generators for large datasets:
```python
async def get_results_stream(job_id: str):
    async for result in storage.stream_results(job_id):
        yield result
```

---

## 📝 Specific Code Issues

### 19. app/main.py

**Line 309**: Undefined variable `CSV_COLUMNS` in scraper/main.py
```python
table.add_row("Columns", str(len(CSV_COLUMNS)))  # CSV_COLUMNS not defined
```

**Line 983-1100**: Excessive datetime parsing logic - should be extracted to utility

**Line 932-936**: Database schema error handling is too generic

### 20. app/scraper.py

**Line 1360**: Potential race condition in URL deduplication
```python
if url and url.startswith('http') and url not in seen_urls:
    cleaned_urls.append(url)
    seen_urls.add(url)  # Should be atomic
```

**Line 1567**: `asyncio.gather()` without timeout - could hang indefinitely

### 21. app/worker.py

**Line 61-62**: Logic issue - `extract_individual_pages` check happens after data scraping, but should be part of scraping strategy

### 22. app/ai_filter.py

**Line 92-112**: Model initialization tries multiple models but doesn't handle all failure cases gracefully

**Line 223-251**: Complex fallback logic that could be simplified

---

## 🧪 Testing Recommendations

### Unit Tests Needed:
1. URL normalization functions
2. HTML parsing and extraction
3. AI filter prompt preparation
4. Restaurant data extraction
5. Error handling paths

### Integration Tests Needed:
1. Full scraping workflow
2. Database operations
3. API endpoint responses
4. Playwright rendering

### Test Structure:
```
tests/
├── unit/
│   ├── test_scraper.py
│   ├── test_ai_filter.py
│   └── test_storage.py
├── integration/
│   ├── test_api_endpoints.py
│   └── test_workflow.py
└── fixtures/
    └── sample_html.py
```

---

## 📚 Documentation Needs

1. **API Documentation**: Add OpenAPI examples for all endpoints
2. **Setup Guide**: Step-by-step deployment instructions
3. **Architecture Diagram**: Visual representation of system components
4. **Error Codes**: Document all possible error responses
5. **Rate Limits**: Document API rate limits and quotas

---

## 🔒 Security Checklist

- [ ] Fix CORS configuration
- [ ] Add input validation and size limits
- [ ] Implement rate limiting
- [ ] Add authentication/authorization
- [ ] Sanitize user inputs before database queries
- [ ] Add request timeout limits
- [ ] Implement CSRF protection for state-changing operations
- [ ] Add security headers (HSTS, CSP, etc.)
- [ ] Audit dependencies for vulnerabilities (`pip-audit` or `safety`)

---

## 📊 Metrics to Track

1. **Performance**:
   - Average scraping time per URL
   - API response times
   - Database query performance
   - Memory usage patterns

2. **Reliability**:
   - Job success/failure rates
   - Error types and frequencies
   - Retry success rates

3. **Usage**:
   - API endpoint usage statistics
   - Most common scraping targets
   - AI provider usage distribution

---

## 🎯 Priority Action Items

### Immediate (This Week):
1. Fix CORS configuration
2. Add input validation and size limits
3. Fix Playwright resource cleanup
4. Add basic error handling tests

### Short Term (This Month):
1. Implement rate limiting
2. Add comprehensive test suite
3. Create centralized configuration
4. Improve logging and monitoring

### Long Term (Next Quarter):
1. Add authentication/authorization
2. Implement caching layer
3. Optimize database queries
4. Add performance monitoring
5. Create comprehensive documentation

---

## ✅ Positive Observations

1. Good separation of concerns
2. Comprehensive feature set
3. Thoughtful error messages
4. Good use of type hints (where present)
5. Proper async/await usage
6. Multiple extraction strategies
7. Good fallback mechanisms

---

## 📖 Additional Recommendations

1. **Monitoring**: Add APM (Application Performance Monitoring) like Datadog or New Relic
2. **Alerting**: Set up alerts for error rates, response times
3. **CI/CD**: Add automated testing and deployment pipeline
4. **Code Review**: Establish code review process
5. **Dependency Updates**: Regular dependency updates and security audits

---

## Conclusion

The codebase is functional and well-structured but needs improvements in security, testing, and error handling. Focus on the critical and high-priority issues first, then gradually address medium-priority improvements. The architecture is solid and can support these enhancements.

**Overall Grade: B+**

**Recommendation**: Address critical security issues immediately, then focus on testing and error handling improvements.

