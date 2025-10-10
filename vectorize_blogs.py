import os
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
import tiktoken
from openai import OpenAI
import time

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vectorize.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class BlogVectorizer:
    """Vectorize blog posts using OpenAI embeddings and store in Supabase"""

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
        self.chunk_size = 800  # tokens
        self.chunk_overlap = 100  # tokens
        self.batch_size = 100  # embeddings per batch

        # Initialize tokenizer for the embedding model
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))

    def chunk_text(self, text: str, title: str) -> List[Dict]:
        """
        Split text into chunks with overlap, prepending title to each chunk

        Returns list of dicts with 'text' and 'token_count'
        """
        # Prepend title to content for context
        full_text = f"{title}\n\n{text}"

        tokens = self.tokenizer.encode(full_text)
        chunks = []

        start = 0
        chunk_index = 0

        while start < len(tokens):
            # Get chunk of tokens
            end = start + self.chunk_size
            chunk_tokens = tokens[start:end]

            # Decode back to text
            chunk_text = self.tokenizer.decode(chunk_tokens)

            chunks.append({
                'text': chunk_text,
                'token_count': len(chunk_tokens),
                'chunk_index': chunk_index
            })

            chunk_index += 1

            # Move start position with overlap
            start = end - self.chunk_overlap

            # Break if we've reached the end
            if end >= len(tokens):
                break

        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

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

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in a single API call"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {str(e)}")
            raise

    def fetch_blog_posts(self, limit: Optional[int] = None) -> List[Dict]:
        """Fetch blog posts from Supabase"""
        try:
            query = self.supabase.table('blog_posts').select('id, url, title, content')

            if limit:
                query = query.limit(limit)

            response = query.execute()

            logger.info(f"Fetched {len(response.data)} blog posts from Supabase")
            return response.data
        except Exception as e:
            logger.error(f"Error fetching blog posts: {str(e)}")
            raise

    def check_existing_chunks(self, blog_post_id: int) -> bool:
        """Check if blog post already has chunks"""
        try:
            response = self.supabase.table('blog_chunks')\
                .select('id')\
                .eq('blog_post_id', blog_post_id)\
                .limit(1)\
                .execute()

            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking existing chunks: {str(e)}")
            return False

    def save_chunks_to_supabase(self, chunks_data: List[Dict]) -> bool:
        """Save chunks with embeddings to Supabase"""
        try:
            # Supabase insert with batch
            response = self.supabase.table('blog_chunks').insert(chunks_data).execute()

            logger.info(f"Saved {len(chunks_data)} chunks to Supabase")
            return True
        except Exception as e:
            logger.error(f"Error saving chunks to Supabase: {str(e)}")
            return False

    def vectorize_blog_post(self, blog_post: Dict, skip_existing: bool = True) -> int:
        """
        Vectorize a single blog post

        Returns number of chunks created
        """
        blog_id = blog_post['id']
        title = blog_post.get('title', 'Untitled')
        content = blog_post.get('content', '')

        # Skip if already processed
        if skip_existing and self.check_existing_chunks(blog_id):
            logger.info(f"Skipping blog post {blog_id} - already vectorized")
            return 0

        if not content:
            logger.warning(f"Skipping blog post {blog_id} - no content")
            return 0

        logger.info(f"Processing blog post {blog_id}: {title}")

        # Chunk the text
        chunks = self.chunk_text(content, title)

        if not chunks:
            logger.warning(f"No chunks generated for blog post {blog_id}")
            return 0

        # Process chunks in batches for embedding generation
        all_chunks_data = []

        for i in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[i:i + self.batch_size]
            batch_texts = [chunk['text'] for chunk in batch_chunks]

            logger.info(f"Generating embeddings for batch {i // self.batch_size + 1} ({len(batch_texts)} chunks)")

            # Generate embeddings for batch
            embeddings = self.generate_embeddings_batch(batch_texts)

            # Prepare data for insertion
            for chunk, embedding in zip(batch_chunks, embeddings):
                chunk_data = {
                    'blog_post_id': blog_id,
                    'chunk_index': chunk['chunk_index'],
                    'chunk_text': chunk['text'],
                    'token_count': chunk['token_count'],
                    'embedding': embedding
                }
                all_chunks_data.append(chunk_data)

            # Rate limiting - be nice to OpenAI API
            if i + self.batch_size < len(chunks):
                time.sleep(0.5)

        # Save all chunks to Supabase
        if self.save_chunks_to_supabase(all_chunks_data):
            logger.info(f"Successfully vectorized blog post {blog_id} with {len(chunks)} chunks")
            return len(chunks)
        else:
            logger.error(f"Failed to save chunks for blog post {blog_id}")
            return 0

    def vectorize_all_posts(self, limit: Optional[int] = None, skip_existing: bool = True):
        """
        Vectorize all blog posts

        Args:
            limit: Maximum number of posts to process (None for all)
            skip_existing: Skip posts that already have chunks
        """
        logger.info("Starting blog vectorization process...")

        # Fetch blog posts
        blog_posts = self.fetch_blog_posts(limit=limit)

        if not blog_posts:
            logger.error("No blog posts found to vectorize")
            return

        total_posts = len(blog_posts)
        successful = 0
        skipped = 0
        failed = 0
        total_chunks = 0

        for i, blog_post in enumerate(blog_posts, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing post {i}/{total_posts}")
            logger.info(f"{'='*60}")

            try:
                chunks_created = self.vectorize_blog_post(blog_post, skip_existing=skip_existing)

                if chunks_created > 0:
                    successful += 1
                    total_chunks += chunks_created
                else:
                    if skip_existing and self.check_existing_chunks(blog_post['id']):
                        skipped += 1
                    else:
                        failed += 1

            except Exception as e:
                logger.error(f"Error processing blog post {blog_post['id']}: {str(e)}")
                failed += 1
                continue

            # Progress update every 10 posts
            if i % 10 == 0:
                logger.info(f"\nProgress: {i}/{total_posts} posts processed")
                logger.info(f"Successful: {successful}, Skipped: {skipped}, Failed: {failed}")
                logger.info(f"Total chunks created: {total_chunks}")

        # Final summary
        logger.info(f"\n{'='*60}")
        logger.info("VECTORIZATION COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total posts processed: {total_posts}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped: {skipped}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total chunks created: {total_chunks}")
        logger.info(f"Average chunks per post: {total_chunks / successful if successful > 0 else 0:.1f}")


def main():
    """Main entry point"""
    vectorizer = BlogVectorizer()

    # Vectorize all blog posts
    # Set limit=10 to test with just 10 posts first
    # Set skip_existing=False to re-process existing posts
    vectorizer.vectorize_all_posts(limit=None, skip_existing=True)


if __name__ == "__main__":
    main()
