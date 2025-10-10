-- Fix RLS Policy to Allow Inserts from Anon Key
-- Run this in your Supabase SQL Editor to fix the permissions issue

-- Drop the restrictive policy for anonymous users
DROP POLICY IF EXISTS "Allow read access for anonymous users" ON blog_posts;

-- Create a new policy that allows all operations for anonymous users
CREATE POLICY "Allow all operations for anonymous users"
    ON blog_posts
    FOR ALL
    TO anon
    USING (true)
    WITH CHECK (true);
