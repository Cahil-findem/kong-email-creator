"""
Insert job postings into Supabase
Usage: python insert_job_posting.py <job_data.json>
"""

import os
import json
import logging
import hashlib
from typing import Dict, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JobPostingManager:
    """Manage job postings in Supabase"""

    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized")

    def generate_job_id(self, job_data: Dict) -> str:
        """
        Generate a unique job ID from job data
        Uses application_link or position + company hash
        """
        # Try to use application link as primary identifier
        if 'metadata' in job_data and 'application_link' in job_data['metadata']:
            link = job_data['metadata']['application_link']
            # Extract the hash from the URL
            if 'ashbyhq.com/kong/' in link:
                job_hash = link.split('/')[-1].split('?')[0]
                return job_hash

        # Fallback: hash of position + company
        position = job_data.get('position', 'unknown')
        company = job_data.get('company', 'unknown')
        combined = f"{position}-{company}".lower()
        # Create URL-safe slug
        slug = combined.replace(' ', '-').replace('/', '-')
        # Add short hash for uniqueness
        hash_suffix = hashlib.md5(combined.encode()).hexdigest()[:8]
        return f"{slug}-{hash_suffix}"

    def extract_job_fields(self, job_data: Dict) -> Dict:
        """Extract fields from job JSON for database columns"""
        # Location extraction
        location = job_data.get('location', {})
        location_city = location.get('city', '')
        location_country = location.get('country', '')
        location_type = location.get('type', '')

        # Compensation extraction
        compensation = job_data.get('compensation', {})
        compensation_currency = compensation.get('currency', '')
        compensation_min = compensation.get('min')
        compensation_max = compensation.get('max')

        # Employment extraction
        employment = job_data.get('employment', {})
        employment_type = employment.get('type', '')
        department = employment.get('department', '')

        # Metadata extraction
        metadata = job_data.get('metadata', {})
        application_link = metadata.get('application_link', '')
        posting_code = metadata.get('posting_code', '')

        return {
            'position': job_data.get('position', ''),
            'company': job_data.get('company', ''),
            'department': department,
            'employment_type': employment_type,
            'location_city': location_city,
            'location_country': location_country,
            'location_type': location_type,
            'compensation_currency': compensation_currency,
            'compensation_min': compensation_min,
            'compensation_max': compensation_max,
            'about_role': job_data.get('about_role', ''),
            'responsibilities': json.dumps(job_data.get('responsibilities', [])),
            'requirements': json.dumps(job_data.get('requirements', {})),
            'application_link': application_link,
            'posting_code': posting_code,
            'raw_job_data': json.dumps(job_data)
        }

    def insert_job_posting(self, job_data: Dict, job_id: Optional[str] = None) -> bool:
        """
        Insert or update a job posting

        Args:
            job_data: Full job posting JSON
            job_id: Optional custom job ID (auto-generated if not provided)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate job_id if not provided
            if not job_id:
                job_id = self.generate_job_id(job_data)

            logger.info(f"Processing job: {job_data.get('position', 'Unknown')} (ID: {job_id})")

            # Extract fields for database columns
            extracted_fields = self.extract_job_fields(job_data)
            extracted_fields['job_id'] = job_id

            # Check if job already exists
            existing = self.supabase.table('job_postings')\
                .select('id')\
                .eq('job_id', job_id)\
                .execute()

            if existing.data:
                # Update existing job posting
                job_pk_id = existing.data[0]['id']
                result = self.supabase.table('job_postings')\
                    .update(extracted_fields)\
                    .eq('id', job_pk_id)\
                    .execute()

                logger.info(f"✓ Updated job posting: {job_id}")
            else:
                # Insert new job posting
                extracted_fields['status'] = 'active'  # Default status
                result = self.supabase.table('job_postings')\
                    .insert(extracted_fields)\
                    .execute()

                logger.info(f"✓ Created new job posting: {job_id}")

            return True

        except Exception as e:
            logger.error(f"Error inserting job posting: {str(e)}", exc_info=True)
            return False

    def get_job_posting(self, job_id: str) -> Optional[Dict]:
        """Retrieve a job posting by job_id"""
        try:
            result = self.supabase.table('job_postings')\
                .select('*')\
                .eq('job_id', job_id)\
                .execute()

            if result.data:
                return result.data[0]
            else:
                logger.warning(f"No job posting found with ID: {job_id}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving job posting: {str(e)}")
            return None

    def get_active_jobs(self, limit: int = 100) -> list:
        """Retrieve all active job postings"""
        try:
            result = self.supabase.table('job_postings')\
                .select('*')\
                .eq('status', 'active')\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()

            logger.info(f"Retrieved {len(result.data)} active job postings")
            return result.data

        except Exception as e:
            logger.error(f"Error retrieving active jobs: {str(e)}")
            return []

    def update_job_status(self, job_id: str, status: str) -> bool:
        """
        Update job status (active, inactive, filled, closed)

        Args:
            job_id: Job identifier
            status: New status (active, inactive, filled, closed)

        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.supabase.table('job_postings')\
                .update({'status': status})\
                .eq('job_id', job_id)\
                .execute()

            logger.info(f"Updated job {job_id} status to: {status}")
            return True

        except Exception as e:
            logger.error(f"Error updating job status: {str(e)}")
            return False

    def insert_jobs_from_file(self, json_file_path: str):
        """
        Insert multiple job postings from a JSON file

        Args:
            json_file_path: Path to JSON file containing job posting(s)
                           Can be a single job object or array of jobs
        """
        logger.info(f"Loading jobs from {json_file_path}")

        try:
            with open(json_file_path, 'r') as f:
                data = json.load(f)

            # Handle both single job and array of jobs
            if isinstance(data, dict):
                jobs = [data]
            elif isinstance(data, list):
                jobs = data
            else:
                logger.error(f"Unexpected JSON structure: {type(data)}")
                return

            total = len(jobs)
            logger.info(f"Found {total} job posting(s) to process")

            successful = 0
            failed = 0

            for i, job_data in enumerate(jobs, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing job {i}/{total}")
                logger.info(f"{'='*60}")

                success = self.insert_job_posting(job_data)

                if success:
                    successful += 1
                else:
                    failed += 1

            # Final summary
            logger.info(f"\n{'='*60}")
            logger.info("JOB POSTING INSERTION COMPLETE")
            logger.info(f"{'='*60}")
            logger.info(f"Total jobs: {total}")
            logger.info(f"Successful: {successful}")
            logger.info(f"Failed: {failed}")

        except Exception as e:
            logger.error(f"Error processing JSON file: {str(e)}")


def main():
    """Main entry point"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python insert_job_posting.py <path_to_job_data.json>")
        print("\nExample:")
        print("  python insert_job_posting.py job_posting.json")
        sys.exit(1)

    json_file_path = sys.argv[1]

    if not os.path.exists(json_file_path):
        print(f"Error: File not found: {json_file_path}")
        sys.exit(1)

    manager = JobPostingManager()
    manager.insert_jobs_from_file(json_file_path)


if __name__ == "__main__":
    main()
