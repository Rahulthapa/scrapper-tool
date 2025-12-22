from supabase import create_client, Client
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
import logging
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ANON_KEY")

        if not supabase_url or not supabase_key:
            missing = []
            if not supabase_url:
                missing.append("SUPABASE_URL")
            if not supabase_key:
                missing.append("SUPABASE_ANON_KEY")
            
            error_msg = (
                f"Supabase credentials not found in environment.\n"
                f"Missing variables: {', '.join(missing)}\n\n"
                f"Please set the following environment variables:\n"
                f"  - SUPABASE_URL: Your Supabase project URL\n"
                f"  - SUPABASE_ANON_KEY: Your Supabase anonymous key\n\n"
                f"You can:\n"
                f"  1. Create a .env file in the project root with these variables\n"
                f"  2. Set them as environment variables in your system\n"
                f"  3. Set them in your deployment platform (Render, etc.)\n\n"
                f"Example .env file:\n"
                f"  SUPABASE_URL=https://your-project.supabase.co\n"
                f"  SUPABASE_ANON_KEY=your-anon-key-here"
            )
            raise ValueError(error_msg)

        # Validate SUPABASE_URL format and DNS
        parsed_url = None
        hostname = None
        try:
            parsed_url = urlparse(supabase_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError(f"Invalid SUPABASE_URL format: {supabase_url}. Expected format: https://your-project.supabase.co")
            
            # Try to resolve the hostname to check DNS
            hostname = parsed_url.hostname
            try:
                socket.gethostbyname(hostname)
                logger.debug(f"Successfully resolved hostname: {hostname}")
            except socket.gaierror as dns_error:
                error_msg = (
                    f"DNS resolution failed for Supabase hostname '{hostname}'.\n"
                    f"This usually means:\n"
                    f"  1. The SUPABASE_URL is incorrect or contains a typo\n"
                    f"  2. There's no internet connection\n"
                    f"  3. DNS servers cannot resolve the hostname\n\n"
                    f"Current SUPABASE_URL: {supabase_url}\n"
                    f"Please verify your SUPABASE_URL is correct and you have internet connectivity."
                )
                logger.error(error_msg)
                raise ValueError(error_msg) from dns_error
        except ValueError as e:
            raise
        except Exception as e:
            logger.warning(f"Could not validate SUPABASE_URL format: {str(e)}")

        # Create Supabase client
        # Using positional arguments to avoid any proxy-related issues
        try:
            self.client: Client = create_client(supabase_url, supabase_key)
            logger.info("Successfully created Supabase client")
        except (TypeError, OSError, socket.gaierror) as e:
            if isinstance(e, (OSError, socket.gaierror)) and ("Name or service not known" in str(e) or "Errno -2" in str(e)):
                hostname_str = hostname if hostname else "unknown"
                error_msg = (
                    f"DNS resolution error when connecting to Supabase.\n"
                    f"Hostname: {hostname_str}\n"
                    f"SUPABASE_URL: {supabase_url}\n\n"
                    f"This error usually means:\n"
                    f"  1. The SUPABASE_URL hostname cannot be resolved\n"
                    f"  2. There's no internet connection\n"
                    f"  3. DNS servers are not accessible\n\n"
                    f"Please check:\n"
                    f"  - Your internet connection\n"
                    f"  - That SUPABASE_URL is correct (no typos)\n"
                    f"  - Your DNS settings"
                )
                logger.error(error_msg)
                raise ValueError(error_msg) from e
            elif 'proxy' in str(e).lower():
                # Fallback: try with explicit keyword arguments
                try:
                    self.client: Client = create_client(
                        supabase_url=supabase_url,
                        supabase_key=supabase_key
                    )
                    logger.info("Successfully created Supabase client (with keyword args)")
                except Exception as e2:
                    logger.error(f"Failed to create Supabase client even with keyword args: {str(e2)}")
                    raise
            else:
                logger.error(f"Failed to create Supabase client: {str(e)}")
                raise

    async def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scraping job"""
        try:
            response = self.client.table('scrape_jobs').insert(job_data).execute()
            return response.data[0] if response.data else None
        except (OSError, socket.gaierror) as e:
            # Handle DNS/network errors
            if "Name or service not known" in str(e) or "Errno -2" in str(e):
                error_msg = (
                    f"DNS resolution error when connecting to database.\n"
                    f"This usually means:\n"
                    f"  1. The SUPABASE_URL hostname cannot be resolved\n"
                    f"  2. There's no internet connection\n"
                    f"  3. DNS servers are not accessible\n\n"
                    f"Please check your internet connection and SUPABASE_URL configuration."
                )
                logger.error(f"DNS error creating job: {error_msg}")
                raise Exception(error_msg) from e
            else:
                raise
        except Exception as e:
            # Extract error message from Supabase exception
            error_msg = str(e)
            
            # Try to extract more details from the exception if it's a dict-like error
            if hasattr(e, 'message'):
                error_msg = str(e.message)
            elif hasattr(e, 'args') and e.args:
                # Supabase errors often have dict-like args
                if isinstance(e.args[0], dict):
                    error_msg = e.args[0].get('message', str(e))
                else:
                    error_msg = str(e.args[0])
            
            # Check for DNS errors in the error message
            if "Name or service not known" in error_msg or "Errno -2" in error_msg:
                error_msg = (
                    f"DNS resolution error when connecting to database.\n"
                    f"Original error: {error_msg}\n\n"
                    f"This usually means:\n"
                    f"  1. The SUPABASE_URL hostname cannot be resolved\n"
                    f"  2. There's no internet connection\n"
                    f"  3. DNS servers are not accessible\n\n"
                    f"Please check your internet connection and SUPABASE_URL configuration."
                )
            
            # Log the error with full details
            logger.error(f"Failed to create job in database: {error_msg}")
            logger.error(f"Job data attempted: {job_data}")
            logger.error(f"Exception type: {type(e).__name__}")
            
            # Create a more user-friendly exception
            raise Exception(error_msg) from e

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID"""
        try:
            logger.debug(f"Fetching job {job_id} from database")
            
            # Try to fetch the job
            response = self.client.table('scrape_jobs').select('*').eq('id', job_id).limit(1).execute()
            
            # Get first result or None
            if response.data and len(response.data) > 0:
                job_data = response.data[0]
            else:
                return None
            
            # Use job_data instead of response.data below
            job = job_data.copy()
            
            logger.debug(f"Database response received, has data: {len(response.data) > 0 if response.data else False}")
            
            logger.debug(f"Job data keys: {list(job.keys())}")
            
            # Ensure all optional fields have defaults
            defaults = {
                'url': None,
                'filters': None,
                'ai_prompt': None,
                'export_format': 'json',
                'crawl_mode': False,
                'search_query': None,
                'max_pages': None,
                'max_depth': None,
                'same_domain': None,
                'use_javascript': False,
                'extract_individual_pages': True,  # Default: enabled for restaurant pages
                'error': None,
                'completed_at': None
            }
            
            for key, default_value in defaults.items():
                if key not in job:
                    job[key] = default_value
            
            # Keep datetime as-is (let main.py handle conversion)
            # Just ensure they're strings if they exist
            if 'created_at' in job and job['created_at']:
                if not isinstance(job['created_at'], str):
                    if hasattr(job['created_at'], 'isoformat'):
                        job['created_at'] = job['created_at'].isoformat()
                    else:
                        job['created_at'] = str(job['created_at'])
            
            if 'completed_at' in job and job.get('completed_at'):
                if not isinstance(job['completed_at'], str):
                    if hasattr(job['completed_at'], 'isoformat'):
                        job['completed_at'] = job['completed_at'].isoformat()
                    else:
                        job['completed_at'] = str(job['completed_at'])
            
            logger.debug(f"Successfully fetched and normalized job {job_id}")
            return job
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Error fetching job {job_id} from database")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {str(e)}")
            logger.error(f"Full traceback:\n{error_traceback}")
            
            # Try to extract more error details
            error_details = str(e)
            if hasattr(e, 'message'):
                error_details = str(e.message)
            elif hasattr(e, 'args') and e.args:
                if isinstance(e.args[0], dict):
                    error_details = e.args[0].get('message', str(e))
                else:
                    error_details = str(e.args[0])
            
            # Re-raise with more context
            raise Exception(f"Database error fetching job {job_id}: {error_details}") from e

    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a job"""
        response = self.client.table('scrape_jobs').update(updates).eq('id', job_id).execute()
        return response.data[0] if response.data else None

    async def save_results(self, job_id: str, results: List[Dict[str, Any]]) -> None:
        """Save scraping results"""
        data = [{'job_id': job_id, 'data': result} for result in results]
        self.client.table('scrape_results').insert(data).execute()

    async def get_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Get results for a job"""
        response = self.client.table('scrape_results').select('*').eq('job_id', job_id).execute()
        return response.data if response.data else []
    
    # ========== Extracted URLs Management ==========
    
    async def save_extracted_urls(self, job_id: str, urls: List[str]) -> None:
        """Save list of extracted URLs for a job with status='pending'"""
        try:
            data = [
                {
                    'job_id': job_id,
                    'url': url,
                    'status': 'pending'
                }
                for url in urls
            ]
            # Use upsert to handle duplicates gracefully
            self.client.table('extracted_urls').upsert(
                data,
                on_conflict='job_id,url'
            ).execute()
            logger.info(f"Saved {len(urls)} extracted URLs for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to save extracted URLs: {str(e)}")
            raise
    
    async def get_extracted_urls(self, job_id: str) -> List[Dict[str, Any]]:
        """Get all extracted URLs for a job with their status"""
        try:
            response = self.client.table('extracted_urls').select('*').eq('job_id', job_id).order('created_at').execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Failed to get extracted URLs: {str(e)}")
            return []
    
    async def update_url_status(
        self, 
        job_id: str, 
        url: str, 
        status: str, 
        data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update scrape status for a specific URL"""
        try:
            updates = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            if status == 'scraped' and data:
                updates['data'] = data
                updates['scraped_at'] = datetime.utcnow().isoformat()
            
            if error_message:
                updates['error_message'] = error_message
            
            response = self.client.table('extracted_urls').update(updates).eq('job_id', job_id).eq('url', url).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            logger.error(f"Failed to update URL status: {str(e)}")
            raise
    
    async def get_scraped_urls(self, job_id: str) -> List[Dict[str, Any]]:
        """Get only URLs that have been successfully scraped (for export)"""
        try:
            response = self.client.table('extracted_urls').select('*').eq('job_id', job_id).eq('status', 'scraped').order('scraped_at').execute()
            urls_with_data = []
            if response.data:
                for item in response.data:
                    if item.get('data'):
                        # Extract the data field and add URL
                        url_data = item.get('data', {})
                        url_data['url'] = item.get('url')
                        urls_with_data.append(url_data)
            return urls_with_data
        except Exception as e:
            logger.error(f"Failed to get scraped URLs: {str(e)}")
            return []
    
    async def get_url_status(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific URL"""
        try:
            response = self.client.table('extracted_urls').select('*').eq('job_id', job_id).eq('url', url).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get URL status: {str(e)}")
            return None