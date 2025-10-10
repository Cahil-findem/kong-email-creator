-- NetApp Blog Posts Table Schema
-- Run this SQL in your Supabase SQL Editor to create the necessary table

CREATE TABLE IF NOT EXISTS blog_posts (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    html_content TEXT,
    excerpt TEXT,
    meta_description TEXT,
    author TEXT,
    published_date TEXT,
    featured_image TEXT,
    tags TEXT[],
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_blog_posts_url ON blog_posts(url);
CREATE INDEX IF NOT EXISTS idx_blog_posts_published_date ON blog_posts(published_date);
CREATE INDEX IF NOT EXISTS idx_blog_posts_author ON blog_posts(author);
CREATE INDEX IF NOT EXISTS idx_blog_posts_scraped_at ON blog_posts(scraped_at);
CREATE INDEX IF NOT EXISTS idx_blog_posts_tags ON blog_posts USING GIN(tags);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger to automatically update updated_at
DROP TRIGGER IF EXISTS update_blog_posts_updated_at ON blog_posts;
CREATE TRIGGER update_blog_posts_updated_at
    BEFORE UPDATE ON blog_posts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security (RLS)
ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;

-- Create a policy to allow all operations for authenticated users
-- Adjust these policies based on your security requirements
CREATE POLICY "Allow all operations for authenticated users"
    ON blog_posts
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- Create a policy to allow read access for anonymous users
CREATE POLICY "Allow read access for anonymous users"
    ON blog_posts
    FOR SELECT
    TO anon
    USING (true);

-- Optional: Create a view for basic post information (without full content)
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
