-- Remove category pages from blog_posts table
-- This removes URLs like /blog/engineering, /blog/enterprise, etc.
-- and keeps only actual blog posts like /blog/engineering/post-slug

DELETE FROM blog_posts
WHERE url LIKE 'https://konghq.com/blog/%'
AND url NOT LIKE 'https://konghq.com/blog/%/%';

-- This will delete entries that match:
-- https://konghq.com/blog
-- https://konghq.com/blog/engineering
-- https://konghq.com/blog/enterprise
-- etc.

-- And keep entries that match:
-- https://konghq.com/blog/engineering/some-post
-- https://konghq.com/blog/enterprise/another-post
-- etc.
