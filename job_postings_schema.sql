-- Job Postings Schema
-- Stores available job positions with full job description JSON
-- Run this in your Supabase SQL Editor

-- ============================================================================
-- Table: job_postings
-- Stores job postings with metadata and full job description JSON
-- ============================================================================
CREATE TABLE IF NOT EXISTS job_postings (
    id bigserial PRIMARY KEY,

    -- Job Identifiers
    job_id text UNIQUE NOT NULL,  -- Unique identifier for the job (e.g., position slug or application link hash)

    -- Core Job Info (extracted for easy querying)
    position text NOT NULL,
    company text,
    department text,
    employment_type text,  -- Full time, Part time, Contract, etc.

    -- Location Info
    location_city text,
    location_country text,
    location_type text,  -- Remote, Hybrid, On-site

    -- Compensation (for filtering/matching)
    compensation_currency text,
    compensation_min numeric,
    compensation_max numeric,

    -- Job Content
    about_role text,  -- Job description/summary
    responsibilities jsonb,  -- Array of responsibilities
    requirements jsonb,  -- Object with must_have and nice_to_have arrays

    -- Full Job Data
    raw_job_data jsonb NOT NULL,  -- Complete job posting JSON

    -- Application Info
    application_link text,
    posting_code text,

    -- Status & Metadata
    status text DEFAULT 'active',  -- active, inactive, filled, closed
    posted_date timestamptz,
    expires_date timestamptz,

    -- Timestamps
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- ============================================================================
-- Indexes for efficient querying
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_job_postings_job_id ON job_postings(job_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_position ON job_postings(position);
CREATE INDEX IF NOT EXISTS idx_job_postings_location_country ON job_postings(location_country);
CREATE INDEX IF NOT EXISTS idx_job_postings_location_type ON job_postings(location_type);
CREATE INDEX IF NOT EXISTS idx_job_postings_status ON job_postings(status);
CREATE INDEX IF NOT EXISTS idx_job_postings_department ON job_postings(department);

-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_job_postings_raw_data ON job_postings USING gin(raw_job_data);

-- ============================================================================
-- Function: Update timestamp on row update
-- ============================================================================
CREATE OR REPLACE FUNCTION update_job_postings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_job_postings_timestamp ON job_postings;
CREATE TRIGGER trigger_update_job_postings_timestamp
    BEFORE UPDATE ON job_postings
    FOR EACH ROW
    EXECUTE FUNCTION update_job_postings_updated_at();

-- ============================================================================
-- Example: Insert job posting
-- ============================================================================
-- INSERT INTO job_postings (
--     job_id,
--     position,
--     company,
--     department,
--     employment_type,
--     location_city,
--     location_country,
--     location_type,
--     compensation_currency,
--     compensation_min,
--     compensation_max,
--     about_role,
--     responsibilities,
--     requirements,
--     raw_job_data,
--     application_link,
--     posting_code,
--     status
-- ) VALUES (
--     'senior-software-engineer-insomnia',
--     'Senior Software Engineer - Insomnia Team',
--     'Kong Inc.',
--     'All Cost Center R&D ENG',
--     'Full time',
--     'Toronto',
--     'Canada',
--     'Remote',
--     'CAD',
--     144800,
--     202800,
--     'As a Senior Software Engineer on the Insomnia team at Kong...',
--     '["Work with a global team of engineers...", "Engage with the Insomnia open source community..."]'::jsonb,
--     '{"must_have": [...], "nice_to_have": [...]}'::jsonb,
--     '{...full job JSON...}'::jsonb,
--     'https://jobs.ashbyhq.com/kong/40d0693f-2727-4662-9e1c-86c80581292a',
--     'LI-SV1',
--     'active'
-- );

-- ============================================================================
-- Example: Query active remote jobs
-- ============================================================================
-- SELECT
--     position,
--     location_country,
--     location_type,
--     compensation_currency,
--     compensation_min,
--     compensation_max,
--     about_role
-- FROM job_postings
-- WHERE status = 'active'
--   AND location_type = 'Remote'
-- ORDER BY created_at DESC;

-- ============================================================================
-- Example: Search jobs by keyword in responsibilities or requirements
-- ============================================================================
-- SELECT
--     position,
--     company,
--     location_country,
--     about_role
-- FROM job_postings
-- WHERE status = 'active'
--   AND (
--     about_role ILIKE '%API%'
--     OR raw_job_data->>'about_role' ILIKE '%API%'
--     OR raw_job_data::text ILIKE '%API%'
--   );

-- ============================================================================
-- Example: Get jobs by compensation range
-- ============================================================================
-- SELECT
--     position,
--     location_country,
--     compensation_currency,
--     compensation_min,
--     compensation_max
-- FROM job_postings
-- WHERE status = 'active'
--   AND compensation_currency = 'USD'
--   AND compensation_min >= 120000
-- ORDER BY compensation_max DESC;

-- ============================================================================
-- View: Active job postings summary
-- ============================================================================
CREATE OR REPLACE VIEW active_jobs_summary AS
SELECT
    id,
    job_id,
    position,
    company,
    department,
    employment_type,
    location_city,
    location_country,
    location_type,
    compensation_currency,
    compensation_min,
    compensation_max,
    application_link,
    created_at,
    updated_at
FROM job_postings
WHERE status = 'active'
ORDER BY created_at DESC;

-- ============================================================================
-- Grant permissions (adjust based on your RLS policies)
-- ============================================================================
-- ALTER TABLE job_postings ENABLE ROW LEVEL SECURITY;

-- Example: Allow authenticated users to read
-- CREATE POLICY "Allow authenticated read access" ON job_postings
--     FOR SELECT USING (auth.role() = 'authenticated');

-- Example: Allow service role to insert/update
-- CREATE POLICY "Allow service role full access" ON job_postings
--     FOR ALL USING (auth.role() = 'service_role');
