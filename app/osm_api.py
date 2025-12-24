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
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re

logger = logging.getLogger(__name__)

OVERPASS_API_BASE = "https://overpass-api.de/api/interpreter"
# Alternative endpoints if main one is down:
# "https://overpass.kumi.systems/api/interpreter"
# "https://overpass.openstreetmap.ru/api/interpreter"

# Rate limiting: 1 request per second for Overpass API
_last_request_time = None
_request_lock = asyncio.Lock()

# Rate limiting for Nominatim geocoding: 1 request per second
_last_nominatim_request_time = None
_nominatim_request_lock = asyncio.Lock()


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
        
        # Check bounding box size and reduce if too large
        bbox_size = self._calculate_bbox_size(bbox)
        logger.info(f"Bounding box size: {bbox_size:.4f} square degrees")
        
        # If bbox is very large (>0.5 square degrees), reduce it
        # This helps prevent timeouts for large cities
        original_bbox = bbox
        if bbox_size > 0.5:
            logger.warning(f"Large bounding box detected ({bbox_size:.4f}), reducing size to prevent timeout")
            bbox = self._reduce_bbox(bbox, factor=0.6)
            logger.info(f"Reduced bounding box size: {self._calculate_bbox_size(bbox):.4f} square degrees")
        
        # Try query with automatic retry on timeout
        max_retries = 3
        include_relations = False  # Start without relations (faster)
        
        for attempt in range(max_retries):
            try:
                # Build query (skip relations for large areas or first attempts)
                query = self._build_steakhouse_query(bbox, include_relations=include_relations)
                result = await self._request(query)
                
                # Parse and format results
                steakhouses = []
                elements = result.get("elements", [])
                
                for element in elements[:limit]:
                    formatted = self._format_steakhouse(element)
                    if formatted:
                        steakhouses.append(formatted)
                
                # If we got results, return them
                if steakhouses or attempt == max_retries - 1:
                    logger.info(f"Found {len(steakhouses)} steakhouses in {location}")
                    # Enhance data if requested
                    if enhance and steakhouses:
                        steakhouses = await self._enhance_steakhouses(steakhouses)
                    return steakhouses
                
                # If no results and we haven't tried relations yet, try with relations
                if not include_relations and attempt < max_retries - 1:
                    logger.debug("No results found, retrying with relations included")
                    include_relations = True
                    continue
                
                # If still no results, return empty list
                return []
                
            except ValueError as e:
                error_msg = str(e)
                # Check if it's a timeout error
                if "timeout" in error_msg.lower() or "504" in error_msg:
                    if attempt < max_retries - 1:
                        # Reduce bounding box and retry
                        reduction_factor = 0.6 - (attempt * 0.1)  # 0.6, 0.5, 0.4
                        bbox = self._reduce_bbox(original_bbox, factor=reduction_factor)
                        logger.warning(
                            f"Overpass timeout on attempt {attempt + 1}/{max_retries}, "
                            f"reducing bounding box to {self._calculate_bbox_size(bbox):.4f} square degrees"
                        )
                        await asyncio.sleep(2)  # Wait before retry
                        continue
                    else:
                        # Last attempt failed
                        raise ValueError(
                            f"Overpass API timeout after {max_retries} attempts with reduced bounding boxes. "
                            f"Try a smaller area or use coordinates for a specific neighborhood."
                        )
                else:
                    # Not a timeout error, re-raise immediately
                    raise
        
        # Should not reach here, but return empty list if we do
        return []
    
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
    
    def _calculate_bbox_size(self, bbox: Tuple[float, float, float, float]) -> float:
        """
        Calculate the approximate size of a bounding box in square degrees.
        
        Args:
            bbox: Bounding box (south, west, north, east)
        
        Returns:
            Approximate area in square degrees
        """
        south, west, north, east = bbox
        lat_span = north - south
        lon_span = east - west
        return lat_span * lon_span
    
    def _reduce_bbox(self, bbox: Tuple[float, float, float, float], factor: float = 0.7) -> Tuple[float, float, float, float]:
        """
        Reduce bounding box size by centering it and reducing dimensions.
        
        Args:
            bbox: Original bounding box (south, west, north, east)
            factor: Reduction factor (0.7 = 70% of original size)
        
        Returns:
            Reduced bounding box (south, west, north, east)
        """
        south, west, north, east = bbox
        
        # Calculate center
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2
        
        # Calculate spans
        lat_span = (north - south) * factor
        lon_span = (east - west) * factor
        
        # Create new bbox centered on original
        new_south = center_lat - lat_span / 2
        new_north = center_lat + lat_span / 2
        new_west = center_lon - lon_span / 2
        new_east = center_lon + lon_span / 2
        
        return (new_south, new_west, new_north, new_east)
    
    def _build_steakhouse_query(self, bbox: Tuple[float, float, float, float], include_relations: bool = False) -> str:
        """
        Build Overpass QL query for steakhouses in bounding box.
        
        Args:
            bbox: Bounding box (south, west, north, east)
            include_relations: Whether to include relations (slower, skip for large areas)
        
        Returns:
            Overpass QL query string
        """
        south, west, north, east = bbox
        
        # Optimized query - start with nodes and ways only (faster)
        # Relations are slower and often not needed for restaurants
        if include_relations:
            query = f"""[out:json][timeout:30];
(
  node["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
  way["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
  relation["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;"""
        else:
            # Faster query without relations
            query = f"""[out:json][timeout:30];
(
  node["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
  way["amenity"="restaurant"]["cuisine"~"steak|steakhouse|steak_house"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;"""
        
        return query
    
    def _get_hardcoded_coordinates(self, location: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Get hardcoded bounding box for major cities (fallback if geocoding fails).
        
        Args:
            location: Location string
        
        Returns:
            Bounding box tuple (south, west, north, east) or None
        """
        # Hardcoded bounding boxes for major US cities
        # Format: (south, west, north, east)
        hardcoded_bboxes = {
            # New York City - optimized smaller bounding box (Manhattan + Brooklyn + Queens core)
            "new york": (40.5774, -74.0591, 40.8176, -73.8004),
            "new york, ny": (40.5774, -74.0591, 40.8176, -73.8004),
            "nyc": (40.5774, -74.0591, 40.8176, -73.8004),
            "los angeles": (33.7037, -118.6682, 34.3373, -118.1553),
            "los angeles, ca": (33.7037, -118.6682, 34.3373, -118.1553),
            "la": (33.7037, -118.6682, 34.3373, -118.1553),
            "chicago": (41.6445, -87.9401, 42.0231, -87.5237),
            "chicago, il": (41.6445, -87.9401, 42.0231, -87.5237),
            "houston": (29.5236, -95.8097, 30.1104, -95.0080),
            "houston, tx": (29.5236, -95.8097, 30.1104, -95.0080),
            "phoenix": (33.1980, -112.2070, 33.6750, -111.6170),
            "phoenix, az": (33.1980, -112.2070, 33.6750, -111.6170),
            "philadelphia": (39.8670, -75.2803, 40.1378, -74.9558),
            "philadelphia, pa": (39.8670, -75.2803, 40.1378, -74.9558),
            "san antonio": (29.2241, -98.6677, 29.6387, -98.3047),
            "san antonio, tx": (29.2241, -98.6677, 29.6387, -98.3047),
            "san diego": (32.5343, -117.3051, 33.1142, -116.9080),
            "san diego, ca": (32.5343, -117.3051, 33.1142, -116.9080),
            "dallas": (32.6170, -97.0690, 33.0238, -96.4637),
            "dallas, tx": (32.6170, -97.0690, 33.0238, -96.4637),
            "austin": (30.0987, -98.0130, 30.5169, -97.5614),
            "austin, tx": (30.0987, -98.0130, 30.5169, -97.5614),
            "miami": (25.7091, -80.3197, 25.8556, -80.1289),
            "miami, fl": (25.7091, -80.3197, 25.8556, -80.1289),
            "atlanta": (33.6478, -84.5514, 33.8869, -84.2898),
            "atlanta, ga": (33.6478, -84.5514, 33.8869, -84.2898),
            "boston": (42.2279, -71.1912, 42.3967, -70.8022),
            "boston, ma": (42.2279, -71.1912, 42.3967, -70.8022),
            "seattle": (47.4955, -122.4597, 47.7341, -122.2244),
            "seattle, wa": (47.4955, -122.4597, 47.7341, -122.2244),
            "denver": (39.6143, -105.1099, 39.9142, -104.6003),
            "denver, co": (39.6143, -105.1099, 39.9142, -104.6003),
            "washington": (38.7916, -77.1198, 38.9959, -76.9094),
            "washington, dc": (38.7916, -77.1198, 38.9959, -76.9094),
            "dc": (38.7916, -77.1198, 38.9959, -76.9094),
        }
        
        location_lower = location.lower().strip()
        return hardcoded_bboxes.get(location_lower)
    
    def _normalize_location(self, location: str) -> List[str]:
        """
        Normalize location string and generate variations to try.
        
        Args:
            location: Raw location string
        
        Returns:
            List of location strings to try (in order of preference)
        """
        # Strip whitespace
        location = location.strip()
        
        # Common location name corrections
        corrections = {
            "newyork": "New York, NY",
            "newyorkcity": "New York, NY",
            "nyc": "New York, NY",
            "losangeles": "Los Angeles, CA",
            "la": "Los Angeles, CA",
            "sanfrancisco": "San Francisco, CA",
            "sf": "San Francisco, CA",
            "chicago": "Chicago, IL",
            "houston": "Houston, TX",
            "phoenix": "Phoenix, AZ",
            "philadelphia": "Philadelphia, PA",
            "sanantonio": "San Antonio, TX",
            "sandiego": "San Diego, CA",
            "dallas": "Dallas, TX",
            "austin": "Austin, TX",
            "miami": "Miami, FL",
            "atlanta": "Atlanta, GA",
            "boston": "Boston, MA",
            "seattle": "Seattle, WA",
            "denver": "Denver, CO",
            "washington": "Washington, DC",
            "dc": "Washington, DC",
        }
        
        # Try exact match first (case-insensitive)
        location_lower = location.lower().replace(" ", "").replace(",", "")
        if location_lower in corrections:
            return [corrections[location_lower], location]
        
        # Try partial matches
        for key, value in corrections.items():
            if key in location_lower or location_lower in key:
                return [value, location]
        
        # Return original (stripped) if no corrections found
        return [location]
    
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
        
        Raises:
            ValueError: If location cannot be resolved
        """
        # Strip whitespace first
        location = location.strip()
        
        if not location:
            raise ValueError("Location cannot be empty")
        
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
        
        # First, try hardcoded coordinates (fastest, no API call)
        hardcoded_bbox = self._get_hardcoded_coordinates(location)
        if hardcoded_bbox:
            logger.info(f"Using hardcoded bounding box for '{location}'")
            return hardcoded_bbox
        
        # Get location variations to try
        location_variations = self._normalize_location(location)
        
        # Try hardcoded coordinates for normalized variations too
        for loc_variant in location_variations:
            hardcoded_bbox = self._get_hardcoded_coordinates(loc_variant)
            if hardcoded_bbox:
                logger.info(f"Using hardcoded bounding box for '{loc_variant}' (normalized from '{location}')")
                return hardcoded_bbox
        
        # Try geocoding each variation until one works
        last_error = None
        for loc_variant in location_variations:
            try:
                return await self._geocode_location(loc_variant)
            except ValueError as e:
                last_error = e
                logger.debug(f"Geocoding failed for '{loc_variant}': {e}")
                continue
        
        # If all variations failed, raise with helpful error message
        if len(location_variations) > 1:
            raise ValueError(
                f"Could not resolve location '{location}': neither name or coordinates are working. "
                f"Tried: {', '.join(location_variations)}. "
                f"Please try: '{location_variations[0]}' or provide coordinates (lat,lon) or bounding box."
            )
        else:
            raise ValueError(
                f"Could not resolve location '{location}': {str(last_error)}. "
                f"Please check the spelling or provide coordinates (lat,lon) or bounding box."
            )
    
    async def _geocode_location(self, location: str) -> Tuple[float, float, float, float]:
        """
        Geocode location name to bounding box using Nominatim API.
        
        Args:
            location: Location name (e.g., "Houston, TX")
        
        Returns:
            Bounding box tuple (south, west, north, east)
        
        Raises:
            ValueError: If geocoding fails
        """
        # Rate limiting: Nominatim requires max 1 request per second
        global _last_nominatim_request_time, _nominatim_request_lock
        
        async with _nominatim_request_lock:
            if _last_nominatim_request_time is not None:
                elapsed = time.time() - _last_nominatim_request_time
                if elapsed < 1.0:
                    wait_time = 1.0 - elapsed
                    logger.debug(f"Rate limiting Nominatim request: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
            _last_nominatim_request_time = time.time()
        
        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    # Use Nominatim to geocode
                    response = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": location,
                            "format": "json",
                            "limit": 1,
                            "addressdetails": 1,
                            "extratags": 1
                        },
                        headers={
                            "User-Agent": "SteakhouseScraper/1.0 (Contact: support@example.com)"  # Required by Nominatim
                        },
                        follow_redirects=True
                    )
                    
                    # Log response for debugging
                    logger.debug(f"Nominatim response for '{location}': HTTP {response.status_code}")
                    
                    if response.status_code == 429:
                        # Rate limited - wait longer before retry
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        logger.warning(f"Nominatim rate limited for '{location}', waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise ValueError(f"Geocoding rate limited: Too many requests to Nominatim. Please wait a moment and try again, or use coordinates (lat,lon).")
                    
                    if response.status_code != 200:
                        error_text = response.text[:200] if hasattr(response, 'text') else "Unknown error"
                        logger.error(f"Geocoding failed for '{location}': HTTP {response.status_code} - {error_text}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        raise ValueError(f"Geocoding failed: HTTP {response.status_code}. Please try again or use coordinates (lat,lon).")
                    
                    results = response.json()
                    if not results or len(results) == 0:
                        raise ValueError(f"Location not found: '{location}'. Please check spelling or use coordinates (lat,lon).")
                    
                    # Get bounding box from result
                    bbox_str = results[0].get("boundingbox", [])
                    if bbox_str and len(bbox_str) == 4:
                        # Nominatim returns [south, north, west, east]
                        south, north, west, east = map(float, bbox_str)
                        logger.info(f"Successfully geocoded '{location}' to bbox: ({south}, {west}, {north}, {east})")
                        return (south, west, north, east)
                    
                    # Fallback: use lat/lon with default radius
                    if "lat" in results[0] and "lon" in results[0]:
                        lat = float(results[0]["lat"])
                        lon = float(results[0]["lon"])
                        radius = 0.45  # ~50km
                        logger.info(f"Geocoded '{location}' to point ({lat}, {lon}), using {radius}° radius")
                        return (lat - radius, lon - radius, lat + radius, lon + radius)
                    
                    raise ValueError(f"Invalid geocoding response for '{location}': missing bounding box or coordinates")
            
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Geocoding timeout for '{location}', retrying in {wait_time}s ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Geocoding timeout for '{location}' after {max_retries} attempts")
                raise ValueError(f"Geocoding timeout for '{location}'. Please try again or use coordinates (lat,lon).")
            
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Geocoding request error for '{location}': {e}, retrying in {wait_time}s ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Geocoding request error for '{location}': {e}")
                raise ValueError(f"Geocoding request failed for '{location}': {str(e)}. Please check your internet connection or use coordinates (lat,lon).")
            
            except ValueError:
                # Re-raise ValueError immediately (no retry for validation errors)
                raise
            
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Geocoding error for '{location}': {e}, retrying in {wait_time}s ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Geocoding failed for '{location}': {e}", exc_info=True)
                raise ValueError(f"Location not found: '{location}'. Please check spelling or use coordinates (lat,lon).")
        
        # Should not reach here, but just in case
        raise ValueError(f"Geocoding failed for '{location}' after {max_retries} attempts. Please use coordinates (lat,lon) or bounding box.")
    
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
        
        # Increase timeout for large queries
        async with httpx.AsyncClient(timeout=60.0) as client:
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

