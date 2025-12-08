import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
import httpx
import re
from urllib.parse import urljoin, urlparse, quote_plus
import json
import logging
import time

logger = logging.getLogger(__name__)

# Import detailed logger
try:
    from app.scraper_logger import get_scraper_logger
    detail_logger = get_scraper_logger()
except ImportError:
    # Fallback if logger not available
    detail_logger = None


class WebScraper:
    def __init__(self, use_playwright: bool = False):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        self.use_playwright = use_playwright
        self.playwright_browser = None

    async def scrape(self, url: str, use_javascript: bool = False) -> Dict[str, Any]:
        """
        General-purpose web scraper that works on any website
        
        Args:
            url: The URL to scrape
            use_javascript: Whether to use Playwright for JavaScript-rendered pages
        
        Returns:
            Dictionary containing structured data from the page
        """
        try:
            # Try to fetch with requests first (faster)
            if not use_javascript:
                return await self._scrape_static(url)
            else:
                return await self._scrape_with_playwright(url)
                
        except Exception as e:
            # If static scraping fails and we haven't tried JS, try with Playwright
            if not use_javascript:
                try:
                    return await self._scrape_with_playwright(url)
                except:
                    pass
            raise Exception(f"Scraping failed: {str(e)}")

    async def _scrape_static(self, url: str) -> Dict[str, Any]:
        """Scrape static HTML content - extracts data from raw HTML including embedded JSON"""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=self.session.headers)
            response.raise_for_status()
            
            html_content = response.text
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # FIRST: Extract embedded JSON data BEFORE removing scripts
            embedded_data = self._extract_embedded_json(soup, url)
            
            # Remove script and style elements for text extraction
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Extract structured data from HTML
            data = await self._extract_structured_data(soup, url, html_content)
            
            # Merge embedded JSON data
            if embedded_data:
                data['embedded_data'] = embedded_data
                # If we found restaurants/businesses, add them prominently
                if 'restaurants' in embedded_data:
                    data['restaurants'] = embedded_data['restaurants']
                if 'businesses' in embedded_data:
                    data['businesses'] = embedded_data['businesses']
                if 'items' in embedded_data:
                    data['items'] = embedded_data['items']
            
            return data
    
    def _extract_embedded_json(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract JSON data embedded in script tags - many sites include data this way"""
        embedded = {}
        
        # 1. JSON-LD structured data (schema.org)
        json_ld_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                json_ld_data.append(data)
                
                # Extract restaurants/businesses from JSON-LD
                if isinstance(data, dict):
                    if data.get('@type') in ['Restaurant', 'LocalBusiness', 'FoodEstablishment']:
                        if 'restaurants' not in embedded:
                            embedded['restaurants'] = []
                        embedded['restaurants'].append(self._parse_jsonld_business(data))
                    elif data.get('@type') == 'ItemList':
                        items = data.get('itemListElement', [])
                        for item in items:
                            if isinstance(item, dict) and item.get('item'):
                                biz = item.get('item', {})
                                if biz.get('@type') in ['Restaurant', 'LocalBusiness', 'FoodEstablishment']:
                                    if 'restaurants' not in embedded:
                                        embedded['restaurants'] = []
                                    embedded['restaurants'].append(self._parse_jsonld_business(biz))
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') in ['Restaurant', 'LocalBusiness']:
                            if 'restaurants' not in embedded:
                                embedded['restaurants'] = []
                            embedded['restaurants'].append(self._parse_jsonld_business(item))
            except (json.JSONDecodeError, AttributeError):
                continue
        
        if json_ld_data:
            embedded['json_ld'] = json_ld_data
        
        # 2. Next.js data (__NEXT_DATA__)
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            try:
                next_data = json.loads(next_data_script.string)
                embedded['next_data'] = next_data
                # Try to find business data in Next.js payload
                self._extract_from_nested(next_data, embedded)
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # 3. Yelp-specific data patterns
        if 'yelp.com' in url.lower():
            embedded.update(self._extract_yelp_data(soup))
        
        # 4. Generic JSON in script tags
        for script in soup.find_all('script'):
            if script.string and len(script.string) > 100:
                # Look for JSON objects/arrays in script content
                text = script.string.strip()
                
                # Try to find JSON data patterns
                patterns = [
                    r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
                    r'window\.pageData\s*=\s*({.+?});',
                    r'var\s+data\s*=\s*({.+?});',
                    r'"results"\s*:\s*(\[.+?\])',
                    r'"businesses"\s*:\s*(\[.+?\])',
                    r'"restaurants"\s*:\s*(\[.+?\])',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            if isinstance(data, list) and len(data) > 0:
                                embedded['extracted_list'] = data[:50]  # Limit
                            elif isinstance(data, dict):
                                embedded['extracted_data'] = data
                        except json.JSONDecodeError:
                            continue
        
        return embedded
    
    def _parse_jsonld_business(self, data: Dict) -> Dict[str, Any]:
        """Parse a JSON-LD business/restaurant entry - extracts comprehensive internal data"""
        address = data.get('address', {})
        if isinstance(address, str):
            address_str = address
            address_parts = {}
        else:
            address_str = ', '.join(filter(None, [
                address.get('streetAddress'),
                address.get('addressLocality'),
                address.get('addressRegion'),
                address.get('postalCode')
            ]))
            address_parts = {
                'street_address': address.get('streetAddress'),
                'city': address.get('addressLocality'),
                'state': address.get('addressRegion'),
                'postal_code': address.get('postalCode'),
                'country': address.get('addressCountry'),
            }
        
        rating = data.get('aggregateRating', {})
        
        # Extract opening hours
        opening_hours = data.get('openingHoursSpecification', [])
        hours_list = []
        if isinstance(opening_hours, list):
            for hours in opening_hours:
                if isinstance(hours, dict):
                    hours_list.append({
                        'day': hours.get('dayOfWeek'),
                        'opens': hours.get('opens'),
                        'closes': hours.get('closes'),
                    })
        
        # Extract menu/offers
        menu = data.get('hasMenu', {})
        menu_url = menu.get('url') if isinstance(menu, dict) else None
        if not menu_url:
            menu_url = data.get('menu')
        
        # Extract offers (prices, deals)
        offers = data.get('offers', {})
        offer_data = {}
        if isinstance(offers, dict):
            offer_data = {
                'price': offers.get('price'),
                'price_currency': offers.get('priceCurrency'),
                'availability': offers.get('availability'),
                'url': offers.get('url'),
            }
        elif isinstance(offers, list) and len(offers) > 0:
            offer_data = {
                'offers': [{
                    'price': o.get('price') if isinstance(o, dict) else None,
                    'price_currency': o.get('priceCurrency') if isinstance(o, dict) else None,
                } for o in offers[:5]]
            }
        
        # Extract cuisine types (can be string or list)
        cuisine = data.get('servesCuisine', [])
        if isinstance(cuisine, str):
            cuisine = [cuisine]
        elif not isinstance(cuisine, list):
            cuisine = []
        
        # Extract additional business details
        result = {
            # Basic info
            'name': data.get('name'),
            'description': data.get('description'),
            'url': data.get('url'),
            'image': data.get('image'),
            
            # Contact
            'phone': data.get('telephone'),
            'email': data.get('email'),
            'website': data.get('url') or data.get('sameAs'),
            
            # Address (both formatted and parts)
            'address': address_str,
            'address_parts': address_parts,
            'latitude': data.get('geo', {}).get('latitude') if isinstance(data.get('geo'), dict) else None,
            'longitude': data.get('geo', {}).get('longitude') if isinstance(data.get('geo'), dict) else None,
            
            # Ratings & reviews
            'rating': rating.get('ratingValue') if isinstance(rating, dict) else None,
            'review_count': rating.get('reviewCount') if isinstance(rating, dict) else None,
            'best_rating': rating.get('bestRating') if isinstance(rating, dict) else None,
            'worst_rating': rating.get('worstRating') if isinstance(rating, dict) else None,
            
            # Restaurant-specific
            'cuisine': cuisine,
            'price_range': data.get('priceRange'),
            'accepts_reservations': data.get('acceptsReservations'),
            'menu_url': menu_url,
            
            # Hours
            'opening_hours': hours_list if hours_list else None,
            'opening_hours_text': data.get('openingHours'),  # Sometimes as text
            
            # Offers/deals
            'offers': offer_data if offer_data else None,
            
            # Additional metadata
            'business_type': data.get('@type'),
            'founding_date': data.get('foundingDate'),
            'number_of_employees': data.get('numberOfEmployees'),
            'payment_accepted': data.get('paymentAccepted'),
            'currencies_accepted': data.get('currenciesAccepted'),
        }
        
        # Remove None values for cleaner output
        return {k: v for k, v in result.items() if v is not None}
    
    def _extract_from_nested(self, data: Any, result: Dict, depth: int = 0) -> None:
        """Recursively extract business data from nested structures"""
        if depth > 5:  # Limit recursion
            return
        
        if isinstance(data, dict):
            # Check if this looks like a business/restaurant
            if 'name' in data and ('address' in data or 'location' in data or 'rating' in data):
                if 'businesses' not in result:
                    result['businesses'] = []
                if len(result['businesses']) < 50:  # Limit
                    result['businesses'].append(data)
            
            # Recurse into values
            for key, value in data.items():
                if key in ['businesses', 'restaurants', 'results', 'items', 'listings']:
                    if isinstance(value, list):
                        result[key] = value[:50]  # Limit
                else:
                    self._extract_from_nested(value, result, depth + 1)
        
        elif isinstance(data, list):
            for item in data[:20]:  # Limit iteration
                self._extract_from_nested(item, result, depth + 1)
    
    def _extract_yelp_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Yelp-specific data patterns - comprehensive internal data extraction"""
        yelp_data = {}
        restaurants = []
        
        # Look for Yelp's data hydration scripts
        for script in soup.find_all('script'):
            if script.string:
                text = script.string
                
                # Yelp often uses patterns like this
                patterns = [
                    r'\"searchPageProps\":\s*({.+?})\s*,\s*\"',
                    r'\"bizDetailsPageProps\":\s*({.+?})\s*,\s*\"',
                    r'\"legacyProps\":\s*({.+?})\s*\}',
                    r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
                    r'\"businesses\":\s*(\[.+?\])',
                    r'\"searchResults\":\s*(\[.+?\])',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            yelp_data['yelp_props'] = data
                            
                            # Extract businesses from Yelp data structure
                            businesses_list = None
                            if isinstance(data, dict):
                                # Try common Yelp data paths
                                businesses_list = (
                                    data.get('searchResults') or
                                    data.get('businesses') or
                                    data.get('results') or
                                    data.get('bizDetails') or
                                    (data.get('searchPageProps', {}) or {}).get('searchResults') or
                                    (data.get('bizDetailsPageProps', {}) or {}).get('business')
                                )
                            
                            if businesses_list:
                                if not isinstance(businesses_list, list):
                                    businesses_list = [businesses_list]
                                
                                for biz in businesses_list[:50]:  # Limit to 50
                                    if isinstance(biz, dict):
                                        restaurant = self._parse_yelp_business(biz)
                                        if restaurant:
                                            restaurants.append(restaurant)
                            
                            break
                        except json.JSONDecodeError:
                            continue
        
        if restaurants:
            yelp_data['restaurants'] = restaurants
        
        return yelp_data
    
    def _parse_yelp_business(self, biz: Dict) -> Dict[str, Any]:
        """Parse Yelp business data structure into standardized format"""
        if not isinstance(biz, dict):
            return None
        
        location = biz.get('location', {})
        coordinates = biz.get('coordinates', {})
        categories = biz.get('categories', [])
        
        return {
            'name': biz.get('name'),
            'yelp_id': biz.get('id'),
            'alias': biz.get('alias'),
            'url': biz.get('url'),
            'image_url': biz.get('image_url'),
            'photos': biz.get('photos', [])[:5],  # Limit photos
            
            # Ratings
            'rating': biz.get('rating'),
            'review_count': biz.get('review_count'),
            
            # Location
            'address': ', '.join(location.get('display_address', [])) if isinstance(location, dict) else None,
            'address_parts': {
                'address1': location.get('address1') if isinstance(location, dict) else None,
                'address2': location.get('address2') if isinstance(location, dict) else None,
                'city': location.get('city') if isinstance(location, dict) else None,
                'state': location.get('state') if isinstance(location, dict) else None,
                'zip_code': location.get('zip_code') if isinstance(location, dict) else None,
                'country': location.get('country') if isinstance(location, dict) else None,
            } if isinstance(location, dict) else None,
            'latitude': coordinates.get('latitude') if isinstance(coordinates, dict) else None,
            'longitude': coordinates.get('longitude') if isinstance(coordinates, dict) else None,
            
            # Contact
            'phone': biz.get('display_phone') or biz.get('phone'),
            'phone_formatted': biz.get('display_phone'),
            
            # Business details
            'price': biz.get('price'),  # $, $$, $$$, $$$$
            'categories': [cat.get('title') if isinstance(cat, dict) else str(cat) for cat in categories],
            'transactions': biz.get('transactions', []),  # pickup, delivery, restaurant_reservation
            'is_closed': biz.get('is_closed'),
            'is_claimed': biz.get('is_claimed'),
            
            # Hours
            'hours': biz.get('hours', []),
            
            # Additional Yelp-specific
            'distance': biz.get('distance'),  # in meters if from search
            'attributes': biz.get('attributes', {}),
            'special_hours': biz.get('special_hours'),
        }

    async def _scrape_with_playwright(self, url: str) -> Dict[str, Any]:
        """Scrape JavaScript-rendered content using Playwright with anti-detection"""
        try:
            from playwright.async_api import async_playwright
            import random
            
            async with async_playwright() as p:
                # Launch with anti-detection settings
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                    ]
                )
                
                # Create context with realistic browser fingerprint
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                    geolocation={'latitude': 40.7128, 'longitude': -74.0060},
                    permissions=['geolocation'],
                    java_script_enabled=True,
                )
                
                page = await context.new_page()
                
                # Add stealth scripts to avoid detection
                await page.add_init_script("""
                    // Override webdriver property
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    
                    // Override plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Override languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Override chrome
                    window.chrome = { runtime: {} };
                    
                    // Override permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)
                
                # Navigate with realistic behavior
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    logger.warning(f"Initial page load issue: {e}, continuing...")
                
                # Random delay to mimic human behavior
                await page.wait_for_timeout(random.randint(2000, 4000))
                
                # Scroll down to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(random.randint(1000, 2000))
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(random.randint(1500, 3000))
                
                # Scroll back up
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(1000)
                
                # Get page content
                html_content = await page.content()
                title = await page.title()
                
                # Extract text content
                text_content = await page.evaluate("""
                    () => {
                        // Remove script and style elements
                        const scripts = document.querySelectorAll('script, style, noscript');
                        scripts.forEach(el => el.remove());
                        
                        // Get main content
                        const body = document.body;
                        return body.innerText || body.textContent || '';
                    }
                """)
                
                # Extract links
                links = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href]'));
                        return links.map(a => ({
                            text: a.innerText.trim(),
                            href: a.href,
                            title: a.title || ''
                        })).slice(0, 100);
                    }
                """)
                
                # Extract images
                images = await page.evaluate("""
                    () => {
                        const imgs = Array.from(document.querySelectorAll('img[src]'));
                        return imgs.map(img => ({
                            src: img.src,
                            alt: img.alt || '',
                            title: img.title || ''
                        })).slice(0, 50);
                    }
                """)
                
                # Extract meta tags
                meta_data = await page.evaluate("""
                    () => {
                        const metas = {};
                        document.querySelectorAll('meta').forEach(meta => {
                            const name = meta.getAttribute('name') || meta.getAttribute('property');
                            const content = meta.getAttribute('content');
                            if (name && content) {
                                metas[name] = content;
                            }
                        });
                        return metas;
                    }
                """)
                
                # Close properly
                await context.close()
                await browser.close()
                
                # Check if we got meaningful content
                if len(text_content.strip()) < 100:
                    logger.warning(f"Low content detected ({len(text_content)} chars), page may be blocked")
                
                # Parse with BeautifulSoup for additional extraction
                soup = BeautifulSoup(html_content, 'html.parser')
                structured_data = await self._extract_structured_data(soup, url, html_content)
                
                # Merge Playwright data
                structured_data.update({
                    'title': title,
                    'text_content': text_content[:10000],  # Limit text
                    'links': links,
                    'images': images,
                    'meta_tags': meta_data,
                    'rendered_with_javascript': True
                })
                
                return structured_data
                
        except ImportError:
            raise Exception("Playwright not available. Install with: pip install playwright && playwright install chromium")
        except Exception as e:
            logger.error(f"Playwright scraping failed: {str(e)}")
            raise Exception(f"Playwright scraping failed: {str(e)}")

    async def _extract_internal_data(
        self, 
        url: str, 
        wait_time: int = 5, 
        scroll: bool = True,
        intercept_network: bool = True
    ) -> Dict[str, Any]:
        """
        Extract internal data from a live page using JavaScript rendering.
        Captures data from JavaScript variables, network requests, and fully rendered DOM.
        """
        try:
            from playwright.async_api import async_playwright
            import random
            import json as json_module
            
            internal_data = {
                'javascript_variables': {},
                'network_responses': [],
                'dom_data': {},
                'restaurants': [],
                'businesses': []
            }
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                )
                
                page = await context.new_page()
                
                # Intercept network requests to capture API responses
                network_data = []
                if intercept_network:
                    async def handle_response(response):
                        try:
                            # Only capture JSON responses that might contain restaurant data
                            content_type = response.headers.get('content-type', '')
                            if 'application/json' in content_type or 'text/json' in content_type:
                                url_pattern = response.url.lower()
                                # Capture responses from common API endpoints
                                if any(keyword in url_pattern for keyword in ['api', 'search', 'business', 'restaurant', 'yelp', 'opentable']):
                                    try:
                                        body = await response.json()
                                        network_data.append({
                                            'url': response.url,
                                            'status': response.status,
                                            'data': body
                                        })
                                    except:
                                        pass
                        except:
                            pass
                    
                    page.on('response', handle_response)
                
                # Navigate to page
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Wait for data to load
                await page.wait_for_timeout(wait_time * 1000)
                
                # Scroll to trigger lazy loading
                if scroll:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await page.wait_for_timeout(2000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(1000)
                
                # Extract data from JavaScript variables
                js_variables = await page.evaluate("""
                    () => {
                        const data = {};
                        
                        // Common variable names that contain data
                        const varNames = [
                            '__PRELOADED_STATE__',
                            '__NEXT_DATA__',
                            'window.__PRELOADED_STATE__',
                            'window.__NEXT_DATA__',
                            'pageData',
                            'initialData',
                            'appData',
                            'searchPageProps',
                            'bizDetailsPageProps',
                            'legacyProps',
                            'yelpData',
                            'restaurantData'
                        ];
                        
                        // Try to extract from window object
                        for (const varName of varNames) {
                            try {
                                const parts = varName.split('.');
                                let obj = window;
                                for (const part of parts) {
                                    if (obj && obj[part]) {
                                        obj = obj[part];
                                    } else {
                                        obj = null;
                                        break;
                                    }
                                }
                                if (obj && typeof obj === 'object') {
                                    data[varName] = obj;
                                }
                            } catch (e) {}
                        }
                        
                        // Also check for script tags with JSON data
                        const scripts = document.querySelectorAll('script[type="application/json"], script[id*="data"], script[id*="state"]');
                        scripts.forEach((script, idx) => {
                            try {
                                const jsonData = JSON.parse(script.textContent);
                                data[`script_${idx}`] = jsonData;
                            } catch (e) {}
                        });
                        
                        return data;
                    }
                """)
                
                internal_data['javascript_variables'] = js_variables
                internal_data['network_responses'] = network_data
                
                # Extract restaurant/business data from JavaScript variables
                restaurants_from_js = []
                for var_name, var_data in js_variables.items():
                    if isinstance(var_data, dict):
                        # Try to find restaurant/business data in the structure
                        self._extract_from_nested(var_data, {'businesses': restaurants_from_js}, 0)
                
                # Extract from network responses
                restaurants_from_network = []
                for response in network_data:
                    if isinstance(response.get('data'), dict):
                        self._extract_from_nested(response['data'], {'businesses': restaurants_from_network}, 0)
                    elif isinstance(response.get('data'), list):
                        for item in response['data']:
                            if isinstance(item, dict) and ('name' in item or 'restaurant' in str(item).lower()):
                                restaurants_from_network.append(item)
                
                # Parse and merge restaurant data
                all_restaurants = []
                
                # Parse restaurants from JS variables
                for restaurant in restaurants_from_js:
                    if isinstance(restaurant, dict):
                        # Check if it's a Yelp business
                        if 'yelp_id' in restaurant or 'alias' in restaurant:
                            parsed = self._parse_yelp_business(restaurant)
                            if parsed:
                                all_restaurants.append(parsed)
                        # Check if it's JSON-LD
                        elif restaurant.get('@type') in ['Restaurant', 'LocalBusiness']:
                            parsed = self._parse_jsonld_business(restaurant)
                            if parsed:
                                all_restaurants.append(parsed)
                        else:
                            all_restaurants.append(restaurant)
                
                # Parse restaurants from network
                for restaurant in restaurants_from_network:
                    if isinstance(restaurant, dict):
                        if 'yelp_id' in restaurant or 'alias' in restaurant:
                            parsed = self._parse_yelp_business(restaurant)
                            if parsed:
                                all_restaurants.append(parsed)
                        else:
                            all_restaurants.append(restaurant)
                
                # Extract from rendered HTML
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                embedded_data = self._extract_embedded_json(soup, url)
                
                if embedded_data:
                    if 'restaurants' in embedded_data:
                        for restaurant in embedded_data['restaurants']:
                            if restaurant not in all_restaurants:
                                all_restaurants.append(restaurant)
                    if 'businesses' in embedded_data:
                        for business in embedded_data['businesses']:
                            if business not in all_restaurants:
                                all_restaurants.append(business)
                
                internal_data['restaurants'] = all_restaurants[:100]  # Limit to 100
                internal_data['businesses'] = all_restaurants[:100]
                
                # Add DOM data
                internal_data['dom_data'] = {
                    'title': await page.title(),
                    'url': page.url,
                    'html_length': len(html_content)
                }
                
                await context.close()
                await browser.close()
                
                return internal_data
                
        except ImportError:
            raise Exception("Playwright not available. Install with: pip install playwright && playwright install chromium")
        except Exception as e:
            logger.error(f"Internal data extraction failed: {str(e)}")
            raise Exception(f"Internal data extraction failed: {str(e)}")

    async def _extract_structured_data(self, soup: BeautifulSoup, url: str, html_content: str) -> Dict[str, Any]:
        """Extract structured data from parsed HTML"""
        base_url = url
        
        # Extract title
        title = None
        if soup.title:
            title = soup.title.string.strip() if soup.title.string else None
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)
        
        # Extract main content (try to find article, main, or content areas)
        main_content = None
        for selector in ['article', 'main', '[role="main"]', '.content', '#content', '.main-content']:
            element = soup.select_one(selector)
            if element:
                main_content = element.get_text(strip=True, separator=' ')
                break
        
        if not main_content:
            # Fallback to body text
            body = soup.find('body')
            if body:
                main_content = body.get_text(strip=True, separator=' ')
        
        # Extract all text (cleaned)
        all_text = soup.get_text(strip=True, separator=' ')
        
        # Extract links with context
        links = []
        for a in soup.find_all('a', href=True)[:100]:
            href = a.get('href')
            if href:
                # Resolve relative URLs
                full_url = urljoin(base_url, href)
                link_text = a.get_text(strip=True)
                links.append({
                    'text': link_text,
                    'href': full_url,
                    'title': a.get('title', '')
                })
        
        # Extract images with context
        images = []
        for img in soup.find_all('img', src=True)[:50]:
            src = img.get('src')
            if src:
                full_url = urljoin(base_url, src)
                images.append({
                    'src': full_url,
                    'alt': img.get('alt', ''),
                    'title': img.get('title', '')
                })
        
        # Extract meta tags
        meta_tags = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property') or meta.get('itemprop')
            content = meta.get('content')
            if name and content:
                meta_tags[name] = content
        
        # Extract headings
        headings = {}
        for level in range(1, 7):
            tag = f'h{level}'
            headings[tag] = [h.get_text(strip=True) for h in soup.find_all(tag)][:20]
        
        # Extract data organized by sections (NEW: categorize by section titles)
        sections_data = self._extract_sections(soup)
        
        # Extract lists
        lists = []
        for ul in soup.find_all(['ul', 'ol'])[:10]:
            items = [li.get_text(strip=True) for li in ul.find_all('li')]
            if items:
                lists.append(items)
        
        # Extract tables
        tables = []
        for table in soup.find_all('table')[:5]:
            rows = []
            for tr in table.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        
        # Extract code blocks
        code_blocks = []
        for code in soup.find_all(['code', 'pre'])[:10]:
            code_text = code.get_text(strip=True)
            if code_text and len(code_text) > 10:
                code_blocks.append(code_text[:500])  # Limit length
        
        # Detect page type
        page_type = self._detect_page_type(soup, meta_tags)
        
        # Extract structured data (JSON-LD, microdata)
        structured_data = self._extract_json_ld(soup)
        
        return {
            'url': url,
            'title': title,
            'text_content': all_text[:10000],  # Limit to 10k chars
            'main_content': main_content[:5000] if main_content else None,
            'links': links,
            'images': images,
            'meta_tags': meta_tags,
            'headings': headings,
            'sections': sections_data,  # NEW: Data organized by section titles
            'lists': lists,
            'tables': tables,
            'code_blocks': code_blocks,
            'page_type': page_type,
            'structured_data': structured_data,
            'word_count': len(all_text.split()) if all_text else 0,
            'rendered_with_javascript': False
        }

    def _extract_sections(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract data organized by section titles.
        Identifies sections by headings (h2, h3, h4) and groups content under each section.
        
        Returns:
            Dictionary where keys are section titles and values contain section content
        """
        sections = {}
        
        # Find all section headings (h2, h3, h4 are most common for sections)
        section_headings = []
        for tag in ['h2', 'h3', 'h4']:
            for heading in soup.find_all(tag):
                heading_text = heading.get_text(strip=True)
                if heading_text and len(heading_text) < 200:  # Reasonable section title length
                    section_headings.append({
                        'tag': tag,
                        'text': heading_text,
                        'element': heading
                    })
        
        # Sort headings by their position in the document
        section_headings.sort(key=lambda x: x['element'].sourceline if hasattr(x['element'], 'sourceline') else 0)
        
        # Extract content for each section
        for i, heading_info in enumerate(section_headings):
            heading = heading_info['element']
            section_title = heading_info['text']
            
            # Find all content between this heading and the next heading
            section_content = []
            current = heading.next_sibling
            
            # Determine the next heading at same or higher level
            next_heading = None
            if i + 1 < len(section_headings):
                next_heading = section_headings[i + 1]['element']
            
            # Collect all content until next heading
            while current and current != next_heading:
                if current == next_heading:
                    break
                
                # Skip if we hit another heading at same or higher level
                if hasattr(current, 'name'):
                    if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        heading_level = int(current.name[1])
                        current_heading_level = int(heading_info['tag'][1])
                        if heading_level <= current_heading_level:
                            break
                
                # Extract text content
                if hasattr(current, 'get_text'):
                    text = current.get_text(strip=True, separator=' ')
                    if text and len(text) > 3:
                        section_content.append({
                            'type': 'text',
                            'content': text[:1000]  # Limit length
                        })
                elif isinstance(current, str):
                    text = current.strip()
                    if text and len(text) > 3:
                        section_content.append({
                            'type': 'text',
                            'content': text[:1000]
                        })
                
                # Extract lists
                if hasattr(current, 'find_all'):
                    for ul in current.find_all(['ul', 'ol'], recursive=False):
                        items = [li.get_text(strip=True) for li in ul.find_all('li')]
                        if items:
                            section_content.append({
                                'type': 'list',
                                'content': items
                            })
                    
                    # Extract links
                    for link in current.find_all('a', href=True, recursive=False):
                        href = link.get('href', '')
                        link_text = link.get_text(strip=True)
                        if href and link_text:
                            section_content.append({
                                'type': 'link',
                                'text': link_text,
                                'url': href
                            })
                
                # Move to next sibling
                try:
                    current = current.next_sibling
                except:
                    break
            
            # If we have content for this section, add it
            if section_content:
                # Clean up section title (remove extra whitespace, normalize)
                clean_title = ' '.join(section_title.split())
                
                # Combine all text content
                combined_text = ' '.join([
                    item['content'] for item in section_content 
                    if item['type'] == 'text'
                ])
                
                # Extract lists
                section_lists = [
                    item['content'] for item in section_content 
                    if item['type'] == 'list'
                ]
                
                # Extract links
                section_links = [
                    {'text': item['text'], 'url': item['url']} 
                    for item in section_content 
                    if item['type'] == 'link'
                ]
                
                sections[clean_title] = {
                    'title': clean_title,
                    'text': combined_text[:2000] if combined_text else None,  # Limit to 2000 chars
                    'lists': section_lists if section_lists else None,
                    'links': section_links if section_links else None,
                    'raw_content': section_content[:20]  # Keep first 20 items for reference
                }
        
        return sections
    
    def _detect_page_type(self, soup: BeautifulSoup, meta_tags: Dict[str, str]) -> str:
        """Detect the type of page (article, product, blog, etc.)"""
        # Check Open Graph type
        og_type = meta_tags.get('og:type', '').lower()
        if og_type:
            return og_type
        
        # Check schema.org type
        schema_type = soup.find(attrs={'itemtype': True})
        if schema_type:
            itemtype = schema_type.get('itemtype', '')
            if 'Article' in itemtype:
                return 'article'
            elif 'Product' in itemtype:
                return 'product'
            elif 'Person' in itemtype:
                return 'profile'
        
        # Heuristic detection
        if soup.find('article'):
            return 'article'
        elif soup.find(attrs={'class': re.compile(r'product|item', re.I)}):
            return 'product'
        elif soup.find('time') or soup.find(attrs={'class': re.compile(r'post|entry', re.I)}):
            return 'blog'
        elif soup.find('form'):
            return 'form'
        
        return 'generic'

    def _extract_json_ld(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract JSON-LD structured data"""
        structured_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured_data.append(data)
            except (json.JSONDecodeError, AttributeError):
                continue
        return structured_data

    async def scrape_opentable(self, location: str, cuisine: str = None, max_results: int = 20) -> Dict[str, Any]:
        """
        Specialized scraper for OpenTable restaurant data.
        Uses their search page and extracts structured restaurant information.
        """
        logger.info(f"Scraping OpenTable for: {location}, cuisine: {cuisine}")
        
        # Build OpenTable search URL
        search_term = cuisine if cuisine else "restaurants"
        encoded_location = quote_plus(location)
        encoded_term = quote_plus(search_term)
        
        url = f"https://www.opentable.com/s?dateTime=2024-12-15T19:00&covers=2&term={encoded_term}&queryUnderstandingType=location&locationString={encoded_location}"
        
        try:
            # OpenTable requires JavaScript rendering
            page_data = await self._scrape_with_playwright(url)
            
            # Try to extract restaurant-specific data
            restaurants = self._parse_opentable_data(page_data)
            
            if restaurants:
                return {
                    'url': url,
                    'source': 'opentable',
                    'location': location,
                    'cuisine': cuisine,
                    'total_found': len(restaurants),
                    'restaurants': restaurants[:max_results],
                    'page_type': 'restaurant_listing'
                }
            else:
                # Return raw data if parsing failed
                return page_data
                
        except Exception as e:
            logger.error(f"OpenTable scraping failed: {e}")
            raise Exception(f"OpenTable scraping failed: {str(e)}")
    
    def _parse_opentable_data(self, page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse OpenTable search results to extract restaurant data"""
        restaurants = []
        
        # Try to extract from JSON-LD structured data first
        structured_data = page_data.get('structured_data', [])
        for data in structured_data:
            if isinstance(data, dict):
                if data.get('@type') == 'Restaurant' or 'Restaurant' in str(data.get('@type', '')):
                    restaurants.append({
                        'name': data.get('name'),
                        'cuisine': data.get('servesCuisine'),
                        'price_range': data.get('priceRange'),
                        'rating': data.get('aggregateRating', {}).get('ratingValue') if isinstance(data.get('aggregateRating'), dict) else None,
                        'review_count': data.get('aggregateRating', {}).get('reviewCount') if isinstance(data.get('aggregateRating'), dict) else None,
                        'address': self._format_address(data.get('address', {})),
                        'phone': data.get('telephone'),
                        'url': data.get('url'),
                    })
                elif data.get('@type') == 'ItemList':
                    # Handle ItemList of restaurants
                    for item in data.get('itemListElement', []):
                        if isinstance(item, dict) and item.get('item'):
                            rest = item.get('item', {})
                            restaurants.append({
                                'name': rest.get('name'),
                                'cuisine': rest.get('servesCuisine'),
                                'price_range': rest.get('priceRange'),
                                'address': self._format_address(rest.get('address', {})),
                                'url': rest.get('url'),
                            })
        
        # Also try to extract from text content using patterns
        if not restaurants:
            text_content = page_data.get('text_content', '')
            main_content = page_data.get('main_content', '')
            
            # Try to find restaurant names from headings
            headings = page_data.get('headings', {})
            for level in ['h2', 'h3']:
                for heading in headings.get(level, []):
                    if heading and len(heading) > 3 and len(heading) < 100:
                        restaurants.append({'name': heading})
        
        return restaurants
    
    def _parse_opentable_restaurant_page(self, soup: BeautifulSoup, url: str, html_content: str) -> Dict[str, Any]:
        """
        Comprehensive parser for OpenTable individual restaurant pages.
        Extracts all sections: Overview, Details, Experiences, Offers, Menu, Reviews, FAQs, etc.
        """
        restaurant_data = {}
        
        if detail_logger:
            detail_logger.log_separator(f"PARSING OPENTABLE PAGE: {url}")
        
        # ========== OVERVIEW SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "OVERVIEW", "STARTED")
        # Restaurant name
        name_elem = soup.select_one('h1.aE-vw__restaurantName, h1[class*="restaurantName"]')
        if name_elem:
            restaurant_data['name'] = name_elem.get_text(strip=True)
        
        # Rating and review count
        rating_elem = soup.select_one('#ratingInfo, [data-testid="restaurant-overview-header"] [data-testid="icVipFill"]')
        if rating_elem:
            rating_text = rating_elem.find_next(string=re.compile(r'\d+\.?\d*\s*\(\d+\)'))
            if rating_text:
                rating_match = re.search(r'(\d+\.?\d*)\s*\((\d+)\)', rating_text)
                if rating_match:
                    restaurant_data['rating'] = float(rating_match.group(1))
                    restaurant_data['review_count'] = int(rating_match.group(2).replace(',', ''))
        
        # Price range
        price_elem = soup.select_one('#priceBandInfo, [data-testid="restaurant-overview-header"]')
        if price_elem:
            price_text = price_elem.get_text()
            price_match = re.search(r'\$(\d+)\s+to\s+\$(\d+)', price_text)
            if price_match:
                restaurant_data['price_range'] = f"${price_match.group(1)} to ${price_match.group(2)}"
        
        # Cuisine
        cuisine_elem = soup.select_one('#cuisineInfo, [data-testid="restaurant-overview-header"]')
        if cuisine_elem:
            cuisine_text = cuisine_elem.get_text(strip=True)
            if cuisine_text and cuisine_text != restaurant_data.get('name'):
                restaurant_data['cuisine'] = cuisine_text
        
        # Address
        address_elem = soup.select_one('[data-testid="addressContainer"], .akxdr__addressContainer, .a4d46__addressText')
        if address_elem:
            restaurant_data['address'] = address_elem.get_text(strip=True)
        
        # Neighborhood
        neighborhood_elem = soup.select_one('.a7d03__neighborhood, [data-testid="neighborhood"]')
        if neighborhood_elem:
            restaurant_data['neighborhood'] = neighborhood_elem.get_text(strip=True)
        
        # ========== ABOUT SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "ABOUT", "STARTED")
        about_section = soup.select_one('section:has(h2:contains("About this restaurant"))')
        if not about_section:
            about_section = soup.find('h2', string=re.compile('About this restaurant', re.I))
            if about_section:
                about_section = about_section.find_parent('section')
        
        if about_section:
            # Tags
            tags = []
            tag_elems = about_section.select('.aBeBa__tag, [class*="tag"]')
            for tag in tag_elems:
                tag_text = tag.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
            if tags:
                restaurant_data['tags'] = tags
            
            # Description
            desc_elem = about_section.select_one('[data-test="restaurant-description"], .asn86__container')
            if desc_elem:
                desc_text = desc_elem.get_text(strip=True)
                if desc_text:
                    restaurant_data['description'] = desc_text
        
        # ========== DETAILS SECTION ==========
        details_section = soup.select_one('[data-test="restaurant-details"], section#details')
        if details_section:
            details_data = {}
            
            # Helper function to find detail by title text
            def find_detail_by_title(title_text):
                title_elems = details_section.find_all('span', class_=re.compile('detailTitle', re.I), string=re.compile(title_text, re.I))
                if not title_elems:
                    # Try alternative selector
                    title_elems = details_section.find_all(string=re.compile(title_text, re.I))
                    title_elems = [e for e in title_elems if e.parent and 'detailTitle' in str(e.parent.get('class', []))]
                
                for title_elem in title_elems:
                    parent = title_elem.find_parent('li')
                    if parent:
                        return parent
                return None
            
            # Location
            location_parent = find_detail_by_title('Location')
            if location_parent:
                location_link = location_parent.select_one('a.a0nB0__link')
                if location_link:
                    details_data['location'] = location_link.get_text(strip=True)
                    details_data['location_url'] = location_link.get('href')
            
            # Price
            price_parent = find_detail_by_title('^Price$')
            if price_parent:
                price_text = price_parent.select_one('.a-Xkf__detail')
                if price_text:
                    details_data['price'] = price_text.get_text(strip=True)
            
            # Dining style
            dining_parent = find_detail_by_title('Dining style')
            if dining_parent:
                dining_text = dining_parent.select_one('.a-Xkf__detail')
                if dining_text:
                    details_data['dining_style'] = dining_text.get_text(strip=True)
            
            # Hours of operation
            hours_parent = find_detail_by_title('Hours')
            if hours_parent:
                hours_text = hours_parent.select_one('.a-Xkf__detail')
                if hours_text:
                    details_data['hours'] = hours_text.get_text(strip=True)
            
            # Website
            website_parent = find_detail_by_title('Website')
            if website_parent:
                website_link = website_parent.select_one('a.a0nB0__link')
                if website_link:
                    details_data['website'] = website_link.get('href')
            
            # Payment options
            payment_parent = find_detail_by_title('Payment')
            if payment_parent:
                payment_text = payment_parent.select_one('.a-Xkf__detail')
                if payment_text:
                    details_data['payment_options'] = payment_text.get_text(strip=True)
            
            # Dress code
            dress_parent = find_detail_by_title('Dress code')
            if dress_parent:
                dress_text = dress_parent.select_one('.a-Xkf__detail')
                if dress_text:
                    details_data['dress_code'] = dress_text.get_text(strip=True)
            
            # Private party facilities
            private_parent = find_detail_by_title('Private party facilities')
            if private_parent:
                private_text = private_parent.select_one('.a-Xkf__detail')
                if private_text:
                    details_data['private_party_facilities'] = private_text.get_text(strip=True)
            
            # Private party contact
            private_contact_parent = find_detail_by_title('Private party contact')
            if private_contact_parent:
                private_contact_text = private_contact_parent.select_one('.a-Xkf__detail')
                if private_contact_text:
                    details_data['private_party_contact'] = private_contact_text.get_text(strip=True)
            
            # Phone number
            phone_parent = find_detail_by_title('Phone')
            if phone_parent:
                phone_link = phone_parent.select_one('a.a0nB0__link[href^="tel:"]')
                if phone_link:
                    details_data['phone'] = phone_link.get_text(strip=True)
            
            # Cuisines
            cuisines_parent = find_detail_by_title('Cuisines')
            if cuisines_parent:
                cuisines_text = cuisines_parent.select_one('.a-Xkf__detail')
                if cuisines_text:
                    details_data['cuisines'] = [c.strip() for c in cuisines_text.get_text(strip=True).split(',')]
            
            # Cross street
            cross_parent = find_detail_by_title('Cross street')
            if cross_parent:
                cross_text = cross_parent.select_one('.a-Xkf__detail')
                if cross_text:
                    details_data['cross_street'] = cross_text.get_text(strip=True)
            
            # Parking details
            parking_parent = find_detail_by_title('Parking')
            if parking_parent:
                parking_text = parking_parent.select_one('.a-Xkf__detail')
                if parking_text:
                    details_data['parking_details'] = parking_text.get_text(strip=True)
            
            # Executive chef
            chef_parent = find_detail_by_title('Executive chef')
            if chef_parent:
                chef_text = chef_parent.select_one('.a-Xkf__detail')
                if chef_text:
                    details_data['executive_chef'] = chef_text.get_text(strip=True)
            
            # Additional info
            additional_parent = find_detail_by_title('Additional')
            if additional_parent:
                additional_text = additional_parent.select_one('.a-Xkf__detail')
                if additional_text:
                    additional_list = [a.strip() for a in additional_text.get_text(strip=True).split(',')]
                    details_data['additional'] = additional_list
            
            if details_data:
                restaurant_data['details'] = details_data
                if detail_logger:
                    detail_logger.log_section_data(url, "DETAILS", details_data, 
                        item_count=len(details_data))
        
        # ========== EXPERIENCES SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "EXPERIENCES", "STARTED")
        experiences_section = soup.select_one('section#experiences, [data-test="experiences"]')
        if experiences_section:
            experiences = []
            experience_items = experiences_section.select('li.aNJ-1__container, [data-test="experience-title"]')
            for exp in experience_items:
                exp_data = {}
                
                # Title
                title_elem = exp.select_one('h3[data-test="experience-title"], .aQTFf__title')
                if title_elem:
                    exp_data['title'] = title_elem.get_text(strip=True)
                
                # Price
                price_elem = exp.select_one('[data-test="experience-price"], .aMvJi__text')
                if price_elem:
                    exp_data['price'] = price_elem.get_text(strip=True)
                
                # Schedule
                schedule_elem = exp.select_one('[data-test="experience-schedule"], .ajdI7__schedule')
                if schedule_elem:
                    exp_data['schedule'] = schedule_elem.get_text(strip=True)
                
                # Description
                desc_elem = exp.select_one('.ar38L__description, .amRka__truncated')
                if desc_elem:
                    exp_data['description'] = desc_elem.get_text(strip=True)
                
                if exp_data:
                    experiences.append(exp_data)
            
            if experiences:
                restaurant_data['experiences'] = experiences
                if detail_logger:
                    detail_logger.log_section_data(url, "EXPERIENCES", experiences, 
                        item_count=len(experiences))
        
        # ========== OFFERS SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "OFFERS", "STARTED")
        offers_section = soup.select_one('section#offers, [data-test="offers"]')
        if offers_section:
            offers = []
            offer_items = offers_section.select('li.aNJ-1__container, [data-test="experience-title"]')
            for offer in offer_items:
                offer_data = {}
                
                # Title
                title_elem = offer.select_one('h3[data-test="experience-title"], .aQTFf__title')
                if title_elem:
                    offer_data['title'] = title_elem.get_text(strip=True)
                
                # Schedule
                schedule_elem = offer.select_one('[data-test="experience-schedule"], .ajdI7__schedule')
                if schedule_elem:
                    offer_data['schedule'] = schedule_elem.get_text(strip=True)
                
                # Times
                times_elem = offer.select_one('[data-test="experience-times"], .ajdI7__schedule')
                if times_elem:
                    offer_data['times'] = times_elem.get_text(strip=True)
                
                # Description
                desc_elem = offer.select_one('.ar38L__description')
                if desc_elem:
                    offer_data['description'] = desc_elem.get_text(strip=True)
                
                if offer_data:
                    offers.append(offer_data)
            
            if offers:
                restaurant_data['offers'] = offers
                if detail_logger:
                    detail_logger.log_section_data(url, "OFFERS", offers, item_count=len(offers))
        
        # ========== POPULAR DISHES SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "POPULAR_DISHES", "STARTED")
        dishes_section = soup.select_one('section#popular_dishes, [data-test="popular-dishes"]')
        if dishes_section:
            dishes = []
            dish_items = dishes_section.select('li[data-name], [data-testid="dish-card"]')
            for dish in dish_items:
                dish_data = {}
                
                # Name
                name_elem = dish.select_one('.aRyvx__dishName, [data-name]')
                if name_elem:
                    dish_data['name'] = name_elem.get_text(strip=True) or name_elem.get('data-name')
                
                # Description
                desc_elem = dish.select_one('.auJtF__dishDescription')
                if desc_elem:
                    dish_data['description'] = desc_elem.get_text(strip=True)
                
                # Reviews
                reviews_elem = dish.select_one('.ancEm__dishReviews')
                if reviews_elem:
                    dish_data['reviews'] = reviews_elem.get_text(strip=True)
                
                # Image
                img_elem = dish.select_one('img')
                if img_elem:
                    dish_data['image_url'] = img_elem.get('src')
                
                if dish_data.get('name'):
                    dishes.append(dish_data)
            
            if dishes:
                restaurant_data['popular_dishes'] = dishes
                if detail_logger:
                    detail_logger.log_section_data(url, "POPULAR_DISHES", dishes, item_count=len(dishes))
        
        # ========== MENU SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "MENU", "STARTED")
        menu_section = soup.select_one('section#menu, [data-test="menu-content"]')
        if menu_section:
            menu_data = {}
            
            # Menu tabs
            menu_tabs = menu_section.select('[data-test="menu-tabs-button"], button[role="tab"]')
            menu_tab_names = []
            for tab in menu_tabs:
                tab_text = tab.get_text(strip=True)
                if tab_text:
                    menu_tab_names.append(tab_text)
            if menu_tab_names:
                menu_data['menu_types'] = menu_tab_names
            
            # Menu items
            menu_items = []
            menu_sections = menu_section.select('article[data-test="menu-section"], .aHUd8__container')
            for section in menu_sections:
                section_title = section.select_one('h3.aEbvO__menuTitle')
                if section_title:
                    section_name = section_title.get_text(strip=True)
                    
                    items = section.select('li.aiC5T__item')
                    section_items = []
                    for item in items:
                        item_data = {}
                        
                        # Item title and price
                        item_details = item.select_one('.acT75__itemDetails')
                        if item_details:
                            title_span = item_details.select_one('span[data-test="item-title"]')
                            price_span = item_details.select_one('span[data-test="item-price"]')
                            if title_span:
                                item_data['title'] = title_span.get_text(strip=True)
                            if price_span:
                                item_data['price'] = price_span.get_text(strip=True)
                        
                        # Description
                        desc = item.select_one('.a3rtU__itemDescription')
                        if desc:
                            item_data['description'] = desc.get_text(strip=True)
                        
                        # Variations
                        variations = item.select('li.aMH0N__variationDetails')
                        if variations:
                            item_data['variations'] = []
                            for var in variations:
                                var_title = var.select_one('span[data-test="variation-title"]')
                                var_price = var.select_one('span[data-test="variation-price"]')
                                if var_title:
                                    var_data = {'title': var_title.get_text(strip=True)}
                                    if var_price:
                                        var_data['price'] = var_price.get_text(strip=True)
                                    item_data['variations'].append(var_data)
                        
                        if item_data.get('title'):
                            section_items.append(item_data)
                    
                    if section_items:
                        menu_items.append({
                            'section': section_name,
                            'items': section_items
                        })
            
            if menu_items:
                menu_data['menu_items'] = menu_items
            
            # Last updated
            last_updated = menu_section.select_one('[data-test="menu-footer"], .aUCtP__footerText')
            if last_updated:
                menu_data['last_updated'] = last_updated.get_text(strip=True)
            
            if menu_data:
                restaurant_data['menu'] = menu_data
                if detail_logger:
                    menu_items_count = len(menu_data.get('menu_items', []))
                    detail_logger.log_section_data(url, "MENU", menu_data, item_count=menu_items_count)
        
        # ========== REVIEWS SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "REVIEWS", "STARTED")
        reviews_section = soup.select_one('section#reviews, [data-test="reviews-list"]')
        if reviews_section:
            reviews_data = {}
            
            # Overall rating
            overall_rating = reviews_section.select_one('.atSiV__ratingValue')
            if overall_rating:
                try:
                    reviews_data['overall_rating'] = float(overall_rating.get_text(strip=True))
                except:
                    pass
            
            # Rating breakdown
            rating_list = reviews_section.select('li.aqPbf__rating-container')
            rating_breakdown = {}
            for rating_item in rating_list:
                rating_name = rating_item.select_one('[data-testid="rating-name"]')
                rating_value = rating_item.select_one('[data-testid="rating-value"]')
                if rating_name and rating_value:
                    try:
                        rating_breakdown[rating_name.get_text(strip=True)] = float(rating_value.get_text(strip=True))
                    except:
                        pass
            if rating_breakdown:
                reviews_data['rating_breakdown'] = rating_breakdown
            
            # Noise level
            noise_elem = reviews_section.select_one('[data-testid="icNoiseLevel"]')
            if noise_elem:
                noise_text = noise_elem.find_next(string=re.compile('Noise'))
                if noise_text:
                    noise_match = re.search(r'Noise\s*•\s*(.+)', noise_text)
                    if noise_match:
                        reviews_data['noise_level'] = noise_match.group(1).strip()
            
            # Review summary
            summary_elem = reviews_section.select_one('.aoSdt__summary')
            if summary_elem:
                reviews_data['summary'] = summary_elem.get_text(strip=True)
            
            # Individual reviews
            review_items = reviews_section.select('li.aafkK__review, [data-test="reviews-list-item"]')
            reviews_list = []
            for review in review_items[:10]:  # Limit to 10 reviews
                review_data = {}
                
                # Reviewer name
                reviewer = review.select_one('.aRUDc__primaryInfo')
                if reviewer:
                    review_data['reviewer'] = reviewer.get_text(strip=True)
                
                # Rating
                review_rating = review.select_one('.atSiV__ratingValue')
                if review_rating:
                    try:
                        review_data['rating'] = float(review_rating.get_text(strip=True))
                    except:
                        pass
                
                # Date
                date_elem = review.select_one('.aiLkE__submittedDate')
                if date_elem:
                    review_data['date'] = date_elem.get_text(strip=True)
                
                # Category ratings
                categories = review.select('li.a-k5x__category')
                category_ratings = {}
                for cat in categories:
                    cat_name = cat.get_text(strip=True).split()[0] if cat.get_text(strip=True) else None
                    cat_rating = cat.select_one('span')
                    if cat_name and cat_rating:
                        try:
                            category_ratings[cat_name] = int(cat_rating.get_text(strip=True))
                        except:
                            pass
                if category_ratings:
                    review_data['category_ratings'] = category_ratings
                
                # Review text
                review_text_elem = review.select_one('.a6rFG__reviewText span')
                if review_text_elem:
                    review_data['text'] = review_text_elem.get_text(strip=True)
                
                # Restaurant response
                response_elem = review.select_one('[data-test="public-restaurant-reply"]')
                if response_elem:
                    response_text = response_elem.select_one('.aGMTG__replyText span')
                    if response_text:
                        review_data['restaurant_response'] = response_text.get_text(strip=True)
                
                if review_data:
                    reviews_list.append(review_data)
            
            if reviews_list:
                reviews_data['reviews'] = reviews_list
            
            if reviews_data:
                restaurant_data['reviews'] = reviews_data
                if detail_logger:
                    reviews_count = len(reviews_data.get('reviews', []))
                    detail_logger.log_section_data(url, "REVIEWS", reviews_data, item_count=reviews_count)
        
        # ========== FAQs SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "FAQS", "STARTED")
        faqs_section = soup.select_one('section#faqs, [data-test="faqs-item"]')
        if faqs_section:
            faqs = []
            faq_items = faqs_section.select('[data-test="faqs-item"]')
            for faq in faq_items:
                faq_data = {}
                
                # Question
                question = faq.select_one('h4.aD1DF__title, button h4')
                if question:
                    faq_data['question'] = question.get_text(strip=True)
                
                # Answer
                answer = faq.select_one('.a0EgX__text, [aria-labelledby] p')
                if answer:
                    faq_data['answer'] = answer.get_text(strip=True)
                
                if faq_data.get('question'):
                    faqs.append(faq_data)
            
            if faqs:
                restaurant_data['faqs'] = faqs
                if detail_logger:
                    detail_logger.log_section_data(url, "FAQS", faqs, item_count=len(faqs))
        
        # ========== PHOTOS SECTION ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "PHOTOS", "STARTED")
        photos_section = soup.select_one('section#photos, [data-test="restaurant-photos"]')
        if photos_section:
            photo_count_elem = photos_section.select_one('h2')
            if photo_count_elem:
                photo_count_text = photo_count_elem.get_text(strip=True)
                photo_count_match = re.search(r'(\d+)\s+Photos?', photo_count_text)
                if photo_count_match:
                    restaurant_data['photo_count'] = int(photo_count_match.group(1))
            
            # Photo URLs
            photo_buttons = photos_section.select('[data-testid="gallery-photo"], button[aria-label*="Enlarge"]')
            photos = []
            for photo in photo_buttons[:20]:  # Limit to 20
                img = photo.select_one('img')
                if img:
                    photo_url = img.get('src')
                    if photo_url:
                        photos.append(photo_url)
            if photos:
                restaurant_data['photos'] = photos
                if detail_logger:
                    detail_logger.log_section_data(url, "PHOTOS", photos, item_count=len(photos))
        
        # ========== BOOKED TIMES INFO ==========
        if detail_logger:
            detail_logger.log_section_extraction(url, "BOOKING_INFO", "STARTED")
        booked_today = soup.select_one('[data-test="icSocialProof"]')
        if booked_today:
            booked_text = booked_today.find_next(string=re.compile('Booked'))
            if booked_text:
                booked_match = re.search(r'Booked\s+(\d+)\s+times?\s+today', booked_text, re.I)
                if booked_match:
                    restaurant_data['booked_today'] = int(booked_match.group(1))
        
        # ========== AVAILABLE TIME SLOTS ==========
        time_slots = soup.select('[data-test="time-slot"], [data-testid^="time-slot"]')
        if time_slots:
            available_times = []
            for slot in time_slots:
                time_text = slot.get_text(strip=True)
                if time_text and re.match(r'\d+:\d+\s*(AM|PM)', time_text, re.I):
                    available_times.append(time_text)
            if available_times:
                restaurant_data['available_time_slots'] = available_times
        
        # Log overview data
        if detail_logger:
            overview_fields = ['name', 'rating', 'review_count', 'price_range', 'cuisine', 'address', 'neighborhood']
            overview_data = {k: restaurant_data.get(k) for k in overview_fields if restaurant_data.get(k)}
            if overview_data:
                detail_logger.log_section_data(url, "OVERVIEW", overview_data)
        
        # Add source URL
        restaurant_data['url'] = url
        restaurant_data['source'] = 'opentable'
        
        if detail_logger:
            detail_logger.log_section_extraction(url, "ALL_SECTIONS", "COMPLETE")
            # Log summary of what was extracted
            sections_found = []
            if restaurant_data.get('name'):
                sections_found.append('Overview')
            if restaurant_data.get('details'):
                sections_found.append('Details')
            if restaurant_data.get('experiences'):
                sections_found.append(f"Experiences ({len(restaurant_data['experiences'])})")
            if restaurant_data.get('offers'):
                sections_found.append(f"Offers ({len(restaurant_data['offers'])})")
            if restaurant_data.get('popular_dishes'):
                sections_found.append(f"Popular Dishes ({len(restaurant_data['popular_dishes'])})")
            if restaurant_data.get('menu'):
                sections_found.append('Menu')
            if restaurant_data.get('reviews'):
                sections_found.append('Reviews')
            if restaurant_data.get('faqs'):
                sections_found.append(f"FAQs ({len(restaurant_data['faqs'])})")
            if restaurant_data.get('photos'):
                sections_found.append(f"Photos ({len(restaurant_data['photos'])})")
            
            detail_logger.log_restaurant_processing(url, "PARSING_COMPLETE", 
                f"Sections found: {', '.join(sections_found) if sections_found else 'None'}")
        
        return restaurant_data
    
    def _format_address(self, address_data: Any) -> str:
        """Format address from structured data"""
        if isinstance(address_data, str):
            return address_data
        if isinstance(address_data, dict):
            parts = []
            if address_data.get('streetAddress'):
                parts.append(address_data['streetAddress'])
            if address_data.get('addressLocality'):
                parts.append(address_data['addressLocality'])
            if address_data.get('addressRegion'):
                parts.append(address_data['addressRegion'])
            if address_data.get('postalCode'):
                parts.append(address_data['postalCode'])
            return ', '.join(parts)
        return ''

    async def extract_restaurant_urls_from_listing(
        self,
        listing_url: str,
        use_javascript: bool = True
    ) -> List[str]:
        """
        Extract restaurant URLs from a listing page (Yelp, OpenTable, etc.).
        This is Step 1: Get all restaurant URLs, don't extract data yet.
        
        Returns:
            List of restaurant page URLs
        """
        logger.info(f"Extracting restaurant URLs from listing page: {listing_url}")
        if detail_logger:
            detail_logger.log_separator(f"EXTRACTING RESTAURANT URLS FROM LISTING")
            detail_logger.log_url_visit(listing_url, status="EXTRACTING_URLS")
        
        # Scrape the listing page
        listing_data = await self.scrape(listing_url, use_javascript=use_javascript)
        
        # Get HTML for parsing
        html_content = listing_data.get('text_content', '')
        if not html_content and use_javascript:
            # For JS pages, we need to get HTML differently
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto(listing_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(3000)
                    html_content = await page.content()
                    await context.close()
                    await browser.close()
            except Exception as e:
                logger.warning(f"Failed to get HTML with Playwright: {e}")
        
        if not html_content:
            # Fallback: use httpx
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = await client.get(listing_url, headers=self.session.headers)
                    response.raise_for_status()
                    html_content = response.text
            except Exception as e:
                logger.error(f"Failed to get HTML: {e}")
                return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract embedded JSON first (most reliable)
        embedded_data = self._extract_embedded_json(soup, listing_url)
        
        restaurant_urls = []
        seen_urls = set()
        
        # Method 1: Extract from embedded JSON (Yelp, OpenTable, etc.)
        if embedded_data.get('restaurants'):
            for restaurant in embedded_data['restaurants']:
                url = restaurant.get('url') or restaurant.get('website') or restaurant.get('yelp_url')
                if url and url not in seen_urls:
                    restaurant_urls.append(url)
                    seen_urls.add(url)
        
        if embedded_data.get('businesses'):
            for business in embedded_data['businesses']:
                url = business.get('url') or business.get('website') or business.get('yelp_url')
                if url and url not in seen_urls:
                    restaurant_urls.append(url)
                    seen_urls.add(url)
        
        # Method 2: Extract from links (common pattern)
        links = listing_data.get('links', [])
        for link in links:
            if isinstance(link, dict):
                href = link.get('href', '')
                text = link.get('text', '').lower()
            else:
                href = str(link)
                text = ''
            
            if not href:
                continue
            
            # Normalize URL first
            if href.startswith('/'):
                href = urljoin(listing_url, href)
            
            # Check if this looks like a restaurant page URL
            href_lower = href.lower()
            is_restaurant_url = (
                ('/biz/' in href_lower and 'yelp.com' in href_lower) or
                ('/restaurant/' in href_lower) or
                ('/r/' in href_lower and 'opentable.com' in href_lower) or
                (href_lower.startswith('https://www.opentable.com/r/') or href_lower.startswith('http://www.opentable.com/r/')) or
                ('restaurant' in text and len(text) > 5 and len(text) < 100) or
                (any(keyword in href_lower for keyword in ['restaurant', 'dining', 'cafe', 'steakhouse']))
            )
            
            if is_restaurant_url and href not in seen_urls and href.startswith('http'):
                restaurant_urls.append(href)
                seen_urls.add(href)
        
        # Method 2b: Extract OpenTable URLs directly from HTML using BeautifulSoup
        if 'opentable.com' in listing_url.lower():
            # Find all links that match OpenTable restaurant URL pattern
            opentable_links = soup.find_all('a', href=re.compile(r'/r/[^/]+', re.I))
            for link in opentable_links:
                href = link.get('href', '')
                if href:
                    # Normalize URL
                    if href.startswith('/'):
                        href = urljoin(listing_url, href)
                    elif not href.startswith('http'):
                        continue
                    
                    # Check if it's a valid OpenTable restaurant URL
                    if '/r/' in href.lower() and 'opentable.com' in href.lower():
                        # Clean URL (remove query params except necessary ones)
                        parsed_url = urlparse(href)
                        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                        if clean_url not in seen_urls:
                            restaurant_urls.append(clean_url)
                            seen_urls.add(clean_url)
                            seen_urls.add(href)
        
        # Method 3: Extract from JavaScript variables (if available)
        if use_javascript:
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto(listing_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(3000)
                    
                    # Extract URLs from JavaScript
                    js_urls = await page.evaluate("""
                        () => {
                            const urls = [];
                            
                            // Find all restaurant links - improved for OpenTable
                            const linkSelectors = [
                                'a[href*="/biz/"]',  // Yelp
                                'a[href*="/restaurant/"]',  // Generic
                                'a[href*="/r/"]',  // OpenTable
                                'a[href^="https://www.opentable.com/r/"]',  // OpenTable full URLs
                                'a[href^="/r/"]'  // OpenTable relative URLs
                            ];
                            
                            linkSelectors.forEach(selector => {
                                const links = document.querySelectorAll(selector);
                                links.forEach(link => {
                                    const href = link.href || link.getAttribute('href');
                                    if (href) {
                                        // Normalize relative URLs
                                        if (href.startsWith('/')) {
                                            urls.push(window.location.origin + href);
                                        } else if (href.startsWith('http')) {
                                            urls.push(href);
                                        }
                                    }
                                });
                            });
                            
                            // Also check for data in window variables
                            const windowVars = [
                                window.__PRELOADED_STATE__,
                                window.__NEXT_DATA__,
                                window.pageData,
                                window.initialData
                            ];
                            
                            windowVars.forEach(data => {
                                if (data) {
                                    try {
                                        const dataStr = JSON.stringify(data);
                                        // Match OpenTable restaurant URLs
                                        const urlPatterns = [
                                            /https?:\\/\\/[^"\\s]*opentable\\.com\\/r\\/[^"\\s]+/g,
                                            /https?:\\/\\/[^"\\s]+\\/(?:biz|restaurant|r)\\/[^"\\s]+/g
                                        ];
                                        
                                        urlPatterns.forEach(pattern => {
                                            const matches = dataStr.match(pattern);
                                            if (matches) {
                                                urls.push(...matches);
                                            }
                                        });
                                    } catch (e) {
                                        // Skip if can't stringify
                                    }
                                }
                            });
                            
                            // Also check for data attributes
                            const dataLinks = document.querySelectorAll('[data-url], [data-href], [data-restaurant-url]');
                            dataLinks.forEach(elem => {
                                const url = elem.getAttribute('data-url') || 
                                           elem.getAttribute('data-href') || 
                                           elem.getAttribute('data-restaurant-url');
                                if (url && (url.includes('/r/') || url.includes('/biz/') || url.includes('/restaurant/'))) {
                                    if (url.startsWith('/')) {
                                        urls.push(window.location.origin + url);
                                    } else if (url.startsWith('http')) {
                                        urls.push(url);
                                    }
                                }
                            });
                            
                            return [...new Set(urls)];
                        }
                    """)
                    
                    for url in js_urls:
                        if url and url not in seen_urls:
                            restaurant_urls.append(url)
                            seen_urls.add(url)
                    
                    await context.close()
                    await browser.close()
            except Exception as e:
                logger.debug(f"JavaScript URL extraction failed: {e}")
        
        # Clean and normalize URLs
        cleaned_urls = []
        for url in restaurant_urls:
            # Remove fragments and common tracking params
            url = url.split('#')[0]
            url = re.sub(r'[?&](utm_[^&]*|ref=[^&]*|source=[^&]*)', '', url)
            
            # Only keep valid restaurant URLs
            if url and url.startswith('http') and url not in seen_urls:
                cleaned_urls.append(url)
                seen_urls.add(url)
        
        logger.info(f"Extracted {len(cleaned_urls)} restaurant URLs from listing page")
        if detail_logger:
            detail_logger.log_listing_urls_found(listing_url, cleaned_urls)
            detail_logger.log_separator()
        
        return cleaned_urls[:100]  # Limit to 100 URLs

    async def extract_from_individual_pages(
        self,
        restaurants: List[Dict[str, Any]],
        use_javascript: bool = True,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Extract detailed data from individual restaurant pages.
        Takes a list of restaurants (from listing pages) and visits each individual page
        to get complete data like full addresses, amenities, menu URLs, etc.
        
        Args:
            restaurants: List of restaurant dicts with at least 'url' or 'name'
            use_javascript: Whether to use Playwright for JS-rendered pages
            max_concurrent: Maximum concurrent page requests
        
        Returns:
            List of restaurants with merged data from listing + individual pages
        """
        import asyncio
        
        if not restaurants:
            return []
        
        logger.info(f"Extracting detailed data from {len(restaurants)} individual restaurant pages")
        
        # Extract URLs from restaurants
        restaurant_urls = []
        for restaurant in restaurants:
            url = restaurant.get('url') or restaurant.get('website') or restaurant.get('yelp_url')
            if url:
                restaurant_urls.append((restaurant, url))
            else:
                # If no URL, keep the restaurant as-is
                logger.warning(f"No URL found for restaurant: {restaurant.get('name', 'Unknown')}")
        
        if not restaurant_urls:
            logger.warning("No restaurant URLs found to extract detailed data from")
            return restaurants
        
        # Process restaurants in batches to avoid overwhelming the server
        detailed_restaurants = []
        
        async def extract_single_restaurant(restaurant_data: Dict, url: str) -> Dict[str, Any]:
            """Extract detailed data from a single restaurant page"""
            start_time = time.time()
            try:
                logger.info(f"Extracting detailed data from: {url}")
                if detail_logger:
                    detail_logger.log_separator(f"PROCESSING RESTAURANT PAGE")
                    detail_logger.log_url_visit(url, status="STARTED")
                    detail_logger.log_restaurant_processing(url, "INITIALIZED")
                
                # Check if this is an OpenTable URL - use specialized parser
                is_opentable = 'opentable.com' in url.lower() and '/r/' in url.lower()
                if detail_logger:
                    detail_logger.log_restaurant_processing(url, "DETECTED_TYPE", 
                        f"OpenTable: {is_opentable}")
                
                # Get HTML content for parsing
                html_content = None
                if use_javascript or is_opentable:
                    # For Playwright, get HTML directly
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "FETCHING_HTML", "Using Playwright")
                    try:
                        from playwright.async_api import async_playwright
                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                            context = await browser.new_context()
                            page = await context.new_page()
                            await page.goto(url, wait_until="networkidle", timeout=30000)
                            await page.wait_for_timeout(3000)  # Wait for dynamic content
                            html_content = await page.content()
                            await context.close()
                            await browser.close()
                        if detail_logger:
                            detail_logger.log_restaurant_processing(url, "HTML_FETCHED", 
                                f"Playwright - Length: {len(html_content):,} bytes")
                    except Exception as e:
                        logger.warning(f"Failed to get HTML with Playwright: {e}")
                        if detail_logger:
                            detail_logger.log_url_error(url, f"Playwright failed: {str(e)}")
                
                # Fallback: get HTML with httpx
                if not html_content:
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "FETCHING_HTML", "Using httpx (fallback)")
                    try:
                        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                            response = await client.get(url, headers=self.session.headers)
                            response.raise_for_status()
                            html_content = response.text
                        if detail_logger:
                            detail_logger.log_restaurant_processing(url, "HTML_FETCHED", 
                                f"httpx - Length: {len(html_content):,} bytes | Status: {response.status_code}")
                    except Exception as e:
                        logger.warning(f"Failed to get HTML with httpx: {e}")
                        if detail_logger:
                            detail_logger.log_url_error(url, f"httpx failed: {str(e)}")
                
                if not html_content:
                    logger.warning(f"Could not get HTML content from {url}")
                    if detail_logger:
                        detail_logger.log_url_error(url, "No HTML content retrieved")
                    return restaurant_data
                
                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Use OpenTable-specific parser if it's an OpenTable URL
                if is_opentable:
                    logger.info("Using OpenTable-specific parser for detailed extraction")
                    if detail_logger:
                        detail_logger.log_restaurant_processing(url, "PARSING", "Using OpenTable parser")
                    opentable_data = self._parse_opentable_restaurant_page(soup, url, html_content)
                    # Merge with existing restaurant data
                    detailed_restaurant = restaurant_data.copy()
                    detailed_restaurant.update(opentable_data)
                    
                    duration = time.time() - start_time
                    logger.info(f"Successfully extracted OpenTable data for: {detailed_restaurant.get('name', 'Unknown')}")
                    if detail_logger:
                        detail_logger.log_data_summary(url, opentable_data)
                        detail_logger.log_url_complete(url, html_length=len(html_content), duration=duration)
                        detail_logger.log_separator()
                    return detailed_restaurant
                
                # For non-OpenTable pages, use general extraction
                # Scrape the page for structured data
                page_data = await self.scrape(url, use_javascript=use_javascript)
                
                # Parse HTML for embedded data
                embedded_data = self._extract_embedded_json(soup, url)
                
                # Merge detailed data into restaurant
                detailed_restaurant = restaurant_data.copy()
                
                # Extract from embedded JSON-LD (most comprehensive)
                if embedded_data.get('restaurants'):
                    embedded_restaurant = embedded_data['restaurants'][0]
                    detailed_restaurant.update(embedded_restaurant)
                elif embedded_data.get('businesses'):
                    embedded_business = embedded_data['businesses'][0]
                    detailed_restaurant.update(embedded_business)
                
                # Extract from page data
                if page_data.get('title'):
                    detailed_restaurant['page_title'] = page_data['title']
                
                # Extract structured data from HTML
                structured_data = await self._extract_structured_data(soup, url, str(page_data))
                
                # Attach all page links so each restaurant carries full hyperlink context
                page_links = structured_data.get('links') or page_data.get('links')
                if page_links:
                    detailed_restaurant['links'] = page_links
                
                # Merge address data (individual pages have full addresses)
                if structured_data.get('text_content'):
                    # Try to extract address from text
                    address_patterns = [
                        r'\d+\s+[A-Za-z0-9\s,]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Circle|Cir)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}',
                        r'\d+[^,]+,\s*[^,]+,\s*[A-Z]{2}\s+\d{5}',
                    ]
                    for pattern in address_patterns:
                        match = re.search(pattern, structured_data['text_content'])
                        if match and not detailed_restaurant.get('address'):
                            detailed_restaurant['address'] = match.group(0).strip()
                            break
                
                # Extract phone from page
                phone_pattern = r'(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})'
                if structured_data.get('text_content') and not detailed_restaurant.get('phone'):
                    phone_match = re.search(phone_pattern, structured_data['text_content'])
                    if phone_match:
                        detailed_restaurant['phone'] = phone_match.group(1)
                
                # Extract menu URLs from links
                menu_urls = {}
                for link in structured_data.get('links', []):
                    href = link.get('href', '').lower()
                    text = link.get('text', '').lower()
                    
                    if 'menu' in href or 'menu' in text:
                        if 'lunch' in href or 'lunch' in text:
                            menu_urls['lunch_menu'] = link.get('href')
                        elif 'dinner' in href or 'dinner' in text:
                            menu_urls['dinner_menu'] = link.get('href')
                        elif 'brunch' in href or 'brunch' in text:
                            menu_urls['brunch_menu'] = link.get('href')
                        elif 'drink' in href or 'drink' in text or 'bar' in href:
                            menu_urls['drinks_menu'] = link.get('href')
                        elif 'dessert' in href or 'dessert' in text:
                            menu_urls['dessert_menu'] = link.get('href')
                        elif 'order' in href or 'order' in text or 'delivery' in href:
                            menu_urls['online_ordering'] = link.get('href')
                        else:
                            menu_urls['main_menu'] = menu_urls.get('main_menu') or link.get('href')
                
                if menu_urls:
                    detailed_restaurant['menu_urls'] = menu_urls
                
                # Extract amenities from text content
                amenities = []
                amenities_keywords = {
                    'wifi': ['wifi', 'wi-fi', 'wireless', 'internet'],
                    'parking': ['parking', 'valet', 'garage', 'lot'],
                    'outdoor_seating': ['outdoor', 'patio', 'terrace', 'al fresco'],
                    'wheelchair_accessible': ['wheelchair', 'accessible', 'ada'],
                    'pet_friendly': ['pet', 'dog', 'friendly'],
                    'live_music': ['live music', 'entertainment', 'band'],
                    'tv': ['tv', 'television', 'sports'],
                    'private_dining': ['private', 'event', 'party room'],
                }
                
                text_lower = structured_data.get('text_content', '').lower()
                for amenity, keywords in amenities_keywords.items():
                    if any(keyword in text_lower for keyword in keywords):
                        amenities.append(amenity)
                
                if amenities:
                    detailed_restaurant['amenities'] = amenities
                
                # Merge all page data
                detailed_restaurant['page_data'] = {
                    'url': url,
                    'scraped_at': page_data.get('scraped_at'),
                    'html_length': len(str(page_data))
                }
                
                logger.info(f"Successfully extracted detailed data for: {detailed_restaurant.get('name', 'Unknown')}")
                return detailed_restaurant
                
            except Exception as e:
                logger.error(f"Failed to extract detailed data from {url}: {str(e)}")
                # Return original restaurant data if extraction fails
                return restaurant_data
        
        # Process in batches with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def extract_with_semaphore(restaurant_data, url):
            async with semaphore:
                return await extract_single_restaurant(restaurant_data, url)
        
        # Create tasks for all restaurants
        tasks = [extract_with_semaphore(restaurant, url) for restaurant, url in restaurant_urls]
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing restaurant {i}: {result}")
                # Keep original restaurant data
                if i < len(restaurants):
                    detailed_restaurants.append(restaurants[i])
            else:
                detailed_restaurants.append(result)
        
        # Add restaurants that didn't have URLs
        processed_names = {r.get('name', '').lower() for r in detailed_restaurants if r.get('name')}
        for restaurant in restaurants:
            if restaurant.get('name', '').lower() not in processed_names:
                detailed_restaurants.append(restaurant)
        
        logger.info(f"Completed detailed extraction for {len(detailed_restaurants)} restaurants")
        return detailed_restaurants

    def close(self):
        self.session.close()
        if self.playwright_browser:
            # Playwright cleanup would go here if we maintain a persistent browser
            pass
