-- Migration: Add Three Separate Embedding Fields
-- This migration transforms the single embedding_text/embedding structure
-- into three separate fields: professional_summary, job_preferences, and interests
-- Each with its own embedding vector for more granular blog matching

-- ============================================================================
-- Step 1: Add new columns to candidate_embeddings table
-- ============================================================================

-- Add professional summary fields
ALTER TABLE candidate_embeddings
ADD COLUMN IF NOT EXISTS professional_summary text,
ADD COLUMN IF NOT EXISTS professional_summary_embedding vector(1536);

-- Add job preferences fields
ALTER TABLE candidate_embeddings
ADD COLUMN IF NOT EXISTS job_preferences text,
ADD COLUMN IF NOT EXISTS job_preferences_embedding vector(1536);

-- Add interests fields
ALTER TABLE candidate_embeddings
ADD COLUMN IF NOT EXISTS interests text,
ADD COLUMN IF NOT EXISTS interests_embedding vector(1536);


-- ============================================================================
-- Step 2: Migrate existing data
-- Move current embedding_text to professional_summary
-- ============================================================================

UPDATE candidate_embeddings
SET
    professional_summary = embedding_text,
    professional_summary_embedding = embedding
WHERE professional_summary IS NULL;


-- ============================================================================
-- Step 3: Create indexes for the new embedding vectors
-- ============================================================================

-- Index for professional summary embeddings
CREATE INDEX IF NOT EXISTS idx_candidate_embeddings_professional_vector
ON candidate_embeddings
USING hnsw (professional_summary_embedding vector_cosine_ops);

-- Index for job preferences embeddings
CREATE INDEX IF NOT EXISTS idx_candidate_embeddings_preferences_vector
ON candidate_embeddings
USING hnsw (job_preferences_embedding vector_cosine_ops);

-- Index for interests embeddings
CREATE INDEX IF NOT EXISTS idx_candidate_embeddings_interests_vector
ON candidate_embeddings
USING hnsw (interests_embedding vector_cosine_ops);


-- ============================================================================
-- Step 4: Update search function to search across all three embeddings
-- Returns combined results from all three embedding types
-- ============================================================================

CREATE OR REPLACE FUNCTION search_blogs_for_candidate_multi(
    prof_embedding vector(1536),
    pref_embedding vector(1536) DEFAULT NULL,
    int_embedding vector(1536) DEFAULT NULL,
    match_threshold float DEFAULT 0.65,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    blog_post_id bigint,
    blog_title text,
    blog_url text,
    blog_author text,
    blog_published_date text,
    chunk_text text,
    similarity float,
    match_type text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH professional_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> prof_embedding) as similarity,
            'professional'::text as match_type
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE 1 - (bc.embedding <=> prof_embedding) > match_threshold
    ),
    preferences_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> pref_embedding) as similarity,
            'preferences'::text as match_type
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE pref_embedding IS NOT NULL
          AND 1 - (bc.embedding <=> pref_embedding) > match_threshold
    ),
    interests_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> int_embedding) as similarity,
            'interests'::text as match_type
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE int_embedding IS NOT NULL
          AND 1 - (bc.embedding <=> int_embedding) > match_threshold
    ),
    all_matches AS (
        SELECT * FROM professional_matches
        UNION ALL
        SELECT * FROM preferences_matches
        UNION ALL
        SELECT * FROM interests_matches
    )
    SELECT
        all_matches.blog_post_id,
        all_matches.blog_title,
        all_matches.blog_url,
        all_matches.blog_author,
        all_matches.blog_published_date,
        all_matches.chunk_text,
        all_matches.similarity,
        all_matches.match_type
    FROM all_matches
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;


-- ============================================================================
-- Step 5: Update deduplicated search function for three embeddings
-- Returns unique blog posts with best match from any of the three embeddings
-- ============================================================================

CREATE OR REPLACE FUNCTION search_top_blogs_for_candidate_multi(
    prof_embedding vector(1536),
    pref_embedding vector(1536) DEFAULT NULL,
    int_embedding vector(1536) DEFAULT NULL,
    match_threshold float DEFAULT 0.65,
    match_count int DEFAULT 30
)
RETURNS TABLE (
    blog_post_id bigint,
    blog_title text,
    blog_url text,
    blog_author text,
    blog_published_date text,
    best_matching_chunk text,
    max_similarity float,
    match_type text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH professional_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> prof_embedding) as similarity,
            'professional'::text as match_type,
            ROW_NUMBER() OVER (PARTITION BY bp.id ORDER BY bc.embedding <=> prof_embedding) as rn
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE 1 - (bc.embedding <=> prof_embedding) > match_threshold
    ),
    preferences_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> pref_embedding) as similarity,
            'preferences'::text as match_type,
            ROW_NUMBER() OVER (PARTITION BY bp.id ORDER BY bc.embedding <=> pref_embedding) as rn
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE pref_embedding IS NOT NULL
          AND 1 - (bc.embedding <=> pref_embedding) > match_threshold
    ),
    interests_matches AS (
        SELECT
            bp.id as blog_post_id,
            bp.title as blog_title,
            bp.url as blog_url,
            bp.author as blog_author,
            bp.published_date as blog_published_date,
            bc.chunk_text,
            1 - (bc.embedding <=> int_embedding) as similarity,
            'interests'::text as match_type,
            ROW_NUMBER() OVER (PARTITION BY bp.id ORDER BY bc.embedding <=> int_embedding) as rn
        FROM blog_chunks bc
        JOIN blog_posts bp ON bc.blog_post_id = bp.id
        WHERE int_embedding IS NOT NULL
          AND 1 - (bc.embedding <=> int_embedding) > match_threshold
    ),
    all_matches AS (
        SELECT * FROM professional_matches WHERE rn = 1
        UNION ALL
        SELECT * FROM preferences_matches WHERE rn = 1
        UNION ALL
        SELECT * FROM interests_matches WHERE rn = 1
    ),
    deduplicated AS (
        SELECT DISTINCT ON (blog_post_id)
            blog_post_id,
            blog_title,
            blog_url,
            blog_author,
            blog_published_date,
            chunk_text as best_matching_chunk,
            similarity as max_similarity,
            match_type
        FROM all_matches
        ORDER BY blog_post_id, similarity DESC
    )
    SELECT * FROM deduplicated
    ORDER BY max_similarity DESC
    LIMIT match_count;
END;
$$;


-- ============================================================================
-- Step 6: Update RPC function to return all three embedding fields
-- ============================================================================

-- Drop existing function first to allow return type change
DROP FUNCTION IF EXISTS get_candidate_profile_with_embedding(text);

-- Recreate with new return type
CREATE FUNCTION get_candidate_profile_with_embedding(
    candidate_external_id text
)
RETURNS TABLE (
    profile_id bigint,
    candidate_id text,
    full_name text,
    email text,
    current_title text,
    current_company text,
    location text,
    about_me text,
    skills jsonb,
    -- Legacy fields (kept for backwards compatibility)
    embedding_text text,
    embedding vector(1536),
    -- New three-field structure
    professional_summary text,
    professional_summary_embedding vector(1536),
    job_preferences text,
    job_preferences_embedding vector(1536),
    interests text,
    interests_embedding vector(1536)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        cp.id as profile_id,
        cp.candidate_id,
        cp.full_name,
        cp.email,
        cp.current_title,
        cp.current_company,
        cp.location,
        cp.about_me,
        cp.skills,
        -- Legacy
        ce.embedding_text,
        ce.embedding,
        -- New fields
        ce.professional_summary,
        ce.professional_summary_embedding,
        ce.job_preferences,
        ce.job_preferences_embedding,
        ce.interests,
        ce.interests_embedding
    FROM candidate_profiles cp
    LEFT JOIN candidate_embeddings ce ON cp.id = ce.candidate_profile_id
    WHERE cp.candidate_id = candidate_external_id;
END;
$$;


-- ============================================================================
-- Step 7: Optional - Keep legacy columns for backwards compatibility
-- If you want to remove them later, uncomment these lines:
-- ============================================================================

-- ALTER TABLE candidate_embeddings DROP COLUMN IF EXISTS embedding_text;
-- ALTER TABLE candidate_embeddings DROP COLUMN IF EXISTS embedding;
-- DROP INDEX IF EXISTS idx_candidate_embeddings_vector;


-- ============================================================================
-- Verification Queries (run these after migration to verify)
-- ============================================================================

-- Check the new structure:
-- SELECT
--     candidate_profile_id,
--     CASE WHEN professional_summary IS NOT NULL THEN 'Yes' ELSE 'No' END as has_professional,
--     CASE WHEN job_preferences IS NOT NULL THEN 'Yes' ELSE 'No' END as has_preferences,
--     CASE WHEN interests IS NOT NULL THEN 'Yes' ELSE 'No' END as has_interests
-- FROM candidate_embeddings;

-- Test the new search function:
-- SELECT * FROM get_candidate_profile_with_embedding('68d193fecb73815f93cc0e45');
