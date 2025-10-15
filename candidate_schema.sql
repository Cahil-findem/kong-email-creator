-- Candidate Vectorization Schema
-- Run this in your Supabase SQL Editor to set up candidate profile vectorization

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Table: candidate_profiles
-- Stores candidate metadata and profile information
-- ============================================================================
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id bigserial PRIMARY KEY,

    -- Candidate IDs
    candidate_id text UNIQUE NOT NULL,  -- External candidate ID (e.g., "68d193fecb73815f93cc0e45")

    -- Basic Info
    full_name text,
    email text,
    location text,
    linkedin_url text,

    -- Professional Info
    current_title text,
    current_company text,
    years_of_experience int,

    -- Profile Content (for reference)
    about_me text,
    skills jsonb,              -- Array of skills
    work_experience jsonb,     -- Array of work history
    education jsonb,           -- Array of education

    -- Metadata
    raw_profile jsonb,         -- Store full original profile for reference
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_candidate_profiles_candidate_id ON candidate_profiles(candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_profiles_email ON candidate_profiles(email);


-- ============================================================================
-- Table: candidate_embeddings
-- Stores vectorized candidate profiles
-- ============================================================================
CREATE TABLE IF NOT EXISTS candidate_embeddings (
    id bigserial PRIMARY KEY,
    candidate_profile_id bigint REFERENCES candidate_profiles(id) ON DELETE CASCADE,

    -- Embedding Data
    embedding_text text NOT NULL,     -- The formatted text that was embedded
    embedding vector(1536) NOT NULL,  -- OpenAI text-embedding-3-small vector
    token_count int,

    -- Metadata
    created_at timestamptz DEFAULT now(),

    -- Ensure one embedding per candidate
    UNIQUE(candidate_profile_id)
);

-- Create HNSW index for fast vector similarity search
CREATE INDEX IF NOT EXISTS idx_candidate_embeddings_vector
ON candidate_embeddings
USING hnsw (embedding vector_cosine_ops);


-- ============================================================================
-- Function: search_blogs_for_candidate
-- Find relevant blog posts for a candidate based on their profile embedding
-- ============================================================================
-- Drop the old function first to allow return type change
DROP FUNCTION IF EXISTS search_blogs_for_candidate(vector, float, int);

CREATE OR REPLACE FUNCTION search_blogs_for_candidate(
    candidate_embedding vector(1536),
    match_threshold float DEFAULT 0.65,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    blog_post_id bigint,
    blog_title text,
    blog_url text,
    blog_author text,
    blog_published_date text,
    blog_featured_image text,
    chunk_text text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        bp.id as blog_post_id,
        bp.title as blog_title,
        bp.url as blog_url,
        bp.author as blog_author,
        bp.published_date as blog_published_date,
        bp.featured_image as blog_featured_image,
        bc.chunk_text,
        1 - (bc.embedding <=> candidate_embedding) as similarity
    FROM blog_chunks bc
    JOIN blog_posts bp ON bc.blog_post_id = bp.id
    WHERE 1 - (bc.embedding <=> candidate_embedding) > match_threshold
    ORDER BY bc.embedding <=> candidate_embedding
    LIMIT match_count;
END;
$$;


-- ============================================================================
-- Function: search_top_blogs_for_candidate (deduplicated by blog post)
-- Returns unique blog posts ranked by best matching chunk
-- ============================================================================
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


-- ============================================================================
-- Function: get_candidate_profile_with_embedding
-- Retrieve candidate profile along with their embedding
-- ============================================================================
-- Drop the old function first to allow return type change
DROP FUNCTION IF EXISTS get_candidate_profile_with_embedding(text);

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
-- View: candidate_profiles_summary
-- Quick overview of all candidates with embeddings
-- ============================================================================
CREATE OR REPLACE VIEW candidate_profiles_summary AS
SELECT
    cp.id,
    cp.candidate_id,
    cp.full_name,
    cp.email,
    cp.current_title,
    cp.current_company,
    cp.location,
    jsonb_array_length(cp.skills) as num_skills,
    CASE WHEN ce.id IS NOT NULL THEN true ELSE false END as has_embedding,
    cp.created_at,
    cp.updated_at
FROM candidate_profiles cp
LEFT JOIN candidate_embeddings ce ON cp.id = ce.candidate_profile_id;


-- ============================================================================
-- Grant permissions (adjust based on your RLS policies)
-- ============================================================================
-- ALTER TABLE candidate_profiles ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE candidate_embeddings ENABLE ROW LEVEL SECURITY;

-- Example: Allow authenticated users to read
-- CREATE POLICY "Allow authenticated read access" ON candidate_profiles
--     FOR SELECT USING (auth.role() = 'authenticated');

-- CREATE POLICY "Allow authenticated read access" ON candidate_embeddings
--     FOR SELECT USING (auth.role() = 'authenticated');
