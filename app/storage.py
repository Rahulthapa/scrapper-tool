from supabase import create_client, Client
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
import logging
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

        # Create Supabase client
        # Using positional arguments to avoid any proxy-related issues
        try:
            self.client: Client = create_client(supabase_url, supabase_key)
        except TypeError as e:
            if 'proxy' in str(e).lower():
                # Fallback: try with explicit keyword arguments
                self.client: Client = create_client(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key
                )
            else:
                raise

    async def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scraping job"""
        try:
            response = self.client.table('scrape_jobs').insert(job_data).execute()
            return response.data[0] if response.data else None
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
