import os
import json
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
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

        # Initialize OpenAI client
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in .env file")

        self.openai_client = OpenAI(api_key=openai_api_key)
        logger.info("OpenAI client initialized")

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

    def select_best_blogs_with_llm(
        self,
        blogs: List[Dict],
        candidate: Dict,
        num_to_select: int = 3
    ) -> List[Dict]:
        """
        Use LLM to select the best N blogs from a list of candidates

        Args:
            blogs: List of blog posts with similarity scores
            candidate: Candidate profile information
            num_to_select: Number of blogs to select (default: 3)

        Returns:
            List of selected blog posts
        """
        if not blogs or len(blogs) <= num_to_select:
            return blogs

        try:
            # Format blog summaries for LLM
            blog_summaries = []
            for idx, blog in enumerate(blogs, 1):
                summary = f"""{idx}. "{blog['blog_title']}"
   Author: {blog.get('blog_author', 'Unknown')}
   Published: {blog.get('blog_published_date', 'Unknown date')}
   Similarity Score: {round(blog.get('max_similarity', 0) * 100, 1)}%
   Excerpt: {blog.get('best_matching_chunk', 'No excerpt')[:200]}..."""
                blog_summaries.append(summary)

            blogs_text = '\n\n'.join(blog_summaries)

            # Create candidate context
            candidate_context = f"""Candidate Profile:
- Name: {candidate.get('full_name', 'Unknown')}
- Current Title: {candidate.get('current_title', 'Unknown')}
- About: {candidate.get('about_me', 'No information available')[:300]}"""

            selection_prompt = f"""You are helping select the most relevant blog posts for a recruiting nurture email campaign.

{candidate_context}

Available Blog Posts (Top {len(blogs)} by embedding similarity):
{blogs_text}

Select the {num_to_select} MOST RELEVANT blog posts for this candidate. Consider:
1. Relevance to their current role and experience
2. Recency (prefer newer content when equally relevant)
3. Topic diversity (don't pick {num_to_select} similar posts)
4. Engaging titles and compelling content
5. Professional development value for their career stage

Respond with ONLY a JSON array of the blog post numbers (1-{len(blogs)}), like: [1, 5, 8]"""

            completion = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": selection_prompt}],
                temperature=0.3,
                max_tokens=50
            )

            result = completion.choices[0].message.content.strip()
            logger.info(f"LLM blog selection response: {result}")

            # Remove markdown code blocks if present
            clean_result = result
            if result.startswith('```'):
                # Remove ```json or ``` prefix and ``` suffix
                clean_result = result.replace('```json', '').replace('```', '').strip()

            # Parse the response
            selected_indices = json.loads(clean_result)
            selected_blogs = [blogs[idx - 1] for idx in selected_indices if 0 < idx <= len(blogs)]

            logger.info(f"LLM selected {len(selected_blogs)} blogs: {[b['blog_title'] for b in selected_blogs]}")

            return selected_blogs if selected_blogs else blogs[:num_to_select]

        except Exception as e:
            logger.error(f"LLM blog selection error: {str(e)}")
            # Fallback to first N blogs if LLM fails
            return blogs[:num_to_select]

    def find_blogs_for_candidate_hybrid(
        self,
        candidate_id: str,
        match_threshold: float = 0.35,
        top_n_embeddings: int = 10,
        final_n_llm: int = 3
    ) -> List[Dict]:
        """
        Hybrid approach: Use embeddings to get top N, then LLM to select final few

        Args:
            candidate_id: External candidate ID
            match_threshold: Minimum similarity score (0-1)
            top_n_embeddings: Number of blogs to get from embedding search
            final_n_llm: Number of blogs to select with LLM from top_n

        Returns:
            List of final selected blog posts
        """
        try:
            # Step 1: Get top N blogs using embeddings
            logger.info(f"Step 1: Getting top {top_n_embeddings} blogs using embeddings...")
            top_blogs = self.find_blogs_for_candidate(
                candidate_id,
                match_threshold=match_threshold,
                match_count=top_n_embeddings,
                deduplicate=True
            )

            if not top_blogs:
                logger.warning(f"No blogs found for candidate {candidate_id}")
                return []

            logger.info(f"Found {len(top_blogs)} blogs from embedding search")

            # Step 2: Use LLM to select best N from top blogs
            logger.info(f"Step 2: Using LLM to select best {final_n_llm} blogs...")
            candidate = self.get_candidate_by_id(candidate_id)

            if not candidate:
                logger.warning("Candidate not found, returning embedding results")
                return top_blogs[:final_n_llm]

            selected_blogs = self.select_best_blogs_with_llm(
                top_blogs,
                candidate,
                num_to_select=final_n_llm
            )

            logger.info(f"Hybrid selection complete: {len(selected_blogs)} blogs selected")
            return selected_blogs

        except Exception as e:
            logger.error(f"Hybrid blog selection error: {str(e)}")
            return []

    def generate_email_recommendations_hybrid(
        self,
        candidate_id: str,
        num_articles: int = 3,
        top_n_embeddings: int = 10,
        match_threshold: float = 0.35
    ) -> Dict:
        """
        Generate personalized blog recommendations using hybrid approach (embeddings + LLM)

        Args:
            candidate_id: External candidate ID
            num_articles: Final number of articles to recommend
            top_n_embeddings: Number of articles to get from embedding search
            match_threshold: Minimum similarity score

        Returns:
            Dict with candidate info and recommended articles
        """
        try:
            # Get candidate info
            candidate = self.get_candidate_by_id(candidate_id)
            if not candidate:
                return None

            # Find matching blogs using hybrid approach
            blogs = self.find_blogs_for_candidate_hybrid(
                candidate_id,
                match_threshold=match_threshold,
                top_n_embeddings=top_n_embeddings,
                final_n_llm=num_articles
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
                ],
                'selection_method': 'hybrid (embeddings + LLM)'
            }

            return recommendations

        except Exception as e:
            logger.error(f"Error generating hybrid recommendations: {str(e)}")
            return None

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
        match_threshold: float = 0.35,
        use_hybrid: bool = False,
        top_n_embeddings: int = 10
    ):
        """
        Generate recommendations for all candidates with embeddings

        Args:
            output_file: Path to save recommendations JSON
            num_articles: Number of articles per candidate
            match_threshold: Minimum similarity score
            use_hybrid: If True, use hybrid (embeddings + LLM) approach
            top_n_embeddings: Number of blogs to get from embeddings (only for hybrid)
        """
        method = "hybrid (embeddings + LLM)" if use_hybrid else "embeddings only"
        logger.info(f"Generating recommendations for all candidates using {method}...")

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
                if use_hybrid:
                    recommendations = self.generate_email_recommendations_hybrid(
                        candidate['candidate_id'],
                        num_articles=num_articles,
                        top_n_embeddings=top_n_embeddings,
                        match_threshold=match_threshold
                    )
                else:
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

    def print_recommendations(
        self,
        candidate_id: str,
        num_articles: int = 5,
        use_hybrid: bool = False,
        top_n_embeddings: int = 10
    ):
        """
        Print formatted recommendations for a candidate (for testing/demo)

        Args:
            candidate_id: External candidate ID
            num_articles: Number of articles to show
            use_hybrid: If True, use hybrid (embeddings + LLM) approach
            top_n_embeddings: Number of blogs to get from embeddings (only for hybrid)
        """
        if use_hybrid:
            recommendations = self.generate_email_recommendations_hybrid(
                candidate_id,
                num_articles=num_articles,
                top_n_embeddings=top_n_embeddings
            )
        else:
            recommendations = self.generate_email_recommendations(
                candidate_id,
                num_articles=num_articles
            )

        if not recommendations:
            print(f"No recommendations found for candidate {candidate_id}")
            return

        candidate = recommendations['candidate']
        articles = recommendations['recommended_articles']
        method = recommendations.get('selection_method', 'embeddings only')

        print(f"\n{'='*80}")
        print(f"PERSONALIZED BLOG RECOMMENDATIONS")
        print(f"{'='*80}")
        print(f"Candidate: {candidate['name']}")
        if candidate['current_title']:
            print(f"Role: {candidate['current_title']}")
        print(f"Selection Method: {method}")
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
        print("     python match_candidates_to_blogs.py <candidate_id> [num_articles] [--hybrid]")
        print("\n  2. Generate recommendations for all candidates:")
        print("     python match_candidates_to_blogs.py --all [output_file] [--hybrid]")
        print("\n  3. Test hybrid selection for one candidate:")
        print("     python match_candidates_to_blogs.py <candidate_id> --hybrid")
        print("\nExamples:")
        print("  python match_candidates_to_blogs.py 68d193fecb73815f93cc0e45")
        print("  python match_candidates_to_blogs.py 68d193fecb73815f93cc0e45 5 --hybrid")
        print("  python match_candidates_to_blogs.py --all candidate_recommendations.json --hybrid")
        sys.exit(1)

    # Check for hybrid flag
    use_hybrid = '--hybrid' in sys.argv

    if sys.argv[1] == '--all':
        # Batch process all candidates
        output_file = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != '--hybrid' else 'candidate_recommendations.json'
        matcher.batch_generate_recommendations(output_file=output_file, use_hybrid=use_hybrid)
    else:
        # Process single candidate
        candidate_id = sys.argv[1]
        num_articles = 5

        # Parse num_articles if provided and not --hybrid
        if len(sys.argv) > 2 and sys.argv[2] != '--hybrid':
            try:
                num_articles = int(sys.argv[2])
            except ValueError:
                pass

        matcher.print_recommendations(candidate_id, num_articles=num_articles, use_hybrid=use_hybrid)


if __name__ == "__main__":
    main()
