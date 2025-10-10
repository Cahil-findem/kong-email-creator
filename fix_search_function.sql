-- Fix the search_top_blogs_for_candidate function
-- Run this in Supabase SQL Editor

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
    best_matching_chunk text,
    max_similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH ranked_chunks AS (
        SELECT
            bp.id as post_id,
            bp.title as title,
            bp.url as url,
            bp.author as author,
            bp.published_date as published_date,
            bc.chunk_text as chunk,
            1 - (bc.embedding <=> candidate_embedding) as sim,
            ROW_NUMBER() OVER (PARTITION BY bp.id ORDER BY bc.embedding <=> candidate_embedding) as rn
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE 1 - (bc.embedding <=> candidate_embedding) > match_threshold
    )
    SELECT
        rc.post_id,
        rc.title,
        rc.url,
        rc.author,
        rc.published_date,
        rc.chunk,
        rc.sim
    FROM ranked_chunks rc
    WHERE rc.rn = 1
    ORDER BY rc.sim DESC
    LIMIT match_count;
END;
$$;
