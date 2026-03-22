-- Customer Preferences Schema
-- Stores per-company preferences (goal, do-not-contact reasons, email feedback)
-- Run this in your Supabase SQL Editor

-- ============================================================================
-- Table: customer_preferences
-- Stores company-scoped preferences for email generation
-- ============================================================================
CREATE TABLE IF NOT EXISTS customer_preferences (
    id bigserial PRIMARY KEY,

    -- Company Identifier
    company_name text UNIQUE NOT NULL,

    -- Preferences
    goal text DEFAULT 'both',
    do_not_contact_reasons jsonb DEFAULT '[]'::jsonb,
    nurture_email_feedback text DEFAULT '',
    job_email_feedback text DEFAULT '',

    -- Timestamps
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),

    -- Constraints
    CONSTRAINT valid_goal CHECK (goal IN ('applicants', 'warm', 'both'))
);

-- ============================================================================
-- Indexes for efficient querying
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_customer_preferences_company_name ON customer_preferences(company_name);

-- ============================================================================
-- Function: Update timestamp on row update
-- ============================================================================
CREATE OR REPLACE FUNCTION update_customer_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_customer_preferences_timestamp ON customer_preferences;
CREATE TRIGGER trigger_update_customer_preferences_timestamp
    BEFORE UPDATE ON customer_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_customer_preferences_updated_at();

-- ============================================================================
-- Grant permissions (adjust based on your RLS policies)
-- ============================================================================
-- ALTER TABLE customer_preferences ENABLE ROW LEVEL SECURITY;

-- Example: Allow authenticated users to read
-- CREATE POLICY "Allow authenticated read access" ON customer_preferences
--     FOR SELECT USING (auth.role() = 'authenticated');

-- Example: Allow service role to insert/update
-- CREATE POLICY "Allow service role full access" ON customer_preferences
--     FOR ALL USING (auth.role() = 'service_role');
