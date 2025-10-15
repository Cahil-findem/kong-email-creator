-- Fix the search_top_blogs_for_candidate function
-- Run this in Supabase SQL Editor

-- Drop the old function first to allow return type change
DROP FUNCTION IF EXISTS search_top_blogs_for_candidate(vector, float, int);

CREATE OR REPLACE FUNCTION search_top_blogs_for_candidate(
    candidate_embedding vector(1536),
    match_threshold float DEFAULT 0.65,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    blog_post_id bigint,
    blog_title text,
    blog_url text,
    blog_author text,
    blog_published_date text,
    blog_featured_image text,
    best_matching_chunk text,
    max_similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH ranked_chunks AS (
        SELECT
            bp.id,
            bp.title,
            bp.url,
            bp.author,
            bp.published_date,
            bp.featured_image,
            bc.chunk_text,
            1 - (bc.embedding <=> candidate_embedding) as similarity,
            ROW_NUMBER() OVER (PARTITION BY bp.id ORDER BY bc.embedding <=> candidate_embedding) as rn
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE 1 - (bc.embedding <=> candidate_embedding) > match_threshold
    )
    SELECT
        rc.id as blog_post_id,
        rc.title as blog_title,
        rc.url as blog_url,
        rc.author as blog_author,
        rc.published_date as blog_published_date,
        rc.featured_image as blog_featured_image,
        rc.chunk_text as best_matching_chunk,
        rc.similarity as max_similarity
    FROM ranked_chunks rc
    WHERE rc.rn = 1
    ORDER BY rc.similarity DESC
    LIMIT match_count;
END;
$$;
