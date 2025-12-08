"""
Parsing layer for extracting data from different sources.
Each source has its own parser function.
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup, Tag
import lxml

logger = logging.getLogger(__name__)


def extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract JSON-LD structured data"""
    json_ld_data = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                json_ld_data.extend(data)
            else:
                json_ld_data.append(data)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return json_ld_data


def extract_microdata(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract microdata (itemscope/itemprop)"""
    microdata = []
    items = soup.find_all(attrs={'itemscope': True})
    
    for item in items:
        data = {}
        itemtype = item.get('itemtype', '')
        if itemtype:
            data['@type'] = itemtype
        
        props = item.find_all(attrs={'itemprop': True})
        for prop in props:
            prop_name = prop.get('itemprop', '')
            if prop_name:
                # Get value
                if prop.name == 'meta':
                    value = prop.get('content', '')
                elif prop.name in ['a', 'link']:
                    value = prop.get('href', '')
                elif prop.name == 'img':
                    value = prop.get('src', '')
                elif prop.name == 'time':
                    value = prop.get('datetime', '') or prop.string
                else:
                    value = prop.string or prop.get_text(strip=True)
                
                if value:
                    if prop_name in data:
                        if not isinstance(data[prop_name], list):
                            data[prop_name] = [data[prop_name]]
                        data[prop_name].append(value)
                    else:
                        data[prop_name] = value
        
        if data:
            microdata.append(data)
    
    return microdata


def extract_og_tags(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract Open Graph tags"""
    og_tags = {}
    for meta in soup.find_all('meta', property=re.compile(r'^og:')):
        property_name = meta.get('property', '').replace('og:', '')
        content = meta.get('content', '')
        if property_name and content:
            og_tags[property_name] = content
    return og_tags


def safe_text(element: Optional[Tag], default: str = "") -> str:
    """Safely extract text from BeautifulSoup element"""
    if element is None:
        return default
    text = element.get_text(strip=True) if hasattr(element, 'get_text') else str(element)
    return text.strip() if text else default


def safe_attr(element: Optional[Tag], attr: str, default: str = "") -> str:
    """Safely extract attribute from BeautifulSoup element"""
    if element is None:
        return default
    value = element.get(attr, default)
    return str(value).strip() if value else default


def find_email(text: str) -> str:
    """Find email address in text"""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    matches = re.findall(pattern, text)
    return matches[0] if matches else ""


def find_phone(text: str) -> str:
    """Find phone number in text"""
    patterns = [
        r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\+?\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0]
    return ""


def parse_google_maps(html: str, url: str) -> Dict[str, Any]:
    """
    Parse Google Maps business listing page
    
    Returns:
        Dictionary with extracted fields
    """
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    # Extract JSON-LD
    json_ld = extract_json_ld(soup)
    if json_ld:
        data['_json_ld'] = json_ld
    
    # Title
    title_selectors = [
        'h1[data-attrid="title"]',
        'h1.section-hero-header-title-title',
        'h1[data-section-id="title"]',
        'h1'
    ]
    for selector in title_selectors:
        title_el = soup.select_one(selector)
        if title_el:
            data['title'] = safe_text(title_el)
            break
    
    # Address
    address_selectors = [
        'button[data-item-id="address"]',
        'span[aria-label*="Address"]',
        '[data-item-id="address"]'
    ]
    for selector in address_selectors:
        addr_el = soup.select_one(selector)
        if addr_el:
            data['address'] = safe_text(addr_el)
            break
    
    # Phone
    phone_el = soup.select_one('button[data-item-id="phone"]')
    if phone_el:
        data['phone'] = safe_text(phone_el)
    
    # Website
    website_el = soup.select_one('a[data-item-id="authority"]')
    if website_el:
        data['website'] = safe_attr(website_el, 'href')
    
    # Rating
    rating_selectors = [
        'div[class*="gm2-display-2"] span[aria-hidden="true"]',
        'div[aria-label*="stars"]',
        '[aria-label*="rating"]'
    ]
    for selector in rating_selectors:
        rating_el = soup.select_one(selector)
        if rating_el:
            rating_text = safe_text(rating_el)
            # Extract number
            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
            if rating_match:
                data['rating'] = rating_match.group(1)
            break
    
    # Price Range
    price_el = soup.select_one('span[aria-label*="Price"]')
    if price_el:
        price_text = safe_text(price_el)
        price_match = re.search(r'(\${1,4})', price_text)
        if price_match:
            data['price_range'] = price_match.group(1)
    
    # Coordinates from URL
    coord_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if coord_match:
        data['latitude'] = coord_match.group(1)
        data['longitude'] = coord_match.group(2)
    
    # Featured Image
    img_el = soup.select_one('meta[property="og:image"]')
    if img_el:
        data['featured_image_url'] = safe_attr(img_el, 'content')
    else:
        img_el = soup.select_one('img[src]')
        if img_el:
            data['featured_image_url'] = safe_attr(img_el, 'src')
    
    # Description/Content
    desc_selectors = [
        '[data-section-id="si_g"]',
        '[jsaction="pane.placeActions.moreDetails"]',
        '.section-info-text'
    ]
    for selector in desc_selectors:
        desc_el = soup.select_one(selector)
        if desc_el:
            data['description'] = safe_text(desc_el)
            break
    
    # Extract from JSON-LD if available
    if json_ld:
        for item in json_ld:
            if isinstance(item, dict):
                if item.get('@type') in ['LocalBusiness', 'Restaurant', 'FoodEstablishment']:
                    if 'name' in item and 'title' not in data:
                        data['title'] = item.get('name', '')
                    if 'address' in item and 'address' not in data:
                        addr = item.get('address', {})
                        if isinstance(addr, dict):
                            data['address'] = ', '.join([
                                addr.get('streetAddress', ''),
                                addr.get('addressLocality', ''),
                                addr.get('addressRegion', ''),
                                addr.get('postalCode', '')
                            ]).strip(', ')
                    if 'telephone' in item and 'phone' not in data:
                        data['phone'] = item.get('telephone', '')
                    if 'url' in item and 'website' not in data:
                        data['website'] = item.get('url', '')
                    if 'aggregateRating' in item and 'rating' not in data:
                        rating = item.get('aggregateRating', {})
                        if isinstance(rating, dict):
                            data['rating'] = str(rating.get('ratingValue', ''))
                    if 'priceRange' in item and 'price_range' not in data:
                        data['price_range'] = item.get('priceRange', '')
                    if 'geo' in item:
                        geo = item.get('geo', {})
                        if isinstance(geo, dict):
                            if 'latitude' in geo and 'latitude' not in data:
                                data['latitude'] = str(geo.get('latitude', ''))
                            if 'longitude' in geo and 'longitude' not in data:
                                data['longitude'] = str(geo.get('longitude', ''))
    
    data['source'] = 'Google Maps'
    data['source_url'] = url
    
    return data


def parse_yelp(html: str, url: str) -> Dict[str, Any]:
    """
    Parse Yelp business page
    
    Returns:
        Dictionary with extracted fields
    """
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    # Extract JSON-LD
    json_ld = extract_json_ld(soup)
    if json_ld:
        data['_json_ld'] = json_ld
    
    # Title
    title_el = soup.select_one('h1[class*="heading"], h1')
    if title_el:
        data['title'] = safe_text(title_el)
    
    # Address
    address_el = soup.select_one('address, p[class*="address"]')
    if address_el:
        data['address'] = safe_text(address_el)
    
    # Phone
    phone_el = soup.select_one('p[class*="phone"], a[href^="tel:"]')
    if phone_el:
        phone_text = safe_text(phone_el)
        if not phone_text:
            phone_text = safe_attr(phone_el, 'href').replace('tel:', '')
        data['phone'] = phone_text
    
    # Website
    website_el = soup.select_one('a[href*="biz_redir"], a[class*="website"]')
    if website_el:
        data['website'] = safe_attr(website_el, 'href')
    
    # Rating
    rating_el = soup.select_one('div[role="img"][aria-label*="star"]')
    if rating_el:
        rating_text = safe_attr(rating_el, 'aria-label', '')
        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
        if rating_match:
            data['rating'] = rating_match.group(1)
    
    # Price Range
    price_el = soup.select_one('span[class*="price-range"]')
    if price_el:
        price_text = safe_text(price_el)
        price_match = re.search(r'(\${1,4})', price_text)
        if price_match:
            data['price_range'] = price_match.group(1)
    
    # Amenities
    amenities = []
    amenity_els = soup.select('div[class*="amenity"], span[class*="amenity"]')
    for el in amenity_els:
        amenity_text = safe_text(el)
        if amenity_text:
            amenities.append(amenity_text)
    
    if amenities:
        data['amenities'] = amenities
    
    # Check for outdoor dining
    body_text = soup.get_text().lower()
    if 'outdoor seating' in body_text or 'outdoor dining' in body_text:
        data['outdoor_dining'] = 'Yes'
    
    # Check for noise level
    noise_match = re.search(r'noise level[:\s]+(\w+)', body_text, re.IGNORECASE)
    if noise_match:
        data['noise'] = noise_match.group(1).capitalize()
    
    # Extract from JSON-LD
    if json_ld:
        for item in json_ld:
            if isinstance(item, dict):
                if item.get('@type') in ['LocalBusiness', 'Restaurant']:
                    if 'name' in item and 'title' not in data:
                        data['title'] = item.get('name', '')
                    if 'address' in item and 'address' not in data:
                        addr = item.get('address', {})
                        if isinstance(addr, dict):
                            data['address'] = ', '.join([
                                addr.get('streetAddress', ''),
                                addr.get('addressLocality', ''),
                                addr.get('addressRegion', ''),
                                addr.get('postalCode', '')
                            ]).strip(', ')
                    if 'telephone' in item and 'phone' not in data:
                        data['phone'] = item.get('telephone', '')
                    if 'url' in item and 'website' not in data:
                        data['website'] = item.get('url', '')
                    if 'aggregateRating' in item and 'rating' not in data:
                        rating = item.get('aggregateRating', {})
                        if isinstance(rating, dict):
                            data['rating'] = str(rating.get('ratingValue', ''))
    
    data['source'] = 'Yelp'
    data['source_url'] = url
    
    return data


def parse_opentable(html: str, url: str) -> Dict[str, Any]:
    """
    Parse OpenTable restaurant page
    
    Returns:
        Dictionary with extracted fields
    """
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    # Extract JSON-LD
    json_ld = extract_json_ld(soup)
    if json_ld:
        data['_json_ld'] = json_ld
    
    # Title
    title_el = soup.select_one('h1[class*="restaurant-name"], h1')
    if title_el:
        data['title'] = safe_text(title_el)
    
    # Address
    address_el = soup.select_one('div[class*="address"], address')
    if address_el:
        data['address'] = safe_text(address_el)
    
    # Phone
    phone_el = soup.select_one('a[href^="tel:"]')
    if phone_el:
        data['phone'] = safe_attr(phone_el, 'href').replace('tel:', '')
    
    # Rating
    rating_el = soup.select_one('div[class*="rating"]')
    if rating_el:
        rating_text = safe_text(rating_el)
        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
        if rating_match:
            data['rating'] = rating_match.group(1)
    
    # Price Range
    price_el = soup.select_one('span[class*="price"]')
    if price_el:
        price_text = safe_text(price_el)
        price_match = re.search(r'(\${1,4})', price_text)
        if price_match:
            data['price_range'] = price_match.group(1)
    
    # Check for Diners' Choice
    body_text = soup.get_text()
    if "Diners' Choice" in body_text or "Diners Choice" in body_text:
        data['diners_choice'] = 'Yes'
    
    # Extract from JSON-LD
    if json_ld:
        for item in json_ld:
            if isinstance(item, dict):
                if item.get('@type') in ['Restaurant', 'FoodEstablishment']:
                    if 'name' in item and 'title' not in data:
                        data['title'] = item.get('name', '')
                    if 'address' in item and 'address' not in data:
                        addr = item.get('address', {})
                        if isinstance(addr, dict):
                            data['address'] = ', '.join([
                                addr.get('streetAddress', ''),
                                addr.get('addressLocality', ''),
                                addr.get('addressRegion', ''),
                                addr.get('postalCode', '')
                            ]).strip(', ')
                    if 'telephone' in item and 'phone' not in data:
                        data['phone'] = item.get('telephone', '')
                    if 'url' in item and 'website' not in data:
                        data['website'] = item.get('url', '')
                    if 'aggregateRating' in item and 'rating' not in data:
                        rating = item.get('aggregateRating', {})
                        if isinstance(rating, dict):
                            data['rating'] = str(rating.get('ratingValue', ''))
    
    data['source'] = 'OpenTable'
    data['source_url'] = url
    
    return data


def parse_official_website(html: str, url: str) -> Dict[str, Any]:
    """
    Parse official business website
    
    Returns:
        Dictionary with extracted fields
    """
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    # Extract JSON-LD
    json_ld = extract_json_ld(soup)
    if json_ld:
        data['_json_ld'] = json_ld
    
    # Extract microdata
    microdata = extract_microdata(soup)
    if microdata:
        data['_microdata'] = microdata
    
    # Extract OG tags
    og_tags = extract_og_tags(soup)
    if og_tags:
        data['_og_tags'] = og_tags
    
    # Title
    title_el = soup.find('title')
    if title_el:
        data['title'] = safe_text(title_el)
    
    # Try OG title
    if 'title' not in data and 'title' in og_tags:
        data['title'] = og_tags['title']
    
    # Description
    desc_el = soup.select_one('meta[name="description"]')
    if desc_el:
        data['description'] = safe_attr(desc_el, 'content')
    
    # Try OG description
    if 'description' not in data and 'description' in og_tags:
        data['description'] = og_tags['description']
    
    # Featured Image
    if 'image' in og_tags:
        data['featured_image_url'] = og_tags['image']
    else:
        img_el = soup.select_one('meta[property="og:image"]')
        if img_el:
            data['featured_image_url'] = safe_attr(img_el, 'content')
    
    # Extract all text for pattern matching
    body_text = soup.get_text()
    
    # Find email
    email = find_email(body_text)
    if email:
        data['email'] = email
    
    # Find phone
    phone = find_phone(body_text)
    if phone and 'phone' not in data:
        data['phone'] = phone
    
    # Address (look for common patterns)
    address_patterns = [
        r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Circle|Ct)[\s,]+[\w\s,]+(?:[A-Z]{2})?\s+\d{5}',
        r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd)[\s,]+[\w\s,]+'
    ]
    for pattern in address_patterns:
        match = re.search(pattern, body_text, re.IGNORECASE)
        if match:
            data['address'] = match.group(0).strip()
            break
    
    # Executive Chef
    chef_match = re.search(r'Executive Chef[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', body_text, re.IGNORECASE)
    if chef_match:
        data['executive_chef'] = chef_match.group(1)
    
    # Chef Bio (look for paragraphs near chef mention)
    chef_paragraphs = []
    for p in soup.find_all('p'):
        p_text = safe_text(p).lower()
        if 'chef' in p_text and len(p_text) > 50:
            chef_paragraphs.append(safe_text(p))
    if chef_paragraphs:
        data['chef_bio'] = ' '.join(chef_paragraphs[:2])
    
    # Gift Card URL
    gift_card_links = soup.find_all('a', href=True, string=re.compile(r'gift', re.I))
    for link in gift_card_links:
        href = safe_attr(link, 'href')
        if href and 'gift' in href.lower():
            data['gift_card_url'] = href
            break
    
    # Private Dining
    private_dining_text = ''
    for section in soup.find_all(['section', 'div'], class_=re.compile(r'private|dining', re.I)):
        private_dining_text += safe_text(section) + ' '
    
    if private_dining_text:
        pd_email = find_email(private_dining_text)
        if pd_email:
            data['private_dining_email'] = pd_email
        
        pd_phone = find_phone(private_dining_text)
        if pd_phone:
            data['private_dining_phone'] = pd_phone
    
    # Video URL
    video_els = soup.find_all(['iframe', 'video', 'a'], src=re.compile(r'youtube|vimeo|video', re.I))
    for el in video_els:
        video_url = safe_attr(el, 'src') or safe_attr(el, 'href')
        if video_url:
            data['video_url'] = video_url
            break
    
    # Parking
    if re.search(r'valet', body_text, re.I):
        data['parking'] = 'Valet'
    elif re.search(r'street parking', body_text, re.I):
        data['parking'] = 'Street'
    elif re.search(r'parking', body_text, re.I):
        data['parking'] = 'Yes'
    
    # Payment Method
    if re.search(r'credit card|visa|mastercard|amex', body_text, re.I):
        data['payment_method'] = 'Credit Cards'
    elif re.search(r'cash only', body_text, re.I):
        data['payment_method'] = 'Cash Only'
    
    # Extract from JSON-LD
    if json_ld:
        for item in json_ld:
            if isinstance(item, dict):
                if item.get('@type') in ['LocalBusiness', 'Restaurant', 'FoodEstablishment', 'Organization']:
                    if 'name' in item and 'title' not in data:
                        data['title'] = item.get('name', '')
                    if 'address' in item and 'address' not in data:
                        addr = item.get('address', {})
                        if isinstance(addr, dict):
                            data['address'] = ', '.join([
                                addr.get('streetAddress', ''),
                                addr.get('addressLocality', ''),
                                addr.get('addressRegion', ''),
                                addr.get('postalCode', '')
                            ]).strip(', ')
                    if 'telephone' in item and 'phone' not in data:
                        data['phone'] = item.get('telephone', '')
                    if 'url' in item and 'website' not in data:
                        data['website'] = item.get('url', '')
                    if 'email' in item and 'email' not in data:
                        data['email'] = item.get('email', '')
                    if 'aggregateRating' in item and 'rating' not in data:
                        rating = item.get('aggregateRating', {})
                        if isinstance(rating, dict):
                            data['rating'] = str(rating.get('ratingValue', ''))
                    if 'priceRange' in item and 'price_range' not in data:
                        data['price_range'] = item.get('priceRange', '')
                    if 'geo' in item:
                        geo = item.get('geo', {})
                        if isinstance(geo, dict):
                            if 'latitude' in geo and 'latitude' not in data:
                                data['latitude'] = str(geo.get('latitude', ''))
                            if 'longitude' in geo and 'longitude' not in data:
                                data['longitude'] = str(geo.get('longitude', ''))
    
    data['source'] = 'Official Website'
    data['source_url'] = url
    
    return data

