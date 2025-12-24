"""
OpenStreetMap Overpass API Integration
COMPLETELY FREE - No API key required

Overpass API allows querying OpenStreetMap data.
Documentation: https://wiki.openstreetmap.org/wiki/Overpass_API

Rate Limits:
- Recommended: Max 1 request per second
- Timeout: 25 seconds per query
- No daily limits, but be respectful of server resources
"""

import httpx
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re

logger = logging.getLogger(__name__)

OVERPASS_API_BASE = "https://overpass-api.de/api/interpreter"
# Alternative endpoints if main one is down:
# "https://overpass.kumi.systems/api/interpreter"
# "https://overpass.openstreetmap.ru/api/interpreter"

# Rate limiting: 1 request per second
_last_request_time = None
_request_lock = asyncio.Lock()


class OverpassAPI:
    """OpenStreetMap Overpass API client for querying steakhouses"""
    
    def __init__(self, endpoint: str = None):
        """
        Initialize Overpass API client.
        
        Args:
            endpoint: Overpass API endpoint URL (optional, uses default)
        """
        self.endpoint = endpoint or OVERPASS_API_BASE
        logger.info(f"Overpass API initialized (endpoint: {self.endpoint})")
    
    async def search_steakhouses(
        self,
        location: str,
        limit: int = 50,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        enhance: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for steakhouses in a location.
        
        Args:
            location: City name (e.g., "Houston, TX") or coordinates string
            limit: Maximum number of results
            bbox: Optional bounding box (south, west, north, east)
            enhance: Whether to enhance data with web scraping (default: False)
        
        Returns:
            List of steakhouse dictionaries with structured data
        """
        # Resolve location to bounding box if not provided
        if bbox is None:
            bbox = await self._resolve_location(location)
        
        # Build and execute Overpass query
        query = self._build_steakhouse_query(bbox)
        result = await self._request(query)
        
        # Parse and format results
        steakhouses = []
        elements = result.get("elements", [])
        
        for element in elements[:limit]:
            formatted = self._format_steakhouse(element)
            if formatted:
                steakhouses.append(formatted)
        
        # Enhance data if requested
        if enhance and steakhouses:
            steakhouses = await self._enhance_steakhouses(steakhouses)
        
        return steakhouses
    
    async def get_steakhouse_details(
        self,
        osm_id: str,
        enhance: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific steakhouse.
        
        Args:
            osm_id: OSM ID in format "node/123456", "way/789012", or "relation/345678"
            enhance: Whether to enhance data with web scraping
        
        Returns:
            Steakhouse dictionary or None if not found
        """
        # Parse OSM ID
        parts = osm_id.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid OSM ID format: {osm_id}. Expected format: 'node/123456'")
        
        osm_type, osm_id_num = parts[0], parts[1]
        
        # Build query for specific element
        query = f"""[out:json][timeout:25];
({osm_type}({osm_id_num});
);
out body;
>;
out skel qt;"""
        
        result = await self._request(query)
        elements = result.get("elements", [])
        
        if not elements:
            return None
        
        formatted = self._format_steakhouse(elements[0])
        
        # Enhance if requested
        if enhance and formatted:
            enhanced_list = await self._enhance_steakhouses([formatted])
            if enhanced_list:
                return enhanced_list[0]
        
        return formatted
    
    def _build_steakhouse_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """
        Build Overpass QL query for steakhouses in bounding box.
        
        Args:
            bbox: Bounding box (south, west, north, east)
        
        Returns:
            Overpass QL query string
        """
        south, west, north, east = bbox
        
        # Query for restaurants with steakhouse cuisine
        # Matches: cuisine=steak_house, cuisine=steakhouse, cuisine=steak, etc.
        query = f"""[out:json][timeout:25];
(
  node["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
  way["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
  relation["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;"""
        
        return query
    
    async def _resolve_location(self, location: str) -> Tuple[float, float, float, float]:
        """
        Resolve location string to bounding box.
        
        Supports:
        - City names: "Houston, TX" → geocode and create bbox
        - Bounding box string: "29.5,-96.0,30.0,-94.5" → parse directly
        - Coordinates: "29.7604,-95.3698" → create bbox around point
        
        Args:
            location: Location string
        
        Returns:
            Bounding box tuple (south, west, north, east)
        """
        # Check if it's already a bounding box string
        bbox_match = re.match(r'^([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)$', location)
        if bbox_match:
            return tuple(float(x) for x in bbox_match.groups())
        
        # Check if it's coordinates (lat,lon)
        coord_match = re.match(r'^([-\d.]+),([-\d.]+)$', location)
        if coord_match:
            lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
            # Create ~50km radius bounding box
            radius = 0.45  # ~50km in degrees
            return (lat - radius, lon - radius, lat + radius, lon + radius)
        
        # Otherwise, geocode using Nominatim (free OSM geocoding service)
        return await self._geocode_location(location)
    
    async def _geocode_location(self, location: str) -> Tuple[float, float, float, float]:
        """
        Geocode location name to bounding box using Nominatim API.
        
        Args:
            location: Location name (e.g., "Houston, TX")
        
        Returns:
            Bounding box tuple (south, west, north, east)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Use Nominatim to geocode
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": location,
                        "format": "json",
                        "limit": 1,
                        "addressdetails": 1
                    },
                    headers={
                        "User-Agent": "SteakhouseScraper/1.0"  # Required by Nominatim
                    }
                )
                
                if response.status_code != 200:
                    raise ValueError(f"Geocoding failed: HTTP {response.status_code}")
                
                results = response.json()
                if not results:
                    raise ValueError(f"Location not found: {location}")
                
                # Get bounding box from result
                bbox_str = results[0].get("boundingbox", [])
                if bbox_str:
                    # Nominatim returns [south, north, west, east]
                    south, north, west, east = map(float, bbox_str)
                    return (south, west, north, east)
                
                # Fallback: use lat/lon with default radius
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                radius = 0.45  # ~50km
                return (lat - radius, lon - radius, lat + radius, lon + radius)
        
        except Exception as e:
            logger.error(f"Geocoding failed for '{location}': {e}")
            raise ValueError(f"Could not resolve location '{location}': {str(e)}")
    
    def _format_steakhouse(self, element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Format OSM element into structured steakhouse data.
        
        Args:
            element: OSM element from Overpass API response
        
        Returns:
            Formatted steakhouse dictionary or None if invalid
        """
        tags = element.get("tags", {})
        
        # Skip if no name
        if not tags.get("name"):
            return None
        
        # Extract basic info
        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        
        # Extract coordinates
        lat = element.get("lat")
        lon = element.get("lon")
        if not lat and element.get("center"):
            lat = element["center"].get("lat")
            lon = element["center"].get("lon")
        
        # Build address
        address_parts = {}
        address_components = []
        
        if tags.get("addr:housenumber"):
            address_components.append(tags["addr:housenumber"])
        if tags.get("addr:street"):
            address_components.append(tags["addr:street"])
            address_parts["street"] = tags["addr:street"]
        if tags.get("addr:city"):
            address_components.append(tags["addr:city"])
            address_parts["city"] = tags["addr:city"]
        if tags.get("addr:state"):
            address_components.append(tags["addr:state"])
            address_parts["state"] = tags["addr:state"]
        if tags.get("addr:postcode"):
            address_components.append(tags["addr:postcode"])
            address_parts["postal_code"] = tags["addr:postcode"]
        if tags.get("addr:country"):
            address_parts["country"] = tags["addr:country"]
        
        address = ", ".join(address_components) if address_components else None
        
        # Extract cuisine
        cuisine_str = tags.get("cuisine", "")
        if isinstance(cuisine_str, str):
            cuisine = [c.strip() for c in cuisine_str.split(";") if c.strip()]
        else:
            cuisine = [cuisine_str] if cuisine_str else []
        
        # Extract amenities
        amenities = []
        if tags.get("parking"):
            amenities.append("parking")
        if tags.get("wifi"):
            amenities.append("wifi")
        if tags.get("outdoor_seating") or tags.get("outdoor_seating") == "yes":
            amenities.append("outdoor_seating")
        if tags.get("wheelchair"):
            amenities.append("wheelchair_accessible")
        if tags.get("smoking"):
            amenities.append("smoking_area")
        
        # Extract seating information
        seating = {}
        if tags.get("capacity"):
            try:
                seating["indoor"] = int(tags["capacity"])
            except:
                pass
        if tags.get("outdoor_seating") == "yes":
            seating["outdoor"] = True
        if tags.get("private_room") == "yes":
            seating["private_rooms"] = True
        
        # Extract payment methods
        payment_methods = []
        if tags.get("payment:credit_cards") == "yes":
            payment_methods.append("credit_card")
        if tags.get("payment:cash") == "yes":
            payment_methods.append("cash")
        if tags.get("payment:debit_cards") == "yes":
            payment_methods.append("debit_card")
        
        # Extract dietary options
        dietary_options = []
        if tags.get("diet:vegetarian") == "yes":
            dietary_options.append("vegetarian")
        if tags.get("diet:vegan") == "yes":
            dietary_options.append("vegan")
        if tags.get("diet:gluten_free") == "yes":
            dietary_options.append("gluten_free")
        
        # Build formatted result
        formatted = {
            "osm_id": f"{osm_type}/{osm_id}",
            "osm_type": osm_type,
            "name": tags.get("name"),
            "description": tags.get("description") or tags.get("note"),
            "cuisine": cuisine,
            "address": address,
            "address_parts": address_parts if address_parts else None,
            "coordinates": {
                "lat": lat,
                "lon": lon
            } if lat and lon else None,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "image": tags.get("image"),
            "menu_url": tags.get("menu") or tags.get("contact:menu"),
            "opening_hours": tags.get("opening_hours"),
            "amenities": amenities if amenities else None,
            "seating": seating if seating else None,
            "payment_methods": payment_methods if payment_methods else None,
            "dietary_options": dietary_options if dietary_options else None,
            "email": tags.get("email") or tags.get("contact:email"),
            "facebook": tags.get("contact:facebook"),
            "instagram": tags.get("contact:instagram"),
            "twitter": tags.get("contact:twitter"),
            "all_tags": tags  # Include all tags for reference
        }
        
        # Remove None values for cleaner output
        formatted = {k: v for k, v in formatted.items() if v is not None}
        
        return formatted
    
    async def _enhance_steakhouses(
        self,
        steakhouses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enhance steakhouse data with web scraping and AI extraction.
        
        This method:
        1. Scrapes restaurant websites for menus, images, detailed amenities
        2. Uses AI to extract steak cut types from descriptions
        
        Args:
            steakhouses: List of steakhouse dictionaries
        
        Returns:
            Enhanced list of steakhouses
        """
        from .scraper import WebScraper
        from .ai_filter import AIFilter
        
        scraper = WebScraper()
        ai_filter = AIFilter()
        
        enhanced = []
        
        for steakhouse in steakhouses:
            enhanced_steakhouse = steakhouse.copy()
            website = steakhouse.get("website")
            
            # Scrape website if available
            if website:
                try:
                    logger.info(f"Enhancing data for {steakhouse.get('name')} from {website}")
                    page_data = await scraper.scrape(website, use_javascript=False)
                    
                    # Extract images if not in OSM
                    if not enhanced_steakhouse.get("image") and page_data.get("images"):
                        enhanced_steakhouse["image"] = page_data["images"][0].get("src") if page_data["images"] else None
                    
                    # Extract menu URLs if not in OSM
                    if not enhanced_steakhouse.get("menu_url"):
                        # Look for menu links in page data
                        links = page_data.get("links", [])
                        for link in links:
                            href = link.get("href", "").lower()
                            text = link.get("text", "").lower()
                            if "menu" in href or "menu" in text:
                                enhanced_steakhouse["menu_url"] = link.get("href")
                                break
                    
                    # Extract additional amenities from page content
                    content = page_data.get("text_content", "") or page_data.get("main_content", "")
                    if content:
                        content_lower = content.lower()
                        amenities = enhanced_steakhouse.get("amenities", [])
                        
                        if "wifi" in content_lower and "wifi" not in amenities:
                            amenities.append("wifi")
                        if "parking" in content_lower and "parking" not in amenities:
                            amenities.append("parking")
                        if "outdoor" in content_lower and "outdoor_seating" not in amenities:
                            amenities.append("outdoor_seating")
                        
                        enhanced_steakhouse["amenities"] = amenities
                
                except Exception as e:
                    logger.warning(f"Failed to enhance {steakhouse.get('name')}: {e}")
            
            # Use AI to extract steak cut types from description
            description = enhanced_steakhouse.get("description") or ""
            if description:
                try:
                    # Create a prompt for extracting steak cut types
                    prompt = "Extract all steak cut types mentioned (e.g., ribeye, filet mignon, sirloin, T-bone, porterhouse, New York strip). Return as JSON array."
                    ai_data = {"text_content": description}
                    extracted = await ai_filter.filter_and_structure(ai_data, prompt)
                    
                    if extracted and isinstance(extracted, list) and len(extracted) > 0:
                        # Try to extract steak cuts from AI response
                        first_result = extracted[0]
                        if isinstance(first_result, dict):
                            # Look for common fields that might contain steak cuts
                            steak_cuts = []
                            for key in ["steak_cut_types", "steak_cuts", "cuts", "items"]:
                                if key in first_result:
                                    value = first_result[key]
                                    if isinstance(value, list):
                                        steak_cuts.extend(value)
                                    elif isinstance(value, str):
                                        steak_cuts.append(value)
                            
                            # If no structured data, try to parse from text
                            if not steak_cuts:
                                text = str(first_result)
                                # Common steak cut patterns
                                cuts_pattern = r'\b(ribeye|filet|mignon|sirloin|t-bone|porterhouse|new york strip|strip steak|tenderloin|flank|skirt|hanger|flat iron)\b'
                                found_cuts = re.findall(cuts_pattern, text.lower())
                                steak_cuts = list(set(found_cuts))
                            
                            if steak_cuts:
                                enhanced_steakhouse["steak_cut_types"] = steak_cuts
                
                except Exception as e:
                    logger.debug(f"AI extraction failed for {steakhouse.get('name')}: {e}")
            
            enhanced.append(enhanced_steakhouse)
        
        return enhanced
    
    async def _request(self, query: str) -> Dict[str, Any]:
        """
        Make a request to Overpass API with rate limiting.
        
        Args:
            query: Overpass QL query string
        
        Returns:
            JSON response from Overpass API
        """
        global _last_request_time
        
        # Rate limiting: 1 request per second
        async with _request_lock:
            if _last_request_time:
                elapsed = (datetime.now() - _last_request_time).total_seconds()
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
            
            _last_request_time = datetime.now()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.endpoint,
                    data=query,
                    headers={
                        "Content-Type": "text/plain",
                        "User-Agent": "SteakhouseScraper/1.0"
                    }
                )
                
                if response.status_code == 429:
                    raise ValueError("Overpass API rate limit exceeded. Please wait before retrying.")
                elif response.status_code == 504:
                    raise ValueError("Overpass API timeout. Try with a smaller bounding box.")
                elif response.status_code != 200:
                    raise ValueError(f"Overpass API error: HTTP {response.status_code}")
                
                return response.json()
            
            except httpx.TimeoutException:
                raise ValueError("Overpass API request timed out. Try with a smaller bounding box.")
            except httpx.RequestError as e:
                raise ValueError(f"Overpass API request failed: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get API status information."""
        return {
            "configured": True,
            "endpoint": self.endpoint,
            "tier": "FREE",
            "rate_limit": "1 request per second (recommended)",
            "message": "Overpass API is ready (completely free, no API key required)"
        }

