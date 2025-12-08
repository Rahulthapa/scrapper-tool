"""
Main CLI entry point for the web scraper.
Supports multiple modes: single-url, list-from-file, search
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import quote_plus

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

try:
    from .config import ScraperConfig, load_config_from_env, load_config_from_file
    from .fetch import Fetcher, FetchError, CaptchaDetectedError, BotChallengeError, RateLimitError
    from .parse import (
        parse_google_maps,
        parse_yelp,
        parse_opentable,
        parse_official_website
    )
    from .normalize import DataNormalizer
    from .export import CSVExporter
except ImportError:
    # Allow running as script
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from config import ScraperConfig, load_config_from_env, load_config_from_file
    from fetch import Fetcher, FetchError, CaptchaDetectedError, BotChallengeError, RateLimitError
    from parse import (
        parse_google_maps,
        parse_yelp,
        parse_opentable,
        parse_official_website
    )
    from normalize import DataNormalizer
    from export import CSVExporter

console = Console()


def setup_logging(config: ScraperConfig):
    """Setup structured logging"""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler(config.log_file) if config.log_file else logging.NullHandler()
        ]
    )


async def scrape_from_urls(
    urls: List[str],
    sources: List[str],
    config: ScraperConfig,
    fetcher: Fetcher
) -> List[Dict[str, Any]]:
    """Scrape data from a list of URLs"""
    all_data = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Scraping URLs...", total=len(urls))
        
        for url in urls:
            try:
                progress.update(task, description=f"Fetching {url[:50]}...")
                
                # Determine source from URL
                if 'google.com/maps' in url or 'maps.google.com' in url:
                    source = 'Google Maps'
                    parser = parse_google_maps
                elif 'yelp.com' in url:
                    source = 'Yelp'
                    parser = parse_yelp
                elif 'opentable.com' in url:
                    source = 'OpenTable'
                    parser = parse_opentable
                else:
                    source = 'Official Website'
                    parser = parse_official_website
                
                if source not in sources:
                    progress.advance(task)
                    continue
                
                # Fetch
                html, metadata = await fetcher.fetch(url, use_dynamic=True)
                
                # Parse
                parsed_data = parser(html, url)
                all_data.append(parsed_data)
                
                progress.advance(task)
                
            except (CaptchaDetectedError, BotChallengeError) as e:
                console.print(f"[yellow]⚠ Skipping {url}: {e}[/yellow]")
                progress.advance(task)
                continue
            except RateLimitError as e:
                console.print(f"[red]⚠ Rate limited on {url}: {e}[/red]")
                progress.advance(task)
                continue
            except FetchError as e:
                console.print(f"[red]✗ Failed {url}: {e}[/red]")
                progress.advance(task)
                continue
            except Exception as e:
                console.print(f"[red]✗ Error on {url}: {e}[/red]")
                if config.debug_mode:
                    import traceback
                    console.print(traceback.format_exc())
                progress.advance(task)
                continue
    
    return all_data


async def scrape_from_search(
    query: str,
    config: ScraperConfig,
    fetcher: Fetcher
) -> List[Dict[str, Any]]:
    """Scrape data by searching Google Maps"""
    all_data = []
    
    console.print(f"[cyan]Searching for: {query}[/cyan]")
    
    # Build Google Maps search URL
    search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    
    try:
        # Fetch search results page
        html, metadata = await fetcher.fetch(search_url, use_dynamic=True)
        
        # Extract place URLs from search results
        # This is a simplified approach - in production you'd parse the search results properly
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        # Find all place links
        place_urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if '/maps/place/' in href or 'place_id' in href:
                if href.startswith('/'):
                    href = f"https://www.google.com{href}"
                if href not in place_urls:
                    place_urls.append(href)
        
        console.print(f"[green]Found {len(place_urls)} places[/green]")
        
        # Limit results
        place_urls = place_urls[:config.max_results]
        
        # Scrape each place
        all_data = await scrape_from_urls(place_urls, config.enabled_sources, config, fetcher)
        
        # Also try to get official websites and scrape those
        website_urls = []
        for data in all_data:
            website = data.get('website', '')
            if website and website not in website_urls:
                website_urls.append(website)
        
        if 'Official Website' in config.enabled_sources and website_urls:
            console.print(f"[cyan]Scraping {len(website_urls)} official websites...[/cyan]")
            website_data = await scrape_from_urls(
                website_urls[:config.max_pages_per_source],
                ['Official Website'],
                config,
                fetcher
            )
            all_data.extend(website_data)
        
    except Exception as e:
        console.print(f"[red]Error in search: {e}[/red]")
        if config.debug_mode:
            import traceback
            console.print(traceback.format_exc())
    
    return all_data


async def main_async(args):
    """Main async function"""
    # Load configuration
    config = ScraperConfig()
    
    if args.config:
        config = load_config_from_file(args.config)
    
    # Override with CLI arguments
    if args.headless is not None:
        config.headless = args.headless
    if args.output:
        config.csv_output_path = args.output
    if args.limit:
        config.max_results = args.limit
    if args.city:
        config.city = args.city
    if args.state:
        config.state = args.state
        config.default_location = f"{config.city}, {config.state}"
    if args.debug:
        config.debug_mode = True
        config.log_level = "DEBUG"
    
    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)
    
    console.print("[bold green]Web Scraper Starting[/bold green]")
    console.print(f"Mode: {args.mode}")
    console.print(f"Output: {config.csv_output_path}")
    console.print(f"Max Results: {config.max_results}")
    
    # Initialize components
    normalizer = DataNormalizer(config)
    exporter = CSVExporter(config)
    
    all_raw_data = []
    
    # Fetch data based on mode
    async with Fetcher(config) as fetcher:
        if args.mode == 'single-url':
            if not args.url:
                console.print("[red]Error: --url required for single-url mode[/red]")
                sys.exit(1)
            
            all_raw_data = await scrape_from_urls(
                [args.url],
                config.enabled_sources,
                config,
                fetcher
            )
            
        elif args.mode == 'list-from-file':
            if not args.file:
                console.print("[red]Error: --file required for list-from-file mode[/red]")
                sys.exit(1)
            
            file_path = Path(args.file)
            if not file_path.exists():
                console.print(f"[red]Error: File not found: {args.file}[/red]")
                sys.exit(1)
            
            # Read URLs from file (one per line)
            with open(file_path, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
            
            console.print(f"[cyan]Loaded {len(urls)} URLs from file[/cyan]")
            all_raw_data = await scrape_from_urls(
                urls[:config.max_results],
                config.enabled_sources,
                config,
                fetcher
            )
            
        elif args.mode == 'search':
            if not args.query:
                console.print("[red]Error: --query required for search mode[/red]")
                sys.exit(1)
            
            all_raw_data = await scrape_from_search(
                args.query,
                config,
                fetcher
            )
        
        else:
            console.print(f"[red]Error: Unknown mode: {args.mode}[/red]")
            sys.exit(1)
    
    # Normalize data
    console.print("[cyan]Normalizing data...[/cyan]")
    normalized_data = normalizer.normalize(all_raw_data)
    
    # Validate
    if not exporter.validate_data(normalized_data):
        console.print("[red]Error: Data validation failed[/red]")
        sys.exit(1)
    
    # Export
    console.print("[cyan]Exporting to CSV...[/cyan]")
    output_file = exporter.export(normalized_data)
    
    # Summary
    console.print("\n[bold green]Scraping Complete![/bold green]")
    
    table = Table(title="Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Entities", str(len(normalized_data)))
    table.add_row("Output File", output_file)
    table.add_row("Columns", str(len(CSV_COLUMNS)))
    
    console.print(table)
    
    console.print(f"\n[green]✓ Data exported to: {output_file}[/green]")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Production-grade web scraper for extracting structured data",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--mode',
        choices=['single-url', 'list-from-file', 'search'],
        required=True,
        help='Scraping mode: single-url, list-from-file, or search'
    )
    
    parser.add_argument(
        '--url',
        help='URL to scrape (required for single-url mode)'
    )
    
    parser.add_argument(
        '--file',
        help='File containing URLs, one per line (required for list-from-file mode)'
    )
    
    parser.add_argument(
        '--query',
        help='Search query (required for search mode). Example: "steakhouses in Houston Texas"'
    )
    
    parser.add_argument(
        '--config',
        help='Path to YAML configuration file'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        help='Output CSV file path (default: output.csv)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of results to scrape'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode (default: True)'
    )
    
    parser.add_argument(
        '--no-headless',
        dest='headless',
        action='store_false',
        help='Run browser with GUI'
    )
    
    parser.add_argument(
        '--city',
        help='City name for location-based searches'
    )
    
    parser.add_argument(
        '--state',
        help='State code for location-based searches'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode with verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set default headless
    if args.headless is None:
        args.headless = True
    
    # Run async main
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        if args.debug:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()

