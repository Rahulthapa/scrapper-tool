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

from .models import ScrapeJobCreate, ScrapeJob, ScrapeResult, JobStatus, ParseHTMLRequest, ExtractInternalDataRequest, ExtractFromIndividualPagesRequest
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


@app.get("/debug")
async def debug_info():
    """Debug endpoint to check configuration and database connection"""
    import os
    
    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": {
            "SUPABASE_URL": "SET" if os.getenv("SUPABASE_URL") else "NOT SET",
            "SUPABASE_ANON_KEY": "SET" if os.getenv("SUPABASE_ANON_KEY") else "NOT SET",
            "GEMINI_API_KEY": "SET" if os.getenv("GEMINI_API_KEY") else "NOT SET",
            "OPENAI_API_KEY": "SET" if os.getenv("OPENAI_API_KEY") else "NOT SET",
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
    """Check if Yelp API is configured."""
    import os
    has_key = bool(os.getenv("YELP_API_KEY"))
    return JSONResponse(status_code=200, content={
        "configured": has_key,
        "message": "Yelp API is ready" if has_key else "YELP_API_KEY not set. Get your free key at https://www.yelp.com/developers/v3/manage_app"
    })


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
        
        # Validate: need either URL or search_query
        if not job_data.get('url') and not job_data.get('search_query'):
            raise HTTPException(
                status_code=400,
                detail="Either 'url' or 'search_query' must be provided"
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
    
    # Get results
    results = await storage_instance.get_results(job_id)
    data = [result.get('data', result) for result in results]
    
    if not data:
        raise HTTPException(status_code=404, detail="No results found for this job")
    
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
