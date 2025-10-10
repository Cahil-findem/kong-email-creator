import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import tiktoken
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging (use StreamHandler only for Vercel compatibility)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class CandidateVectorizer:
    """Vectorize candidate profiles using OpenAI embeddings and store in Supabase"""

    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized")

        # Initialize OpenAI client
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in .env file")

        self.openai_client = OpenAI(api_key=openai_api_key)
        logger.info("OpenAI client initialized")

        # Configuration
        self.embedding_model = "text-embedding-3-small"
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))

    def extract_candidate_info(self, candidate_data: Dict) -> Dict:
        """
        Extract relevant information from candidate JSON structure

        Returns a cleaned dict with key candidate information
        """
        # Get candidate basic info
        candidate = candidate_data.get('candidate', {})

        # Extract basic details
        full_name = candidate.get('full_name', '')
        email = candidate.get('emails', [''])[0] if candidate.get('emails') else ''
        location = candidate.get('location', {})
        location_str = ''
        if isinstance(location, dict):
            parts = [location.get('city', ''), location.get('state', ''), location.get('country', '')]
            location_str = ', '.join([p for p in parts if p])
        else:
            location_str = candidate.get('location_raw', '')

        linkedin_url = candidate.get('linkedin', '')
        about_me = candidate.get('about_me', '')

        # Extract skills
        skills = candidate_data.get('skills', [])

        # Extract work experience
        workexp = candidate_data.get('workexp', [])

        # Get current/most recent job
        current_title = ''
        current_company = ''
        years_of_experience = 0

        if workexp:
            # Sort by start date (most recent first)
            sorted_exp = sorted(
                [w for w in workexp if w.get('duration', {}).get('start_date')],
                key=lambda x: x.get('duration', {}).get('start_date', ''),
                reverse=True
            )

            if sorted_exp:
                most_recent = sorted_exp[0]
                current_company = most_recent.get('company', {}).get('name', '')
                projects = most_recent.get('projects', [])
                if projects:
                    current_title = projects[0].get('role_and_group', {}).get('title', '')

                # Calculate years of experience
                years_of_experience = len([w for w in workexp if w.get('duration', {}).get('start_date')])

        # Extract education
        education = candidate_data.get('education', [])

        return {
            'candidate_id': candidate_data.get('ref', ''),
            'full_name': full_name,
            'email': email,
            'location': location_str,
            'linkedin_url': linkedin_url,
            'current_title': current_title,
            'current_company': current_company,
            'years_of_experience': years_of_experience,
            'about_me': about_me,
            'skills': skills,
            'work_experience': workexp,
            'education': education,
            'raw_profile': candidate_data
        }

    def format_work_experience(self, workexp: List[Dict]) -> str:
        """Format work experience into readable text"""
        if not workexp:
            return "No work experience listed"

        formatted = []
        for exp in workexp[:5]:  # Limit to top 5 most relevant/recent
            company_name = exp.get('company', {}).get('name', 'Unknown Company')
            location = exp.get('company', {}).get('location', '')

            projects = exp.get('projects', [])
            title = projects[0].get('role_and_group', {}).get('title', 'Unknown Role') if projects else 'Unknown Role'
            description = projects[0].get('description', '') if projects else ''

            duration = exp.get('duration', {})
            start_date = duration.get('start_date', '')
            end_date = duration.get('end_date', 'Present')

            # Format dates
            if start_date:
                try:
                    start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).strftime('%B %Y')
                except:
                    start = start_date[:7] if len(start_date) >= 7 else start_date
            else:
                start = 'Unknown'

            if end_date and end_date != 'Present':
                try:
                    end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).strftime('%B %Y')
                except:
                    end = end_date[:7] if len(end_date) >= 7 else end_date
            else:
                end = 'Present'

            exp_text = f"- {company_name}"
            if location:
                exp_text += f" ({location})"
            exp_text += f"\n  {title}"
            exp_text += f"\n  {start} - {end}"

            if description:
                # Clean up description
                desc_clean = description.replace('\n', ' ').replace('  ', ' ').strip()
                if len(desc_clean) > 300:
                    desc_clean = desc_clean[:297] + '...'
                exp_text += f"\n  {desc_clean}"

            formatted.append(exp_text)

        return '\n\n'.join(formatted)

    def format_education(self, education: List[Dict]) -> str:
        """Format education into readable text"""
        if not education:
            return "No education listed"

        formatted = []
        for edu in education:
            school = edu.get('school_info', {}).get('name', 'Unknown School')
            details = edu.get('education_details', {})
            degree = details.get('degree', [])
            degree_str = degree[0] if degree else 'Degree'
            major = details.get('major', [])
            major_str = major[0] if major else ''

            duration = edu.get('duration', {})
            start_date = duration.get('start_date', '')
            end_date = duration.get('end_date', '')

            # Format dates
            years = ''
            if start_date and end_date:
                try:
                    start_year = datetime.fromisoformat(start_date.replace('Z', '+00:00')).year
                    end_year = datetime.fromisoformat(end_date.replace('Z', '+00:00')).year
                    years = f"{start_year} - {end_year}"
                except:
                    pass

            edu_text = f"- {degree_str}"
            if major_str:
                edu_text += f" in {major_str}"
            edu_text += f" from {school}"
            if years:
                edu_text += f" ({years})"

            formatted.append(edu_text)

        return '\n'.join(formatted)

    def format_profile_for_embedding(self, candidate_info: Dict) -> str:
        """
        Format candidate profile into text optimized for embedding

        This creates a comprehensive profile that captures:
        - Professional identity
        - Skills and expertise
        - Work experience
        - Educational background
        """
        parts = []

        # Header with name and location
        if candidate_info['full_name']:
            parts.append(f"Candidate: {candidate_info['full_name']}")

        if candidate_info['location']:
            parts.append(f"Location: {candidate_info['location']}")

        if candidate_info['current_title']:
            title_part = f"Current Role: {candidate_info['current_title']}"
            if candidate_info['current_company']:
                title_part += f" at {candidate_info['current_company']}"
            parts.append(title_part)

        parts.append('')  # Blank line

        # Professional summary
        if candidate_info['about_me']:
            parts.append("Professional Summary:")
            parts.append(candidate_info['about_me'])
            parts.append('')

        # Skills
        if candidate_info['skills']:
            skills_str = ', '.join(candidate_info['skills'][:30])  # Limit to top 30 skills
            parts.append("Skills and Expertise:")
            parts.append(skills_str)
            parts.append('')

        # Work Experience
        if candidate_info['work_experience']:
            parts.append("Work Experience:")
            parts.append(self.format_work_experience(candidate_info['work_experience']))
            parts.append('')

        # Education
        if candidate_info['education']:
            parts.append("Education:")
            parts.append(self.format_education(candidate_info['education']))

        profile_text = '\n'.join(parts)
        return profile_text

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    def save_candidate_profile(self, candidate_info: Dict) -> Optional[int]:
        """
        Save candidate profile to Supabase

        Returns the profile ID if successful, None otherwise
        """
        try:
            # Check if candidate already exists
            existing = self.supabase.table('candidate_profiles')\
                .select('id')\
                .eq('candidate_id', candidate_info['candidate_id'])\
                .execute()

            if existing.data:
                # Update existing profile
                profile_id = existing.data[0]['id']
                self.supabase.table('candidate_profiles')\
                    .update({
                        'full_name': candidate_info['full_name'],
                        'email': candidate_info['email'],
                        'location': candidate_info['location'],
                        'linkedin_url': candidate_info['linkedin_url'],
                        'current_title': candidate_info['current_title'],
                        'current_company': candidate_info['current_company'],
                        'years_of_experience': candidate_info['years_of_experience'],
                        'about_me': candidate_info['about_me'],
                        'skills': json.dumps(candidate_info['skills']),
                        'work_experience': json.dumps(candidate_info['work_experience']),
                        'education': json.dumps(candidate_info['education']),
                        'raw_profile': json.dumps(candidate_info['raw_profile']),
                        'updated_at': 'now()'
                    })\
                    .eq('id', profile_id)\
                    .execute()

                logger.info(f"Updated existing candidate profile: {candidate_info['candidate_id']}")
            else:
                # Insert new profile
                result = self.supabase.table('candidate_profiles').insert({
                    'candidate_id': candidate_info['candidate_id'],
                    'full_name': candidate_info['full_name'],
                    'email': candidate_info['email'],
                    'location': candidate_info['location'],
                    'linkedin_url': candidate_info['linkedin_url'],
                    'current_title': candidate_info['current_title'],
                    'current_company': candidate_info['current_company'],
                    'years_of_experience': candidate_info['years_of_experience'],
                    'about_me': candidate_info['about_me'],
                    'skills': json.dumps(candidate_info['skills']),
                    'work_experience': json.dumps(candidate_info['work_experience']),
                    'education': json.dumps(candidate_info['education']),
                    'raw_profile': json.dumps(candidate_info['raw_profile'])
                }).execute()

                profile_id = result.data[0]['id']
                logger.info(f"Created new candidate profile: {candidate_info['candidate_id']}")

            return profile_id

        except Exception as e:
            logger.error(f"Error saving candidate profile: {str(e)}")
            return None

    def save_candidate_embedding(self, profile_id: int, embedding_text: str, embedding: List[float]) -> bool:
        """Save candidate embedding to Supabase"""
        try:
            token_count = self.count_tokens(embedding_text)

            # Check if embedding already exists
            existing = self.supabase.table('candidate_embeddings')\
                .select('id')\
                .eq('candidate_profile_id', profile_id)\
                .execute()

            if existing.data:
                # Update existing embedding
                self.supabase.table('candidate_embeddings')\
                    .update({
                        'embedding_text': embedding_text,
                        'embedding': embedding,
                        'token_count': token_count
                    })\
                    .eq('candidate_profile_id', profile_id)\
                    .execute()
                logger.info(f"Updated embedding for profile {profile_id}")
            else:
                # Insert new embedding
                self.supabase.table('candidate_embeddings').insert({
                    'candidate_profile_id': profile_id,
                    'embedding_text': embedding_text,
                    'embedding': embedding,
                    'token_count': token_count
                }).execute()
                logger.info(f"Created new embedding for profile {profile_id}")

            return True

        except Exception as e:
            logger.error(f"Error saving candidate embedding: {str(e)}")
            return False

    def vectorize_candidate(self, candidate_data: Dict, skip_existing: bool = True) -> bool:
        """
        Vectorize a single candidate profile

        Args:
            candidate_data: Raw candidate JSON data
            skip_existing: Skip if candidate already has an embedding

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract candidate information
            candidate_info = self.extract_candidate_info(candidate_data)
            candidate_id = candidate_info['candidate_id']

            if not candidate_id:
                logger.warning("Candidate missing ID, skipping")
                return False

            logger.info(f"Processing candidate: {candidate_info['full_name']} ({candidate_id})")

            # Save profile to database
            profile_id = self.save_candidate_profile(candidate_info)
            if not profile_id:
                logger.error(f"Failed to save profile for candidate {candidate_id}")
                return False

            # Check if embedding already exists
            if skip_existing:
                existing = self.supabase.table('candidate_embeddings')\
                    .select('id')\
                    .eq('candidate_profile_id', profile_id)\
                    .execute()

                if existing.data:
                    logger.info(f"Skipping candidate {candidate_id} - already has embedding")
                    return True

            # Format profile for embedding
            profile_text = self.format_profile_for_embedding(candidate_info)
            logger.info(f"Formatted profile ({self.count_tokens(profile_text)} tokens)")

            # Generate embedding
            logger.info("Generating embedding...")
            embedding = self.generate_embedding(profile_text)

            # Save embedding
            success = self.save_candidate_embedding(profile_id, profile_text, embedding)

            if success:
                logger.info(f"Successfully vectorized candidate {candidate_id}")
                return True
            else:
                logger.error(f"Failed to save embedding for candidate {candidate_id}")
                return False

        except Exception as e:
            logger.error(f"Error vectorizing candidate: {str(e)}")
            return False

    def vectorize_candidates_from_json(self, json_file_path: str, skip_existing: bool = True):
        """
        Vectorize candidates from a JSON file

        Args:
            json_file_path: Path to JSON file containing candidate data
            skip_existing: Skip candidates that already have embeddings
        """
        logger.info(f"Loading candidates from {json_file_path}")

        try:
            with open(json_file_path, 'r') as f:
                candidates_data = json.load(f)

            # Handle different JSON structures
            if isinstance(candidates_data, dict):
                # If it's a dict with candidate IDs as keys
                candidates = list(candidates_data.values())
            elif isinstance(candidates_data, list):
                # If it's already a list
                candidates = candidates_data
            else:
                logger.error(f"Unexpected JSON structure: {type(candidates_data)}")
                return

            total = len(candidates)
            logger.info(f"Found {total} candidates to process")

            successful = 0
            skipped = 0
            failed = 0

            for i, candidate_data in enumerate(candidates, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing candidate {i}/{total}")
                logger.info(f"{'='*60}")

                success = self.vectorize_candidate(candidate_data, skip_existing=skip_existing)

                if success:
                    successful += 1
                else:
                    failed += 1

            # Final summary
            logger.info(f"\n{'='*60}")
            logger.info("VECTORIZATION COMPLETE")
            logger.info(f"{'='*60}")
            logger.info(f"Total candidates: {total}")
            logger.info(f"Successful: {successful}")
            logger.info(f"Failed: {failed}")

        except Exception as e:
            logger.error(f"Error processing JSON file: {str(e)}")


def main():
    """Main entry point"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python vectorize_candidates.py <path_to_candidates.json>")
        print("\nExample:")
        print("  python vectorize_candidates.py candidates.json")
        sys.exit(1)

    json_file_path = sys.argv[1]

    if not os.path.exists(json_file_path):
        print(f"Error: File not found: {json_file_path}")
        sys.exit(1)

    vectorizer = CandidateVectorizer()
    vectorizer.vectorize_candidates_from_json(json_file_path, skip_existing=True)


if __name__ == "__main__":
    main()
