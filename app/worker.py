import asyncio
import logging
import re
from typing import Dict, Any, List
from datetime import datetime
from .scraper import WebScraper
from .crawler import WebCrawler
from .ai_filter import AIFilter
from .storage import Storage
from .models import JobStatus

logger = logging.getLogger(__name__)


class ScraperWorker:
    def __init__(self, storage_instance=None):
        self.scraper = WebScraper()
        self.ai_filter = AIFilter()
        self.storage = storage_instance or Storage()

    async def process_job(self, job_id: str) -> None:
        """Process a scraping job"""
        logger.info(f"Starting to process job {job_id}")
        
        # Initialize detailed logger for this job
        try:
            from app.scraper_logger import get_scraper_logger
            detail_logger = get_scraper_logger()
            detail_logger.log_separator(f"PROCESSING JOB: {job_id}")
        except Exception as e:
            logger.warning(f"Could not initialize detailed logger: {e}")
            detail_logger = None
        
        errors = []
        
        try:
            # Update job status to running
            await self.storage.update_job(job_id, {'status': JobStatus.RUNNING.value})
            if detail_logger:
                detail_logger.log_restaurant_processing("", "JOB_STATUS", f"Status updated to RUNNING")

            # Get job details
            job = await self.storage.get_job(job_id)
            if not job:
                raise Exception(f"Job {job_id} not found")
            
            job_mode = 'crawl' if job.get('crawl_mode') else 'single'
            job_url = job.get('url', '')
            job_query = job.get('search_query', '')
            
            logger.info(f"Job: mode={job_mode}, url={job_url}, query={job_query}")
            
            if detail_logger:
                detail_logger.log_restaurant_processing(job_url or "N/A", "JOB_INFO", 
                    f"Mode: {job_mode}, URL: {job_url}, Query: {job_query}")
                if job_url:
                    detail_logger.log_url_visit(job_url, status="JOB_STARTED")

            filtered_data = []
            use_javascript = job.get('use_javascript', False)

            # Check if this is a crawl job or single URL job
            if detail_logger:
                if job.get('crawl_mode'):
                    detail_logger.log_restaurant_processing(job_url or "N/A", "JOB_TYPE", "CRAWL MODE")
                else:
                    detail_logger.log_restaurant_processing(job_url or "N/A", "JOB_TYPE", "SINGLE URL MODE")
            
            if job.get('crawl_mode'):
                filtered_data = await self._process_crawl_job(job, errors)
            else:
                filtered_data = await self._process_single_url_job(job, errors)
            
            if detail_logger:
                detail_logger.log_restaurant_processing(job_url or "N/A", "JOB_COMPLETE", 
                    f"Scraped {len(filtered_data)} items")

            # If no data scraped, report the errors
            if not filtered_data:
                error_msg = "No data could be scraped. "
                if errors:
                    error_msg += "Errors: " + "; ".join(errors[:3])  # First 3 errors
                if detail_logger:
                    detail_logger.log_warning(f"No data scraped. Errors: {error_msg}", job_url or "N/A")
                else:
                    error_msg += "The target site may be blocking automated access."
                
                await self.storage.update_job(job_id, {
                    'status': JobStatus.FAILED.value,
                    'error': error_msg
                })
                return

            # Extract from individual pages if requested and we have restaurant data
            if job.get('extract_individual_pages'):
                filtered_data = await self._extract_from_individual_pages_if_needed(filtered_data, job, errors)

            # Apply AI filtering if prompt provided
            if job.get('ai_prompt') and filtered_data:
                filtered_data = await self._apply_ai_filter(filtered_data, job['ai_prompt'], errors)

            # Save results - ensure each item is a dict with URL
            logger.info(f"Saving {len(filtered_data)} results for job {job_id}")
            
            # Debug: Log what we're saving
            if filtered_data:
                logger.info(f"Sample result structure: {list(filtered_data[0].keys())[:10] if isinstance(filtered_data[0], dict) else type(filtered_data[0])}")
                # Count how many have URLs
                urls_count = sum(1 for item in filtered_data if isinstance(item, dict) and item.get('url'))
                logger.info(f"Results with URLs: {urls_count}/{len(filtered_data)}")
                
                # Log first few URLs to verify
                urls_found = [item.get('url') for item in filtered_data[:5] if isinstance(item, dict) and item.get('url')]
                logger.info(f"First 5 URLs being saved: {urls_found}")
            
            # Ensure all items are dicts and have URLs
            cleaned_data = []
            for item in filtered_data:
                if isinstance(item, dict):
                    # Ensure URL exists
                    if not item.get('url'):
                        item['url'] = item.get('extracted_url') or item.get('website') or 'N/A'
                    cleaned_data.append(item)
                else:
                    logger.warning(f"Skipping non-dict item: {type(item)}")
            
            if len(cleaned_data) != len(filtered_data):
                logger.warning(f"Cleaned {len(filtered_data)} items to {len(cleaned_data)} valid dicts")
            
            await self.storage.save_results(job_id, cleaned_data)

            # Update job status to completed
            await self.storage.update_job(job_id, {
                'status': JobStatus.COMPLETED.value,
                'completed_at': datetime.utcnow().isoformat()
            })
            logger.info(f"Job {job_id} completed with {len(filtered_data)} results")
            
            # Log completion to detailed logger
            try:
                from app.scraper_logger import get_scraper_logger
                detail_logger = get_scraper_logger()
                job_url_local = locals().get('job_url', 'N/A') if 'job_url' in locals() else 'N/A'
                detail_logger.log_restaurant_processing(job_url_local, "JOB_FINAL_STATUS", 
                    f"COMPLETED with {len(filtered_data)} results")
                detail_logger.log_separator(f"JOB {job_id} COMPLETED")
            except:
                pass

        except Exception as e:
            error_msg = str(e)
            if errors:
                error_msg += " | Additional errors: " + "; ".join(errors[:2])
            
            logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
            
            # Log to detailed logger
            try:
                from app.scraper_logger import get_scraper_logger
                detail_logger = get_scraper_logger()
                job_url_local = locals().get('job_url', 'N/A') if 'job_url' in locals() else 'N/A'
                detail_logger.log_error(f"Job {job_id} failed: {error_msg}", job_url_local, e)
                detail_logger.log_separator(f"JOB {job_id} FAILED")
            except:
                pass
            
            try:
                await self.storage.update_job(job_id, {
                    'status': JobStatus.FAILED.value,
                    'error': error_msg[:500]  # Limit error length
                })
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")

    async def _process_crawl_job(self, job: Dict, errors: List[str]) -> List[Dict]:
        """Process a crawl mode job"""
        crawler = WebCrawler(
            max_pages=job.get('max_pages', 10),
            max_depth=job.get('max_depth', 2),
            same_domain=job.get('same_domain', True)
        )
        
        use_javascript = job.get('use_javascript', False)
        search_query = job.get('search_query')
        
        try:
            if search_query:
                logger.info(f"Crawling from search: {search_query}")
                
                # First try with JavaScript if enabled
                if use_javascript:
                    try:
                        return await crawler.crawl_from_search(
                            search_query=search_query,
                            max_pages=job.get('max_pages', 10),
                            use_javascript=True
                        )
                    except Exception as e:
                        errors.append(f"JS crawl failed: {str(e)[:100]}")
                        logger.warning(f"JavaScript crawl failed, trying without: {e}")
                
                # Try without JavaScript
                return await crawler.crawl_from_search(
                    search_query=search_query,
                    max_pages=job.get('max_pages', 10),
                    use_javascript=False
                )
            else:
                # Crawl from URL
                start_urls = [job['url']] if job.get('url') else []
                if not start_urls:
                    raise Exception("No URL or search query provided")
                
                return await crawler.crawl(
                    start_urls=start_urls,
                    use_javascript=use_javascript
                )
        except Exception as e:
            errors.append(str(e)[:200])
            logger.error(f"Crawl failed: {e}")
            return []

    async def _process_single_url_job(self, job: Dict, errors: List[str]) -> List[Dict]:
        """Process a single URL scrape job"""
        if not job.get('url'):
            raise Exception("URL is required for single page scraping")
        
        url = job['url']
        use_javascript = job.get('use_javascript', False)
        extract_individual_pages = job.get('extract_individual_pages', True)  # DEFAULT: enabled
        
        logger.info(f"Scraping: {url} (JS: {use_javascript}, Individual Pages: {extract_individual_pages})")
        
        # Log to detailed logger
        try:
            from app.scraper_logger import get_scraper_logger
            detail_logger = get_scraper_logger()
            detail_logger.log_separator(f"PROCESSING SINGLE URL: {url}")
            detail_logger.log_restaurant_processing(url, "SCRAPING_START", 
                f"JS: {use_javascript}, Individual Pages: {extract_individual_pages}")
        except:
            detail_logger = None
        
        # Check if this is a restaurant listing page
        is_restaurant_listing = self._is_restaurant_listing_page(url)
        
        # Debug logging for detection
        logger.info(f"Listing page detection for {url}: {is_restaurant_listing}")
        if detail_logger:
            detail_logger.log_restaurant_processing(url, "PAGE_TYPE", 
                f"Is listing page: {is_restaurant_listing}")
            # Log detection details
            url_lower = url.lower()
            detection_details = {
                "has_opentable": "opentable.com" in url_lower,
                "has_r_path": "/r/" in url_lower,
                "has_metro": "/metro/" in url_lower,
                "has_region": "/region/" in url_lower,
                "has_neighborhood": "/neighborhood/" in url_lower,
            }
            detail_logger.log_restaurant_processing(url, "DETECTION_DETAILS", str(detection_details))
        
        # DEFAULT BEHAVIOR: For restaurant listing pages, always extract from individual pages (unless explicitly disabled)
        if is_restaurant_listing and extract_individual_pages:
            use_javascript = True  # Individual pages need JS
            if detail_logger:
                detail_logger.log_restaurant_processing(url, "PROCESSING_MODE", 
                    "Using individual page extraction")
        
        # If individual page extraction is enabled, use the new process
        if extract_individual_pages and is_restaurant_listing:
            if detail_logger:
                detail_logger.log_separator(f"EXTRACTING RESTAURANT URLS FROM LISTING PAGE")
                detail_logger.log_restaurant_processing(url, "LISTING_PAGE_DETECTED", 
                    "Starting URL extraction and individual page visits")
            result = await self._process_restaurant_listing_with_individual_pages(url, use_javascript, errors)
            if detail_logger:
                detail_logger.log_restaurant_processing(url, "PROCESSING_COMPLETE", 
                    f"Extracted {len(result)} restaurants from individual pages")
                detail_logger.log_separator()
            return result
        elif is_restaurant_listing and not extract_individual_pages:
            if detail_logger:
                detail_logger.log_warning(f"Listing page detected but individual page extraction is disabled", url)
            logger.warning(f"Listing page detected but individual page extraction is disabled for {url}")
        
        # Check for special site handling
        if 'opentable.com' in url.lower():
            use_javascript = True  # OpenTable always needs JS
            logger.info("Detected OpenTable - using JavaScript rendering")
            if detail_logger:
                detail_logger.log_restaurant_processing(url, "SITE_DETECTED", "OpenTable - using JS")
        
        try:
            # Try with JavaScript first if enabled
            if use_javascript:
                try:
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "SCRAPING_METHOD", "JavaScript (Playwright)")
                    data = await self.scraper.scrape(url, use_javascript=True)
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "SCRAPING_SUCCESS", 
                            f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                    return [data]
                except Exception as e:
                    errors.append(f"JS scrape failed: {str(e)[:100]}")
                    logger.warning(f"JavaScript scraping failed, trying static: {e}")
                    if detail_logger:
                        detail_logger.log_warning(f"JS scrape failed, trying static: {str(e)[:100]}", url)
            
            # Try static scraping
            if detail_logger:
                detail_logger.log_restaurant_processing(url, "SCRAPING_METHOD", "Static (httpx)")
            data = await self.scraper.scrape(url, use_javascript=False)
            if detail_logger:
                detail_logger.log_restaurant_processing(url, "SCRAPING_SUCCESS", 
                    f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            return [data]
            
        except Exception as e:
            errors.append(str(e)[:200])
            logger.error(f"Scraping failed for {url}: {e}")
            if detail_logger:
                detail_logger.log_error(f"Scraping failed: {str(e)}", url, e)
            return []
    
    def _is_restaurant_listing_page(self, url: str) -> bool:
        """Check if URL is a restaurant listing page"""
        url_lower = url.lower()
        
        # Special handling for OpenTable - check first before regex
        if 'opentable.com' in url_lower:
            # Individual restaurant pages have /r/ in the path
            if '/r/' in url_lower:
                logger.debug(f"OpenTable URL {url} is an individual restaurant page (has /r/)")
                return False  # This is an individual restaurant page
            
            # OpenTable listing pages - check for specific patterns
            listing_indicators = ['/metro/', '/region/', '/neighborhood/', '/s?', '/s?dateTime=']
            for indicator in listing_indicators:
                if indicator in url_lower:
                    logger.debug(f"OpenTable URL {url} detected as listing page (has {indicator})")
                    return True
            
            # If it's OpenTable but not a restaurant page and not excluded pages, it's likely a listing
            excluded = ['/restaurant/', '/profile/', '/about', '/help', '/contact', '/terms', '/privacy', '/gift-cards']
            if not any(excluded_page in url_lower for excluded_page in excluded):
                # Additional check: if URL contains "restaurants" (plural), it's likely a listing
                if 'restaurants' in url_lower:
                    logger.debug(f"OpenTable URL {url} detected as listing page (contains 'restaurants')")
                    return True
                # Default: treat as listing if not excluded
                logger.debug(f"OpenTable URL {url} detected as listing page (default for non-excluded pages)")
                return True
        
        # Check URL patterns with regex for other sites
        listing_patterns = [
            'yelp.com/search',
            'tripadvisor.com/search',
            'google.com/search.*restaurant',
            'google.com/maps/search',
            '/search.*restaurant',
            '/search.*food',
            '/search.*dining',
        ]
        
        for pattern in listing_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    async def _process_restaurant_listing_with_individual_pages(
        self,
        listing_url: str,
        use_javascript: bool,
        errors: List[str]
    ) -> List[Dict]:
        """
        NEW DEFAULT PROCESS for restaurant listing pages:
        1. Extract restaurant URLs from listing page
        2. Visit each individual restaurant page
        3. Extract ALL data from individual pages
        4. Return combined list
        """
        logger.info(f"Using default process: Extract URLs → Visit individual pages → Get complete data")
        
        try:
            # STEP 1: Extract restaurant URLs from listing page
            logger.info("Step 1: Extracting restaurant URLs from listing page...")
            restaurant_urls = await self.scraper.extract_restaurant_urls_from_listing(
                listing_url=listing_url,
                use_javascript=use_javascript
            )
            
            if not restaurant_urls:
                logger.warning("No restaurant URLs found in listing page, falling back to regular scraping")
                # Fallback to regular scraping
                data = await self.scraper.scrape(listing_url, use_javascript=use_javascript)
                return [data]
            
            logger.info(f"Step 1 Complete: Found {len(restaurant_urls)} restaurant URLs")
            
            # STEP 2: Create minimal restaurant objects with just URLs
            restaurants_with_urls = [
                {'url': url, 'source_listing_url': listing_url, 'extracted_url': url}
                for url in restaurant_urls
            ]
            
            # STEP 3: Visit each individual page and extract ALL data
            logger.info(f"Step 2: Visiting {len(restaurants_with_urls)} individual restaurant pages...")
            try:
                from app.scraper_logger import get_scraper_logger
                detail_logger = get_scraper_logger()
                detail_logger.log_separator(f"VISITING {len(restaurants_with_urls)} INDIVIDUAL RESTAURANT PAGES")
            except ImportError:
                detail_logger = None
            
            logger.info(f"About to call extract_from_individual_pages with {len(restaurants_with_urls)} restaurants")
            detailed_restaurants = await self.scraper.extract_from_individual_pages(
                restaurants=restaurants_with_urls,
                use_javascript=True,  # Always use JS for individual pages
                max_concurrent=10  # Increased concurrency for better performance (like Apify)
            )
            
            logger.info(f"Step 2 Complete: Extracted data from {len(detailed_restaurants)} individual pages")
            if len(detailed_restaurants) == 0:
                logger.warning(f"⚠️ WARNING: No restaurants extracted! Expected {len(restaurants_with_urls)}")
                # Return ALL extracted URLs even if scraping failed - at least they'll be in CSV
                logger.info(f"Returning {len(restaurants_with_urls)} URLs (scraping failed but URLs will be in CSV)")
                return restaurants_with_urls
            elif len(detailed_restaurants) < len(restaurants_with_urls):
                logger.warning(f"⚠️ WARNING: Only extracted {len(detailed_restaurants)}/{len(restaurants_with_urls)} restaurants")
                # Add missing URLs as entries with just URL (no data)
                scraped_urls = {r.get('url', '').lower() for r in detailed_restaurants if r.get('url')}
                for restaurant in restaurants_with_urls:
                    if restaurant.get('url', '').lower() not in scraped_urls:
                        # Add URL entry even if scraping failed
                        detailed_restaurants.append({
                            'url': restaurant.get('url'),
                            'source_listing_url': listing_url,
                            'extracted_url': restaurant.get('url'),
                            'scraping_status': 'failed',
                            'error': 'Could not extract data from this URL'
                        })
            
            # Ensure all restaurants have URL field
            for restaurant in detailed_restaurants:
                if 'url' not in restaurant or not restaurant.get('url'):
                    restaurant['url'] = restaurant.get('extracted_url') or restaurant.get('website') or 'N/A'
                if 'source_listing_url' not in restaurant:
                    restaurant['source_listing_url'] = listing_url
            
            # CRITICAL: Ensure ALL extracted URLs are included, even if scraping failed
            # Create a set of URLs we already have
            existing_urls = {r.get('url', '').lower() for r in detailed_restaurants if r.get('url')}
            
            # Add any missing URLs as entries (even if scraping failed)
            for url in restaurant_urls:
                url_lower = url.lower()
                if url_lower not in existing_urls:
                    logger.info(f"Adding missing URL to results: {url}")
                    detailed_restaurants.append({
                        'url': url,
                        'source_listing_url': listing_url,
                        'extracted_url': url,
                        'scraping_status': 'not_scraped',
                        'note': 'URL extracted from listing page but individual page not scraped'
                    })
            
            # Log URLs
            logger.info(f"📋 Final results: {len(detailed_restaurants)} restaurants (from {len(restaurant_urls)} extracted URLs)")
            logger.info(f"📋 Extracted URLs ({len(restaurant_urls)} total):")
            for idx, url in enumerate(restaurant_urls[:20], 1):
                logger.info(f"   {idx}. {url}")
            if len(restaurant_urls) > 20:
                logger.info(f"   ... and {len(restaurant_urls) - 20} more URLs")
            
            # Final validation: ensure we have at least as many results as URLs
            if len(detailed_restaurants) < len(restaurant_urls):
                logger.warning(f"⚠️ Still missing {len(restaurant_urls) - len(detailed_restaurants)} URLs in results!")
            
            return detailed_restaurants
            
        except Exception as e:
            error_msg = f"Restaurant listing process failed: {str(e)[:200]}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
            # Fallback to regular scraping
            try:
                data = await self.scraper.scrape(listing_url, use_javascript=use_javascript)
                return [data]
            except:
                return []

    async def _apply_ai_filter(self, data: List[Dict], prompt: str, errors: List[str]) -> List[Dict]:
        """Apply AI filtering to scraped data"""
        logger.info(f"Applying AI filter to {len(data)} items")
        
        ai_filtered = []
        for idx, page_data in enumerate(data):
            try:
                result = await self.ai_filter.filter_and_structure(page_data, prompt)
                if isinstance(result, list):
                    ai_filtered.extend(result)
                else:
                    ai_filtered.append(result)
            except Exception as e:
                errors.append(f"AI filter error on item {idx+1}: {str(e)[:50]}")
                logger.warning(f"AI filtering failed for item {idx + 1}: {e}")
                # Include original data if AI fails
                ai_filtered.append(page_data)
        
        logger.info(f"AI filtering complete: {len(ai_filtered)} items")
        return ai_filtered if ai_filtered else data

    async def _extract_from_individual_pages_if_needed(
        self, 
        data: List[Dict], 
        job: Dict, 
        errors: List[str]
    ) -> List[Dict]:
        """
        Extract detailed data from individual restaurant pages if:
        1. extract_individual_pages is enabled (DEFAULT: True)
        2. We have restaurant data with URLs
        """
        # Default to True if not specified (new default behavior)
        if job.get('extract_individual_pages') is False:
            return data
        
        # Check if we have restaurant data
        restaurants = []
        for item in data:
            # Check if this looks like restaurant data
            if isinstance(item, dict):
                # Check if it has restaurant indicators
                has_restaurant_data = (
                    'restaurants' in item or
                    'businesses' in item or
                    (item.get('name') and (
                        'restaurant' in str(item.get('title', '')).lower() or
                        'restaurant' in str(item.get('url', '')).lower() or
                        any(keyword in str(item).lower() for keyword in ['yelp', 'opentable', 'dining', 'food'])
                    ))
                )
                
                if has_restaurant_data:
                    # Extract restaurants from the item
                    if 'restaurants' in item:
                        restaurants.extend(item['restaurants'])
                    elif 'businesses' in item:
                        restaurants.extend(item['businesses'])
                    else:
                        # Single restaurant object
                        restaurants.append(item)
        
        if not restaurants:
            logger.info("No restaurant data found to extract from individual pages")
            return data
        
        # Filter restaurants that have URLs
        restaurants_with_urls = []
        for restaurant in restaurants:
            if isinstance(restaurant, dict):
                url = restaurant.get('url') or restaurant.get('website') or restaurant.get('yelp_url')
                if url:
                    restaurants_with_urls.append(restaurant)
        
        if not restaurants_with_urls:
            logger.info("No restaurant URLs found for individual page extraction")
            return data
        
        logger.info(f"Extracting detailed data from {len(restaurants_with_urls)} individual restaurant pages")
        
        try:
            use_javascript = job.get('use_javascript', True)  # Default to True for individual pages
            detailed_restaurants = await self.scraper.extract_from_individual_pages(
                restaurants=restaurants_with_urls,
                use_javascript=use_javascript,
                max_concurrent=5
            )
            
            logger.info(f"Successfully extracted data from {len(detailed_restaurants)} individual pages")
            
            # Replace original restaurant data with detailed data
            # Keep non-restaurant data items
            result = []
            restaurant_names = {r.get('name', '').lower() for r in detailed_restaurants if r.get('name')}
            
            for item in data:
                if isinstance(item, dict):
                    # Check if this item contains restaurants we processed
                    if 'restaurants' in item:
                        # Replace restaurants list
                        item['restaurants'] = detailed_restaurants
                        result.append(item)
                    elif 'businesses' in item:
                        item['businesses'] = detailed_restaurants
                        result.append(item)
                    elif item.get('name', '').lower() in restaurant_names:
                        # This is a restaurant we processed, replace with detailed version
                        detailed = next((r for r in detailed_restaurants if r.get('name', '').lower() == item.get('name', '').lower()), item)
                        result.append(detailed)
                    else:
                        # Keep non-restaurant items as-is
                        result.append(item)
                else:
                    result.append(item)
            
            # Add any detailed restaurants that weren't in original data
            existing_names = {r.get('name', '').lower() for r in result if isinstance(r, dict) and r.get('name')}
            for restaurant in detailed_restaurants:
                if restaurant.get('name', '').lower() not in existing_names:
                    result.append(restaurant)
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to extract from individual pages: {str(e)[:200]}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
            # Return original data if extraction fails
            return data
