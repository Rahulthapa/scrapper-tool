"""
Fetch layer for web scraping.
Handles HTTP requests, Playwright browser automation, and robots.txt compliance.
"""
import asyncio
import logging
import random
import time
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import hashlib

from .config import ScraperConfig

logger = logging.getLogger(__name__)


class RobotsTxtChecker:
    """Manages robots.txt checking and caching"""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.cache: Dict[str, Tuple[RobotFileParser, float]] = {}
        self.cache_ttl = config.robots_txt_cache_ttl
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Check if URL can be fetched according to robots.txt"""
        if not self.config.respect_robots_txt:
            return True
        
        domain = self._get_domain(url)
        robots_url = urljoin(domain, "/robots.txt")
        
        # Check cache
        if domain in self.cache:
            rp, timestamp = self.cache[domain]
            if time.time() - timestamp < self.cache_ttl:
                return rp.can_fetch(user_agent, url)
        
        # Fetch robots.txt
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.set_url(robots_url)
                    rp.read()
                    self.cache[domain] = (rp, time.time())
                    return rp.can_fetch(user_agent, url)
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt for {domain}: {e}")
        
        # Default to allowing if robots.txt can't be fetched
        return True


class FetchError(Exception):
    """Custom exception for fetch errors"""
    pass


class CaptchaDetectedError(FetchError):
    """Raised when CAPTCHA is detected"""
    pass


class BotChallengeError(FetchError):
    """Raised when bot challenge is detected"""
    pass


class RateLimitError(FetchError):
    """Raised when rate limited"""
    pass


class Fetcher:
    """Main fetcher class for static and dynamic content"""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.robots_checker = RobotsTxtChecker(config)
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self.consecutive_errors = 0
        
    async def __aenter__(self):
        """Async context manager entry"""
        if self.config.browser_type:
            self.playwright = await async_playwright().start()
            browser_launcher = getattr(self.playwright, self.config.browser_type)
            self.browser = await browser_launcher.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            self.context = await self.browser.new_context(
                viewport={
                    'width': self.config.viewport_width,
                    'height': self.config.viewport_height
                },
                user_agent=self.config.get_user_agent()
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def _detect_captcha(self, html: str) -> bool:
        """Detect CAPTCHA in HTML"""
        captcha_indicators = [
            'recaptcha',
            'hcaptcha',
            'captcha',
            'challenge-platform',
            'cf-browser-verification',
            'access denied',
            'unusual traffic'
        ]
        html_lower = html.lower()
        return any(indicator in html_lower for indicator in captcha_indicators)
    
    def _detect_bot_challenge(self, html: str) -> bool:
        """Detect bot challenge pages"""
        challenge_indicators = [
            'please verify you are human',
            'verify you are not a robot',
            'cloudflare',
            'ddos protection',
            'security check',
            'checking your browser'
        ]
        html_lower = html.lower()
        return any(indicator in html_lower for indicator in challenge_indicators)
    
    async def fetch_static(self, url: str, retry_count: int = 0) -> Tuple[str, Dict[str, Any]]:
        """
        Fetch static HTML content using HTTPX
        
        Returns:
            Tuple of (HTML content, metadata dict)
        """
        # Check robots.txt
        if not await self.robots_checker.can_fetch(url, self.config.get_user_agent()):
            logger.info(f"Skipping {url} - blocked by robots.txt")
            raise FetchError("Blocked by robots.txt")
        
        headers = {
            'User-Agent': self.config.get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        try:
            async with httpx.AsyncClient(
                timeout=self.config.request_timeout,
                follow_redirects=True,
                headers=headers
            ) as client:
                response = await client.get(url)
                
                # Check status codes
                if response.status_code == 403:
                    if self.config.skip_on_403:
                        raise FetchError("403 Forbidden - skipping")
                    raise RateLimitError("403 Forbidden")
                
                if response.status_code == 429:
                    if self.config.skip_on_429:
                        raise FetchError("429 Too Many Requests - skipping")
                    raise RateLimitError("429 Too Many Requests")
                
                response.raise_for_status()
                html = response.text
                
                # Detect CAPTCHA
                if self._detect_captcha(html):
                    if self.config.skip_on_captcha:
                        raise CaptchaDetectedError("CAPTCHA detected")
                    logger.warning(f"CAPTCHA detected on {url}")
                
                # Detect bot challenge
                if self._detect_bot_challenge(html):
                    raise BotChallengeError("Bot challenge detected")
                
                self.consecutive_errors = 0
                
                metadata = {
                    "url": url,
                    "status": "success",
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "final_url": str(response.url),
                    "timestamp": time.time()
                }
                
                logger.info(f"Successfully fetched {url}")
                return html, metadata
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [403, 429]:
                self.consecutive_errors += 1
                if self.consecutive_errors >= self.config.max_consecutive_errors:
                    raise FetchError(f"Too many consecutive errors: {self.consecutive_errors}")
            
            if retry_count < self.config.max_retries:
                backoff = self.config.retry_backoff_factor ** retry_count
                await asyncio.sleep(backoff)
                return await self.fetch_static(url, retry_count + 1)
            
            raise FetchError(f"HTTP error {e.response.status_code}: {str(e)}")
            
        except httpx.TimeoutException:
            if retry_count < self.config.max_retries:
                backoff = self.config.retry_backoff_factor ** retry_count
                await asyncio.sleep(backoff)
                return await self.fetch_static(url, retry_count + 1)
            raise FetchError(f"Timeout fetching {url}")
            
        except Exception as e:
            if retry_count < self.config.max_retries:
                backoff = self.config.retry_backoff_factor ** retry_count
                await asyncio.sleep(backoff)
                return await self.fetch_static(url, retry_count + 1)
            raise FetchError(f"Error fetching {url}: {str(e)}")
    
    async def fetch_dynamic(self, url: str, retry_count: int = 0) -> Tuple[str, Dict[str, Any]]:
        """
        Fetch dynamic content using Playwright
        
        Returns:
            Tuple of (HTML content, metadata dict)
        """
        if not self.browser or not self.context:
            raise FetchError("Browser not initialized. Use async context manager.")
        
        # Check robots.txt
        if not await self.robots_checker.can_fetch(url, self.config.get_user_agent()):
            logger.info(f"Skipping {url} - blocked by robots.txt")
            raise FetchError("Blocked by robots.txt")
        
        page = await self.context.new_page()
        
        try:
            # Set additional headers
            await page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            # Navigate
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=self.config.request_timeout * 1000
            )
            
            if not response:
                raise FetchError(f"No response from {url}")
            
            status_code = response.status
            
            # Check status codes
            if status_code == 403:
                if self.config.skip_on_403:
                    raise FetchError("403 Forbidden - skipping")
                raise RateLimitError("403 Forbidden")
            
            if status_code == 429:
                if self.config.skip_on_429:
                    raise FetchError("429 Too Many Requests - skipping")
                raise RateLimitError("429 Too Many Requests")
            
            # Wait for content to load
            await asyncio.sleep(1)
            
            # Get HTML
            html = await page.content()
            
            # Detect CAPTCHA
            if self._detect_captcha(html):
                if self.config.skip_on_captcha:
                    raise CaptchaDetectedError("CAPTCHA detected")
                logger.warning(f"CAPTCHA detected on {url}")
            
            # Detect bot challenge
            if self._detect_bot_challenge(html):
                raise BotChallengeError("Bot challenge detected")
            
            self.consecutive_errors = 0
            
            metadata = {
                "url": url,
                "status": "success",
                "status_code": status_code,
                "final_url": page.url,
                "timestamp": time.time()
            }
            
            logger.info(f"Successfully fetched {url} (dynamic)")
            return html, metadata
            
        except PlaywrightTimeoutError:
            if retry_count < self.config.max_retries:
                backoff = self.config.retry_backoff_factor ** retry_count
                await asyncio.sleep(backoff)
                await page.close()
                return await self.fetch_dynamic(url, retry_count + 1)
            raise FetchError(f"Timeout fetching {url}")
            
        except Exception as e:
            if retry_count < self.config.max_retries:
                backoff = self.config.retry_backoff_factor ** retry_count
                await asyncio.sleep(backoff)
                await page.close()
                return await self.fetch_dynamic(url, retry_count + 1)
            raise FetchError(f"Error fetching {url}: {str(e)}")
            
        finally:
            await page.close()
    
    async def fetch(self, url: str, use_dynamic: bool = False) -> Tuple[str, Dict[str, Any]]:
        """
        Fetch URL - automatically chooses static or dynamic
        
        Args:
            url: URL to fetch
            use_dynamic: Force use of Playwright
        
        Returns:
            Tuple of (HTML content, metadata)
        """
        # Rate limiting
        await asyncio.sleep(self.config.get_delay())
        
        if use_dynamic or self.browser:
            return await self.fetch_dynamic(url)
        else:
            return await self.fetch_static(url)

