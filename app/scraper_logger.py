"""
Detailed logging module for web scraper operations.
Logs all URLs visited, sections extracted, and data found.
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

class ScraperLogger:
    """Detailed logger for scraper operations"""
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize the scraper logger.
        
        Args:
            log_file: Path to log file. If None, uses 'scraper_logs/scraper_{timestamp}.log'
        """
        if log_file is None:
            # Create logs directory if it doesn't exist
            log_dir = Path("scraper_logs")
            log_dir.mkdir(exist_ok=True)
            
            # Create log file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = str(log_dir / f"scraper_{timestamp}.log")
        
        self.log_file = log_file
        
        # Create logger
        self.logger = logging.getLogger('scraper_detailed')
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # File handler
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler (optional, for debugging)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info("=" * 80)
        self.logger.info(f"Scraper logging started - Log file: {log_file}")
        self.logger.info("=" * 80)
    
    def log_url_visit(self, url: str, method: str = "GET", status: str = "STARTED"):
        """Log when a URL is being visited"""
        self.logger.info(f"[URL VISIT] {status} | Method: {method} | URL: {url}")
    
    def log_url_complete(self, url: str, status_code: Optional[int] = None, 
                        html_length: Optional[int] = None, duration: Optional[float] = None):
        """Log when URL visit is complete"""
        info_parts = [f"[URL COMPLETE] URL: {url}"]
        if status_code:
            info_parts.append(f"Status: {status_code}")
        if html_length:
            info_parts.append(f"HTML Length: {html_length:,} bytes")
        if duration:
            info_parts.append(f"Duration: {duration:.2f}s")
        self.logger.info(" | ".join(info_parts))
    
    def log_url_error(self, url: str, error: str):
        """Log URL visit error"""
        self.logger.error(f"[URL ERROR] URL: {url} | Error: {error}")
    
    def log_section_extraction(self, url: str, section_name: str, status: str = "STARTED"):
        """Log when extracting a section"""
        self.logger.info(f"[SECTION] {status} | URL: {url} | Section: {section_name}")
    
    def log_section_data(self, url: str, section_name: str, data: Any, item_count: Optional[int] = None):
        """Log data extracted from a section"""
        if item_count is not None:
            self.logger.info(f"[SECTION DATA] URL: {url} | Section: {section_name} | Items Found: {item_count}")
        else:
            data_str = str(data)[:200] if data else "None"
            self.logger.info(f"[SECTION DATA] URL: {url} | Section: {section_name} | Data: {data_str}")
    
    def log_field_extracted(self, url: str, section: str, field_name: str, value: Any):
        """Log when a specific field is extracted"""
        value_str = str(value)[:100] if value else "None"
        self.logger.debug(f"[FIELD] URL: {url} | Section: {section} | Field: {field_name} | Value: {value_str}")
    
    def log_listing_urls_found(self, listing_url: str, urls: List[str]):
        """Log restaurant URLs found from listing page"""
        self.logger.info(f"[LISTING] URL: {listing_url} | Found {len(urls)} restaurant URLs")
        for i, url in enumerate(urls[:10], 1):  # Log first 10
            self.logger.info(f"[LISTING]   {i}. {url}")
        if len(urls) > 10:
            self.logger.info(f"[LISTING]   ... and {len(urls) - 10} more URLs")
    
    def log_restaurant_processing(self, url: str, step: str, details: Optional[str] = None):
        """Log restaurant processing steps"""
        msg = f"[RESTAURANT] URL: {url} | Step: {step}"
        if details:
            msg += f" | {details}"
        self.logger.info(msg)
    
    def log_data_summary(self, url: str, data: Dict[str, Any]):
        """Log summary of extracted data"""
        self.logger.info(f"[DATA SUMMARY] URL: {url}")
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                count = len(value) if value else 0
                self.logger.info(f"[DATA SUMMARY]   {key}: {count} items")
            elif value:
                value_str = str(value)[:100]
                self.logger.info(f"[DATA SUMMARY]   {key}: {value_str}")
    
    def log_separator(self, text: str = ""):
        """Log a separator line"""
        if text:
            self.logger.info(f"{'=' * 80}")
            self.logger.info(f"  {text}")
            self.logger.info(f"{'=' * 80}")
        else:
            self.logger.info("-" * 80)
    
    def log_warning(self, message: str, url: Optional[str] = None):
        """Log a warning"""
        if url:
            self.logger.warning(f"[WARNING] URL: {url} | {message}")
        else:
            self.logger.warning(f"[WARNING] {message}")
    
    def log_error(self, message: str, url: Optional[str] = None, exception: Optional[Exception] = None):
        """Log an error"""
        if url:
            msg = f"[ERROR] URL: {url} | {message}"
        else:
            msg = f"[ERROR] {message}"
        
        if exception:
            msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
        
        self.logger.error(msg)
        if exception:
            import traceback
            self.logger.debug(f"[ERROR TRACEBACK]\n{traceback.format_exc()}")


# Global logger instance
_scraper_logger: Optional[ScraperLogger] = None

def get_scraper_logger(log_file: Optional[str] = None) -> ScraperLogger:
    """Get or create the global scraper logger"""
    global _scraper_logger
    if _scraper_logger is None:
        _scraper_logger = ScraperLogger(log_file)
    return _scraper_logger

def reset_logger():
    """Reset the global logger (useful for testing)"""
    global _scraper_logger
    _scraper_logger = None

