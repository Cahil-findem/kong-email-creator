-- Company campaigns: client-authored source content that steers email generation.
--
-- Campaigns live on customer_preferences rather than in their own table because
-- they are prompt configuration -- the same kind of thing as nurture_email_feedback
-- and signature_html -- not rendered templates. This also means the existing
-- /api/company-preferences CRUD manages them with no new endpoints.
--
-- Shape: a JSON array of campaign objects, each:
--   key              slug used by the campaign_key param on /api/generate-email
--   name             human label
--   email_type       'nurture' | 'job'
--   source_content   the client's copy, verbatim, as plain text
--   key_facts        [] strings that MUST survive rewriting unchanged (stats, place
--                    names). Generation fails if any goes missing.
--   subject_examples [] client-supplied subject lines used to steer the subject LLM
--   tone_notes       optional guidance ("punchier, for passive GTM talent")
--   image_url        public https image rendered verbatim in the card
--   image_alt        alt text
--   cta_label        optional call-to-action text
--   cta_url          optional call-to-action href (never model-generated)
--   is_active        bool
--
-- Run this in your Supabase SQL Editor.

ALTER TABLE customer_preferences
    ADD COLUMN IF NOT EXISTS campaigns jsonb DEFAULT '[]'::jsonb;

COMMENT ON COLUMN customer_preferences.campaigns IS
    'Client-authored campaign source content used to steer email generation; selected per request via the campaign_key param.';
