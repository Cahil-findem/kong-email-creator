-- Add pinned_blogs field to candidate_profiles table
-- This allows manually specifying specific blogs for a candidate

ALTER TABLE candidate_profiles
ADD COLUMN IF NOT EXISTS pinned_blogs jsonb DEFAULT '[]'::jsonb;

COMMENT ON COLUMN candidate_profiles.pinned_blogs IS 'Array of manually pinned blog URLs or IDs that should always be included in recommendations for this candidate';

-- Example usage:
-- UPDATE candidate_profiles
-- SET pinned_blogs = '[
--   {"url": "https://konghq.com/blog/example-1", "title": "Example Blog 1"},
--   {"url": "https://konghq.com/blog/example-2", "title": "Example Blog 2"}
-- ]'::jsonb
-- WHERE candidate_id = 'pub_5c7baa020cadfda94cb36a7f';
