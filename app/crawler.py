import asyncio
from typing import Dict, Any, List, Set, Optional
from urllib.parse import urljoin, urlparse, urlunparse, quote_plus
from collections import deque
import re
import logging
from .scraper import WebScraper

logger = logging.getLogger(__name__)


class WebCrawler:
    """
    General-purpose web crawler that can discover and scrape multiple pages
    """
    
    def __init__(self, max_pages: int = 10, max_depth: int = 2, same_domain: bool = True):
        self.scraper = WebScraper()
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.same_domain = same_domain
        self.visited_urls: Set[str] = set()
        self.results: List[Dict[str, Any]] = []
        
    async def crawl(
        self, 
        start_urls: List[str], 
        use_javascript: bool = False,
        keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Crawl the web starting from seed URLs
        """
        self.visited_urls.clear()
        self.results.clear()
        
        # Normalize and validate start URLs
        seed_urls = []
        for url in start_urls:
            normalized = self._normalize_url(url)
            if normalized and normalized not in self.visited_urls:
                seed_urls.append(normalized)
                self.visited_urls.add(normalized)
        
        if not seed_urls:
            raise ValueError("No valid starting URLs provided")
        
        # Crawl queue: (url, depth)
        queue = deque([(url, 0) for url in seed_urls])
        
        while queue and len(self.results) < self.max_pages:
            url, depth = queue.popleft()
            
            if depth > self.max_depth:
                continue
            
            try:
                logger.info(f"Crawling: {url} (depth: {depth})")
                # Scrape the page
                page_data = await self.scraper.scrape(url, use_javascript=use_javascript)
                
                # Filter by keywords if provided
                if keywords:
                    page_text = page_data.get('text_content', '').lower()
                    if not any(keyword.lower() in page_text for keyword in keywords):
                        continue
                
                # Add to results
                self.results.append({
                    **page_data,
                    'crawl_depth': depth,
                    'discovered_from': url if depth > 0 else None
                })
                
                logger.info(f"Successfully scraped: {url} ({len(self.results)}/{self.max_pages} pages)")
                
                # Extract links for further crawling
                if depth < self.max_depth and len(self.results) < self.max_pages:
                    links = page_data.get('links', [])
                    base_domain = self._get_domain(url)
                    
                    for link_info in links:
                        link_url = link_info.get('href') if isinstance(link_info, dict) else link_info
                        
                        if not link_url:
                            continue
                        
                        full_url = urljoin(url, link_url)
                        normalized = self._normalize_url(full_url)
                        
                        if not normalized:
                            continue
                        
                        if self._should_follow_link(normalized, base_domain):
                            if normalized not in self.visited_urls:
                                self.visited_urls.add(normalized)
                                queue.append((normalized, depth + 1))
                
                # Small delay to be respectful
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Error crawling {url}: {str(e)}")
                continue
        
        return self.results
    
    async def crawl_from_search(
        self,
        search_query: str,
        max_pages: int = 10,
        use_javascript: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Crawl the web based on a search query.
        Uses multiple strategies to find relevant pages.
        """
        logger.info(f"Starting search-based crawl for: {search_query}")
        
        # Detect if this is a local business search
        is_local_search = self._is_local_business_search(search_query)
        
        result_urls = []
        
        if is_local_search:
            # For local business searches, use business directories directly
            logger.info("Detected local business search, using business directories")
            result_urls = await self._get_local_business_urls(search_query, max_pages)
        
        if not result_urls:
            # Try web search engines
            logger.info("Trying web search engines")
            result_urls = await self._search_web(search_query, max_pages)
        
        if not result_urls:
            raise ValueError(
                f"Could not find results for '{search_query}'. "
                "Try providing a specific URL instead, or rephrase your search query."
            )
        
        logger.info(f"Found {len(result_urls)} URLs to crawl")
        
        # Crawl the discovered URLs
        self.max_pages = max_pages
        # Don't filter by keywords for search results - AI will filter later
        return await self.crawl(result_urls, use_javascript=use_javascript, keywords=None)
    
    def _is_local_business_search(self, query: str) -> bool:
        """Check if query is searching for local businesses"""
        query_lower = query.lower()
        
        # Location indicators
        location_patterns = [
            r'\bin\s+\w+',  # "in Houston"
            r'\bnear\s+\w+',  # "near downtown"
            r'\baround\s+\w+',  # "around Austin"
            r',\s*\w+',  # ", Texas"
        ]
        
        # Business type indicators
        business_keywords = [
            'restaurant', 'restaurants', 'steakhouse', 'steak house', 'cafe', 'coffee',
            'hotel', 'hotels', 'motel', 'bar', 'bars', 'pub', 'pubs',
            'store', 'stores', 'shop', 'shops', 'mall',
            'gym', 'fitness', 'spa', 'salon',
            'doctor', 'dentist', 'clinic', 'hospital',
            'lawyer', 'attorney', 'plumber', 'electrician',
            'pizza', 'burger', 'sushi', 'mexican', 'italian', 'chinese', 'indian',
            'food', 'dining', 'eat', 'best'
        ]
        
        has_location = any(re.search(p, query_lower) for p in location_patterns)
        has_business = any(kw in query_lower for kw in business_keywords)
        
        return has_location and has_business
    
    async def _get_local_business_urls(self, query: str, max_results: int) -> List[str]:
        """Get URLs from business directories for local searches"""
        urls = []
        encoded_query = quote_plus(query)
        
        # Extract location from query for better results
        location = self._extract_location(query)
        encoded_location = quote_plus(location) if location else ""
        
        # Business search type
        business_type = self._extract_business_type(query)
        encoded_business = quote_plus(business_type) if business_type else encoded_query
        
        # Generate URLs for popular business directories
        directory_urls = []
        
        # Check if this is a restaurant search - prioritize OpenTable
        is_restaurant_search = any(word in query.lower() for word in [
            'restaurant', 'steakhouse', 'steak', 'food', 'dining', 
            'pizza', 'sushi', 'mexican', 'italian', 'chinese', 'indian',
            'cafe', 'bistro', 'grill', 'bar', 'pub', 'eatery'
        ])
        
        if is_restaurant_search and location:
            # OpenTable - best for restaurant data
            directory_urls.append(
                f"https://www.opentable.com/s?dateTime=2024-12-15T19:00&covers=2&term={encoded_business}&queryUnderstandingType=location&locationString={encoded_location}"
            )
        
        # Yelp
        if location:
            directory_urls.append(
                f"https://www.yelp.com/search?find_desc={encoded_business}&find_loc={encoded_location}"
            )
        else:
            directory_urls.append(f"https://www.yelp.com/search?find_desc={encoded_query}")
        
        # TripAdvisor (for restaurants/hotels)
        if any(word in query.lower() for word in ['restaurant', 'hotel', 'food', 'dining', 'steakhouse', 'steak']):
            if location:
                directory_urls.append(
                    f"https://www.tripadvisor.com/Search?q={encoded_query}"
                )
        
        # Yellow Pages
        if location:
            directory_urls.append(
                f"https://www.yellowpages.com/search?search_terms={encoded_business}&geo_location_terms={encoded_location}"
            )
        
        # Return URLs for scraping
        for url in directory_urls[:max_results]:
            try:
                logger.info(f"Adding business directory: {url}")
                urls.append(url)
            except Exception as e:
                logger.warning(f"Failed to add directory URL: {e}")
                continue
        
        return urls[:max_results]
    
    def _extract_location(self, query: str) -> Optional[str]:
        """Extract location from search query"""
        # Pattern: "X in Location" or "X, Location"
        patterns = [
            r'in\s+([^,]+(?:,\s*[^,]+)?)\s*$',  # "in Houston, Texas"
            r'in\s+(\w+(?:\s+\w+)?)\s*$',  # "in Houston"
            r',\s*([^,]+)\s*$',  # ", Texas"
            r'near\s+(\w+(?:\s+\w+)?)',  # "near downtown"
            r'around\s+(\w+(?:\s+\w+)?)',  # "around Austin"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_business_type(self, query: str) -> Optional[str]:
        """Extract business type from search query"""
        query_lower = query.lower()
        
        # Remove location part
        cleaned = re.sub(r'\s+in\s+.+$', '', query_lower, flags=re.IGNORECASE)
        cleaned = re.sub(r',\s*.+$', '', cleaned)
        cleaned = re.sub(r'\s+near\s+.+$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+around\s+.+$', '', cleaned, flags=re.IGNORECASE)
        
        # Remove common words
        cleaned = re.sub(r'\b(best|top|good|great|and|the|their|address|addresses)\b', '', cleaned)
        
        return cleaned.strip() if cleaned.strip() else None
    
    async def _search_web(self, query: str, max_results: int) -> List[str]:
        """Search the web using various search engines"""
        result_urls = []
        encoded_query = quote_plus(query)
        
        # Try multiple search approaches
        search_strategies = [
            # DuckDuckGo HTML (sometimes works)
            f"https://html.duckduckgo.com/html/?q={encoded_query}",
            # Bing (more lenient)
            f"https://www.bing.com/search?q={encoded_query}",
        ]
        
        for search_url in search_strategies:
            if len(result_urls) >= max_results:
                break
                
            try:
                logger.info(f"Trying search engine: {search_url}")
                
                # Use JavaScript rendering for better results
                search_results = await self.scraper.scrape(search_url, use_javascript=True)
                
                links = search_results.get('links', [])
                
                for link in links:
                    if len(result_urls) >= max_results:
                        break
                        
                    href = link.get('href') if isinstance(link, dict) else link
                    
                    if not href:
                        continue
                    
                    # Skip search engine internal links
                    if self._is_search_engine_link(href):
                        continue
                    
                    # Skip common non-result links
                    if self._is_valid_result_url(href):
                        if href not in result_urls:
                            result_urls.append(href)
                            logger.info(f"Found result URL: {href}")
                
                if result_urls:
                    break  # Found results, stop trying other engines
                    
            except Exception as e:
                logger.warning(f"Search engine failed: {e}")
                continue
        
        return result_urls
    
    def _is_search_engine_link(self, url: str) -> bool:
        """Check if URL is an internal search engine link"""
        search_domains = [
            'duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com',
            'baidu.com', 'yandex.com', 'ask.com'
        ]
        
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        return any(sd in domain for sd in search_domains)
    
    def _is_valid_result_url(self, url: str) -> bool:
        """Check if URL is a valid search result"""
        if not url:
            return False
        
        # Must be http/https
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Skip common non-content patterns
        skip_patterns = [
            r'javascript:', r'mailto:', r'tel:',
            r'/search\?', r'/images\?', r'/videos\?',
            r'\.pdf$', r'\.doc$', r'\.xls$',
        ]
        
        return not any(re.search(p, url, re.IGNORECASE) for p in skip_patterns)
    
    def _normalize_url(self, url: str) -> Optional[str]:
        """Normalize and validate URL"""
        if not url:
            return None
        
        # Remove fragments
        if '#' in url:
            url = url.split('#')[0]
        
        # Remove common tracking parameters
        url = re.sub(r'[?&](utm_[^&]*|ref=[^&]*|source=[^&]*)', '', url)
        
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        
        # Only allow http/https
        if parsed.scheme not in ['http', 'https']:
            return None
        
        # Reconstruct URL
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or '/',
            parsed.params,
            parsed.query,
            ''
        ))
        
        return normalized
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def _should_follow_link(self, url: str, base_domain: str) -> bool:
        """Determine if we should follow a link"""
        if not self._is_valid_url(url):
            return False
        
        # Skip common non-content URLs
        skip_patterns = [
            r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|tar|gz)$',
            r'\.(jpg|jpeg|png|gif|svg|webp|ico)$',
            r'\.(mp4|avi|mov|wmv|flv)$',
            r'\.(mp3|wav|ogg)$',
            r'mailto:', r'javascript:', r'tel:',
            r'#',
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Domain filtering
        if self.same_domain:
            link_domain = self._get_domain(url)
            if link_domain != base_domain:
                return False
        
        return True
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling"""
        if not url:
            return False
        
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
