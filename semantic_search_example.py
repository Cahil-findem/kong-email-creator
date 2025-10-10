import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables
load_dotenv()


def semantic_search(query: str, match_count: int = 5, match_threshold: float = 0.7):
    """
    Perform semantic search on blog content

    Args:
        query: The search query text
        match_count: Number of results to return
        match_threshold: Minimum similarity score (0-1)

    Returns:
        List of matching blog chunks with metadata
    """
    # Initialize clients
    supabase: Client = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_KEY')
    )

    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Generate embedding for the query
    print(f"Generating embedding for query: '{query}'")
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    query_embedding = response.data[0].embedding

    # Search for similar chunks using the search function
    print(f"Searching for similar content...")
    result = supabase.rpc(
        'search_blog_chunks',
        {
            'query_embedding': query_embedding,
            'match_threshold': match_threshold,
            'match_count': match_count
        }
    ).execute()

    return result.data


def main():
    """Example usage of semantic search"""

    # Example queries
    queries = [
        "How do I secure my API with authentication?",
        "What is service mesh and how does it work?",
        "AI gateway and LLM integration",
    ]

    for query in queries:
        print("\n" + "="*80)
        print(f"QUERY: {query}")
        print("="*80)

        results = semantic_search(query, match_count=3, match_threshold=0.7)

        if not results:
            print("No results found.")
            continue

        for i, result in enumerate(results, 1):
            print(f"\n--- Result {i} (Similarity: {result['similarity']:.3f}) ---")
            print(f"Title: {result['blog_title']}")
            print(f"URL: {result['blog_url']}")
            print(f"Author: {result.get('blog_author', 'Unknown')}")
            print(f"Published: {result.get('blog_published_date', 'Unknown')}")
            print(f"\nExcerpt:")
            # Show first 300 characters of the chunk
            print(result['chunk_text'][:300] + "...")


if __name__ == "__main__":
    main()
