"""
Example usage of the web scraper
This demonstrates how to use the scraper programmatically
"""
import asyncio
from config import ScraperConfig
from fetch import Fetcher
from parse import parse_google_maps, parse_official_website
from normalize import DataNormalizer
from export import CSVExporter


async def example_single_url():
    """Example: Scrape a single Google Maps URL"""
    config = ScraperConfig()
    config.csv_output_path = "example_output.csv"
    
    url = "https://www.google.com/maps/place/Your+Restaurant+Name"
    
    async with Fetcher(config) as fetcher:
        # Fetch
        html, metadata = await fetcher.fetch(url, use_dynamic=True)
        
        # Parse
        data = parse_google_maps(html, url)
        
        # Normalize
        normalizer = DataNormalizer(config)
        normalized = normalizer.normalize([data])
        
        # Export
        exporter = CSVExporter(config)
        output_file = exporter.export(normalized)
        
        print(f"Exported to: {output_file}")


async def example_search():
    """Example: Search and scrape multiple results"""
    config = ScraperConfig()
    config.max_results = 10
    config.csv_output_path = "search_results.csv"
    
    query = "steakhouses in Houston Texas"
    
    # This is a simplified example - use main.py for full search functionality
    print(f"Search example for: {query}")
    print("Use: python -m scraper.main --mode search --query '{query}'")


if __name__ == '__main__':
    print("Example usage of the scraper")
    print("For full functionality, use: python -m scraper.main")
    # asyncio.run(example_single_url())

