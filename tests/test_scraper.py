import pytest
from app.scraper import WebScraper


@pytest.mark.asyncio
async def test_scraper_basic():
    scraper = WebScraper()
    # Add tests here
    assert scraper is not None
