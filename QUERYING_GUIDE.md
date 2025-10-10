# Querying the Vectorized Blog Database

This guide shows you how to query your vectorized blog database from any application using semantic search.

## Overview

Your database now contains:
- **752 blog posts** in the `blog_posts` table
- **1,672 vectorized chunks** in the `blog_chunks` table
- Each chunk has a **1536-dimensional embedding** from OpenAI

## Quick Start

### 1. Prerequisites

You need:
- **Supabase credentials** (URL + anon key)
- **OpenAI API key** (to generate query embeddings)

### 2. Basic Flow

```
User Query → Generate Embedding → Search Database → Return Results
```

## Implementation Examples

### Python Example

```python
import os
from supabase import create_client
from openai import OpenAI

# Initialize clients
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def search_blogs(query: str, limit: int = 5):
    """Perform semantic search on blog content"""

    # Step 1: Generate embedding for the query
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    query_embedding = response.data[0].embedding

    # Step 2: Search for similar chunks
    results = supabase.rpc(
        'search_blog_chunks',
        {
            'query_embedding': query_embedding,
            'match_threshold': 0.7,  # Similarity threshold (0-1)
            'match_count': limit
        }
    ).execute()

    return results.data

# Example usage
results = search_blogs("How to secure APIs with authentication")

for result in results:
    print(f"Title: {result['blog_title']}")
    print(f"URL: {result['blog_url']}")
    print(f"Similarity: {result['similarity']:.2%}")
    print(f"Excerpt: {result['chunk_text'][:200]}...")
    print()
```

### JavaScript/TypeScript Example

```javascript
import { createClient } from '@supabase/supabase-js'
import OpenAI from 'openai'

// Initialize clients
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
)

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
})

async function searchBlogs(query, limit = 5) {
  // Step 1: Generate embedding for the query
  const embeddingResponse = await openai.embeddings.create({
    model: "text-embedding-3-small",
    input: query
  })

  const queryEmbedding = embeddingResponse.data[0].embedding

  // Step 2: Search for similar chunks
  const { data, error } = await supabase.rpc('search_blog_chunks', {
    query_embedding: queryEmbedding,
    match_threshold: 0.7,
    match_count: limit
  })

  if (error) throw error

  return data
}

// Example usage
const results = await searchBlogs("How to secure APIs with authentication")

results.forEach(result => {
  console.log(`Title: ${result.blog_title}`)
  console.log(`URL: ${result.blog_url}`)
  console.log(`Similarity: ${(result.similarity * 100).toFixed(1)}%`)
  console.log(`Excerpt: ${result.chunk_text.slice(0, 200)}...`)
  console.log()
})
```

### Next.js API Route Example

```typescript
// app/api/search/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'
import OpenAI from 'openai'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_KEY!
)

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY!
})

export async function POST(request: NextRequest) {
  try {
    const { query, limit = 5 } = await request.json()

    if (!query) {
      return NextResponse.json(
        { error: 'Query is required' },
        { status: 400 }
      )
    }

    // Generate embedding
    const embeddingResponse = await openai.embeddings.create({
      model: "text-embedding-3-small",
      input: query
    })

    const queryEmbedding = embeddingResponse.data[0].embedding

    // Search database
    const { data, error } = await supabase.rpc('search_blog_chunks', {
      query_embedding: queryEmbedding,
      match_threshold: 0.7,
      match_count: limit
    })

    if (error) throw error

    return NextResponse.json({ results: data })

  } catch (error) {
    console.error('Search error:', error)
    return NextResponse.json(
      { error: 'Search failed' },
      { status: 500 }
    )
  }
}
```

### React Component Example

```typescript
// components/BlogSearch.tsx
'use client'

import { useState } from 'react'

interface SearchResult {
  chunk_id: number
  blog_title: string
  blog_url: string
  similarity: number
  chunk_text: string
  blog_author?: string
  blog_published_date?: string
}

export default function BlogSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 10 })
      })

      const data = await response.json()
      setResults(data.results || [])
    } catch (error) {
      console.error('Search error:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <form onSubmit={handleSearch} className="mb-8">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about Kong APIs, AI Gateway, etc..."
          className="w-full p-4 border rounded-lg"
        />
        <button
          type="submit"
          disabled={loading}
          className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      <div className="space-y-6">
        {results.map((result) => (
          <div key={result.chunk_id} className="border rounded-lg p-6">
            <h3 className="text-xl font-bold mb-2">
              <a
                href={result.blog_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                {result.blog_title}
              </a>
            </h3>

            <div className="text-sm text-gray-600 mb-3">
              Similarity: {(result.similarity * 100).toFixed(1)}%
              {result.blog_author && ` • By ${result.blog_author}`}
              {result.blog_published_date && ` • ${result.blog_published_date}`}
            </div>

            <p className="text-gray-700">
              {result.chunk_text.slice(0, 300)}...
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

## Database Function Details

### `search_blog_chunks` Function

**Parameters:**
- `query_embedding` (vector(1536)): The embedding vector of your search query
- `match_threshold` (float, default 0.7): Minimum similarity score (0-1)
- `match_count` (int, default 10): Maximum number of results to return

**Returns:**
```typescript
{
  chunk_id: number           // ID of the matching chunk
  blog_post_id: number       // ID of the source blog post
  chunk_text: string         // The chunk content
  similarity: number         // Similarity score (0-1)
  blog_title: string         // Title of the blog post
  blog_url: string           // URL of the blog post
  blog_author: string        // Author name
  blog_published_date: string // Publication date
}[]
```

## Direct Database Queries

### Get All Blog Posts

```sql
SELECT id, title, url, author, published_date, featured_image, tags
FROM blog_posts
ORDER BY published_date DESC;
```

### Get Blog Post with Chunks

```sql
SELECT
  bp.id,
  bp.title,
  bp.url,
  bp.content,
  json_agg(
    json_build_object(
      'chunk_index', bc.chunk_index,
      'chunk_text', bc.chunk_text,
      'token_count', bc.token_count
    ) ORDER BY bc.chunk_index
  ) as chunks
FROM blog_posts bp
LEFT JOIN blog_chunks bc ON bp.id = bc.blog_post_id
WHERE bp.id = 1
GROUP BY bp.id;
```

### Count Statistics

```sql
-- Total posts and chunks
SELECT
  (SELECT COUNT(*) FROM blog_posts) as total_posts,
  (SELECT COUNT(*) FROM blog_chunks) as total_chunks,
  (SELECT AVG(chunk_count) FROM (
    SELECT COUNT(*) as chunk_count
    FROM blog_chunks
    GROUP BY blog_post_id
  ) as counts) as avg_chunks_per_post;
```

## Advanced Use Cases

### 1. Hybrid Search (Keyword + Semantic)

```python
def hybrid_search(query: str, limit: int = 10):
    # Semantic search
    embedding = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    ).data[0].embedding

    semantic_results = supabase.rpc('search_blog_chunks', {
        'query_embedding': embedding,
        'match_threshold': 0.6,
        'match_count': limit
    }).execute()

    # Keyword search
    keyword_results = supabase.table('blog_posts')\
        .select('*')\
        .ilike('content', f'%{query}%')\
        .limit(limit)\
        .execute()

    # Merge and deduplicate results
    all_results = []
    seen_ids = set()

    for result in semantic_results.data:
        if result['blog_post_id'] not in seen_ids:
            all_results.append(result)
            seen_ids.add(result['blog_post_id'])

    return all_results[:limit]
```

### 2. Filtered Semantic Search

```python
def search_by_author(query: str, author: str, limit: int = 5):
    # Generate embedding
    embedding = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    ).data[0].embedding

    # Search with filter
    results = supabase.rpc('search_blog_chunks', {
        'query_embedding': embedding,
        'match_threshold': 0.7,
        'match_count': 100  # Get more results to filter
    }).execute()

    # Filter by author
    filtered = [
        r for r in results.data
        if r.get('blog_author') == author
    ][:limit]

    return filtered
```

### 3. Question Answering with RAG

```python
def answer_question(question: str):
    # Step 1: Search for relevant content
    embedding = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=question
    ).data[0].embedding

    results = supabase.rpc('search_blog_chunks', {
        'query_embedding': embedding,
        'match_threshold': 0.75,
        'match_count': 3
    }).execute()

    # Step 2: Build context from results
    context = "\n\n".join([
        f"Source: {r['blog_title']}\n{r['chunk_text']}"
        for r in results.data
    ])

    # Step 3: Generate answer with GPT
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that answers questions based on the provided blog content. Always cite sources."
            },
            {
                "role": "user",
                "content": f"Context from Kong blog posts:\n\n{context}\n\nQuestion: {question}"
            }
        ]
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": [
            {"title": r['blog_title'], "url": r['blog_url']}
            for r in results.data
        ]
    }
```

## Environment Variables

Create a `.env` file in your app:

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# OpenAI
OPENAI_API_KEY=sk-your-openai-key
```

## Performance Tips

### 1. Caching Query Embeddings

Cache frequently asked questions to avoid regenerating embeddings:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_query_embedding(query: str):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    return response.data[0].embedding
```

### 2. Batch Queries

If searching multiple queries, batch the embedding generation:

```python
def batch_search(queries: list[str]):
    # Generate all embeddings in one API call
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=queries
    )

    embeddings = [item.embedding for item in response.data]

    # Search for each embedding
    results = []
    for query, embedding in zip(queries, embeddings):
        result = supabase.rpc('search_blog_chunks', {
            'query_embedding': embedding,
            'match_threshold': 0.7,
            'match_count': 5
        }).execute()
        results.append({"query": query, "results": result.data})

    return results
```

### 3. Adjust Match Threshold

- **0.8-1.0**: Very similar (strict matching)
- **0.7-0.8**: Similar (recommended)
- **0.6-0.7**: Somewhat related (broader results)
- **0.5-0.6**: Loosely related (very broad)

### 4. Result Deduplication

If multiple chunks from the same post match, deduplicate:

```python
def deduplicate_results(results):
    seen_posts = {}
    deduplicated = []

    for result in results:
        post_id = result['blog_post_id']
        if post_id not in seen_posts:
            seen_posts[post_id] = result
            deduplicated.append(result)
        elif result['similarity'] > seen_posts[post_id]['similarity']:
            # Keep the chunk with highest similarity
            seen_posts[post_id] = result
            deduplicated = [
                r for r in deduplicated
                if r['blog_post_id'] != post_id
            ]
            deduplicated.append(result)

    return deduplicated
```

## Cost Estimation

**OpenAI Embedding Costs:**
- Model: `text-embedding-3-small`
- Price: $0.020 per 1M tokens
- Average query: ~10-20 tokens
- Cost per query: ~$0.0000002 (essentially free)

**Example:**
- 1,000 queries/day = ~$0.006/day = ~$2/year

## Security Best Practices

### 1. Use Row Level Security (RLS)

Already configured in your database, but you can add custom policies:

```sql
-- Example: Restrict access to published posts only
CREATE POLICY "Public posts only" ON blog_posts
FOR SELECT TO anon
USING (published = true);
```

### 2. Rate Limiting

Implement rate limiting in your API:

```typescript
// Example with Vercel Edge Config
import { ratelimit } from '@/lib/ratelimit'

export async function POST(request: NextRequest) {
  const ip = request.ip ?? 'anonymous'
  const { success } = await ratelimit.limit(ip)

  if (!success) {
    return NextResponse.json(
      { error: 'Too many requests' },
      { status: 429 }
    )
  }

  // ... rest of search logic
}
```

### 3. Input Validation

Always validate and sanitize user input:

```typescript
function validateQuery(query: string): boolean {
  // Check length
  if (query.length < 3 || query.length > 500) {
    return false
  }

  // Check for SQL injection attempts
  const sqlPattern = /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b)/i
  if (sqlPattern.test(query)) {
    return false
  }

  return true
}
```

## Troubleshooting

### No Results Found

1. **Lower the threshold**: Try 0.6 or 0.5
2. **Rephrase query**: Use different wording
3. **Check data**: Verify chunks exist in database

### Slow Queries

1. **Check index**: Ensure vector index exists
2. **Reduce match_count**: Fetch fewer results
3. **Use connection pooling**: Reuse database connections

### Incorrect Results

1. **Increase threshold**: Try 0.75 or 0.8 for stricter matching
2. **Use hybrid search**: Combine with keyword search
3. **Improve query**: Add more context to the query

## Example Queries to Try

- "How do I implement API authentication with Kong?"
- "What is the difference between API Gateway and Service Mesh?"
- "Best practices for securing LLM applications"
- "How to deploy Kong Gateway on Kubernetes"
- "Rate limiting strategies for APIs"
- "What is agentic AI and how does it work?"

## Support & Resources

- **Original Documentation**: See `VECTORIZATION_README.md` for setup details
- **Supabase Docs**: https://supabase.com/docs/guides/ai
- **OpenAI Embeddings**: https://platform.openai.com/docs/guides/embeddings
- **pgvector**: https://github.com/pgvector/pgvector

---

Built with ❤️ using OpenAI embeddings, Supabase, and pgvector
