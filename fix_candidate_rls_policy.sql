-- Fix RLS Policy for Candidate Tables
-- Run this in your Supabase SQL Editor to allow API operations on candidate tables
--
-- This script enables full access for anonymous users (API key access)
-- to perform all operations on candidate_profiles and candidate_embeddings

-- ============================================================================
-- candidate_profiles table
-- ============================================================================

-- Drop existing restrictive policies if they exist
DROP POLICY IF EXISTS "Allow read access for anonymous users" ON candidate_profiles;
DROP POLICY IF EXISTS "Allow authenticated read access" ON candidate_profiles;

-- Create policy allowing all operations for anonymous users (API access)
CREATE POLICY "Allow all operations for anonymous users"
    ON candidate_profiles
    FOR ALL
    TO anon
    USING (true)
    WITH CHECK (true);

-- Optional: Also allow for authenticated users
CREATE POLICY "Allow all operations for authenticated users"
    ON candidate_profiles
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- candidate_embeddings table
-- ============================================================================

-- Drop existing restrictive policies if they exist
DROP POLICY IF EXISTS "Allow read access for anonymous users" ON candidate_embeddings;
DROP POLICY IF EXISTS "Allow authenticated read access" ON candidate_embeddings;

-- Create policy allowing all operations for anonymous users (API access)
CREATE POLICY "Allow all operations for anonymous users"
    ON candidate_embeddings
    FOR ALL
    TO anon
    USING (true)
    WITH CHECK (true);

-- Optional: Also allow for authenticated users
CREATE POLICY "Allow all operations for authenticated users"
    ON candidate_embeddings
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- Verify RLS is enabled (should already be enabled)
-- ============================================================================

-- Enable RLS if not already enabled
ALTER TABLE candidate_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_embeddings ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- Verification Query (run after applying fix)
-- ============================================================================

-- Check active policies:
-- SELECT schemaname, tablename, policyname, roles, cmd
-- FROM pg_policies
-- WHERE tablename IN ('candidate_profiles', 'candidate_embeddings')
-- ORDER BY tablename, policyname;
