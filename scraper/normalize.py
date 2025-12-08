"""
Normalization layer for combining and standardizing data from multiple sources.
Ensures all fields match the CSV column structure exactly.
"""
import re
import hashlib
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse

from .config import ScraperConfig, CSV_COLUMNS

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Replace spaces and special chars with hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    return text


def normalize_phone(phone: str) -> str:
    """Normalize phone number to readable format"""
    if not phone:
        return ""
    
    # Remove all non-digit characters except +
    digits = re.sub(r'[^\d+]', '', phone)
    
    # Format US numbers
    if digits.startswith('+1'):
        digits = digits[2:]
    elif digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]
    
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    
    return phone.strip()


def normalize_price_range(price: str) -> str:
    """Normalize price range to $, $$, $$$, or $$$$"""
    if not price:
        return ""
    
    # Count dollar signs
    dollar_count = price.count('$')
    if dollar_count >= 1 and dollar_count <= 4:
        return '$' * dollar_count
    
    # Try to extract from text
    price_lower = price.lower()
    if 'inexpensive' in price_lower or 'budget' in price_lower:
        return '$'
    elif 'moderate' in price_lower or 'mid-range' in price_lower:
        return '$$'
    elif 'expensive' in price_lower or 'upscale' in price_lower:
        return '$$$'
    elif 'very expensive' in price_lower or 'fine dining' in price_lower:
        return '$$$$'
    
    return price.strip()


def normalize_boolean(value: Any) -> str:
    """Convert boolean-like values to Yes/No"""
    if not value:
        return "No"
    
    if isinstance(value, bool):
        return "Yes" if value else "No"
    
    value_str = str(value).lower().strip()
    if value_str in ['yes', 'true', '1', 'y']:
        return "Yes"
    elif value_str in ['no', 'false', '0', 'n', '']:
        return "No"
    
    return "Yes" if value_str else "No"


def normalize_rating(rating: str) -> str:
    """Normalize rating to float string"""
    if not rating:
        return ""
    
    # Extract number
    match = re.search(r'(\d+\.?\d*)', str(rating))
    if match:
        try:
            rating_float = float(match.group(1))
            if 0 <= rating_float <= 5:
                return str(rating_float)
        except ValueError:
            pass
    
    return str(rating).strip()


def generate_id(title: str, address: str, salt: str = "") -> int:
    """
    Generate stable numeric ID from title and address
    
    Uses SHA256 hash and converts to integer
    """
    if not title and not address:
        return 0
    
    # Create canonical string
    canonical = f"{title.lower().strip()}|{address.lower().strip()}|{salt}"
    
    # Hash
    hash_obj = hashlib.sha256(canonical.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Convert first 8 characters to integer
    try:
        id_int = int(hash_hex[:8], 16)
        return id_int
    except ValueError:
        # Fallback: use hash of full string
        return abs(hash(canonical)) % (10 ** 9)


def extract_neighborhood(address: str) -> str:
    """Extract neighborhood from address"""
    if not address:
        return ""
    
    # Common patterns
    # Address format: "123 Main St, Neighborhood, City, State ZIP"
    parts = [p.strip() for p in address.split(',')]
    if len(parts) >= 2:
        # Second part is often neighborhood
        return parts[-2]
    
    return ""


def extract_cross_street(text: str) -> str:
    """Extract cross street from text"""
    if not text:
        return ""
    
    # Look for "near", "at", "corner of" patterns
    patterns = [
        r'near\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r'at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave)',
        r'corner\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""


def normalize_tags(tags: Any) -> str:
    """Convert tags to comma-separated string"""
    if not tags:
        return ""
    
    if isinstance(tags, list):
        return ', '.join(str(t).strip() for t in tags if t)
    elif isinstance(tags, str):
        # Split by common delimiters
        tags_list = re.split(r'[,;|]', tags)
        return ', '.join(t.strip() for t in tags_list if t.strip())
    
    return str(tags).strip()


def create_content(data: Dict[str, Any]) -> str:
    """Create content field from available data"""
    parts = []
    
    if data.get('description'):
        parts.append(data['description'])
    
    if data.get('executive_chef'):
        parts.append(f"Executive Chef: {data['executive_chef']}")
    
    if data.get('chef_bio'):
        parts.append(f"Chef Bio: {data['chef_bio']}")
    
    if data.get('website'):
        parts.append(f"Website: {data['website']}")
    
    return '\n\n'.join(parts)


def create_excerpt(content: str, max_length: int = 160) -> str:
    """Create excerpt from content (first sentence or truncated)"""
    if not content:
        return ""
    
    # Try to get first sentence
    sentences = re.split(r'[.!?]\s+', content)
    if sentences and len(sentences[0]) <= max_length:
        return sentences[0].strip()
    
    # Truncate
    if len(content) > max_length:
        return content[:max_length].rsplit(' ', 1)[0] + '...'
    
    return content.strip()


class DataNormalizer:
    """Main class for normalizing data from multiple sources"""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.seen_entities: Dict[int, Dict[str, Any]] = {}
        self.id_counter = 1
    
    def normalize(self, raw_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize list of raw data dictionaries into CSV-ready format
        
        Args:
            raw_data_list: List of dictionaries from parsers
        
        Returns:
            List of normalized dictionaries matching CSV columns
        """
        # Group by entity (deduplicate)
        entities: Dict[int, Dict[str, Any]] = {}
        
        for raw_data in raw_data_list:
            # Generate ID
            title = raw_data.get('title', '')
            address = raw_data.get('address', '')
            entity_id = generate_id(title, address, self.config.id_hash_salt)
            
            # Use incremental ID if hash collision or missing data
            if entity_id == 0 or entity_id in entities:
                entity_id = self.id_counter
                self.id_counter += 1
            
            # Merge data from multiple sources
            if entity_id in entities:
                # Merge with existing entity
                entities[entity_id] = self._merge_data(entities[entity_id], raw_data)
            else:
                # New entity
                entities[entity_id] = raw_data.copy()
                entities[entity_id]['_entity_id'] = entity_id
        
        # Normalize each entity
        normalized_list = []
        for entity_id, entity_data in entities.items():
            normalized = self._normalize_entity(entity_data, entity_id)
            normalized_list.append(normalized)
        
        return normalized_list
    
    def _merge_data(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """Merge data from new source into existing entity"""
        merged = existing.copy()
        
        # Prefer non-empty values
        for key, value in new.items():
            if key.startswith('_'):
                continue
            
            if not merged.get(key) and value:
                merged[key] = value
            elif value and isinstance(value, list) and not isinstance(merged.get(key), list):
                merged[key] = value
        
        # Combine sources
        if 'sources' not in merged:
            merged['sources'] = []
        merged['sources'].append(new.get('source', 'Unknown'))
        
        return merged
    
    def _normalize_entity(self, data: Dict[str, Any], entity_id: int) -> Dict[str, Any]:
        """Normalize a single entity to match CSV columns"""
        normalized = {}
        
        # ID
        normalized['ID'] = str(entity_id)
        
        # Title
        normalized['Title'] = data.get('title', '').strip()
        
        # Slug
        normalized['Slug'] = slugify(normalized['Title']) or f"item-{entity_id}"
        
        # Content
        content = create_content(data)
        normalized['Content'] = content
        
        # Excerpt
        normalized['Excerpt'] = create_excerpt(content)
        
        # Post Status
        normalized['Post Status'] = 'publish'
        
        # Post Date
        normalized['Post Date'] = datetime.now().strftime('%Y-%m-%d')
        
        # Featured Image URL
        normalized['Featured Image URL'] = data.get('featured_image_url', '').strip()
        
        # Location
        normalized['Location'] = self.config.default_location
        
        # Address
        normalized['Address'] = data.get('address', '').strip()
        
        # Phone
        phone = data.get('phone', '')
        normalized['Phone'] = normalize_phone(phone)
        normalized['Phone Number (ACF)'] = normalized['Phone']  # Duplicate for ACF field
        
        # Website
        normalized['Website'] = data.get('website', '').strip()
        
        # Email
        normalized['Email'] = data.get('email', '').strip()
        
        # Rating
        normalized['Rating'] = normalize_rating(data.get('rating', ''))
        
        # Price Range
        normalized['Price Range'] = normalize_price_range(data.get('price_range', ''))
        
        # Latitude
        normalized['Latitude'] = data.get('latitude', '').strip()
        
        # Longitude
        normalized['Longitude'] = data.get('longitude', '').strip()
        
        # Diners Choice
        normalized['Diners Choice'] = normalize_boolean(data.get('diners_choice', ''))
        
        # Top Rated
        normalized['Top Rated'] = normalize_boolean(data.get('top_rated', ''))
        
        # Outdoor Dining
        normalized['Outdoor Dining'] = normalize_boolean(data.get('outdoor_dining', ''))
        
        # Neighborhood
        normalized['Neighborhood'] = extract_neighborhood(normalized['Address'])
        
        # Dress Code
        normalized['Dress Code'] = data.get('dress_code', '').strip()
        
        # Chef Bio
        normalized['Chef Bio'] = data.get('chef_bio', '').strip()
        
        # Gift Card URL
        normalized['Gift Card URL'] = data.get('gift_card_url', '').strip()
        
        # Private Dining Email
        normalized['Private Dining Email'] = data.get('private_dining_email', '').strip()
        
        # Private Dining Phone
        normalized['Private Dining Phone'] = data.get('private_dining_phone', '').strip()
        
        # Video URL
        normalized['Video URL'] = data.get('video_url', '').strip()
        
        # Parking
        normalized['Parking'] = data.get('parking', '').strip()
        
        # Payment Method
        normalized['Payment Method'] = data.get('payment_method', '').strip()
        
        # Noise
        normalized['Noise'] = data.get('noise', '').strip()
        
        # Executive Chef
        normalized['Executive Chef'] = data.get('executive_chef', '').strip()
        
        # Cross Street
        cross_street = extract_cross_street(data.get('description', '') + ' ' + normalized['Address'])
        normalized['Cross Street'] = cross_street
        
        # Google Business Link
        google_link = data.get('source_url', '') if data.get('source') == 'Google Maps' else ''
        normalized['Google Business Link'] = google_link
        
        # Categories
        categories = data.get('categories', [])
        if isinstance(categories, str):
            categories = [c.strip() for c in categories.split(',')]
        normalized['Categories'] = normalize_tags(categories) or 'Restaurant;Dining'
        
        # Tags
        tags = data.get('tags', []) or data.get('amenities', [])
        normalized['Tags'] = normalize_tags(tags)
        
        # Cuisines
        cuisines = data.get('cuisines', [])
        if isinstance(cuisines, str):
            cuisines = [c.strip() for c in cuisines.split(',')]
        normalized['Cuisines'] = normalize_tags(cuisines) or 'American'
        
        # Ensure all CSV columns are present with empty string if missing
        for column in CSV_COLUMNS:
            if column not in normalized:
                normalized[column] = ""
        
        # Return only columns in CSV_COLUMNS order
        return {col: normalized.get(col, "") for col in CSV_COLUMNS}

