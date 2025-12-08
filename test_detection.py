"""Quick test script to verify listing page detection"""
import re

def test_is_restaurant_listing_page(url: str) -> bool:
    """Check if URL is a restaurant listing page"""
    url_lower = url.lower()
    
    # Special handling for OpenTable - check first before regex
    if 'opentable.com' in url_lower:
        # Individual restaurant pages have /r/ in the path
        if '/r/' in url_lower:
            print(f"  ❌ OpenTable URL is an individual restaurant page (has /r/)")
            return False
        
        # OpenTable listing pages - check for specific patterns
        listing_indicators = ['/metro/', '/region/', '/neighborhood/', '/s?', '/s?dateTime=']
        for indicator in listing_indicators:
            if indicator in url_lower:
                print(f"  ✅ OpenTable URL detected as listing page (has {indicator})")
                return True
        
        # If it's OpenTable but not a restaurant page and not excluded pages, it's likely a listing
        excluded = ['/restaurant/', '/profile/', '/about', '/help', '/contact', '/terms', '/privacy', '/gift-cards']
        if not any(excluded_page in url_lower for excluded_page in excluded):
            # Additional check: if URL contains "restaurants" (plural), it's likely a listing
            if 'restaurants' in url_lower:
                print(f"  ✅ OpenTable URL detected as listing page (contains 'restaurants')")
                return True
            # Default: treat as listing if not excluded
            print(f"  ✅ OpenTable URL detected as listing page (default for non-excluded pages)")
            return True
    
    # Check URL patterns with regex for other sites
    listing_patterns = [
        'yelp.com/search',
        'tripadvisor.com/search',
        'google.com/search.*restaurant',
        'google.com/maps/search',
        '/search.*restaurant',
        '/search.*food',
        '/search.*dining',
    ]
    
    for pattern in listing_patterns:
        if re.search(pattern, url_lower):
            print(f"  ✅ Detected as listing page (matches {pattern})")
            return True
    
    print(f"  ❌ NOT detected as listing page")
    return False

# Test URLs
test_urls = [
    "https://www.opentable.com/metro/houston-restaurants",
    "https://www.opentable.com/r/state-fare-houston",
    "https://www.opentable.com/region/houston/houston-restaurants",
    "https://www.opentable.com/s?term=pizza",
]

print("Testing Listing Page Detection\n" + "="*50)
for url in test_urls:
    print(f"\n🔍 Testing: {url}")
    result = test_is_restaurant_listing_page(url)
    print(f"   Result: {'LISTING PAGE ✅' if result else 'SINGLE PAGE ❌'}")

print("\n" + "="*50)
print("Expected Results:")
print("  - /metro/houston-restaurants → LISTING PAGE ✅")
print("  - /r/state-fare-houston → SINGLE PAGE ❌")
print("  - /region/houston/... → LISTING PAGE ✅")
print("  - /s?term=pizza → LISTING PAGE ✅")

