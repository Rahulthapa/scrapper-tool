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
        errors = []
        
        try:
            # Update job status to running
            await self.storage.update_job(job_id, {'status': JobStatus.RUNNING.value})

            # Get job details
            job = await self.storage.get_job(job_id)
            if not job:
                raise Exception(f"Job {job_id} not found")
            
            logger.info(f"Job: mode={'crawl' if job.get('crawl_mode') else 'single'}, url={job.get('url')}, query={job.get('search_query')}")

            filtered_data = []
            use_javascript = job.get('use_javascript', False)

            # Check if this is a crawl job or single URL job
            if job.get('crawl_mode'):
                filtered_data = await self._process_crawl_job(job, errors)
            else:
                filtered_data = await self._process_single_url_job(job, errors)

            # If no data scraped, report the errors
            if not filtered_data:
                error_msg = "No data could be scraped. "
                if errors:
                    error_msg += "Errors: " + "; ".join(errors[:3])  # First 3 errors
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

            # Save results
            logger.info(f"Saving {len(filtered_data)} results for job {job_id}")
            await self.storage.save_results(job_id, filtered_data)

            # Update job status to completed
            await self.storage.update_job(job_id, {
                'status': JobStatus.COMPLETED.value,
                'completed_at': datetime.utcnow().isoformat()
            })
            logger.info(f"Job {job_id} completed with {len(filtered_data)} results")

        except Exception as e:
            error_msg = str(e)
            if errors:
                error_msg += " | Additional errors: " + "; ".join(errors[:2])
            
            logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
            
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
        
        # Check if this is a restaurant listing page
        is_restaurant_listing = self._is_restaurant_listing_page(url)
        
        # DEFAULT BEHAVIOR: For restaurant listing pages, always extract from individual pages (unless explicitly disabled)
        if is_restaurant_listing and extract_individual_pages:
            use_javascript = True  # Individual pages need JS
        
        # If individual page extraction is enabled, use the new process
        if extract_individual_pages and is_restaurant_listing:
            return await self._process_restaurant_listing_with_individual_pages(url, use_javascript, errors)
        
        # Check for special site handling
        if 'opentable.com' in url.lower():
            use_javascript = True  # OpenTable always needs JS
            logger.info("Detected OpenTable - using JavaScript rendering")
        
        try:
            # Try with JavaScript first if enabled
            if use_javascript:
                try:
                    data = await self.scraper.scrape(url, use_javascript=True)
                    return [data]
                except Exception as e:
                    errors.append(f"JS scrape failed: {str(e)[:100]}")
                    logger.warning(f"JavaScript scraping failed, trying static: {e}")
            
            # Try static scraping
            data = await self.scraper.scrape(url, use_javascript=False)
            return [data]
            
        except Exception as e:
            errors.append(str(e)[:200])
            logger.error(f"Scraping failed for {url}: {e}")
            return []
    
    def _is_restaurant_listing_page(self, url: str) -> bool:
        """Check if URL is a restaurant listing page"""
        url_lower = url.lower()
        
        # Check URL patterns
        listing_patterns = [
            'yelp.com/search',
            'opentable.com/s',
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
                {'url': url, 'source_listing_url': listing_url}
                for url in restaurant_urls
            ]
            
            # STEP 3: Visit each individual page and extract ALL data
            logger.info(f"Step 2: Visiting {len(restaurants_with_urls)} individual restaurant pages...")
            detailed_restaurants = await self.scraper.extract_from_individual_pages(
                restaurants=restaurants_with_urls,
                use_javascript=True,  # Always use JS for individual pages
                max_concurrent=5
            )
            
            logger.info(f"Step 2 Complete: Extracted data from {len(detailed_restaurants)} individual pages")
            
            # STEP 4: Return combined list
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
