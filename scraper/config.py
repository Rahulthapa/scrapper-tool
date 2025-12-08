"""
Configuration module for the web scraper.
All settings can be overridden via CLI arguments or environment variables.
"""
import os
from typing import List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path


# Strict CSV column order - DO NOT MODIFY ORDER
CSV_COLUMNS = [
    "ID",
    "Title",
    "Slug",
    "Content",
    "Excerpt",
    "Post Status",
    "Post Date",
    "Featured Image URL",
    "Location",
    "Address",
    "Phone",
    "Website",
    "Email",
    "Rating",
    "Price Range",
    "Latitude",
    "Longitude",
    "Diners Choice",
    "Top Rated",
    "Outdoor Dining",
    "Neighborhood",
    "Dress Code",
    "Chef Bio",
    "Gift Card URL",
    "Private Dining Email",
    "Private Dining Phone",
    "Video URL",
    "Phone Number (ACF)",
    "Parking",
    "Payment Method",
    "Noise",
    "Executive Chef",
    "Cross Street",
    "Google Business Link",
    "Categories",
    "Tags",
    "Cuisines"
]

# Enabled data sources
SOURCES = [
    "Google Maps",
    "Yelp",
    "OpenTable",
    "Official Website"
]

# Source-specific URL patterns
SOURCE_PATTERNS = {
    "Google Maps": {
        "search_url": "https://www.google.com/maps/search/{query}",
        "place_url": "https://www.google.com/maps/place/{place_id}",
        "selectors": {
            "title": "h1[data-attrid='title'], h1.section-hero-header-title-title",
            "address": "button[data-item-id='address'], span[aria-label*='Address']",
            "phone": "button[data-item-id='phone']",
            "website": "a[data-item-id='authority']",
            "rating": "div[class*='gm2-display-2'] span[aria-hidden='true'], div[aria-label*='stars']",
            "price_range": "span[aria-label*='Price']",
            "reviews_count": "button[jsaction*='reviews']",
        }
    },
    "Yelp": {
        "search_url": "https://www.yelp.com/search?find_desc={query}&find_loc={location}",
        "business_url": "https://www.yelp.com/biz/{business_id}",
        "selectors": {
            "title": "h1[class*='heading']",
            "address": "address, p[class*='address']",
            "phone": "p[class*='phone']",
            "rating": "div[role='img'][aria-label*='star']",
            "price_range": "span[class*='price-range']",
            "amenities": "div[class*='amenity']",
        }
    },
    "OpenTable": {
        "search_url": "https://www.opentable.com/s/?city={city}&query={query}",
        "restaurant_url": "https://www.opentable.com/restaurant/profile/{id}",
        "selectors": {
            "title": "h1[class*='restaurant-name']",
            "address": "div[class*='address']",
            "phone": "a[href^='tel:']",
            "rating": "div[class*='rating']",
            "price_range": "span[class*='price']",
        }
    }
}

# Global scraping configuration
@dataclass
class ScraperConfig:
    """Main configuration class for the scraper"""
    
    # CSV Configuration
    csv_columns: List[str] = field(default_factory=lambda: CSV_COLUMNS)
    csv_output_path: str = "output.csv"
    
    # Source Configuration
    enabled_sources: List[str] = field(default_factory=lambda: SOURCES)
    source_patterns: Dict[str, Dict[str, Any]] = field(default_factory=lambda: SOURCE_PATTERNS)
    
    # Rate Limiting
    delay_between_requests: float = 2.0  # seconds
    delay_jitter: float = 0.5  # random jitter
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    request_timeout: int = 30  # seconds
    
    # Browser Configuration
    headless: bool = True
    browser_type: str = "chromium"  # chromium, firefox, webkit
    viewport_width: int = 1920
    viewport_height: int = 1080
    slow_mo: int = 0  # milliseconds
    
    # User Agent
    user_agents: List[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ])
    
    # Proxy Configuration
    proxy_enabled: bool = False
    proxy_list: List[str] = field(default_factory=list)
    
    # Robots.txt
    respect_robots_txt: bool = True
    robots_txt_cache_ttl: int = 3600  # seconds
    
    # Location Configuration
    default_location: str = "Houston, TX"
    city: str = "Houston"
    state: str = "TX"
    
    # Scraping Limits
    max_results: int = 100
    max_pages_per_source: int = 50
    max_depth: int = 3
    
    # Error Handling
    skip_on_captcha: bool = True
    skip_on_403: bool = True
    skip_on_429: bool = True
    max_consecutive_errors: int = 5
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "scraper.log"
    debug_mode: bool = False
    
    # Data Processing
    deduplicate: bool = True
    merge_sources: bool = True
    extract_json_ld: bool = True
    extract_microdata: bool = True
    extract_og_tags: bool = True
    
    # ID Generation
    id_hash_salt: str = ""
    
    def get_user_agent(self) -> str:
        """Get a random user agent"""
        import random
        return random.choice(self.user_agents)
    
    def get_delay(self) -> float:
        """Get delay with jitter"""
        import random
        return self.delay_between_requests + random.uniform(0, self.delay_jitter)


def load_config_from_env() -> ScraperConfig:
    """Load configuration from environment variables"""
    config = ScraperConfig()
    
    # Override from environment
    if os.getenv("SCRAPER_HEADLESS"):
        config.headless = os.getenv("SCRAPER_HEADLESS").lower() == "true"
    
    if os.getenv("SCRAPER_DELAY"):
        config.delay_between_requests = float(os.getenv("SCRAPER_DELAY"))
    
    if os.getenv("SCRAPER_MAX_RESULTS"):
        config.max_results = int(os.getenv("SCRAPER_MAX_RESULTS"))
    
    if os.getenv("SCRAPER_LOCATION"):
        config.default_location = os.getenv("SCRAPER_LOCATION")
    
    if os.getenv("SCRAPER_OUTPUT"):
        config.csv_output_path = os.getenv("SCRAPER_OUTPUT")
    
    return config


def load_config_from_file(config_path: str) -> ScraperConfig:
    """Load configuration from YAML file"""
    import yaml
    
    config = ScraperConfig()
    
    if not Path(config_path).exists():
        return config
    
    with open(config_path, 'r') as f:
        yaml_config = yaml.safe_load(f)
    
    if yaml_config:
        for key, value in yaml_config.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    return config

