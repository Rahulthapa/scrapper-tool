from typing import Dict, Any, List
import os
import json
import logging
import re

logger = logging.getLogger(__name__)

# Comprehensive restaurant extraction prompt
COMPREHENSIVE_RESTAURANT_PROMPT = """Extract ALL restaurant data with complete internal information including:

BASIC INFORMATION:
- Restaurant name, description, tagline, slogan
- Website URL, social media links (Facebook, Instagram, Twitter)
- Business type, establishment type

CONTACT DETAILS:
- Phone number (all formats), email address, contact form URL

LOCATION DATA:
- Full formatted address, address parts (street, city, state, zip, country)
- GPS coordinates (latitude, longitude)
- Neighborhood, area, parking information, public transit access

RATINGS & REVIEWS:
- Overall rating, review count, rating breakdown by category
- Review sources (Yelp, Google, TripAdvisor)

PRICING & COST:
- Price range, average cost, menu price ranges
- Happy hour information, special offers, deals, discounts

CUISINE & MENU:
- Cuisine types (all categories), dietary options (vegetarian, vegan, gluten-free, halal, kosher)
- ALL menu URLs: main menu, lunch menu, dinner menu, brunch menu, drinks menu, dessert menu, online ordering URL, delivery menu URL, takeout menu URL
- Menu items (if available), signature dishes, specialties, chef name

HOURS & AVAILABILITY:
- Opening hours (all days with times), special hours, happy hour times, brunch hours, closed days

AMENITIES & FEATURES:
- Wi-Fi availability, parking (valet, street, lot, garage), outdoor seating, patio, terrace
- Indoor seating capacity, private dining rooms, event space, bar area, lounge
- Live music, TV screens, wheelchair accessible, high chairs, kid-friendly
- Pet-friendly, dress code, noise level, ambiance (casual, formal, romantic, family-friendly)
- Good for groups, good for kids, romantic setting, business meetings, solo dining, date night

SERVICES & OPTIONS:
- Reservations (accepted, required, online booking), walk-ins, takeout, delivery (all services: DoorDash, Uber Eats, Grubhub)
- Curbside pickup, drive-through, catering services, private events, group dining, gift cards

PAYMENT & TRANSACTIONS:
- Payment methods (cash, credit cards, mobile payments), currencies accepted, tips accepted

PHOTOS & MEDIA:
- Main image URL, photo gallery URLs, logo URL, menu images, interior/exterior photos, food photos, all image URLs

ADDITIONAL METADATA:
- Yelp ID, Google Place ID, TripAdvisor ID, OpenTable ID, business owner, awards, certifications

INTERNAL DATA:
- Any API data, JavaScript variables, internal IDs, analytics data, any other restaurant-related fields

Return as a JSON array where each restaurant is a complete object with ALL available fields. Include every piece of information, no matter how small. Omit fields that are not available."""


class AIFilter:
    """
    AI-powered data filter and extractor.
    Supports multiple AI providers:
    - Google Gemini (FREE tier available)
    - OpenAI GPT (paid)
    - Fallback to smart extraction (no API needed)
    """
    
    def __init__(self, api_key: str = None):
        self.gemini_api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.model = None
        self._init_ai_provider()
    
    def _init_ai_provider(self):
        """Initialize the best available AI provider"""
        # Try Google Gemini first (FREE tier)
        if self.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_api_key)
                
                # Try multiple model names in order of preference
                # gemini-2.5-flash-lite is the latest fast model
                model_names = [
                    'gemini-2.5-flash-lite',  # Latest fast model (user preference)
                    'gemini-2.5-flash',       # Alternative flash version
                    'gemini-pro',             # Fallback: most stable, widely available
                    'gemini-1.5-pro',         # Fallback: newer version
                    'models/gemini-2.5-flash-lite',  # With models/ prefix
                ]
                
                for model_name in model_names:
                    try:
                        self.model = genai.GenerativeModel(model_name)
                        # Test if model works by checking if it's accessible
                        self.provider = "gemini"
                        logger.info(f"AI Filter initialized with Google Gemini ({model_name})")
                        return
                    except Exception as model_error:
                        logger.debug(f"Failed to initialize model {model_name}: {model_error}")
                        continue
                
                # If all models failed, raise the last error
                raise Exception(f"None of the Gemini models worked. Tried: {', '.join(model_names)}")
                
            except ImportError:
                logger.warning("google-generativeai not installed, trying OpenAI")
            except Exception as e:
                logger.warning(f"Failed to init Gemini: {e}")
        
        # Try OpenAI as fallback
        if self.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_api_key)
                self.provider = "openai"
                logger.info("AI Filter initialized with OpenAI")
                return
            except ImportError:
                logger.warning("openai not installed")
            except Exception as e:
                logger.warning(f"Failed to init OpenAI: {e}")
        
        # Fallback to smart extraction (no API needed)
        self.provider = "smart_extraction"
        logger.info("AI Filter using smart extraction (no API)")

    async def filter_and_structure(
        self,
        data: Dict[str, Any],
        prompt: str = None
    ) -> List[Dict[str, Any]]:
        """
        Use AI to filter and structure scraped data based on user prompt.
        
        Args:
            data: Raw scraped data from the web page
            prompt: User's instruction for what to extract (e.g., "Extract all product names and prices")
        
        Returns:
            List of structured data items matching the prompt
        """
        if not prompt:
            return [data]
        
        try:
            if self.provider == "gemini":
                return await self._filter_with_gemini(data, prompt)
            elif self.provider == "openai":
                return await self._filter_with_openai(data, prompt)
            else:
                return await self._smart_extraction(data, prompt)
        except Exception as e:
            logger.error(f"AI filtering failed: {e}")
            # Return original data on failure
            return [data]

    async def _filter_with_gemini(self, data: Dict[str, Any], prompt: str) -> List[Dict[str, Any]]:
        """Use Google Gemini to extract data"""
        try:
            # Prepare the content for AI
            content_text = self._prepare_content(data)
            
            # Enhanced prompt for comprehensive restaurant data extraction
            is_comprehensive_restaurant = any(keyword in prompt.lower() for keyword in [
                'all', 'everything', 'complete', 'comprehensive', 'amenities', 
                'menu url', 'internal data', 'all data'
            ])
            
            if is_comprehensive_restaurant:
                system_instruction = """You are an expert restaurant data extraction assistant. Extract EVERY piece of restaurant-related information available, including:
- Basic info (name, description, website, social media)
- Contact (phone, email, all formats)
- Location (full address, GPS, parking, transit)
- Ratings (all sources, breakdowns, review counts)
- Pricing (range, deals, offers, group pricing)
- Cuisine (all types, dietary options)
- Menu URLs (ALL types: main, lunch, dinner, brunch, drinks, online ordering, delivery, takeout)
- Hours (all days, special hours, happy hour)
- Amenities (Wi-Fi, parking, seating, accessibility, pet-friendly, etc.)
- Services (reservations, takeout, delivery, catering, events)
- Payment (all methods, mobile payments)
- Photos (all image URLs)
- Internal data (API responses, JavaScript variables, any restaurant-related fields)
- Any other restaurant-related information

Be extremely thorough - extract every available detail, no matter how small."""
            else:
                system_instruction = "You are a data extraction assistant. Extract information based on the user's request."
            
            ai_prompt = f"""{system_instruction}

USER REQUEST: {prompt}

WEB PAGE CONTENT:
{content_text}

INSTRUCTIONS:
1. Extract ALL information that matches the user's request
2. For restaurant data, include EVERY available field (amenities, menu URLs, services, etc.)
3. Return the data as a JSON array of objects
4. Each object should have ALL relevant key-value pairs
5. If no matching data is found, return an empty array []
6. Be comprehensive and include all matching items and details
7. For menu URLs, extract ALL types: main menu, lunch, dinner, brunch, drinks, online ordering, delivery, takeout
8. For amenities, extract everything: Wi-Fi, parking, seating, accessibility, pet-friendly, etc.
9. Include internal data, API responses, and JavaScript variables if they contain restaurant information

Return ONLY valid JSON, no explanations or markdown. Example format:
[{{"name": "Restaurant", "menu_urls": {{"main": "url1", "lunch": "url2"}}, "amenities": ["Wi-Fi", "Parking"]}}]

JSON OUTPUT:"""

            # Try to generate content, with fallback model retry
            try:
                response = self.model.generate_content(ai_prompt)
                result_text = response.text.strip()
            except Exception as model_error:
                # If model error, try to reinitialize with a different model
                if "404" in str(model_error) or "not found" in str(model_error).lower():
                    logger.warning(f"Model not found, trying to reinitialize with fallback models: {model_error}")
                    import google.generativeai as genai
                    
                    # Try fallback models in order
                    fallback_models = ['gemini-2.5-flash-lite', 'gemini-pro', 'gemini-1.5-pro']
                    last_error = None
                    for fallback_model in fallback_models:
                        try:
                            self.model = genai.GenerativeModel(fallback_model)
                            response = self.model.generate_content(ai_prompt)
                            result_text = response.text.strip()
                            logger.info(f"Successfully used fallback model {fallback_model}")
                            break
                        except Exception as fallback_error:
                            last_error = fallback_error
                            logger.debug(f"Fallback model {fallback_model} failed: {fallback_error}")
                            continue
                    else:
                        # All fallbacks failed
                        logger.error(f"All fallback models failed. Last error: {last_error}")
                        raise model_error  # Raise original error
                else:
                    raise
            
            # Clean up the response (remove markdown code blocks if present)
            result_text = self._clean_json_response(result_text)
            
            # Parse JSON response
            try:
                extracted = json.loads(result_text)
                if isinstance(extracted, list):
                    return extracted if extracted else [data]
                else:
                    return [extracted]
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse Gemini response as JSON: {result_text[:200]}")
                return [{"ai_extracted": result_text, "original_url": data.get("url")}]
                
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            raise

    async def _filter_with_openai(self, data: Dict[str, Any], prompt: str) -> List[Dict[str, Any]]:
        """Use OpenAI GPT to extract data"""
        try:
            content_text = self._prepare_content(data)
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction assistant. Extract information from web content and return it as JSON."
                    },
                    {
                        "role": "user",
                        "content": f"""Extract the following from this web page:

REQUEST: {prompt}

CONTENT:
{content_text}

Return ONLY a JSON array of extracted items. No explanations."""
                    }
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            result_text = response.choices[0].message.content.strip()
            result_text = self._clean_json_response(result_text)
            
            try:
                extracted = json.loads(result_text)
                if isinstance(extracted, list):
                    return extracted if extracted else [data]
                else:
                    return [extracted]
            except json.JSONDecodeError:
                return [{"ai_extracted": result_text, "original_url": data.get("url")}]
                
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            raise

    async def _smart_extraction(self, data: Dict[str, Any], prompt: str) -> List[Dict[str, Any]]:
        """
        Smart extraction without AI API.
        Automatically detects page type and extracts structured data.
        """
        prompt_lower = prompt.lower()
        
        # Detect if this is a restaurant/business listing page
        is_restaurant_search = any(word in prompt_lower for word in [
            "restaurant", "steakhouse", "food", "dining", "cafe", "bar",
            "business", "store", "shop", "hotel", "place"
        ])
        
        # Auto-detect from page title/content
        title = (data.get("title") or "").lower()
        content = (data.get("text_content") or "").lower()
        
        is_yelp = "yelp" in title or "yelp" in content[:500]
        is_google_maps = "google" in title and "map" in title
        is_tripadvisor = "tripadvisor" in title or "tripadvisor" in content[:500]
        is_listing_page = any(x in title for x in ["best", "top", "near", "search"])
        
        # Extract restaurants/businesses from listing pages
        if is_restaurant_search or is_yelp or is_tripadvisor or is_listing_page:
            businesses = self._extract_businesses_from_listing(data)
            if businesses:
                return businesses
        
        # Fallback to pattern-based extraction
        result = {"url": data.get("url"), "title": data.get("title")}
        
        if any(word in prompt_lower for word in ["price", "cost", "dollar", "$"]):
            result["prices"] = self._extract_prices(data)
        
        if any(word in prompt_lower for word in ["email", "contact", "mail"]):
            result["emails"] = self._extract_emails(data)
        
        if any(word in prompt_lower for word in ["phone", "number", "call", "tel"]):
            result["phones"] = self._extract_phones(data)
        
        if any(word in prompt_lower for word in ["link", "url", "href"]):
            result["links"] = data.get("links", [])[:20]
        
        if any(word in prompt_lower for word in ["image", "picture", "photo", "img"]):
            result["images"] = data.get("images", [])[:20]
        
        if any(word in prompt_lower for word in ["heading", "title", "h1", "h2"]):
            result["headings"] = data.get("headings", {})
        
        if any(word in prompt_lower for word in ["table", "data", "list"]):
            result["tables"] = data.get("tables", [])
            result["lists"] = data.get("lists", [])
        
        # If nothing specific matched, return text content
        if len(result) <= 2:
            result["text_content"] = data.get("text_content", "")[:5000]
            result["main_content"] = data.get("main_content", "")
        
        return [result]
    
    def _extract_businesses_from_listing(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract business/restaurant data from listing pages (Yelp, Google, TripAdvisor, etc.)
        Uses multiple extraction methods and merges results.
        """
        businesses = []
        
        # Method 1: Extract from headings (h3 usually contains business names)
        headings = data.get("headings", {})
        h3_headings = headings.get("h3", [])
        
        # Method 2: Parse the main content text
        main_content = data.get("main_content") or data.get("text_content") or ""
        
        # Method 3: Extract from images (alt text often has business names)
        images = data.get("images", [])
        image_map = {}
        for img in images:
            alt = img.get("alt") or img.get("title") or ""
            if alt and len(alt) > 3:
                # Clean up common suffixes
                name = re.sub(r'\s+on Yelp$', '', alt)
                name = re.sub(r'\s+- TripAdvisor$', '', name)
                if name:
                    image_map[name.lower()] = img.get("src", "")
        
        # Method 4: Extract from links
        links = data.get("links", [])
        link_map = {}
        for link in links:
            text = link.get("text", "").strip()
            href = link.get("href", "")
            if text and len(text) > 3 and len(text) < 100:
                link_map[text.lower()] = href
        
        # Parse numbered headings (e.g., "1.Taste of Texas", "2.Steak 48")
        for heading in h3_headings:
            # Remove numbering like "1.", "2.", etc.
            name = re.sub(r'^\d+\.\s*', '', heading).strip()
            if name and len(name) > 2:
                business = {"name": name}
                
                # Find associated image
                name_lower = name.lower()
                for img_name, img_url in image_map.items():
                    if name_lower in img_name or img_name in name_lower:
                        business["image_url"] = img_url
                        break
                
                # Find associated link
                for link_text, link_url in link_map.items():
                    if name_lower in link_text or link_text in name_lower:
                        business["url"] = link_url
                        break
                
                businesses.append(business)
        
        # Now parse the main content to extract ratings, reviews, prices, locations
        # Pattern: "Name Rating (Reviews) Location Price"
        # Example: "Taste of Texas 4.5 (4.9k reviews) Memorial $$$"
        
        # Find rating and review patterns
        rating_pattern = r'(\d+\.?\d*)\s*\((\d+\.?\d*k?)\s*reviews?\)'
        price_pattern = r'(\${1,4})'
        
        # Try to match each business with its details
        for business in businesses:
            name = business.get("name", "")
            if not name:
                continue
            
            # Search for this business's details in the content
            # Create a search pattern that looks for the name followed by rating info
            escaped_name = re.escape(name)
            
            # Look for pattern: Name + rating + reviews + location + price
            detail_pattern = rf'{escaped_name}\s*(\d+\.?\d*)\s*\((\d+\.?\d*k?)\s*reviews?\)\s*([A-Za-z\s/]+)?\s*(\${1,4})?'
            match = re.search(detail_pattern, main_content, re.IGNORECASE)
            
            if match:
                business["rating"] = float(match.group(1)) if match.group(1) else None
                
                # Parse review count (handle "4.9k" format)
                review_str = match.group(2)
                if review_str:
                    if 'k' in review_str.lower():
                        business["review_count"] = int(float(review_str.lower().replace('k', '')) * 1000)
                    else:
                        business["review_count"] = int(float(review_str))
                
                if match.group(3):
                    location = match.group(3).strip()
                    # Clean up location (remove trailing keywords)
                    location = re.sub(r'\s*(Waitlist|Make|Halal|Locally|Fine).*$', '', location, flags=re.IGNORECASE)
                    if location and len(location) > 1:
                        business["neighborhood"] = location.strip()
                
                if match.group(4):
                    business["price_range"] = match.group(4)
            else:
                # Simpler fallback: just look for rating near the name
                simple_pattern = rf'{escaped_name}.*?(\d+\.?\d*)\s*\('
                simple_match = re.search(simple_pattern, main_content, re.IGNORECASE | re.DOTALL)
                if simple_match:
                    try:
                        rating = float(simple_match.group(1))
                        if 1 <= rating <= 5:
                            business["rating"] = rating
                    except:
                        pass
        
        # Also extract any businesses from the lists data
        lists_data = data.get("lists", [])
        for lst in lists_data:
            for item in lst:
                if isinstance(item, str) and len(item) > 10:
                    # Try to parse list items that contain business info
                    # Pattern: "Name Rating (reviews) Location Price Description"
                    list_match = re.search(
                        r'^(\d+\.)?([A-Za-z\s&\'\-]+?)(\d+\.?\d*)\s*\((\d+\.?\d*k?)\s*reviews?\)\s*([A-Za-z\s/]+)?\s*(\${1,4})?',
                        item
                    )
                    if list_match:
                        name = list_match.group(2).strip()
                        # Check if we already have this business
                        existing = next((b for b in businesses if b.get("name", "").lower() == name.lower()), None)
                        if not existing and name:
                            business = {
                                "name": name,
                                "rating": float(list_match.group(3)) if list_match.group(3) else None,
                            }
                            
                            review_str = list_match.group(4)
                            if review_str:
                                if 'k' in review_str.lower():
                                    business["review_count"] = int(float(review_str.lower().replace('k', '')) * 1000)
                                else:
                                    business["review_count"] = int(float(review_str))
                            
                            if list_match.group(5):
                                business["neighborhood"] = list_match.group(5).strip()
                            
                            if list_match.group(6):
                                business["price_range"] = list_match.group(6)
                            
                            businesses.append(business)
        
        # Extract categories from links
        category_keywords = ['steakhouse', 'seafood', 'american', 'italian', 'mexican', 
                          'japanese', 'chinese', 'thai', 'indian', 'french', 'wine bar',
                          'sushi', 'brazilian', 'mediterranean', 'middle eastern', 'korean']
        
        for business in businesses:
            name_lower = business.get("name", "").lower()
            categories = []
            
            # Look for category links associated with this business
            for link in links:
                link_text = link.get("text", "").lower()
                if link_text in category_keywords:
                    # Check if this link is near the business in the content
                    categories.append(link_text.title())
            
            if categories:
                business["categories"] = list(set(categories))[:5]
        
        # Filter out empty or invalid businesses
        valid_businesses = []
        seen_names = set()
        for b in businesses:
            name = b.get("name", "").strip()
            if name and name.lower() not in seen_names and len(name) > 2:
                # Filter out non-business entries
                if not any(skip in name.lower() for skip in ['sponsored', 'result', 'all', 'near me', 'more']):
                    seen_names.add(name.lower())
                    valid_businesses.append(b)
        
        return valid_businesses if valid_businesses else None

    def _prepare_content(self, data: Dict[str, Any]) -> str:
        """
        Prepare content for AI processing.
        Includes section-based data if available for better categorization.
        """
        parts = []
        
        if data.get("title"):
            parts.append(f"TITLE: {data['title']}")
        
        if data.get("meta_tags"):
            desc = data["meta_tags"].get("description", "")
            if desc:
                parts.append(f"DESCRIPTION: {desc}")
        
        # NEW: Include section-based data if available (for categorization)
        if data.get("sections"):
            parts.append("\n=== PAGE SECTIONS (organized by section titles) ===")
            for section_title, section_data in data["sections"].items():
                section_text = f"\nSECTION: {section_title}\n"
                if section_data.get("text"):
                    section_text += f"Text: {section_data['text'][:1000]}\n"
                if section_data.get("lists"):
                    # Prepare JSON outside f-string to avoid backslash issues
                    lists_json = json.dumps(section_data['lists'][:5])
                    section_text += f"Lists: {lists_json}\n"
                if section_data.get("links"):
                    # Prepare JSON outside f-string to avoid backslash issues
                    links_json = json.dumps(section_data['links'][:5])
                    section_text += f"Links: {links_json}\n"
                parts.append(section_text)
            parts.append("=== END SECTIONS ===\n")
        
        if data.get("headings"):
            for level, texts in data["headings"].items():
                for text in texts[:5]:  # Limit headings
                    parts.append(f"{level.upper()}: {text}")
        
        if data.get("main_content"):
            # Limit content size for API
            parts.append(f"CONTENT: {data['main_content'][:8000]}")
        elif data.get("text_content"):
            parts.append(f"CONTENT: {data['text_content'][:8000]}")
        
        if data.get("tables"):
            for i, table in enumerate(data["tables"][:3]):
                # Prepare JSON outside f-string to avoid backslash issues
                table_json = json.dumps(table[:10])
                parts.append(f"TABLE {i+1}: {table_json}")
        
        if data.get("lists"):
            for i, lst in enumerate(data["lists"][:5]):
                # Prepare JSON outside f-string to avoid backslash issues
                list_json = json.dumps(lst[:10])
                parts.append(f"LIST {i+1}: {list_json}")
        
        return "\n\n".join(parts)

    def _clean_json_response(self, text: str) -> str:
        """Clean AI response to extract valid JSON"""
        # Remove markdown code blocks
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()
        return text

    def _extract_prices(self, data: Dict[str, Any]) -> List[str]:
        """Extract price patterns from text"""
        text = data.get("text_content", "") + " " + data.get("main_content", "")
        # Match common price patterns
        patterns = [
            r'\$[\d,]+\.?\d*',  # $10, $10.99, $1,000
            r'[\d,]+\.?\d*\s*(?:USD|dollars?)',  # 10 USD, 10 dollars
            r'(?:Rs\.?|₹)\s*[\d,]+\.?\d*',  # Rs. 100, ₹100
            r'€[\d,]+\.?\d*',  # €10
            r'£[\d,]+\.?\d*',  # £10
        ]
        prices = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            prices.extend(matches)
        return list(set(prices))[:20]

    def _extract_emails(self, data: Dict[str, Any]) -> List[str]:
        """Extract email addresses from text"""
        text = data.get("text_content", "") + " " + str(data.get("links", []))
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)
        return list(set(emails))[:20]

    def _extract_phones(self, data: Dict[str, Any]) -> List[str]:
        """Extract phone numbers from text"""
        text = data.get("text_content", "")
        patterns = [
            r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
            r'\+\d{1,3}[-.\s]?\d{4,14}',  # International
        ]
        phones = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        return list(set(phones))[:20]
