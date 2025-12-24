"""
Yelp Fusion API Integration
FREE TIER: 5000 API calls per day (no credit card required)

Get your FREE API key at: https://www.yelp.com/developers/v3/manage_app

Rate Limits:
- Free tier: 5,000 calls per day
- Rate limit headers are checked automatically
- Errors are raised when limits are exceeded
"""

import os
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

YELP_API_BASE = "https://api.yelp.com/v3"
FREE_TIER_DAILY_LIMIT = 5000  # Free tier limit per day


class YelpAPI:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("YELP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Yelp API key not found. Set YELP_API_KEY environment variable. "
                "Get your FREE API key at: https://www.yelp.com/developers/v3/manage_app"
            )
        # Simple rate limit tracking (resets daily)
        self.daily_call_count = 0
        self.last_reset_date = datetime.now().date()
    
    async def search_businesses(
        self,
        term: str,
        location: str,
        categories: str = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "best_match",
        price: str = None,
    ) -> Dict[str, Any]:
        """
        Search for businesses on Yelp.
        
        Args:
            term: Search term (e.g., "steakhouse", "pizza")
            location: Location (e.g., "Houston, TX")
            categories: Category filter (e.g., "restaurants,bars")
            limit: Number of results (max 50)
            sort_by: "best_match", "rating", "review_count", "distance"
            price: Price filter "1", "2", "3", "4" or combinations like "1,2"
        
        Returns:
            Dict with 'businesses' list and 'total' count
        """
        params = {
            "term": term,
            "location": location,
            "limit": min(limit, 50),
            "offset": offset,
            "sort_by": sort_by,
        }
        
        if categories:
            params["categories"] = categories
        if price:
            params["price"] = price
        
        return await self._request("GET", "/businesses/search", params=params)
    
    async def get_business_details(self, business_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific business."""
        return await self._request("GET", f"/businesses/{business_id}")
    
    async def get_business_reviews(self, business_id: str, limit: int = 3) -> Dict[str, Any]:
        """Get reviews for a specific business."""
        return await self._request("GET", f"/businesses/{business_id}/reviews", params={"limit": limit})
    
    async def search_restaurants(
        self,
        location: str,
        cuisine: str = None,
        limit: int = 20,
        price: str = None,
        sort_by: str = "rating",
    ) -> List[Dict[str, Any]]:
        """
        Search for restaurants and return clean, structured data.
        
        Args:
            location: City/address (e.g., "Houston, TX")
            cuisine: Type of food (e.g., "steakhouse", "italian")
            limit: Number of results
            price: Price range "1"-"4" ($ to $$$$)
            sort_by: How to sort results
        
        Returns:
            List of restaurant dictionaries with clean data
        """
        term = cuisine if cuisine else "restaurants"
        
        result = await self.search_businesses(
            term=term,
            location=location,
            categories="restaurants,food",
            limit=limit,
            sort_by=sort_by,
            price=price,
        )
        
        restaurants = []
        for biz in result.get("businesses", []):
            restaurants.append(self._format_business(biz))
        
        return restaurants
    
    def _format_business(self, biz: Dict[str, Any]) -> Dict[str, Any]:
        """Format a Yelp business into clean structure."""
        location = biz.get("location", {})
        
        return {
            "name": biz.get("name"),
            "rating": biz.get("rating"),
            "review_count": biz.get("review_count"),
            "price": biz.get("price"),
            "phone": biz.get("display_phone"),
            "address": ", ".join(location.get("display_address", [])),
            "city": location.get("city"),
            "state": location.get("state"),
            "zip_code": location.get("zip_code"),
            "categories": [cat.get("title") for cat in biz.get("categories", [])],
            "url": biz.get("url"),
            "image_url": biz.get("image_url"),
            "coordinates": biz.get("coordinates"),
            "is_closed": biz.get("is_closed"),
            "distance_meters": biz.get("distance"),
        }
    
    def _check_rate_limit(self):
        """Check and reset daily call count if needed"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            # New day, reset counter
            self.daily_call_count = 0
            self.last_reset_date = today
            logger.info("Yelp API daily call counter reset")
        
        # Check if we're approaching the limit
        remaining = FREE_TIER_DAILY_LIMIT - self.daily_call_count
        if remaining <= 0:
            raise ValueError(
                f"Yelp API FREE tier daily limit reached ({FREE_TIER_DAILY_LIMIT} calls/day). "
                f"Limit resets at midnight. Consider upgrading or wait until tomorrow."
            )
        elif remaining < 100:
            logger.warning(f"Yelp API: Only {remaining} calls remaining today (FREE tier limit: {FREE_TIER_DAILY_LIMIT})")
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        data: Dict = None,
    ) -> Dict[str, Any]:
        """Make a request to the Yelp API with rate limit tracking."""
        # Check rate limit before making request
        self._check_rate_limit()
        
        url = f"{YELP_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
            )
            
            # Increment call count on successful request
            if response.status_code < 400:
                self.daily_call_count += 1
                remaining = FREE_TIER_DAILY_LIMIT - self.daily_call_count
                if remaining % 100 == 0 or remaining < 50:
                    logger.info(f"Yelp API: {remaining} calls remaining today (FREE tier)")
            
            if response.status_code == 401:
                raise ValueError(
                    "Invalid Yelp API key. "
                    "Get your FREE API key at: https://www.yelp.com/developers/v3/manage_app"
                )
            elif response.status_code == 429:
                # Check rate limit headers if available
                retry_after = response.headers.get("Retry-After", "unknown")
                raise ValueError(
                    f"Yelp API rate limit exceeded (FREE tier: {FREE_TIER_DAILY_LIMIT} calls/day). "
                    f"Retry after: {retry_after}. "
                    f"Used: {self.daily_call_count}/{FREE_TIER_DAILY_LIMIT} calls today."
                )
            
            response.raise_for_status()
            return response.json()
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics"""
        remaining = FREE_TIER_DAILY_LIMIT - self.daily_call_count
        return {
            "daily_limit": FREE_TIER_DAILY_LIMIT,
            "calls_used": self.daily_call_count,
            "calls_remaining": remaining,
            "reset_date": self.last_reset_date.isoformat(),
            "tier": "FREE"
        }

