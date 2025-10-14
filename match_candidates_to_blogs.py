import os
import json
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

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


class CandidateBlogMatcher:
    """Match candidates to relevant blog posts using vector similarity"""

    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized")

    def get_candidate_by_id(self, candidate_id: str) -> Optional[Dict]:
        """Fetch candidate profile and embedding by candidate ID"""
        try:
            result = self.supabase.rpc(
                'get_candidate_profile_with_embedding',
                {'candidate_external_id': candidate_id}
            ).execute()

            if result.data:
                return result.data[0]
            else:
                logger.warning(f"No candidate found with ID: {candidate_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching candidate: {str(e)}")
            return None

    def get_all_candidates_with_embeddings(self) -> List[Dict]:
        """Fetch all candidates that have embeddings"""
        try:
            result = self.supabase.table('candidate_profiles')\
                .select('id, candidate_id, full_name, email, current_title, about_me')\
                .execute()

            # Filter to only candidates with embeddings
            candidates_with_embeddings = []
            for candidate in result.data:
                # Check if has embedding
                embedding_check = self.supabase.table('candidate_embeddings')\
                    .select('id')\
                    .eq('candidate_profile_id', candidate['id'])\
                    .execute()

                if embedding_check.data:
                    candidates_with_embeddings.append(candidate)

            logger.info(f"Found {len(candidates_with_embeddings)} candidates with embeddings")
            return candidates_with_embeddings

        except Exception as e:
            logger.error(f"Error fetching candidates: {str(e)}")
            return []

    def find_blogs_for_candidate(
        self,
        candidate_id: str,
        match_threshold: float = 0.35,
        match_count: int = 5,
        deduplicate: bool = True
    ) -> List[Dict]:
        """
        Find relevant blog posts for a candidate using three-embedding search

        Args:
            candidate_id: External candidate ID
            match_threshold: Minimum similarity score (0-1)
            match_count: Number of blog posts to return
            deduplicate: If True, return unique blog posts (best matching chunk per post)

        Returns:
            List of matching blog posts with similarity scores
        """
        try:
            # Get candidate profile and embeddings
            candidate = self.get_candidate_by_id(candidate_id)

            if not candidate:
                logger.error(f"Candidate {candidate_id} not found")
                return []

            # Get professional summary embedding (prioritize new format)
            prof_embedding = candidate.get('professional_summary_embedding')

            # Fallback to legacy embedding if new format not available yet
            if not prof_embedding and candidate.get('embedding'):
                logger.warning(f"Using legacy embedding field for candidate {candidate_id}")
                prof_embedding = candidate['embedding']

            if not prof_embedding:
                logger.error(f"Candidate {candidate_id} has no embeddings")
                return []

            # Always use single-embedding search (simple and reliable)
            if deduplicate:
                function_name = 'search_top_blogs_for_candidate'
            else:
                function_name = 'search_blogs_for_candidate'

            rpc_params = {
                'candidate_embedding': prof_embedding,
                'match_threshold': match_threshold,
                'match_count': match_count
            }

            logger.info(f"Searching blogs using professional summary embedding")

            result = self.supabase.rpc(function_name, rpc_params).execute()

            if result.data:
                logger.info(f"Found {len(result.data)} matching blogs for candidate {candidate_id}")
                return result.data
            else:
                logger.info(f"No matching blogs found for candidate {candidate_id}")
                return []

        except Exception as e:
            logger.error(f"Error finding blogs for candidate: {str(e)}")
            return []

    def generate_email_recommendations(
        self,
        candidate_id: str,
        num_articles: int = 3,
        match_threshold: float = 0.35
    ) -> Dict:
        """
        Generate personalized blog recommendations for email nurturing

        Args:
            candidate_id: External candidate ID
            num_articles: Number of articles to recommend
            match_threshold: Minimum similarity score

        Returns:
            Dict with candidate info and recommended articles
        """
        try:
            # Get candidate info
            candidate = self.get_candidate_by_id(candidate_id)
            if not candidate:
                return None

            # Find matching blogs
            blogs = self.find_blogs_for_candidate(
                candidate_id,
                match_threshold=match_threshold,
                match_count=num_articles,
                deduplicate=True
            )

            # Format for email
            recommendations = {
                'candidate': {
                    'name': candidate.get('full_name', 'there'),
                    'email': candidate.get('email', ''),
                    'current_title': candidate.get('current_title', ''),
                },
                'recommended_articles': [
                    {
                        'title': blog['blog_title'],
                        'url': blog['blog_url'],
                        'author': blog.get('blog_author', ''),
                        'published_date': blog.get('blog_published_date', ''),
                        'relevance_score': round(blog.get('max_similarity', 0) * 100, 1),
                        'excerpt': blog.get('best_matching_chunk', '')[:200] + '...'
                    }
                    for blog in blogs
                ]
            }

            return recommendations

        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return None

    def batch_generate_recommendations(
        self,
        output_file: str = 'candidate_recommendations.json',
        num_articles: int = 3,
        match_threshold: float = 0.35
    ):
        """
        Generate recommendations for all candidates with embeddings

        Args:
            output_file: Path to save recommendations JSON
            num_articles: Number of articles per candidate
            match_threshold: Minimum similarity score
        """
        logger.info("Generating recommendations for all candidates...")

        # Get all candidates
        candidates = self.get_all_candidates_with_embeddings()

        if not candidates:
            logger.error("No candidates found with embeddings")
            return

        all_recommendations = []

        for i, candidate in enumerate(candidates, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing candidate {i}/{len(candidates)}: {candidate['full_name']}")
            logger.info(f"{'='*60}")

            try:
                recommendations = self.generate_email_recommendations(
                    candidate['candidate_id'],
                    num_articles=num_articles,
                    match_threshold=match_threshold
                )

                if recommendations and recommendations['recommended_articles']:
                    all_recommendations.append(recommendations)
                    logger.info(f"Generated {len(recommendations['recommended_articles'])} recommendations")
                else:
                    logger.warning(f"No recommendations found for {candidate['full_name']}")

            except Exception as e:
                logger.error(f"Error processing candidate {candidate['candidate_id']}: {str(e)}")
                continue

        # Save to file
        try:
            with open(output_file, 'w') as f:
                json.dump(all_recommendations, f, indent=2)

            logger.info(f"\n{'='*60}")
            logger.info("RECOMMENDATIONS COMPLETE")
            logger.info(f"{'='*60}")
            logger.info(f"Total candidates processed: {len(candidates)}")
            logger.info(f"Candidates with recommendations: {len(all_recommendations)}")
            logger.info(f"Results saved to: {output_file}")

        except Exception as e:
            logger.error(f"Error saving recommendations: {str(e)}")

    def print_recommendations(self, candidate_id: str, num_articles: int = 5):
        """
        Print formatted recommendations for a candidate (for testing/demo)

        Args:
            candidate_id: External candidate ID
            num_articles: Number of articles to show
        """
        recommendations = self.generate_email_recommendations(
            candidate_id,
            num_articles=num_articles
        )

        if not recommendations:
            print(f"No recommendations found for candidate {candidate_id}")
            return

        candidate = recommendations['candidate']
        articles = recommendations['recommended_articles']

        print(f"\n{'='*80}")
        print(f"PERSONALIZED BLOG RECOMMENDATIONS")
        print(f"{'='*80}")
        print(f"Candidate: {candidate['name']}")
        if candidate['current_title']:
            print(f"Role: {candidate['current_title']}")
        print(f"\nTop {len(articles)} Recommended Articles:")
        print(f"{'='*80}\n")

        for i, article in enumerate(articles, 1):
            print(f"{i}. {article['title']}")
            print(f"   Relevance: {article['relevance_score']}%")
            print(f"   URL: {article['url']}")
            if article['author']:
                print(f"   Author: {article['author']}")
            if article['published_date']:
                print(f"   Published: {article['published_date']}")
            print(f"   Excerpt: {article['excerpt']}")
            print()

        print(f"{'='*80}\n")


def main():
    """Main entry point"""
    import sys

    matcher = CandidateBlogMatcher()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  1. Generate recommendations for one candidate:")
        print("     python match_candidates_to_blogs.py <candidate_id>")
        print("\n  2. Generate recommendations for all candidates:")
        print("     python match_candidates_to_blogs.py --all")
        print("\nExamples:")
        print("  python match_candidates_to_blogs.py 68d193fecb73815f93cc0e45")
        print("  python match_candidates_to_blogs.py --all")
        sys.exit(1)

    if sys.argv[1] == '--all':
        # Batch process all candidates
        output_file = sys.argv[2] if len(sys.argv) > 2 else 'candidate_recommendations.json'
        matcher.batch_generate_recommendations(output_file=output_file)
    else:
        # Process single candidate
        candidate_id = sys.argv[1]
        num_articles = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        matcher.print_recommendations(candidate_id, num_articles=num_articles)


if __name__ == "__main__":
    main()
