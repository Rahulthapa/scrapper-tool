# OpenStreetMap Overpass API Setup Guide

## Overview

OpenStreetMap (OSM) Overpass API is a **completely FREE** service that allows querying OSM data. No API key is required, making it an ideal addition to your free API stack.

## What is Overpass API?

Overpass API is a read-only API that serves up custom selected parts of the OSM map data. It's perfect for querying specific types of locations (like steakhouses) within geographic areas.

**Key Features:**
- ✅ Completely free - no API key required
- ✅ No daily limits (but be respectful of server resources)
- ✅ Real-time OSM data
- ✅ Powerful query language (Overpass QL)
- ✅ Multiple public endpoints available

## API Endpoints

### 1. Search Steakhouses

**Endpoint:** `GET /api/osm/search`

**Parameters:**
- `location` (required): Location string
  - City name: `"Houston, TX"`
  - Coordinates: `"29.7604,-95.3698"` (creates ~50km radius)
  - Bounding box: `"29.5,-96.0,30.0,-94.5"` (south,west,north,east)
- `limit` (optional): Maximum results (default: 50, max: 200)
- `enhance` (optional): Enhance with web scraping (default: false)

**Example:**
```bash
# Search steakhouses in Houston
curl "http://localhost:8000/api/osm/search?location=Houston,TX&limit=20"

# Search with data enhancement
curl "http://localhost:8000/api/osm/search?location=Houston,TX&limit=20&enhance=true"
```

**Response:**
```json
{
  "success": true,
  "source": "osm_overpass",
  "location": "Houston, TX",
  "total": 15,
  "steakhouses": [
    {
      "osm_id": "node/123456",
      "osm_type": "node",
      "name": "Steakhouse Name",
      "description": "Fine dining steakhouse...",
      "cuisine": ["steakhouse", "american"],
      "address": "123 Main St, Houston, TX 77002",
      "address_parts": {
        "street": "123 Main St",
        "city": "Houston",
        "state": "TX",
        "postal_code": "77002"
      },
      "coordinates": {
        "lat": 29.7604,
        "lon": -95.3698
      },
      "phone": "+1-713-555-1234",
      "website": "https://steakhouse.com",
      "image": "https://...",
      "menu_url": "https://...",
      "opening_hours": "Mo-Su 17:00-22:00",
      "amenities": ["parking", "wifi", "outdoor_seating"],
      "seating": {
        "indoor": 50,
        "outdoor": 20,
        "private_rooms": true
      },
      "steak_cut_types": ["ribeye", "filet", "sirloin"],
      "payment_methods": ["cash", "credit_card"],
      "dietary_options": ["vegetarian", "gluten_free"],
      "all_tags": {...}
    }
  ]
}
```

### 2. Get Specific Steakhouse

**Endpoint:** `GET /api/osm/steakhouse/{osm_id}`

**Parameters:**
- `osm_id` (path): OSM ID in format `node/123456`, `way/789012`, or `relation/345678`
- `enhance` (optional): Enhance with web scraping (default: false)

**Example:**
```bash
curl "http://localhost:8000/api/osm/steakhouse/node/123456?enhance=true"
```

### 3. Check API Status

**Endpoint:** `GET /api/osm/status`

**Example:**
```bash
curl "http://localhost:8000/api/osm/status"
```

**Response:**
```json
{
  "configured": true,
  "endpoint": "https://overpass-api.de/api/interpreter",
  "tier": "FREE",
  "rate_limit": "1 request per second (recommended)",
  "message": "Overpass API is ready (completely free, no API key required)"
}
```

## Data Enhancement

When `enhance=true`, the API will:

1. **Web Scraping:**
   - Scrape restaurant websites for menus and images
   - Extract additional amenities from page content
   - Find menu URLs if not in OSM data

2. **AI Extraction:**
   - Use Google Gemini (free) to extract steak cut types from descriptions
   - Identify specific cuts like ribeye, filet mignon, sirloin, etc.

**Note:** Enhancement requires more time and resources. Use it when you need complete data.

## Location Formats

### City Name
```
location=Houston,TX
```
Automatically geocoded using Nominatim (free OSM geocoding service).

### Coordinates
```
location=29.7604,-95.3698
```
Creates a ~50km radius bounding box around the point.

### Bounding Box
```
location=29.5,-96.0,30.0,-94.5
```
Direct bounding box: `(south, west, north, east)` in decimal degrees.

## Rate Limits & Best Practices

### Rate Limits
- **Recommended:** Max 1 request per second
- **Timeout:** 25 seconds per query
- **No daily limits** (but be respectful!)

### Best Practices

1. **Use Appropriate Bounding Boxes:**
   - Smaller boxes = faster queries
   - Large boxes may timeout
   - Start with city-level searches

2. **Respect Server Resources:**
   - Don't make rapid-fire requests
   - Cache results when possible
   - Use enhancement sparingly (it's slower)

3. **Error Handling:**
   - Handle timeouts gracefully
   - Retry with smaller bounding boxes if needed
   - Check status endpoint before large queries

## OSM Data Structure

### Available Fields

**Basic Information:**
- `name` - Restaurant name
- `description` - Description text
- `cuisine` - Cuisine types (array)

**Location:**
- `address` - Full formatted address
- `address_parts` - Address components (street, city, state, postal_code)
- `coordinates` - GPS coordinates (lat, lon)

**Contact:**
- `phone` - Phone number
- `website` - Official website
- `email` - Email address
- `facebook`, `instagram`, `twitter` - Social media links

**Details:**
- `opening_hours` - Hours of operation (OSM format)
- `menu_url` - Menu URL (if available)
- `image` - Image URL (if available)

**Amenities:**
- `amenities` - Array of amenities (parking, wifi, outdoor_seating, etc.)
- `seating` - Seating information (indoor capacity, outdoor, private rooms)
- `payment_methods` - Accepted payment methods
- `dietary_options` - Dietary options (vegetarian, vegan, gluten_free)

**Enhanced Data (when enhance=true):**
- `steak_cut_types` - Array of steak cuts (ribeye, filet, sirloin, etc.)
- Additional images and menu URLs from website scraping

**Metadata:**
- `osm_id` - OSM identifier (e.g., "node/123456")
- `osm_type` - OSM element type (node, way, relation)
- `all_tags` - All OSM tags for reference

## Troubleshooting

### "Location not found"
- Check spelling of city name
- Try using coordinates instead
- Verify location exists in OSM

### "Overpass API timeout"
- Use a smaller bounding box
- Reduce the limit parameter
- Try a different Overpass endpoint

### "No steakhouses found"
- OSM data may be incomplete in that area
- Try a larger bounding box
- Check if steakhouses are tagged correctly in OSM

### "Rate limit exceeded"
- Wait before retrying
- Reduce request frequency
- The API enforces 1 request per second

## Integration with Other APIs

The OSM Overpass API works great alongside:

- **Yelp API** - Combine OSM location data with Yelp reviews
- **Google Gemini** - Use AI to extract additional details
- **Web Scraping** - Enhance OSM data with website information

## Example Use Cases

### 1. Find All Steakhouses in a City
```python
GET /api/osm/search?location=Houston,TX&limit=50
```

### 2. Get Detailed Info with Enhancement
```python
GET /api/osm/search?location=Houston,TX&enhance=true
```

### 3. Search by Coordinates
```python
GET /api/osm/search?location=29.7604,-95.3698&limit=20
```

### 4. Get Specific Steakhouse
```python
GET /api/osm/steakhouse/node/123456
```

## Cost Summary

| Feature | Cost | API Key Required |
|---------|------|-----------------|
| Overpass API | FREE | ❌ No |
| Nominatim Geocoding | FREE | ❌ No |
| Data Enhancement | FREE | ❌ No (uses existing Gemini API) |
| **Total** | **$0.00** | **❌ No** |

## Additional Resources

- **Overpass API Documentation:** https://wiki.openstreetmap.org/wiki/Overpass_API
- **Overpass QL Guide:** https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
- **Nominatim Geocoding:** https://nominatim.org/
- **OSM Tagging Guide:** https://wiki.openstreetmap.org/wiki/Tags

## Support

For issues:
1. Check the status endpoint: `GET /api/osm/status`
2. Review error messages for specific guidance
3. Try with a smaller bounding box if timeouts occur
4. Verify location format is correct

---

**Enjoy free, unlimited access to OpenStreetMap data!** 🗺️

