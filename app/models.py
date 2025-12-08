from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScrapeJobCreate(BaseModel):
    url: Optional[HttpUrl] = None  # Optional for crawl mode
    search_query: Optional[str] = None  # For web crawling mode
    crawl_mode: Optional[bool] = False  # Enable web crawling
    max_pages: Optional[int] = 10  # Max pages to crawl
    max_depth: Optional[int] = 2  # Max crawl depth
    same_domain: Optional[bool] = True  # Only crawl same domain
    filters: Optional[Dict[str, Any]] = None
    ai_prompt: Optional[str] = None
    export_format: Optional[str] = "json"
    use_javascript: Optional[bool] = False  # Use Playwright for JS-rendered pages
    extract_individual_pages: Optional[bool] = True  # Extract from individual restaurant pages (for listing pages) - DEFAULT: enabled


class ParseHTMLRequest(BaseModel):
    html: str  # Raw HTML content
    source_url: Optional[str] = None  # Optional: where the HTML came from
    ai_prompt: Optional[str] = None  # Optional: AI extraction prompt
    extract_individual_pages: Optional[bool] = True  # Extract from individual restaurant pages - DEFAULT: enabled


class ExtractInternalDataRequest(BaseModel):
    url: HttpUrl  # URL to extract internal data from
    wait_time: Optional[int] = 5  # Seconds to wait for data to load
    scroll: Optional[bool] = True  # Scroll page to trigger lazy loading
    intercept_network: Optional[bool] = True  # Intercept API calls
    ai_prompt: Optional[str] = None  # Optional: AI extraction prompt
    extract_individual_pages: Optional[bool] = True  # Extract from individual restaurant pages - DEFAULT: enabled


class ExtractFromIndividualPagesRequest(BaseModel):
    restaurants: List[Dict[str, Any]]  # List of restaurants with URLs
    use_javascript: Optional[bool] = True  # Use Playwright for JS pages
    max_concurrent: Optional[int] = 5  # Max concurrent requests
    ai_prompt: Optional[str] = None  # Optional: AI extraction prompt


class ScrapeJob(BaseModel):
    id: str
    url: Optional[str] = None  # Optional for crawl mode
    status: JobStatus
    filters: Optional[Dict[str, Any]] = None
    ai_prompt: Optional[str] = None
    export_format: str
    crawl_mode: Optional[bool] = False
    search_query: Optional[str] = None
    max_pages: Optional[int] = None
    max_depth: Optional[int] = None
    same_domain: Optional[bool] = None
    use_javascript: Optional[bool] = False
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ScrapeResult(BaseModel):
    job_id: str
    data: List[Dict[str, Any]]
    total_items: int
    filtered_items: int
