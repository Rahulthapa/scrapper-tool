import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
import httpx
import re
from urllib.parse import urljoin, urlparse, quote_plus
import json
import logging

logger = logging.getLogger(__name__)


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
            
            # Check if this looks like a restaurant page URL
            href_lower = href.lower()
            is_restaurant_url = (
                ('/biz/' in href_lower and 'yelp.com' in href_lower) or
                ('/restaurant/' in href_lower) or
                ('/r/' in href_lower and 'opentable.com' in href_lower) or
                ('restaurant' in text and len(text) > 5 and len(text) < 100) or
                (any(keyword in href_lower for keyword in ['restaurant', 'dining', 'cafe', 'steakhouse']))
            )
            
            if is_restaurant_url and href not in seen_urls:
                # Normalize URL
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(listing_url, href)
                
                if href.startswith('http') and href not in seen_urls:
                    restaurant_urls.append(href)
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
                            
                            // Find all restaurant links
                            const links = document.querySelectorAll('a[href*="/biz/"], a[href*="/restaurant/"], a[href*="/r/"]');
                            links.forEach(link => {
                                const href = link.href;
                                if (href && (href.includes('/biz/') || href.includes('/restaurant/') || href.includes('/r/'))) {
                                    urls.push(href);
                                }
                            });
                            
                            // Also check for data in window variables
                            if (window.__PRELOADED_STATE__) {
                                const data = window.__PRELOADED_STATE__;
                                // Try to find restaurant URLs in the data
                                const dataStr = JSON.stringify(data);
                                const urlMatches = dataStr.match(/https?:\\/\\/[^"\\s]+\\/(?:biz|restaurant|r)\\/[^"\\s]+/g);
                                if (urlMatches) {
                                    urls.push(...urlMatches);
                                }
                            }
                            
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
            try:
                logger.info(f"Extracting detailed data from: {url}")
                
                # Get HTML content for parsing
                html_content = None
                if use_javascript:
                    # For Playwright, get HTML directly
                    try:
                        from playwright.async_api import async_playwright
                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                            context = await browser.new_context()
                            page = await context.new_page()
                            await page.goto(url, wait_until="networkidle", timeout=30000)
                            await page.wait_for_timeout(2000)
                            html_content = await page.content()
                            await context.close()
                            await browser.close()
                    except Exception as e:
                        logger.warning(f"Failed to get HTML with Playwright: {e}")
                
                # Fallback: get HTML with httpx
                if not html_content:
                    try:
                        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                            response = await client.get(url, headers=self.session.headers)
                            response.raise_for_status()
                            html_content = response.text
                    except Exception as e:
                        logger.warning(f"Failed to get HTML with httpx: {e}")
                
                if not html_content:
                    logger.warning(f"Could not get HTML content from {url}")
                    return restaurant_data
                
                # Scrape the page for structured data
                page_data = await self.scrape(url, use_javascript=use_javascript)
                
                # Parse HTML for embedded data
                soup = BeautifulSoup(html_content, 'html.parser')
                
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
