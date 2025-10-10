-- Migration: Add featured_image column to existing blog_posts table
-- Run this ONLY if you already created the table without the featured_image column

-- Add the featured_image column
ALTER TABLE blog_posts
ADD COLUMN IF NOT EXISTS featured_image TEXT;

-- Update the view to include featured_image
CREATE OR REPLACE VIEW blog_posts_preview AS
SELECT
    id,
    url,
    title,
    excerpt,
    meta_description,
    author,
    published_date,
    featured_image,
    tags,
    scraped_at,
    created_at
FROM blog_posts;
