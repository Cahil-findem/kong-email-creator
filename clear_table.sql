-- Clear all data from blog_posts table
-- Run this in your Supabase SQL Editor to start fresh

DELETE FROM blog_posts;

-- Optional: Reset the ID sequence to start from 1 again
ALTER SEQUENCE blog_posts_id_seq RESTART WITH 1;
