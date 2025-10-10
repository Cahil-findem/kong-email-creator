# Blog Vectorization Guide

This guide explains how to vectorize your blog content for semantic search using OpenAI embeddings and Supabase pgvector.

## Overview

The vectorization system:
- **Chunks** blog posts into ~800 token pieces with 100 token overlap
- **Embeds** each chunk using OpenAI's `text-embedding-3-small` model (1536 dimensions)
- **Stores** embeddings in Supabase with pgvector for efficient similarity search
- **Includes** both title and content in embeddings for better context

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Add OpenAI API Key

Add your OpenAI API key to `.env`:

```bash
OPENAI_API_KEY=sk-your-actual-api-key-here
```

Get your API key from: https://platform.openai.com/api-keys

### 3. Run Database Schema

Run the `vectorize_schema.sql` in your Supabase SQL Editor:

```sql
-- This will:
-- 1. Enable pgvector extension
-- 2. Create blog_chunks table
-- 3. Create vector similarity index
-- 4. Create semantic search function
```

## Usage

### Vectorize All Blog Posts

```bash
python vectorize_blogs.py
```

This will:
- Fetch all blog posts from Supabase
- Skip posts that are already vectorized
- Chunk content into ~800 token pieces
- Generate embeddings for each chunk
- Save to `blog_chunks` table
- Log progress to `vectorize.log`

**Note:** Processing 734 blog posts will take approximately 30-60 minutes and cost ~$0.50-$1.00 in OpenAI API fees.

### Vectorize Limited Posts (Testing)

To test with just 10 posts first:

```python
# Edit vectorize_blogs.py, change main() to:
vectorizer.vectorize_all_posts(limit=10, skip_existing=True)
```

### Re-process Existing Posts

To re-vectorize posts that already have chunks:

```python
vectorizer.vectorize_all_posts(limit=None, skip_existing=False)
```

## Semantic Search

### Using the Example Script

```bash
python semantic_search_example.py
```

This demonstrates semantic search with example queries.

### Using in Your App

```python
from supabase import create_client
from openai import OpenAI

# Initialize clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Generate query embedding
query = "How do I secure my API?"
response = openai_client.embeddings.create(
    model="text-embedding-3-small",
    input=query
)
query_embedding = response.data[0].embedding

# Search for similar chunks
results = supabase.rpc(
    'search_blog_chunks',
    {
        'query_embedding': query_embedding,
        'match_threshold': 0.7,  # Minimum similarity (0-1)
        'match_count': 10         # Number of results
    }
).execute()

# Process results
for result in results.data:
    print(f"Title: {result['blog_title']}")
    print(f"URL: {result['blog_url']}")
    print(f"Similarity: {result['similarity']}")
    print(f"Excerpt: {result['chunk_text'][:200]}...")
```

## Database Schema

### blog_chunks Table

| Column | Type | Description |
|--------|------|-------------|
| id | bigint | Primary key |
| blog_post_id | bigint | Reference to blog_posts.id |
| chunk_index | int | Chunk number within the blog post |
| chunk_text | text | The chunked content (includes title) |
| token_count | int | Number of tokens in this chunk |
| embedding | vector(1536) | OpenAI embedding vector |
| created_at | timestamp | When chunk was created |

### Search Function

`search_blog_chunks(query_embedding, match_threshold, match_count)`

Returns:
- `chunk_id`: ID of the matching chunk
- `blog_post_id`: ID of the source blog post
- `chunk_text`: The chunk content
- `similarity`: Cosine similarity score (0-1)
- `blog_title`: Title of the blog post
- `blog_url`: URL of the blog post
- `blog_author`: Author name
- `blog_published_date`: Publication date

## Configuration

In `vectorize_blogs.py`:

```python
self.embedding_model = "text-embedding-3-small"  # OpenAI model
self.chunk_size = 800          # tokens per chunk
self.chunk_overlap = 100       # overlap between chunks
self.batch_size = 100          # embeddings per API call
```

### Chunk Size Considerations

- **Smaller chunks (400-600 tokens)**: More precise matching, more chunks, higher cost
- **Larger chunks (800-1200 tokens)**: More context, fewer chunks, lower cost
- **Overlap**: Ensures important content isn't split across chunk boundaries

## Cost Estimation

**OpenAI text-embedding-3-small pricing:** $0.020 per 1M tokens

For 734 blog posts averaging ~1000 words each:
- Total tokens: ~734,000 words × 1.3 (tokens/words) = ~954,000 tokens
- Cost: ~$0.02 for initial vectorization
- Very cheap for semantic search!

## Monitoring

### Check Progress

```bash
# Watch the log file in real-time
tail -f vectorize.log
```

### Query Stats

```sql
-- Count total chunks
SELECT COUNT(*) FROM blog_chunks;

-- Count chunks per blog post
SELECT
    bp.title,
    COUNT(bc.id) as chunk_count,
    SUM(bc.token_count) as total_tokens
FROM blog_chunks bc
JOIN blog_posts bp ON bc.blog_post_id = bp.id
GROUP BY bp.id, bp.title
ORDER BY chunk_count DESC;

-- Check embedding dimensions
SELECT
    id,
    blog_post_id,
    array_length(embedding, 1) as dimensions
FROM blog_chunks
LIMIT 5;
```

## Troubleshooting

### Error: "OPENAI_API_KEY not found"
- Make sure you've added `OPENAI_API_KEY=sk-...` to your `.env` file

### Error: "vector extension does not exist"
- Run the `vectorize_schema.sql` in Supabase SQL Editor first

### Slow Performance
- Decrease `batch_size` if hitting rate limits
- Increase `chunk_size` to create fewer chunks

### Poor Search Results
- Lower `match_threshold` (try 0.5 or 0.6)
- Increase `match_count` to get more results
- Try different query phrasing

## Advanced Usage

### Custom Search with Filters

```python
# Search within specific date range or author
result = supabase.rpc('search_blog_chunks', {
    'query_embedding': query_embedding,
    'match_threshold': 0.7,
    'match_count': 10
}).execute()

# Then filter in Python
filtered = [
    r for r in result.data
    if '2024' in r.get('blog_published_date', '')
]
```

### Hybrid Search (Keyword + Semantic)

```python
# First: Full-text search
keyword_results = supabase.table('blog_posts')\
    .select('*')\
    .textSearch('content', 'API security')\
    .execute()

# Second: Semantic search
semantic_results = supabase.rpc('search_blog_chunks', {
    'query_embedding': query_embedding,
    'match_threshold': 0.7,
    'match_count': 10
}).execute()

# Combine and rank results
```

## Next Steps

1. **Run the schema**: Execute `vectorize_schema.sql` in Supabase
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Add API key**: Add `OPENAI_API_KEY` to `.env`
4. **Test with 10 posts**: Modify and run `vectorize_blogs.py`
5. **Vectorize all posts**: Run full vectorization
6. **Try semantic search**: Run `semantic_search_example.py`

Happy searching! 🚀
