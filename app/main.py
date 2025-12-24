from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from typing import Optional, List
import uuid
import json
import os
import logging
from datetime import datetime
from pathlib import Path

from .models import (
    ScrapeJobCreate, ScrapeJob, ScrapeResult, JobStatus, 
    ParseHTMLRequest, ExtractInternalDataRequest, ExtractFromIndividualPagesRequest,
    ExtractUrlsRequest, ExtractUrlsResponse, UrlsListResponse, UrlStatus,
    ScrapeUrlRequest, ScrapeUrlResponse, ScrapeUrlsRequest, ScrapeUrlsResponse
)
from .storage import Storage
from .worker import ScraperWorker
from .exporter import DataExporter

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize detailed scraper logger
try:
    from .scraper_logger import get_scraper_logger
    detail_logger = get_scraper_logger()
    logger.info(f"Detailed scraper logging initialized: {detail_logger.log_file}")
except ImportError:
    logger.warning("Detailed scraper logger not available")
    detail_logger = None

app = FastAPI(
    title="AI Web Scraper",
    description="Intelligent web scraping API with AI-powered filtering and data extraction",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler to ensure all errors return JSON
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions and return JSON responses"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {str(exc)}"
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and return JSON responses"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors()
        }
)

# Initialize storage and worker (lazy initialization to handle missing credentials gracefully)
storage = None
worker = None
exporter = DataExporter()

def get_storage():
    """Get storage instance, initializing if needed"""
    global storage
    if storage is None:
        try:
            storage = Storage()
        except ValueError as e:
            # Re-raise with helpful message
            raise HTTPException(
                status_code=500,
                detail=str(e)
            )
    return storage

def get_worker():
    """Get worker instance, initializing if needed"""
    global worker
    if worker is None:
        storage_instance = get_storage()
        worker = ScraperWorker(storage_instance=storage_instance)
    return worker


# Serve frontend static files if they exist
dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist")
if os.path.exists(dist_path):
    # Mount assets directory at /assets (Vite's default output path)
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    @app.get("/")
    @app.head("/")
    async def serve_frontend():
        """Serve the frontend application"""
        index_path = os.path.join(dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(
            status_code=200,
            content={
            "message": "AI Web Scraper API",
            "version": "1.0.0",
            "status": "running"
        }
        )
else:
    @app.get("/")
    @app.head("/")
    async def root():
        return JSONResponse(
            status_code=200,
            content={
            "message": "AI Web Scraper API",
            "version": "1.0.0",
            "status": "running",
                "frontend": "not_built",
                "instructions": {
                    "step1": "Install Node.js from https://nodejs.org/ (version 18+)",
                    "step2": "Run: npm install",
                    "step3": "Run: npm run build",
                    "step4": "Restart the server",
                    "alternative": "Or run 'npm run dev' in a separate terminal for development mode"
                },
                "api_docs": "/docs",
                "health_check": "/health"
            }
        )


@app.get("/health")
@app.head("/health")
async def health_check():
    """Health check endpoint - quick response for Render deployment"""
    # Return immediately without blocking on database
    # Render just needs to know the server is running
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.get("/logs")
async def list_log_files():
    """List all available log files"""
    log_dir = Path("scraper_logs")
    if not log_dir.exists():
        return {"logs": [], "message": "No log files found"}
    
    log_files = []
    for log_file in sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = log_file.stat()
        log_files.append({
            "filename": log_file.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/logs/{log_file.name}"
        })
    
    return {
        "logs": log_files,
        "total": len(log_files),
        "log_directory": str(log_dir.absolute())
    }


@app.get("/logs/latest")
async def get_latest_log():
    """Get the most recent log file"""
    log_dir = Path("scraper_logs")
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="No log files found")
    
    log_files = list(log_dir.glob("*.log"))
    if not log_files:
        raise HTTPException(status_code=404, detail="No log files found")
    
    latest_log = max(log_files, key=lambda x: x.stat().st_mtime)
    
    return FileResponse(
        path=str(latest_log),
        media_type="text/plain",
        filename=latest_log.name,
        headers={"Content-Disposition": f"inline; filename={latest_log.name}"}
    )


@app.get("/logs/{filename}")
async def get_log_file(filename: str):
    """Get a specific log file by filename"""
    log_dir = Path("scraper_logs")
    log_file = log_dir / filename
    
    # Security: prevent directory traversal
    if not log_file.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    if not log_file.suffix == ".log":
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    return FileResponse(
        path=str(log_file),
        media_type="text/plain",
        filename=filename,
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/logs/{filename}/tail")
async def tail_log_file(
    filename: str,
    lines: int = Query(100, ge=1, le=1000, description="Number of lines to return")
):
    """Get the last N lines of a log file"""
    log_dir = Path("scraper_logs")
    log_file = log_dir / filename
    
    # Security: prevent directory traversal
    if not log_file.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    if not log_file.suffix == ".log":
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "filename": filename,
            "total_lines": len(all_lines),
            "returned_lines": len(tail_lines),
            "lines": tail_lines
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")


@app.get("/logs/{filename}/content")
async def get_log_content(filename: str):
    """Get full content of a log file as JSON"""
    log_dir = Path("scraper_logs")
    log_file = log_dir / filename
    
    # Security: prevent directory traversal
    if not log_file.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    if not log_file.suffix == ".log":
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        stat = log_file.stat()
        return {
            "filename": filename,
            "size": stat.st_size,
            "total_lines": len(content.splitlines()),
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")


@app.get("/logs/test")
async def test_logging():
    """Test endpoint to verify logging is working"""
    try:
        from app.scraper_logger import get_scraper_logger
        test_logger = get_scraper_logger()
        
        # Write a test log entry
        test_logger.log_separator("TEST LOGGING")
        test_logger.log_url_visit("https://test.example.com", status="TEST")
        test_logger.log_section_extraction("https://test.example.com", "TEST_SECTION", "STARTED")
        test_logger.log_section_data("https://test.example.com", "TEST_SECTION", {"test": "data"}, item_count=1)
        test_logger.log_url_complete("https://test.example.com", html_length=1000, duration=1.5)
        test_logger.log_separator()
        
        return {
            "status": "success",
            "message": "Test log entry written",
            "log_file": test_logger.log_file,
            "log_file_exists": Path(test_logger.log_file).exists(),
            "log_file_size": Path(test_logger.log_file).stat().st_size if Path(test_logger.log_file).exists() else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to test logging: {str(e)}",
            "error_type": type(e).__name__
        }


@app.get("/debug/listing-detection")
async def debug_listing_detection(url: str = Query(..., description="URL to test")):
    """Debug endpoint to test listing page detection"""
    try:
        from app.worker import ScraperWorker
        worker = ScraperWorker()
        is_listing = worker._is_restaurant_listing_page(url)
        
        return {
            "url": url,
            "is_listing_page": is_listing,
            "detection_logic": {
                "has_opentable": "opentable.com" in url.lower(),
                "has_r_path": "/r/" in url.lower(),
                "has_metro": "/metro/" in url.lower(),
                "has_region": "/region/" in url.lower(),
                "has_neighborhood": "/neighborhood/" in url.lower(),
                "has_search": "/s?" in url.lower() or "/s?dateTime=" in url.lower(),
            },
            "recommendation": "Should extract individual pages" if is_listing else "Will scrape single page only"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/jobs/{job_id}/extracted-urls")
async def get_extracted_urls(job_id: str):
    """Get list of URLs extracted from a scraping job"""
    try:
        storage_instance = get_storage()
        job = await storage_instance.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get results for this job
        results = await storage_instance.get_results(job_id)
        
        # Extract URLs from results
        extracted_urls = []
        if results:
            for result in results:
                if isinstance(result, dict):
                    # Check if result has URL
                    if 'url' in result:
                        extracted_urls.append({
                            'url': result['url'],
                            'name': result.get('name', 'Unknown'),
                            'source': result.get('source_listing_url')
                        })
                    # Check if result has restaurants array
                    if 'restaurants' in result:
                        for restaurant in result['restaurants']:
                            if 'url' in restaurant:
                                extracted_urls.append({
                                    'url': restaurant['url'],
                                    'name': restaurant.get('name', 'Unknown'),
                                    'source': restaurant.get('source_listing_url')
                                })
                    # Check if result has metadata with extracted_urls
                    if 'metadata' in result and 'extracted_urls' in result['metadata']:
                        for url in result['metadata']['extracted_urls']:
                            extracted_urls.append({
                                'url': url if isinstance(url, str) else url.get('url', str(url)),
                                'name': 'Unknown',
                                'source': result['metadata'].get('source_listing_url')
                            })
        
        return {
            "job_id": job_id,
            "job_url": job.get('url'),
            "total_urls": len(extracted_urls),
            "urls": extracted_urls,
            "status": job.get('status')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting extracted URLs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/debug")
async def debug_info():
    """Debug endpoint to check configuration and database connection"""
    import os
    
    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": {
            "SUPABASE_URL": "SET" if os.getenv("SUPABASE_URL") else "NOT SET",
            "SUPABASE_ANON_KEY": "SET" if os.getenv("SUPABASE_ANON_KEY") else "NOT SET",
            "GEMINI_API_KEY": "SET (FREE tier)" if os.getenv("GEMINI_API_KEY") else "NOT SET - Get free key at https://makersuite.google.com/app/apikey",
            "YELP_API_KEY": "SET (FREE tier)" if os.getenv("YELP_API_KEY") else "NOT SET - Get free key at https://www.yelp.com/developers/v3/manage_app",
            "OSM_OVERPASS_API": "ALWAYS AVAILABLE (FREE, no API key required)",
        },
        "database": {"status": "unknown"},
        "ai_provider": "unknown"
    }
    
    # Check database connection
    try:
        storage_instance = get_storage()
        # Try a simple query to verify connection
        response = storage_instance.client.table('scrape_jobs').select('id').limit(1).execute()
        debug_info["database"] = {
            "status": "connected",
            "table_accessible": True
        }
    except HTTPException as e:
        debug_info["database"] = {
            "status": "error",
            "error": e.detail
        }
    except Exception as e:
        debug_info["database"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check AI provider
    try:
        from .ai_filter import AIFilter
        ai = AIFilter()
        debug_info["ai_provider"] = ai.provider
    except Exception as e:
        debug_info["ai_provider"] = f"error: {str(e)}"
    
    return JSONResponse(status_code=200, content=debug_info)


@app.get("/debug/jobs")
async def debug_recent_jobs():
    """Show recent jobs with their status and errors for debugging"""
    try:
        storage_instance = get_storage()
        
        # Get last 10 jobs
        response = storage_instance.client.table('scrape_jobs').select(
            'id, url, status, error, created_at, crawl_mode, search_query, use_javascript'
        ).order('created_at', desc=True).limit(10).execute()
        
        jobs = []
        for job in (response.data or []):
            jobs.append({
                "id": job.get('id'),
                "url": job.get('url') or job.get('search_query'),
                "status": job.get('status'),
                "error": job.get('error'),
                "crawl_mode": job.get('crawl_mode'),
                "use_javascript": job.get('use_javascript'),
                "created_at": job.get('created_at')
            })
        
        return JSONResponse(status_code=200, content={
            "total_jobs": len(jobs),
            "jobs": jobs
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/parse-html")
async def parse_html(request: ParseHTMLRequest):
    """
    Parse raw HTML content directly - bypasses anti-bot protection.
    Automatically detects listing pages (Yelp, Google, etc.) and extracts structured data.
    
    How to use:
    1. Open the target page in your browser
    2. Right-click -> View Page Source (or Ctrl+U)
    3. Copy all the HTML
    4. Paste it here
    """
    try:
        from bs4 import BeautifulSoup
        from .scraper import WebScraper
        from .ai_filter import AIFilter
        
        if not request.html or len(request.html.strip()) < 100:
            raise HTTPException(status_code=400, detail="HTML content is too short or empty")
        
        logger.info(f"Parsing HTML content ({len(request.html)} chars)")
        
        def collect_restaurant_links(items, fallback_links=None):
            """Build unique list of restaurant hyperlinks from any result set."""
            if not items and not fallback_links:
                return []
            seen = set()
            links = []
            
            def add_link(value):
                if not value:
                    return
                value = str(value).strip()
                if not value or value in seen:
                    return
                seen.add(value)
                links.append(value)
            
            if items:
                records = items if isinstance(items, list) else [items]
                for item in records:
                    if isinstance(item, dict):
                        for key in ("url", "website", "yelp_url", "link", "href"):
                            add_link(item.get(key))
                    elif isinstance(item, str):
                        add_link(item)
            
            if fallback_links:
                for link in fallback_links:
                    if isinstance(link, dict):
                        add_link(link.get("href"))
                    else:
                        add_link(link)
            
            return links
        
        # Parse with BeautifulSoup - keep scripts first to extract JSON
        soup_with_scripts = BeautifulSoup(request.html, 'html.parser')
        
        # Extract embedded JSON data BEFORE removing scripts
        scraper = WebScraper()
        source_url = request.source_url or "pasted-html"
        embedded_data = scraper._extract_embedded_json(soup_with_scripts, source_url)
        
        # Now remove scripts for text extraction
        soup = BeautifulSoup(request.html, 'html.parser')
        for element in soup(['script', 'style', 'noscript']):
            element.decompose()
        
        # Extract structured data
        data = await scraper._extract_structured_data(soup, source_url, request.html)
        data['source'] = 'pasted_html'
        data['html_length'] = len(request.html)
        
        # Merge embedded JSON data
        if embedded_data:
            data['embedded_data'] = embedded_data
            if 'restaurants' in embedded_data:
                data['restaurants'] = embedded_data['restaurants']
                logger.info(f"Found {len(embedded_data['restaurants'])} restaurants in embedded JSON data")
            if 'businesses' in embedded_data:
                data['businesses'] = embedded_data['businesses']
                logger.info(f"Found {len(embedded_data['businesses'])} businesses in embedded JSON data")
        
        # Check if we already have structured restaurant data from embedded JSON
        # If so, prioritize it over AI extraction (faster and more accurate)
        has_embedded_restaurants = bool(data.get('restaurants') or data.get('businesses'))
        
        if has_embedded_restaurants and not request.ai_prompt:
            # Return embedded data directly - it's already structured and comprehensive
            restaurants = data.get('restaurants', []) or data.get('businesses', [])
            restaurant_links = collect_restaurant_links(restaurants, data.get('links'))
            return JSONResponse(status_code=200, content={
                "success": True,
                "ai_filtered": False,
                "auto_extracted": True,
                "source": "embedded_json",
                "extraction_method": "JSON-LD/Yelp internal data",
                "results": restaurants,
                "total_items": len(restaurants),
                "restaurant_links": restaurant_links,
                "raw_data": data,
                "note": "Data extracted from embedded JSON (JSON-LD schema or site-specific data). This is the most accurate source."
            })
        
        # Auto-detect page type and extract structured data
        ai_filter = AIFilter()
        
        # Use AI prompt if provided, otherwise use comprehensive restaurant prompt for restaurant pages
        if request.ai_prompt:
            extraction_prompt = request.ai_prompt
        else:
            # Check if this looks like a restaurant page
            is_restaurant_page = any(keyword in str(data.get('title', '')).lower() or 
                                   keyword in str(data.get('url', '')).lower() or
                                   keyword in str(data.get('text_content', '')).lower()[:500]
                                   for keyword in ['restaurant', 'yelp', 'opentable', 'tripadvisor', 
                                                   'dining', 'food', 'cafe', 'steakhouse', 'menu'])
            
            if is_restaurant_page or has_embedded_restaurants:
                # Use comprehensive restaurant prompt
                from .ai_filter import COMPREHENSIVE_RESTAURANT_PROMPT
                extraction_prompt = COMPREHENSIVE_RESTAURANT_PROMPT
                logger.info("Using comprehensive restaurant extraction prompt (auto-detected restaurant page)")
            else:
                extraction_prompt = "Extract all restaurants, businesses, or listings with their names, ratings, reviews, prices, and locations"
        
        logger.info(f"Applying extraction with prompt: {extraction_prompt[:50]}...")
        filtered_results = await ai_filter.filter_and_structure(data, extraction_prompt)
        
        # If we have embedded restaurants, merge them with AI results (avoid duplicates)
        if has_embedded_restaurants and filtered_results:
            embedded_restaurants = data.get('restaurants', []) or data.get('businesses', [])
            # Merge, avoiding duplicates by name
            seen_names = {r.get('name', '').lower() for r in filtered_results if r.get('name')}
            for restaurant in embedded_restaurants:
                if restaurant.get('name') and restaurant.get('name', '').lower() not in seen_names:
                    filtered_results.append(restaurant)
                    seen_names.add(restaurant.get('name', '').lower())
        
        # DEFAULT BEHAVIOR: Auto-detect restaurant listing pages and extract from individual pages
        is_restaurant_listing = any(keyword in str(data.get('url', '')).lower() or 
                                   keyword in str(data.get('title', '')).lower() or
                                   keyword in str(data.get('text_content', '')).lower()[:500]
                                   for keyword in ['yelp.com/search', 'opentable.com/s', 'tripadvisor.com/search', 
                                                  'restaurant', 'dining', 'food', 'steakhouse'])
        
        # If it's a restaurant listing and we have restaurant data, extract from individual pages by default
        should_extract_individual = request.extract_individual_pages or (
            is_restaurant_listing and 
            filtered_results and 
            any(r.get('url') or r.get('name') for r in filtered_results if isinstance(r, dict))
        )
        
        # Extract from individual pages if requested or auto-detected
        if should_extract_individual and filtered_results:
            logger.info(f"Extracting detailed data from individual restaurant pages")
            try:
                # Filter restaurants with URLs
                restaurants_with_urls = []
                for item in filtered_results:
                    if isinstance(item, dict):
                        url = item.get('url') or item.get('website') or item.get('yelp_url')
                        if url and item.get('name'):
                            restaurants_with_urls.append(item)
                
                if restaurants_with_urls:
                    detailed_restaurants = await scraper.extract_from_individual_pages(
                        restaurants=restaurants_with_urls,
                        use_javascript=True,  # Use JS for individual pages
                        max_concurrent=5
                    )
                    
                    # Replace restaurants in results
                    restaurant_names = {r.get('name', '').lower() for r in detailed_restaurants if r.get('name')}
                    updated_results = []
                    for item in filtered_results:
                        if isinstance(item, dict) and item.get('name', '').lower() in restaurant_names:
                            # Replace with detailed version
                            detailed = next((r for r in detailed_restaurants if r.get('name', '').lower() == item.get('name', '').lower()), item)
                            updated_results.append(detailed)
                        else:
                            updated_results.append(item)
                    
                    filtered_results = updated_results
                    logger.info(f"Successfully extracted data from {len(detailed_restaurants)} individual pages")
            except Exception as e:
                logger.warning(f"Failed to extract from individual pages: {e}")
                # Continue with original results
        
        # Check if we got meaningful results
        restaurant_links = collect_restaurant_links(filtered_results, data.get('links'))

        if filtered_results and len(filtered_results) > 0:
            # Check if results have actual business data vs just raw data
            first_result = filtered_results[0]
            has_business_data = any(key in first_result for key in ['name', 'rating', 'review_count', 'price_range'])
            
            if has_business_data:
                return JSONResponse(status_code=200, content={
                    "success": True,
                    "ai_filtered": bool(request.ai_prompt),
                    "auto_extracted": not bool(request.ai_prompt),
                    "has_embedded_data": has_embedded_restaurants,
                    "prompt": extraction_prompt,
                    "results": filtered_results,
                    "total_items": len(filtered_results),
                    "restaurant_links": restaurant_links,
                    "raw_data": data
                })
        
        # Fallback: return raw data if smart extraction didn't find structured data
        fallback_links = collect_restaurant_links(
            data.get('restaurants') or data.get('businesses') or [],
            data.get('links')
        )
        return JSONResponse(status_code=200, content={
            "success": True,
            "ai_filtered": False,
            "auto_extracted": False,
            "has_embedded_data": has_embedded_restaurants,
            "data": data,
            "restaurant_links": fallback_links,
            "note": "No structured business data detected. Try adding an AI prompt to extract specific data."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HTML parsing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse HTML: {str(e)}")


@app.get("/extract-internal-data")
async def extract_internal_data_info():
    """GET endpoint - shows usage information for extract-internal-data"""
    return JSONResponse(status_code=200, content={
        "endpoint": "/extract-internal-data",
        "method": "POST",
        "description": "Extract internal data from a live URL using JavaScript rendering",
        "usage": {
            "method": "POST",
            "url": "/extract-internal-data",
            "content_type": "application/json",
            "body": {
                "url": "https://www.yelp.com/search?find_desc=steakhouse&find_loc=Houston,TX",
                "wait_time": 5,
                "scroll": True,
                "intercept_network": True,
                "extract_individual_pages": True,
                "ai_prompt": "Extract all restaurants with complete data"
            }
        },
        "parameters": {
            "url": "Required - URL to extract internal data from",
            "wait_time": "Optional (default: 5) - Seconds to wait for data to load",
            "scroll": "Optional (default: true) - Scroll page to trigger lazy loading",
            "intercept_network": "Optional (default: true) - Intercept API calls",
                "extract_individual_pages": "Optional (default: true) - Extract from individual restaurant pages",
            "ai_prompt": "Optional - AI extraction prompt"
        },
        "example_curl": """curl -X POST https://ai-web-scraper-7ctv.onrender.com/extract-internal-data \\
  -H "Content-Type: application/json" \\
  -d '{
    "url": "https://www.yelp.com/search?find_desc=steakhouse&find_loc=Houston,TX",
    "extract_individual_pages": true,
    "ai_prompt": "Extract all restaurants with complete data"
  }'""",
        "note": "This endpoint requires POST method. Use a tool like curl, Postman, or the frontend interface."
    })


@app.post("/extract-internal-data")
async def extract_internal_data(request: ExtractInternalDataRequest):
    """
    Extract internal data from a live URL using JavaScript rendering.
    This captures data loaded dynamically via JavaScript, API calls, and internal variables.
    
    How it works:
    1. Loads the page with Playwright (headless browser)
    2. Waits for JavaScript to execute and data to load
    3. Extracts data from JavaScript variables (window.__PRELOADED_STATE__, etc.)
    4. Intercepts network requests to capture API responses
    5. Executes custom JavaScript to extract internal data structures
    6. Scrolls page to trigger lazy loading
    
    This is perfect for sites where data is loaded dynamically and not in the initial HTML.
    """
    try:
        from .scraper import WebScraper
        from .ai_filter import AIFilter
        import json
        
        logger.info(f"Extracting internal data from: {request.url}")
        
        scraper = WebScraper()
        
        # Use Playwright to extract internal data
        internal_data = await scraper._extract_internal_data(
            url=str(request.url),
            wait_time=request.wait_time,
            scroll=request.scroll,
            intercept_network=request.intercept_network
        )
        
        if not internal_data:
            raise HTTPException(
                status_code=404,
                detail="No internal data could be extracted. The page may not have loaded properly or may be blocking automated access."
            )
        
        # Extract restaurants/businesses if found
        restaurants = []
        if 'restaurants' in internal_data:
            restaurants = internal_data['restaurants']
        elif 'businesses' in internal_data:
            restaurants = internal_data['businesses']
        elif 'data' in internal_data and isinstance(internal_data['data'], list):
            # Check if data contains restaurants
            for item in internal_data['data']:
                if isinstance(item, dict) and ('name' in item or 'restaurant' in str(item).lower()):
                    restaurants.append(item)
        
        # Optionally extract from individual pages for more detailed data
        if restaurants and request.extract_individual_pages:
            logger.info(f"Extracting detailed data from {len(restaurants)} individual restaurant pages")
            try:
                restaurants = await scraper.extract_from_individual_pages(
                    restaurants=restaurants,
                    use_javascript=True,
                    max_concurrent=5
                )
                logger.info(f"Successfully extracted detailed data from individual pages")
            except Exception as e:
                logger.warning(f"Failed to extract from individual pages: {e}, using listing data only")
        
        # If we found restaurants directly, return them
        if restaurants and not request.ai_prompt:
            return JSONResponse(status_code=200, content={
                "success": True,
                "ai_filtered": False,
                "auto_extracted": True,
                "source": "internal_data",
                "extraction_method": "JavaScript rendering + network interception",
                "results": restaurants,
                "total_items": len(restaurants),
                "internal_data_keys": list(internal_data.keys()),
                "internal_data": internal_data,
                "restaurant_links": [
                    item.get('url') or item.get('website') or item.get('yelp_url')
                    for item in restaurants
                    if isinstance(item, dict) and (item.get('url') or item.get('website') or item.get('yelp_url'))
                ],
                "note": "Data extracted from JavaScript variables and network requests. This includes dynamically loaded content."
            })
        
        # Apply AI filter if prompt provided
        if request.ai_prompt:
            ai_filter = AIFilter()
            logger.info(f"Applying AI extraction with prompt: {request.ai_prompt[:50]}...")
            filtered_results = await ai_filter.filter_and_structure(internal_data, request.ai_prompt)
            
            if filtered_results:
                return JSONResponse(status_code=200, content={
                    "success": True,
                    "ai_filtered": True,
                    "auto_extracted": False,
                    "source": "internal_data",
                    "extraction_method": "JavaScript rendering + AI extraction",
                    "prompt": request.ai_prompt,
                    "results": filtered_results,
                    "total_items": len(filtered_results),
                    "internal_data_keys": list(internal_data.keys()),
                    "internal_data": internal_data,
                    "restaurant_links": [
                        item.get('url') or item.get('website') or item.get('yelp_url')
                        for item in filtered_results
                        if isinstance(item, dict) and (item.get('url') or item.get('website') or item.get('yelp_url'))
                    ]
                })
        
        # Return raw internal data
        return JSONResponse(status_code=200, content={
            "success": True,
            "ai_filtered": False,
            "auto_extracted": False,
            "source": "internal_data",
            "extraction_method": "JavaScript rendering + network interception",
            "data": internal_data,
            "internal_data_keys": list(internal_data.keys()),
            "restaurant_links": [
                item.get('url') or item.get('website') or item.get('yelp_url')
                for item in restaurants
                if isinstance(item, dict) and (item.get('url') or item.get('website') or item.get('yelp_url'))
            ] if restaurants else [],
            "note": "Internal data extracted. Use an AI prompt to structure it, or access specific keys from the data object."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Internal data extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract internal data: {str(e)}")


@app.post("/extract-from-individual-pages")
async def extract_from_individual_pages(request: ExtractFromIndividualPagesRequest):
    """
    Extract detailed data from individual restaurant pages.
    
    This endpoint takes a list of restaurants (from listing pages) and visits each
    individual restaurant page to extract comprehensive data like:
    - Full addresses (street, city, state, zip)
    - Complete amenities list
    - All menu URLs (main, lunch, dinner, brunch, drinks, online ordering)
    - Detailed hours, services, payment methods
    - Photos, reviews, and other page-specific data
    
    Perfect for getting complete data that's only available on individual pages.
    """
    try:
        from .scraper import WebScraper
        from .ai_filter import AIFilter
        
        if not request.restaurants or len(request.restaurants) == 0:
            raise HTTPException(status_code=400, detail="No restaurants provided")
        
        logger.info(f"Extracting detailed data from {len(request.restaurants)} individual restaurant pages")
        
        scraper = WebScraper()
        
        # Extract detailed data from individual pages
        detailed_restaurants = await scraper.extract_from_individual_pages(
            restaurants=request.restaurants,
            use_javascript=request.use_javascript,
            max_concurrent=request.max_concurrent
        )
        
        if not detailed_restaurants:
            raise HTTPException(
                status_code=404,
                detail="No detailed data could be extracted from individual pages"
            )
        
        # Apply AI filter if prompt provided
        if request.ai_prompt:
            ai_filter = AIFilter()
            logger.info(f"Applying AI extraction with prompt: {request.ai_prompt[:50]}...")
            
            # Process each restaurant with AI
            ai_filtered_results = []
            for restaurant in detailed_restaurants:
                try:
                    filtered = await ai_filter.filter_and_structure(restaurant, request.ai_prompt)
                    if isinstance(filtered, list):
                        ai_filtered_results.extend(filtered)
                    else:
                        ai_filtered_results.append(filtered)
                except Exception as e:
                    logger.warning(f"AI filtering failed for restaurant {restaurant.get('name', 'Unknown')}: {e}")
                    ai_filtered_results.append(restaurant)
            
            return JSONResponse(status_code=200, content={
                "success": True,
                "ai_filtered": True,
                "source": "individual_pages",
                "extraction_method": "Individual page scraping + AI extraction",
                "prompt": request.ai_prompt,
                "results": ai_filtered_results,
                "total_items": len(ai_filtered_results),
                "pages_processed": len(detailed_restaurants)
            })
        
        # Return detailed restaurants without AI filtering
        return JSONResponse(status_code=200, content={
            "success": True,
            "ai_filtered": False,
            "source": "individual_pages",
            "extraction_method": "Individual page scraping",
            "results": detailed_restaurants,
            "total_items": len(detailed_restaurants),
            "pages_processed": len(detailed_restaurants),
            "note": "Detailed data extracted from individual restaurant pages. Includes full addresses, amenities, menu URLs, and other page-specific data."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Individual page extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract from individual pages: {str(e)}")


# ============ YELP API ENDPOINTS ============

@app.get("/api/yelp/search")
async def yelp_search(
    term: str = Query(..., description="Search term (e.g., steakhouse, pizza)"),
    location: str = Query(..., description="Location (e.g., Houston, TX)"),
    limit: int = Query(20, ge=1, le=50, description="Number of results"),
    sort_by: str = Query("rating", description="Sort by: best_match, rating, review_count, distance"),
    price: Optional[str] = Query(None, description="Price filter: 1, 2, 3, 4 or combinations like 1,2"),
):
    """
    Search Yelp for businesses/restaurants.
    Requires YELP_API_KEY environment variable.
    
    Get your free API key at: https://www.yelp.com/developers/v3/manage_app
    """
    try:
        from .yelp_api import YelpAPI
        
        yelp = YelpAPI()
        restaurants = await yelp.search_restaurants(
            location=location,
            cuisine=term,
            limit=limit,
            sort_by=sort_by,
            price=price,
        )
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "source": "yelp_api",
            "location": location,
            "term": term,
            "total": len(restaurants),
            "restaurants": restaurants,
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Yelp API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Yelp API error: {str(e)}")


@app.get("/api/yelp/business/{business_id}")
async def yelp_business_details(business_id: str):
    """Get detailed information about a specific Yelp business."""
    try:
        from .yelp_api import YelpAPI
        
        yelp = YelpAPI()
        details = await yelp.get_business_details(business_id)
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "business": details,
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Yelp API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Yelp API error: {str(e)}")


@app.get("/api/yelp/status")
async def yelp_api_status():
    """Check if Yelp API is configured and get usage stats."""
    has_key = bool(os.getenv("YELP_API_KEY"))
    if not has_key:
        return JSONResponse(status_code=200, content={
            "configured": False,
            "message": "YELP_API_KEY not set. Get your FREE key at https://www.yelp.com/developers/v3/manage_app",
            "tier": "FREE",
            "daily_limit": 5000
        })
    
    try:
        from .yelp_api import YelpAPI
        yelp = YelpAPI()
        stats = yelp.get_usage_stats()
        return JSONResponse(status_code=200, content={
            "configured": True,
            "message": "Yelp API is ready (FREE tier)",
            **stats
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "configured": False,
            "message": f"Yelp API error: {str(e)}",
            "tier": "FREE",
            "daily_limit": 5000
        })


# ============ OPENSTREETMAP OVERPASS API ENDPOINTS ============

@app.get("/api/osm/search")
async def osm_search_steakhouses(
    location: str = Query(..., description="Location (e.g., 'Houston, TX' or '29.5,-96.0,30.0,-94.5' for bbox)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    enhance: bool = Query(False, description="Enhance data with web scraping and AI extraction"),
):
    """
    Search OpenStreetMap for steakhouses in a location.
    
    Completely FREE - no API key required!
    
    Location can be:
    - City name: "Houston, TX"
    - Coordinates: "29.7604,-95.3698" (creates ~50km radius)
    - Bounding box: "29.5,-96.0,30.0,-94.5" (south,west,north,east)
    
    When enhance=true:
    - Scrapes restaurant websites for menus and images
    - Uses AI to extract steak cut types from descriptions
    """
    try:
        from .osm_api import OverpassAPI
        
        osm = OverpassAPI()
        steakhouses = await osm.search_steakhouses(
            location=location,
            limit=limit,
            enhance=enhance
        )
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "source": "osm_overpass",
            "location": location,
            "total": len(steakhouses),
            "steakhouses": steakhouses,
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OSM Overpass API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OSM Overpass API error: {str(e)}")


@app.get("/api/osm/steakhouse/{osm_id}")
async def osm_steakhouse_details(
    osm_id: str,
    enhance: bool = Query(False, description="Enhance data with web scraping and AI extraction"),
):
    """
    Get detailed information about a specific steakhouse from OpenStreetMap.
    
    OSM ID format: "node/123456", "way/789012", or "relation/345678"
    
    Completely FREE - no API key required!
    """
    try:
        from .osm_api import OverpassAPI
        
        osm = OverpassAPI()
        steakhouse = await osm.get_steakhouse_details(
            osm_id=osm_id,
            enhance=enhance
        )
        
        if not steakhouse:
            raise HTTPException(status_code=404, detail=f"Steakhouse {osm_id} not found")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "source": "osm_overpass",
            "steakhouse": steakhouse,
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OSM Overpass API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OSM Overpass API error: {str(e)}")


@app.get("/api/osm/status")
async def osm_api_status():
    """Check OSM Overpass API status. Always available - completely free!"""
    try:
        from .osm_api import OverpassAPI
        
        osm = OverpassAPI()
        status = osm.get_status()
        
        return JSONResponse(status_code=200, content=status)
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "configured": True,
            "message": f"OSM Overpass API is ready (completely free, no API key required). Error: {str(e)}",
            "tier": "FREE"
        })


@app.post("/jobs/osm-only", response_model=ScrapeJob, status_code=201)
async def create_osm_only_job(
    location: str = Query(..., description="Location (e.g., 'Houston, TX' or '29.7604,-95.3698')"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    export_format: str = Query("json", description="Export format: json, csv, excel"),
    background_tasks: BackgroundTasks = None
):
    """
    Create a scraping job that uses ONLY OpenStreetMap Overpass API.
    No web scraping is performed - pure OSM data only.
    
    This is faster and uses only free OSM data.
    """
    try:
        storage_instance = get_storage()
        worker_instance = get_worker()
        
        job_id = str(uuid.uuid4())
        
        job_data = {
            'id': job_id,
            'status': JobStatus.PENDING.value,
            'osm_only': True,
            'osm_location': location,
            'osm_limit': limit,
            'export_format': export_format,
            'created_at': datetime.utcnow().isoformat(),
        }
        
        # Save job to database
        job = await storage_instance.create_job(job_data)
        
        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        # Process job in background
        async def process_job_wrapper():
            """Wrapper to ensure background task errors are logged"""
            try:
                await worker_instance.process_job(job_id)
            except Exception as e:
                logger.error(f"Background task failed for job {job_id}: {str(e)}", exc_info=True)
                try:
                    storage = get_storage()
                    await storage.update_job(job_id, {
                        'status': JobStatus.FAILED.value,
                        'error': str(e)
                    })
                except Exception as update_error:
                    logger.error(f"Failed to update job status: {update_error}")
        
        if background_tasks:
            background_tasks.add_task(process_job_wrapper)
        else:
            # If no background tasks, process immediately (for testing)
            import asyncio
            asyncio.create_task(process_job_wrapper())
        
        logger.info(f"OSM-only job {job_id} created for location: {location}")
        
        return job
        
    except Exception as e:
        logger.error(f"Failed to create OSM-only job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@app.get("/test/job/{job_id}")
async def test_get_job(job_id: str):
    """Test endpoint to diagnose job fetching issues - returns raw data"""
    try:
        logger.info(f"TEST: Fetching job {job_id}")
        storage_instance = get_storage()
        
        # Try to fetch raw data
        response = storage_instance.client.table('scrape_jobs').select('*').eq('id', job_id).limit(1).execute()
        
        if not response.data or len(response.data) == 0:
            return JSONResponse(
                status_code=404,
                content={"error": "Job not found", "job_id": job_id}
            )
        
        # Convert datetime objects to strings for JSON serialization
        raw_data = response.data[0].copy()
        for key, value in raw_data.items():
            if hasattr(value, 'isoformat'):
                raw_data[key] = value.isoformat()
            elif value is None:
                raw_data[key] = None
        
        # Return raw data for inspection
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "raw_data": raw_data,
                "data_type": str(type(response.data)),
                "keys": list(raw_data.keys()) if isinstance(raw_data, dict) else "not a dict",
                "status": raw_data.get('status'),
                "export_format": raw_data.get('export_format'),
                "has_created_at": 'created_at' in raw_data,
                "created_at_type": str(type(raw_data.get('created_at'))) if raw_data.get('created_at') else None
            }
        )
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"TEST endpoint error: {e}")
        logger.error(f"Full traceback:\n{error_traceback}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": error_traceback
            }
        )


@app.post("/jobs", response_model=ScrapeJob, status_code=201)
async def create_job(job_request: ScrapeJobCreate, background_tasks: BackgroundTasks):
    """Create a new scraping job"""
    try:
        storage_instance = get_storage()
        worker_instance = get_worker()
        
        job_id = str(uuid.uuid4())
        
        # Build job data - only include fields that exist in the database
        # This handles cases where migration hasn't been applied yet
        job_data = {
            'id': job_id,
            'url': str(job_request.url) if job_request.url else None,
            'status': JobStatus.PENDING.value,
            'filters': job_request.filters,
            'ai_prompt': job_request.ai_prompt,
            'export_format': job_request.export_format or 'json',
            'created_at': datetime.utcnow().isoformat(),
        }
        
        # Add crawl-related fields only if crawl_mode is enabled
        # Note: These fields will cause an error if the database migration hasn't been run
        if job_request.crawl_mode:
                job_data.update({
                    'crawl_mode': True,
                    'search_query': job_request.search_query,
                    'max_pages': job_request.max_pages or 10,
                    'max_depth': job_request.max_depth or 2,
                    'same_domain': job_request.same_domain if job_request.same_domain is not None else True,
                })
        
        # Add JavaScript rendering field
        # Note: This field will cause an error if the database migration hasn't been run
        if job_request.use_javascript:
            job_data['use_javascript'] = True
        
        # Add individual page extraction field
        if job_request.extract_individual_pages:
            job_data['extract_individual_pages'] = True
        
        # Add max_restaurants limit (for testing - scrape only first N restaurants)
        if hasattr(job_request, 'max_restaurants') and job_request.max_restaurants:
            job_data['max_restaurants'] = job_request.max_restaurants
        
        # Add OSM-only fields
        if job_request.osm_only:
            if not job_request.osm_location:
                raise HTTPException(
                    status_code=400,
                    detail="osm_location is required when osm_only=True"
                )
            job_data.update({
                'osm_only': True,
                'osm_location': job_request.osm_location,
                'osm_limit': job_request.osm_limit or 50,
            })
            # OSM-only doesn't need URL, so clear it if provided
            if job_data.get('url'):
                logger.warning(f"URL provided but osm_only=True, ignoring URL")
                job_data['url'] = None
        
        # Validate: need either URL, search_query, or osm_location
        if not job_data.get('url') and not job_data.get('search_query') and not job_data.get('osm_location'):
            raise HTTPException(
                status_code=400,
                detail="Either 'url', 'search_query', or 'osm_location' (with osm_only=True) must be provided"
            )
        
        job = await storage_instance.create_job(job_data)
        
        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        # Process job in background with proper error handling
        # FastAPI BackgroundTasks supports async functions directly
        async def process_job_wrapper():
            """Wrapper to ensure background task errors are logged"""
            try:
                await worker_instance.process_job(job_id)
            except Exception as e:
                logger.error(f"Background task failed for job {job_id}: {str(e)}", exc_info=True)
                # Update job status to failed
                try:
                    storage = get_storage()
                    await storage.update_job(job_id, {
                        'status': JobStatus.FAILED.value,
                        'error': str(e)
                    })
                except Exception as update_error:
                    logger.error(f"Failed to update job status: {update_error}")
        
        background_tasks.add_task(process_job_wrapper)
        logger.info(f"Job {job_id} created and queued for processing")
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Error creating job: {str(e)}", exc_info=True)
        
        # Check if it's a database schema error
        error_str = str(e).lower()
        if 'crawl_mode' in error_str or 'pgrst' in error_str or 'column' in error_str:
            raise HTTPException(
                status_code=500,
                detail=f"Database schema error: {str(e)}. Please run the migration SQL in Supabase and refresh the schema cache. See database_migration.sql for details."
            )
        
        raise HTTPException(status_code=500, detail=f"Error creating job: {str(e)}")


@app.get("/jobs/{job_id}", response_model=ScrapeJob)
async def get_job(job_id: str):
    """Get job status by ID - always returns ScrapeJob model"""
    try:
        logger.info(f"Fetching job {job_id}")
        
        try:
            storage_instance = get_storage()
        except Exception as storage_init_error:
            logger.error(f"Failed to initialize storage: {storage_init_error}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database connection error: {str(storage_init_error)}"
            )
        
        try:
            job = await storage_instance.get_job(job_id)
        except Exception as storage_error:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Storage error fetching job {job_id}: {storage_error}")
            logger.error(f"Full traceback:\n{error_traceback}")
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(storage_error)}"
            )
        
        if not job:
            logger.warning(f"Job {job_id} not found")
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.debug(f"Raw job data keys: {list(job.keys()) if isinstance(job, dict) else 'not a dict'}")
        logger.debug(f"Raw job data type: {type(job)}")
        
        # Normalize status to ensure it's a valid JobStatus enum value
        status = job.get('status', 'pending')
        if status not in ['pending', 'running', 'completed', 'failed']:
            logger.warning(f"Invalid status '{status}' for job {job_id}, defaulting to 'pending'")
            status = 'pending'
        
        # Normalize and ensure all fields are present
        # CRITICAL: export_format must be a string, not None
        export_format = job.get('export_format')
        if not export_format or not isinstance(export_format, str):
            export_format = 'json'
        
        normalized_job = {
            'id': str(job.get('id', job_id)),
            'url': job.get('url'),
            'status': status,
            'filters': job.get('filters'),
            'ai_prompt': job.get('ai_prompt'),
            'export_format': export_format,  # Always a string
            'crawl_mode': bool(job.get('crawl_mode', False)) if job.get('crawl_mode') is not None else False,
            'search_query': job.get('search_query'),
            'max_pages': job.get('max_pages'),
            'max_depth': job.get('max_depth'),
            'same_domain': job.get('same_domain'),
            'use_javascript': bool(job.get('use_javascript', False)) if job.get('use_javascript') is not None else False,
            'error': job.get('error'),
        }
        
        # Handle created_at - convert to datetime object
        created_at = job.get('created_at')
        try:
            if created_at:
                if isinstance(created_at, str):
                    # Try multiple datetime formats
                    created_at_clean = created_at.strip()
                    parsed = False
                    
                    # Try dateutil parser first (more flexible)
                    try:
                        from dateutil import parser as date_parser
                        normalized_job['created_at'] = date_parser.parse(created_at_clean)
                        parsed = True
                    except (ImportError, ValueError, AttributeError):
                        pass
                    
                    if not parsed:
                        # Try ISO format
                        try:
                            # Remove timezone info
                            created_at_clean = created_at_clean.replace('Z', '').replace('+00:00', '').strip()
                            if 'T' in created_at_clean:
                                # Remove microseconds if present
                                if '.' in created_at_clean:
                                    parts = created_at_clean.split('.')
                                    created_at_clean = parts[0]
                                normalized_job['created_at'] = datetime.fromisoformat(created_at_clean)
                            else:
                                # Try standard format
                                normalized_job['created_at'] = datetime.strptime(created_at_clean, '%Y-%m-%d %H:%M:%S')
                            parsed = True
                        except (ValueError, AttributeError):
                            logger.warning(f"Could not parse created_at: {created_at}, using current time")
                            normalized_job['created_at'] = datetime.utcnow()
                elif hasattr(created_at, 'isoformat'):
                    normalized_job['created_at'] = created_at
                else:
                    normalized_job['created_at'] = datetime.utcnow()
            else:
                normalized_job['created_at'] = datetime.utcnow()
        except Exception as e:
            logger.warning(f"Error parsing created_at: {e}, using current time")
            normalized_job['created_at'] = datetime.utcnow()
        
        # Handle completed_at
        completed_at = job.get('completed_at')
        try:
            if completed_at:
                if isinstance(completed_at, str):
                    completed_at_clean = completed_at.strip()
                    parsed = False
                    
                    # Try dateutil parser first
                    try:
                        from dateutil import parser as date_parser
                        normalized_job['completed_at'] = date_parser.parse(completed_at_clean)
                        parsed = True
                    except (ImportError, ValueError, AttributeError):
                        pass
                    
                    if not parsed:
                        try:
                            completed_at_clean = completed_at_clean.replace('Z', '').replace('+00:00', '').strip()
                            if 'T' in completed_at_clean:
                                if '.' in completed_at_clean:
                                    completed_at_clean = completed_at_clean.split('.')[0]
                                normalized_job['completed_at'] = datetime.fromisoformat(completed_at_clean)
                            else:
                                normalized_job['completed_at'] = datetime.strptime(completed_at_clean, '%Y-%m-%d %H:%M:%S')
                        except (ValueError, AttributeError):
                            normalized_job['completed_at'] = None
                elif hasattr(completed_at, 'isoformat'):
                    normalized_job['completed_at'] = completed_at
                else:
                    normalized_job['completed_at'] = None
            else:
                normalized_job['completed_at'] = None
        except Exception as e:
            logger.warning(f"Error parsing completed_at: {e}")
            normalized_job['completed_at'] = None
        
        # Ensure status is JobStatus enum before validation
        if isinstance(normalized_job.get('status'), str):
            try:
                normalized_job['status'] = JobStatus(normalized_job['status'])
            except ValueError:
                logger.warning(f"Invalid status '{normalized_job.get('status')}', using PENDING")
                normalized_job['status'] = JobStatus.PENDING
        
        # Validate and return using response model
        try:
            # Double-check required fields before validation
            if not normalized_job.get('id'):
                normalized_job['id'] = str(job_id)
            if not normalized_job.get('status'):
                normalized_job['status'] = JobStatus.PENDING
            if not normalized_job.get('export_format'):
                normalized_job['export_format'] = 'json'
            if not normalized_job.get('created_at'):
                normalized_job['created_at'] = datetime.utcnow()
            
            # Ensure status is JobStatus enum
            if isinstance(normalized_job.get('status'), str):
                try:
                    normalized_job['status'] = JobStatus(normalized_job['status'])
                except ValueError:
                    normalized_job['status'] = JobStatus.PENDING
            
            result = ScrapeJob(**normalized_job)
            logger.info(f"Successfully fetched job {job_id}")
            return result
        except Exception as model_error:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Pydantic validation error for job {job_id}: {model_error}")
            logger.error(f"Model error type: {type(model_error).__name__}")
            logger.error(f"Full traceback:\n{error_traceback}")
            
            # Get detailed validation errors if available
            if hasattr(model_error, 'errors'):
                try:
                    validation_errors = model_error.errors()
                    logger.error(f"Validation errors: {validation_errors}")
                except:
                    pass
            
            logger.error(f"Normalized job keys: {list(normalized_job.keys())}")
            logger.error(f"Normalized job values (sanitized): {str(normalized_job)[:500]}")
            
            # Try to fix common issues
            try:
                # Ensure all required fields are present and correct type
                fixed_job = {
                    'id': str(normalized_job.get('id', job_id)),
                    'status': normalized_job.get('status', JobStatus.PENDING),
                    'export_format': normalized_job.get('export_format', 'json'),
                    'created_at': normalized_job.get('created_at', datetime.utcnow()),
                    'url': normalized_job.get('url'),
                    'filters': normalized_job.get('filters'),
                    'ai_prompt': normalized_job.get('ai_prompt'),
                    'crawl_mode': bool(normalized_job.get('crawl_mode', False)),
                    'search_query': normalized_job.get('search_query'),
                    'max_pages': normalized_job.get('max_pages'),
                    'max_depth': normalized_job.get('max_depth'),
                    'same_domain': normalized_job.get('same_domain'),
                    'use_javascript': bool(normalized_job.get('use_javascript', False)),
                    'completed_at': normalized_job.get('completed_at'),
                    'error': normalized_job.get('error'),
                }
                
                # Ensure status is JobStatus enum
                if isinstance(fixed_job['status'], str):
                    fixed_job['status'] = JobStatus(fixed_job['status'])
                
                result = ScrapeJob(**fixed_job)
                logger.info(f"Successfully created job after fixes")
                return result
            except Exception as e2:
                logger.error(f"Second validation attempt failed: {e2}")
                # Last resort: return minimal valid job object
                try:
                    return ScrapeJob(
                        id=str(job_id),
                        status=JobStatus.PENDING,
                        export_format='json',
                        created_at=datetime.utcnow(),
                        url=normalized_job.get('url'),
                        crawl_mode=False,
                        use_javascript=False,
                        error=f'Data parsing error: {str(model_error)}'
                    )
                except Exception as e3:
                    logger.error(f"Even minimal job creation failed: {e3}")
                    # Absolute last resort: create job with all defaults
                    # This should never fail
                    try:
                        return ScrapeJob(
                            id=str(job_id),
                            status=JobStatus.PENDING,
                            export_format='json',
                            created_at=datetime.utcnow(),
                            url=None,
                            crawl_mode=False,
                            use_javascript=False,
                            error=f'Data parsing error: {str(model_error)}'
                        )
                    except Exception as e4:
                        # This should never happen, but if it does, raise HTTPException
                        logger.critical(f"CRITICAL: Cannot create ScrapeJob object: {e4}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Internal error: Unable to format job data. Original error: {str(model_error)}"
                        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {str(e)}", exc_info=True)
        logger.error(f"Exception type: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching job: {str(e)}"
        )


@app.get("/jobs/{job_id}/results", response_model=ScrapeResult)
async def get_job_results(job_id: str):
    """Get scraping results for a job"""
    storage_instance = get_storage()
    
    # Check if job exists
    job = await storage_instance.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get results
    results = await storage_instance.get_results(job_id)
    
    # Extract data from results
    data = [result.get('data', result) for result in results]
    
    return ScrapeResult(
        job_id=job_id,
        data=data,
        total_items=len(data),
        filtered_items=len(data)
    )


@app.get("/jobs/{job_id}/export")
async def export_job_results(
    job_id: str,
    format: str = Query("json", regex="^(json|csv|excel)$")
):
    """Export job results in specified format"""
    storage_instance = get_storage()
    
    # Check if job exists
    job = await storage_instance.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get('status') != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400, 
            detail=f"Job is not completed. Current status: {job.get('status')}"
        )
    
    # Check if this is a selective scraping job (has extracted_urls)
    # If so, only export scraped URLs
    try:
        extracted_urls = await storage_instance.get_extracted_urls(job_id)
        if extracted_urls:
            # Use scraped URLs only
            scraped_data = await storage_instance.get_scraped_urls(job_id)
            if scraped_data:
                data = scraped_data
                logger.info(f"Exporting {len(data)} scraped URLs for selective scraping job {job_id}")
            else:
                # No scraped URLs yet
                data = []
        else:
            # Regular job - use old method
            results = await storage_instance.get_results(job_id)
            data = [result.get('data', result) for result in results]
    except Exception as e:
        # Fallback to old method if extracted_urls table doesn't exist
        logger.warning(f"Could not check extracted_urls, using old method: {str(e)}")
        results = await storage_instance.get_results(job_id)
        data = [result.get('data', result) for result in results]
    
    # Debug logging
    logger.info(f"Exporting {len(data)} results for job {job_id}")
    if data:
        # Check structure
        first_item = data[0] if isinstance(data[0], dict) else {}
        logger.info(f"First item keys: {list(first_item.keys())[:10] if isinstance(first_item, dict) else 'Not a dict'}")
        # Count URLs
        urls_count = sum(1 for item in data if isinstance(item, dict) and item.get('url'))
        logger.info(f"Items with URLs in export: {urls_count}/{len(data)}")
    
    if not data:
        raise HTTPException(status_code=404, detail="No results found for this job")
    
    # Flatten if data contains nested structures (e.g., if results are wrapped)
    flattened_data = []
    for item in data:
        if isinstance(item, dict):
            # If item has 'restaurants' key, expand it
            if 'restaurants' in item and isinstance(item['restaurants'], list):
                for restaurant in item['restaurants']:
                    if isinstance(restaurant, dict):
                        flattened_data.append(restaurant)
            # If item has 'data' key (double nested), use that
            elif 'data' in item:
                if isinstance(item['data'], list):
                    flattened_data.extend(item['data'])
                else:
                    flattened_data.append(item['data'])
            # Otherwise, add item as-is
            else:
                flattened_data.append(item)
        else:
            flattened_data.append(item)
    
    # Use flattened data if we found nested structures
    if len(flattened_data) > len(data):
        logger.info(f"Flattened {len(data)} results into {len(flattened_data)} items")
        data = flattened_data
    
    # Export based on format
    if format == "json":
        json_str = exporter.to_json(data)
        return JSONResponse(
            content=json.loads(json_str),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=scrape_results_{job_id}.json"}
        )
    elif format == "csv":
        csv_bytes = exporter.to_csv(data)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=scrape_results_{job_id}.csv"}
        )
    elif format == "excel":
        excel_bytes = exporter.to_excel(data)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=scrape_results_{job_id}.xlsx"}
        )


# ========== URL Extraction Workflow Endpoints ==========

@app.post("/jobs/extract-urls", response_model=ExtractUrlsResponse, status_code=201)
async def extract_urls(request: ExtractUrlsRequest, background_tasks: BackgroundTasks):
    """
    Extract restaurant URLs from a listing page and create a job.
    Does NOT scrape the URLs - just extracts them for manual selection.
    """
    try:
        storage_instance = get_storage()
        worker_instance = get_worker()
        
        # Create a new job for URL extraction
        job_id = str(uuid.uuid4())
        job_data = {
            'id': job_id,
            'url': str(request.listing_url),
            'status': JobStatus.PENDING.value,
            'export_format': 'json',
            'use_javascript': request.use_javascript,
            'created_at': datetime.utcnow().isoformat(),
        }
        
        job = await storage_instance.create_job(job_data)
        logger.info(f"Created job {job_id} for URL extraction from {request.listing_url}")
        
        # Extract URLs in background
        async def extract_and_save():
            try:
                await storage_instance.update_job(job_id, {'status': JobStatus.RUNNING.value})
                
                # Extract URLs only (no scraping)
                urls = await worker_instance.extract_urls_only(
                    listing_url=str(request.listing_url),
                    use_javascript=request.use_javascript
                )
                
                # Save extracted URLs to database
                if urls:
                    await storage_instance.save_extracted_urls(job_id, urls)
                    logger.info(f"Saved {len(urls)} URLs for job {job_id}")
                
                # Update job status
                await storage_instance.update_job(job_id, {
                    'status': JobStatus.COMPLETED.value,
                    'completed_at': datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error extracting URLs: {str(e)}")
                await storage_instance.update_job(job_id, {
                    'status': JobStatus.FAILED.value,
                    'error': str(e),
                    'completed_at': datetime.utcnow().isoformat()
                })
        
        background_tasks.add_task(extract_and_save)
        
        # Return immediately with job_id
        # Frontend will poll /jobs/{job_id}/urls to get the URLs
        return ExtractUrlsResponse(
            job_id=job_id,
            urls=[],  # Will be populated when extraction completes
            total=0,
            message="URL extraction started. Poll /jobs/{job_id}/urls for results."
        )
        
    except ValueError as e:
        # Handle validation/DNS errors from storage
        error_msg = str(e)
        logger.error(f"Error creating URL extraction job: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Handle any other exceptions and ensure message is JSON serializable
        error_msg = str(e) if e else "Unknown error occurred"
        logger.error(f"Error creating URL extraction job: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create URL extraction job: {error_msg}"
        )


@app.get("/jobs/{job_id}/urls", response_model=UrlsListResponse)
async def get_extracted_urls_list(job_id: str):
    """Get all extracted URLs for a job with their scrape status"""
    try:
        storage_instance = get_storage()
        
        # Check if job exists
        job = await storage_instance.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get extracted URLs with status
        url_records = await storage_instance.get_extracted_urls(job_id)
        
        # Convert to response format
        urls = [
            UrlStatus(
                url=record.get('url', ''),
                status=record.get('status', 'pending'),
                scraped_at=record.get('scraped_at'),
                error_message=record.get('error_message')
            )
            for record in url_records
        ]
        
        # Count by status
        scraped_count = sum(1 for u in urls if u.status == 'scraped')
        pending_count = sum(1 for u in urls if u.status == 'pending')
        failed_count = sum(1 for u in urls if u.status == 'failed')
        
        return UrlsListResponse(
            job_id=job_id,
            urls=urls,
            total=len(urls),
            scraped_count=scraped_count,
            pending_count=pending_count,
            failed_count=failed_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting extracted URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get extracted URLs: {str(e)}")


@app.post("/jobs/{job_id}/scrape-url", response_model=ScrapeUrlResponse)
async def scrape_single_url(job_id: str, request: ScrapeUrlRequest):
    """Scrape a single restaurant URL"""
    try:
        storage_instance = get_storage()
        worker_instance = get_worker()
        
        # Initialize detail logger
        try:
            from app.scraper_logger import get_scraper_logger
            detail_logger = get_scraper_logger()
            logger.info(f"Detail logger initialized: {detail_logger.log_file if detail_logger else 'None'}")
        except Exception as logger_error:
            logger.error(f"Failed to initialize detail logger: {logger_error}", exc_info=True)
            detail_logger = None
        
        if detail_logger:
            try:
                logger.info(f"Writing to log file: {detail_logger.log_file}")
                detail_logger.log_separator(f"SCRAPING SINGLE URL: {request.url}")
                detail_logger.log_url_visit(request.url, status="STARTING")
                detail_logger.log_restaurant_processing(request.url, "SCRAPE_START", f"Job ID: {job_id}")
                # Force flush to ensure logs are written
                detail_logger.flush()
                logger.info(f"Initial log entries written to {detail_logger.log_file}")
            except Exception as log_error:
                logger.error(f"Failed to write initial log entries: {log_error}", exc_info=True)
        else:
            logger.warning("Detail logger is None - logging will not work")
        
        # Check if job exists
        job = await storage_instance.get_job(job_id)
        if not job:
            error_msg = "Job not found"
            if detail_logger:
                detail_logger.log_error(error_msg, request.url)
            raise HTTPException(status_code=404, detail=error_msg)
        
        # Check if URL exists in extracted URLs
        url_status = await storage_instance.get_url_status(job_id, request.url)
        if not url_status:
            error_msg = "URL not found in extracted URLs for this job"
            if detail_logger:
                detail_logger.log_error(error_msg, request.url)
            raise HTTPException(status_code=404, detail=error_msg)
        
        # Check if already scraped
        if url_status.get('status') == 'scraped':
            if detail_logger:
                detail_logger.log_restaurant_processing(request.url, "ALREADY_SCRAPED", "Returning cached data")
            return ScrapeUrlResponse(
                url=request.url,
                status='scraped',
                data=url_status.get('data')
            )
        
        # Update status to scraping
        await storage_instance.update_url_status(job_id, request.url, 'scraping')
        if detail_logger:
            detail_logger.log_restaurant_processing(request.url, "STATUS_UPDATE", "Status changed to scraping")
        
        try:
            if detail_logger:
                detail_logger.log_restaurant_processing(request.url, "SCRAPING", "Starting scrape with Playwright")
            
            # For OpenTable URLs, extract HTML directly and use the specialized parser
            if 'opentable.com' in request.url.lower() and '/r/' in request.url.lower():
                if detail_logger:
                    detail_logger.log_restaurant_processing(request.url, "PARSING", "Using OpenTable parser with direct HTML extraction")
                
                # Extract HTML directly using Playwright (similar to extract_single_restaurant)
                html_content = None
                from playwright.async_api import async_playwright
                import random
                
                try:
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(
                            headless=True,
                            args=[
                                '--disable-blink-features=AutomationControlled',
                                '--disable-dev-shm-usage',
                                '--no-sandbox',
                                '--disable-setuid-sandbox',
                            ]
                        )
                        
                        context = await browser.new_context(
                            viewport={'width': 1920, 'height': 1080},
                            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            locale='en-US',
                            timezone_id='America/New_York',
                        )
                        
                        page = await context.new_page()
                        
                        # Add stealth scripts
                        await page.add_init_script("""
                            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                            window.chrome = { runtime: {} };
                        """)
                        
                        # Navigate with longer timeout and retry logic
                        max_retries = 3
                        page_loaded = False
                        for retry in range(max_retries):
                            try:
                                await page.goto(
                                    request.url, 
                                    wait_until="domcontentloaded", 
                                    timeout=30000  # Increased to 30 seconds
                                )
                                page_loaded = True
                                break
                            except Exception as goto_error:
                                if retry < max_retries - 1:
                                    logger.warning(f"Page load attempt {retry + 1} failed, retrying: {goto_error}")
                                    await page.wait_for_timeout(1000 * (retry + 1))  # Exponential backoff
                                else:
                                    raise
                        
                        if not page_loaded:
                            raise Exception("Failed to load page after multiple retries")
                        
                        # Wait for dynamic content to load
                        await page.wait_for_timeout(500)  # Increased wait time
                        
                        # Scroll to trigger lazy loading
                        try:
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                            await page.wait_for_timeout(300)  # Increased wait time
                        except:
                            pass
                        
                        # Get full HTML content
                        html_content = await page.content()
                        
                        await context.close()
                        await browser.close()
                        
                        if detail_logger:
                            detail_logger.log_restaurant_processing(request.url, "HTML_FETCHED", 
                                f"Extracted {len(html_content):,} bytes of HTML")
                
                except Exception as html_error:
                    logger.error(f"Failed to extract HTML with Playwright: {html_error}")
                    if detail_logger:
                        detail_logger.log_url_error(request.url, f"HTML extraction failed: {str(html_error)}")
                    
                    # Fallback: Try with standard scraper (which has its own retry logic)
                    logger.warning(f"Falling back to standard scraper for {request.url}")
                    try:
                        scraped_data = await worker_instance.scraper.scrape(
                            request.url,
                            use_javascript=True
                        )
                        # Try to parse with OpenTable parser if we got any content
                        if scraped_data.get('text_content') and len(scraped_data.get('text_content', '')) > 1000:
                            from bs4 import BeautifulSoup
                            # Use text_content as HTML (it's the best we have)
                            html_content = scraped_data.get('text_content', '')
                            soup = BeautifulSoup(html_content, 'html.parser')
                            scraped_data = worker_instance.scraper._parse_opentable_restaurant_page(
                                soup, 
                                request.url, 
                                html_content
                            )
                            if detail_logger:
                                detail_logger.log_restaurant_processing(request.url, "PARSE_SUCCESS_FALLBACK", 
                                    f"Parsed {len(scraped_data)} data fields using fallback method")
                        else:
                            # If fallback also failed, raise the original error
                            raise Exception(f"HTML extraction failed: {str(html_error)}")
                    except Exception as fallback_error:
                        logger.error(f"Fallback scraper also failed: {fallback_error}")
                        raise Exception(f"HTML extraction failed: {str(html_error)}")
                
                # Parse with OpenTable parser
                if html_content and len(html_content) > 1000:  # Ensure we have meaningful content
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    scraped_data = worker_instance.scraper._parse_opentable_restaurant_page(
                        soup, 
                        request.url, 
                        html_content
                    )
                    if detail_logger:
                        detail_logger.log_restaurant_processing(request.url, "PARSE_SUCCESS", 
                            f"Parsed {len(scraped_data)} data fields")
                else:
                    logger.warning(f"HTML content too small ({len(html_content) if html_content else 0} bytes) for {request.url}")
                    if detail_logger:
                        detail_logger.log_warning(f"HTML content too small for parsing", request.url)
                    # Fallback to basic scrape
                    scraped_data = await worker_instance.scraper.scrape(
                        request.url,
                        use_javascript=True
                    )
            else:
                # For non-OpenTable URLs, use standard scraper
                scraped_data = await worker_instance.scraper.scrape(
                    request.url,
                    use_javascript=True
                )
            
            if detail_logger:
                detail_logger.log_restaurant_processing(request.url, "SCRAPE_SUCCESS", 
                    f"Scraped {len(str(scraped_data))} bytes of data")
            
            # Update status to scraped and save data
            await storage_instance.update_url_status(
                job_id,
                request.url,
                'scraped',
                data=scraped_data
            )
            
            if detail_logger:
                detail_logger.log_restaurant_processing(request.url, "SAVED", "Data saved to database")
                detail_logger.log_url_complete(request.url, html_length=len(str(scraped_data)))
                detail_logger.flush()  # Ensure logs are written
            
            return ScrapeUrlResponse(
                url=request.url,
                status='scraped',
                data=scraped_data
            )
            
        except Exception as scrape_error:
            # Log full error with traceback
            import traceback
            error_traceback = traceback.format_exc()
            error_msg = str(scrape_error)
            
            logger.error(f"Scraping failed for {request.url}: {error_msg}")
            logger.error(f"Full traceback:\n{error_traceback}")
            
            if detail_logger:
                detail_logger.log_error(f"Scraping failed: {error_msg}", request.url, scrape_error)
                detail_logger.logger.debug(f"[ERROR TRACEBACK]\n{error_traceback}")
            
            # Update status to failed
            await storage_instance.update_url_status(
                job_id,
                request.url,
                'failed',
                error_message=error_msg
            )
            
            return ScrapeUrlResponse(
                url=request.url,
                status='failed',
                error_message=error_msg
            )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error scraping URL: {str(e)}")
        logger.error(f"Full traceback:\n{error_traceback}")
        if detail_logger:
            detail_logger.log_error(f"Unexpected error: {str(e)}", request.url, e)
            detail_logger.logger.debug(f"[ERROR TRACEBACK]\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Failed to scrape URL: {str(e)}")


@app.post("/jobs/{job_id}/scrape-urls", response_model=ScrapeUrlsResponse)
async def scrape_multiple_urls(job_id: str, request: ScrapeUrlsRequest):
    """Scrape multiple restaurant URLs (bulk operation)"""
    try:
        storage_instance = get_storage()
        worker_instance = get_worker()
        
        # Initialize detail logger
        try:
            from app.scraper_logger import get_scraper_logger
            detail_logger = get_scraper_logger()
            logger.info(f"Detail logger initialized: {detail_logger.log_file if detail_logger else 'None'}")
        except Exception as logger_error:
            logger.error(f"Failed to initialize detail logger: {logger_error}", exc_info=True)
            detail_logger = None
        
        if detail_logger:
            try:
                logger.info(f"Writing to log file: {detail_logger.log_file}")
                detail_logger.log_separator(f"BULK SCRAPING: {len(request.urls)} URLs")
                detail_logger.log_info(f"Starting bulk scrape for job {job_id}")
                # Force flush to ensure logs are written
                detail_logger.flush()
                logger.info(f"Initial log entries written to {detail_logger.log_file}")
            except Exception as log_error:
                logger.error(f"Failed to write initial log entries: {log_error}", exc_info=True)
        else:
            logger.warning("Detail logger is None - logging will not work")
        
        # Check if job exists
        job = await storage_instance.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        scraped = []
        failed = []
        
        # Process URLs sequentially (one at a time for memory efficiency)
        for idx, url in enumerate(request.urls, 1):
            try:
                if detail_logger:
                    detail_logger.log_separator(f"SCRAPING URL {idx}/{len(request.urls)}: {url}")
                
                # Check if URL exists
                url_status = await storage_instance.get_url_status(job_id, url)
                if not url_status:
                    error_msg = "URL not found in extracted URLs"
                    failed.append(ScrapeUrlResponse(
                        url=url,
                        status='failed',
                        error_message=error_msg
                    ))
                    if detail_logger:
                        detail_logger.log_error(error_msg, url)
                    continue
                
                # Skip if already scraped
                if url_status.get('status') == 'scraped':
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "SKIPPED", "Already scraped")
                    scraped.append(ScrapeUrlResponse(
                        url=url,
                        status='scraped',
                        data=url_status.get('data')
                    ))
                    continue
                
                # Update to scraping
                await storage_instance.update_url_status(job_id, url, 'scraping')
                if detail_logger:
                    detail_logger.log_restaurant_processing(url, "SCRAPING", f"URL {idx}/{len(request.urls)}")
                
                # For OpenTable URLs, extract HTML directly and use the specialized parser
                if 'opentable.com' in url.lower() and '/r/' in url.lower():
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "PARSING", "Using OpenTable parser with direct HTML extraction")
                    
                    # Extract HTML directly using Playwright
                    html_content = None
                    from playwright.async_api import async_playwright
                    import random
                    
                    try:
                        async with async_playwright() as p:
                            browser = await p.chromium.launch(
                                headless=True,
                                args=[
                                    '--disable-blink-features=AutomationControlled',
                                    '--disable-dev-shm-usage',
                                    '--no-sandbox',
                                    '--disable-setuid-sandbox',
                                ]
                            )
                            
                            context = await browser.new_context(
                                viewport={'width': 1920, 'height': 1080},
                                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                                locale='en-US',
                                timezone_id='America/New_York',
                            )
                            
                            page = await context.new_page()
                            
                            # Add stealth scripts
                            await page.add_init_script("""
                                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                                window.chrome = { runtime: {} };
                            """)
                            
                            # Navigate with longer timeout and retry logic
                            max_retries = 3
                            page_loaded = False
                            for retry in range(max_retries):
                                try:
                                    await page.goto(
                                        url, 
                                        wait_until="domcontentloaded", 
                                        timeout=30000  # Increased to 30 seconds
                                    )
                                    page_loaded = True
                                    break
                                except Exception as goto_error:
                                    if retry < max_retries - 1:
                                        logger.warning(f"Page load attempt {retry + 1} failed for {url}, retrying: {goto_error}")
                                        await page.wait_for_timeout(1000 * (retry + 1))  # Exponential backoff
                                    else:
                                        raise
                            
                            if not page_loaded:
                                raise Exception("Failed to load page after multiple retries")
                            
                            # Wait for dynamic content to load
                            await page.wait_for_timeout(500)  # Increased wait time
                            
                            # Scroll to trigger lazy loading
                            try:
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                                await page.wait_for_timeout(300)  # Increased wait time
                            except:
                                pass
                            
                            # Get full HTML content
                            html_content = await page.content()
                            
                            await context.close()
                            await browser.close()
                            
                            if detail_logger:
                                detail_logger.log_restaurant_processing(url, "HTML_FETCHED", 
                                    f"Extracted {len(html_content):,} bytes of HTML")
                    
                    except Exception as html_error:
                        logger.error(f"Failed to extract HTML with Playwright for {url}: {html_error}")
                        if detail_logger:
                            detail_logger.log_url_error(url, f"HTML extraction failed: {str(html_error)}")
                        
                        # Fallback: Try with standard scraper (which has its own retry logic)
                        logger.warning(f"Falling back to standard scraper for {url}")
                        try:
                            scraped_data = await worker_instance.scraper.scrape(
                                url,
                                use_javascript=True
                            )
                            # Try to parse with OpenTable parser if we got any content
                            if scraped_data.get('text_content') and len(scraped_data.get('text_content', '')) > 1000:
                                from bs4 import BeautifulSoup
                                # Use text_content as HTML (it's the best we have)
                                html_content = scraped_data.get('text_content', '')
                                soup = BeautifulSoup(html_content, 'html.parser')
                                scraped_data = worker_instance.scraper._parse_opentable_restaurant_page(
                                    soup,
                                    url,
                                    html_content
                                )
                                if detail_logger:
                                    detail_logger.log_restaurant_processing(url, "PARSE_SUCCESS_FALLBACK", 
                                        f"Parsed {len(scraped_data)} data fields using fallback method")
                            else:
                                # If fallback also failed, raise the original error
                                raise Exception(f"HTML extraction failed: {str(html_error)}")
                        except Exception as fallback_error:
                            logger.error(f"Fallback scraper also failed for {url}: {fallback_error}")
                            raise Exception(f"HTML extraction failed: {str(html_error)}")
                    
                    # Parse with OpenTable parser (only if we got HTML from direct extraction)
                    if html_content and len(html_content) > 1000:  # Ensure we have meaningful content
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html_content, 'html.parser')
                        scraped_data = worker_instance.scraper._parse_opentable_restaurant_page(
                            soup,
                            url,
                            html_content
                        )
                        if detail_logger:
                            detail_logger.log_restaurant_processing(url, "PARSE_SUCCESS", 
                                f"Parsed {len(scraped_data)} data fields")
                    else:
                        logger.warning(f"HTML content too small ({len(html_content) if html_content else 0} bytes) for {url}")
                        if detail_logger:
                            detail_logger.log_warning(f"HTML content too small for parsing", url)
                        # Fallback to basic scrape
                        scraped_data = await worker_instance.scraper.scrape(
                            url,
                            use_javascript=True
                        )
                else:
                    # For non-OpenTable URLs, use standard scraper
                    scraped_data = await worker_instance.scraper.scrape(
                        url,
                        use_javascript=True
                    )
                
                # Update status and save data
                await storage_instance.update_url_status(
                    job_id,
                    url,
                    'scraped',
                    data=scraped_data
                )
                
                if detail_logger:
                    detail_logger.log_restaurant_processing(url, "SCRAPED", "Successfully scraped and saved")
                    detail_logger.flush()  # Ensure logs are written
                
                scraped.append(ScrapeUrlResponse(
                    url=url,
                    status='scraped',
                    data=scraped_data
                ))
                
            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                error_msg = str(e)
                
                logger.error(f"Failed to scrape {url}: {error_msg}")
                logger.error(f"Full traceback:\n{error_traceback}")
                
                if detail_logger:
                    detail_logger.log_error(f"Scraping failed: {error_msg}", url, e)
                    detail_logger.logger.debug(f"[ERROR TRACEBACK]\n{error_traceback}")
                
                await storage_instance.update_url_status(
                    job_id,
                    url,
                    'failed',
                    error_message=error_msg
                )
                
                failed.append(ScrapeUrlResponse(
                    url=url,
                    status='failed',
                    error_message=error_msg
                ))
        
        if detail_logger:
            detail_logger.log_separator(f"BULK SCRAPING COMPLETE")
            detail_logger.log_info(f"Success: {len(scraped)}, Failed: {len(failed)}")
        
        return ScrapeUrlsResponse(
            scraped=scraped,
            failed=failed,
            total=len(request.urls),
            success_count=len(scraped),
            failed_count=len(failed)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error scraping URLs: {str(e)}")
        logger.error(f"Full traceback:\n{error_traceback}")
        if detail_logger:
            detail_logger.log_error(f"Unexpected error: {str(e)}", None, e)
            detail_logger.logger.debug(f"[ERROR TRACEBACK]\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Failed to scrape URLs: {str(e)}")
