"""
Flask app for candidate email generation
Provides a web interface to vectorize candidates and generate personalized emails
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import re
import html as _html
import json
import logging
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client
from openai import OpenAI
import tiktoken

# Load environment variables FIRST
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Import our existing classes
from vectorize_candidates import CandidateVectorizer
from match_candidates_to_blogs import CandidateBlogMatcher

# Initialize OpenAI for semantic processing (after loading env vars)
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize our services
vectorizer = CandidateVectorizer()
matcher = CandidateBlogMatcher()


# ============================================================================
# AUTHENTICATION HELPER
# ============================================================================

def check_api_key():
    """Check API key if authentication is enabled"""
    api_key = os.getenv('API_KEY')
    if api_key:
        provided_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if provided_key != api_key:
            return False
    return True


# ============================================================================
# INTERNAL HELPER FUNCTIONS (not exposed as endpoints)
# ============================================================================

def create_candidate_summaries(candidate_info):
    """
    Internal: Create three separate summaries for comprehensive candidate understanding
    Returns dict with: professional_summary, job_preferences, interests
    """
    # Extract key details
    name = candidate_info.get('full_name', '')
    title = candidate_info.get('current_title', '')
    company = candidate_info.get('current_company', '')
    location = candidate_info.get('location', '')
    about_me = candidate_info.get('about_me', '')
    skills = candidate_info.get('skills', [])

    # Get work history summary
    work_exp = candidate_info.get('work_experience', [])
    companies = []
    titles = []
    if work_exp and isinstance(work_exp, list):
        for exp in work_exp[:3]:  # Top 3 positions
            if isinstance(exp, dict):
                comp_name = exp.get('company', {}).get('name', '')
                job_title = exp.get('title', '')
                if comp_name:
                    companies.append(comp_name)
                if job_title:
                    titles.append(job_title)

    # Build context for LLM
    profile_context = f"""
Candidate Name: {name}
Current Role: {title} at {company}
Location: {location}
Previous Companies: {', '.join(companies) if companies else 'N/A'}
Previous Titles: {', '.join(titles) if titles else 'N/A'}
About: {about_me[:500] if about_me else 'N/A'}
Key Skills: {', '.join(skills[:15]) if skills else 'N/A'}
"""

    # Use LLM to create three separate summaries
    system_prompt = """You are an AI that analyzes candidate profiles to create three distinct summaries for vectorized matching.

Given a candidate profile, generate THREE separate text summaries as valid JSON:

1. **professional_summary**: A 2-3 sentence paragraph describing their professional identity, domain expertise, key competencies, career trajectory, and professional values. Focus on WHO they are as a professional.

2. **job_preferences**: A simple structured format with three lines:
   - Job Titles: [comma-separated list of 2-3 target job titles they'd likely pursue]
   - Location: [their preferred work location - Remote, City/State, or Flexible]
   - Seniority: [IC, Senior IC, Manager, Senior Manager, Director, VP, or Executive]

3. **interests**: A bulleted list of professional interests directly tied to their job role and day-to-day work, formatted as:
   • [Interest/Skill/Domain 1]
   • [Interest/Skill/Domain 2]
   • [Interest/Skill/Domain 3]
   • [Interest/Skill/Domain 4]
   • [Interest/Skill/Domain 5]

   Guidelines:
   - Infer interests from what they actually do in their role, not from their broader industry.
   - Prioritize functional depth — what a strong performer in their position focuses on mastering or improving.
   - Include specific processes, tools, or performance areas that define excellence in that job.
   - Keep interests practitioner-level, not aspirational or trend-focused.
   - Avoid unrelated technologies or high-level topics unless clearly used in their work.

   Example for an Account Executive:
   • Pipeline generation and deal qualification
   • Forecast accuracy and CRM optimization
   • Multi-threaded enterprise selling
   • Negotiation and closing strategies
   • Cross-functional alignment with marketing and CS

Output ONLY valid JSON in this exact format:
{
  "professional_summary": "...",
  "job_preferences": "Job Titles: ...\nLocation: ...\nSeniority: ...",
  "interests": "• ...\n• ...\n• ...\n• ...\n• ..."
}

Be specific and inferential. Don't just list their current role - synthesize patterns and predict interests."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": profile_context}
            ],
            temperature=0.7,
            max_tokens=400,
            response_format={"type": "json_object"}
        )

        summaries_json = response.choices[0].message.content.strip()
        summaries = json.loads(summaries_json)

        logger.info(f"Generated professional summary: {summaries['professional_summary'][:80]}...")
        logger.info(f"Generated job preferences: {summaries['job_preferences'][:80]}...")
        logger.info(f"Generated interests: {summaries['interests'][:80]}...")

        return summaries

    except Exception as e:
        logger.error(f"Error generating candidate summaries: {str(e)}")
        # Fallback to basic summaries
        skill_list = '\n'.join([f"• {skill}" for skill in skills[:5]]) if skills else "• Industry trends\n• Professional development"
        return {
            "professional_summary": f"{name} is a {title} with expertise in {', '.join(skills[:5]) if skills else 'various areas'}. Currently working at {company}.",
            "job_preferences": f"Job Titles: {title}, Senior {title}\nLocation: {location if location else 'Flexible'}\nSeniority: Senior IC",
            "interests": skill_list
        }


def vectorize_candidate_summaries(candidate_data, summaries):
    """
    Internal: Vectorize candidate using three LLM-generated summaries
    summaries dict contains: professional_summary, job_preferences, interests
    Returns: success boolean
    """
    try:
        logger.info("Vectorizing candidate with three-field summary...")

        # Extract candidate information
        candidate_info = vectorizer.extract_candidate_info(candidate_data)
        candidate_id = candidate_info['candidate_id']

        if not candidate_id:
            logger.error("Candidate missing ID")
            return False

        # Save profile to database
        profile_id = vectorizer.save_candidate_profile(candidate_info)
        if not profile_id:
            logger.error(f"Failed to save profile for candidate {candidate_id}")
            return False

        logger.info(f"Saved candidate profile {candidate_id} with profile_id {profile_id}")

        # Generate three separate embeddings
        professional_summary = summaries.get('professional_summary', '')
        job_preferences = summaries.get('job_preferences', '')
        interests = summaries.get('interests', '')

        logger.info(f"Generating embeddings for three fields...")
        logger.info(f"  - Professional summary: {len(professional_summary)} chars")
        logger.info(f"  - Job preferences: {len(job_preferences)} chars")
        logger.info(f"  - Interests: {len(interests)} chars")

        # Generate embeddings using OpenAI
        prof_embedding = vectorizer.generate_embedding(professional_summary)
        pref_embedding = vectorizer.generate_embedding(job_preferences)
        int_embedding = vectorizer.generate_embedding(interests)

        # Save all three embeddings to database
        supabase = vectorizer.supabase

        # Check if embedding exists
        existing = supabase.table('candidate_embeddings').select('id').eq(
            'candidate_profile_id', profile_id
        ).execute()

        if existing.data:
            # Update existing embedding
            result = supabase.table('candidate_embeddings').update({
                'professional_summary': professional_summary,
                'professional_summary_embedding': prof_embedding,
                'job_preferences': job_preferences,
                'job_preferences_embedding': pref_embedding,
                'interests': interests,
                'interests_embedding': int_embedding,
                # Keep legacy field for backwards compatibility
                'embedding_text': professional_summary,
                'embedding': prof_embedding
            }).eq('candidate_profile_id', profile_id).execute()
        else:
            # Insert new embedding
            result = supabase.table('candidate_embeddings').insert({
                'candidate_profile_id': profile_id,
                'professional_summary': professional_summary,
                'professional_summary_embedding': prof_embedding,
                'job_preferences': job_preferences,
                'job_preferences_embedding': pref_embedding,
                'interests': interests,
                'interests_embedding': int_embedding,
                # Keep legacy field for backwards compatibility
                'embedding_text': professional_summary,
                'embedding': prof_embedding,
                'token_count': len(professional_summary.split()) + len(job_preferences.split()) + len(interests.split())
            }).execute()

        logger.info(f"Successfully vectorized candidate {candidate_id} with three-field embeddings")
        return True

    except Exception as e:
        logger.error(f"Error vectorizing candidate: {str(e)}", exc_info=True)
        return False


# Company-scoped forced blogs: when a sender company is listed here, its nurture
# emails include EXACTLY these blogs (in order) and skip auto-matching entirely.
# URLs must already exist in the blog_posts table for the same company.
# Each entry may be a plain URL string, or a dict with:
#   url:   the blog_posts URL (required)
#   intro: optional lead-in sentence/framing for the email (overrides the default
#          "why this is relevant to you" line for that blog only).
COMPANY_FORCED_BLOGS = {
    "Kong": [
        {
            "url": "https://www.linkedin.com/posts/kellycapitali_when-you-assemble-the-best-sales-minds-a-ugcPost-7475995635389837313-ckNw",
            "intro": (
                "I wanted to highlight Kong's President's Club — this year we took our top "
                "sales performers to Vietnam. Thought you'd enjoy a look at how we recognize and "
                "reward the team."
            ),
            "card_blurb": (
                "Silverback Circle is Kong's President's Club — our top sales performers "
                "celebrated in Vietnam this year, with Fiji on deck for next year."
            ),
            "image_fit": "contain",
        },
    ],
}


# ── Company campaigns ──────────────────────────────────────────────────────
# A campaign is client-authored source content that steers generation: the model
# rewrites it per candidate rather than rendering it verbatim. Facts that must
# not drift (stats, the CTA link, the image) are pinned outside the model.

CAMPAIGN_CARD_TOKEN = "{{CAMPAIGN_CARD}}"


def get_company_campaign(company, campaign_key):
    """Look up one campaign from customer_preferences.campaigns.

    Returns the campaign dict, or None if the company, column, or key is absent.
    """
    if not company or not campaign_key:
        return None
    try:
        result = matcher.supabase.table('customer_preferences').select(
            'campaigns'
        ).eq('company_name', company).execute()
    except Exception as e:
        logger.warning(f"Could not load campaigns for '{company}': {e}")
        return None
    if not result.data:
        return None
    campaigns = result.data[0].get('campaigns') or []
    if isinstance(campaigns, str):
        try:
            campaigns = json.loads(campaigns)
        except json.JSONDecodeError:
            return None
    for c in campaigns:
        if c.get('key') == campaign_key:
            if c.get('is_active') is False:
                logger.warning(f"Campaign '{campaign_key}' for '{company}' is inactive")
                return None
            return c
    return None


def _insert_before_signoff(email_body, block):
    """Place `block` just before the sign-off paragraph, else append it."""
    signoff = re.search(r'<p[^>]*>\s*(Best|Thanks|Cheers|Warmly)\b', email_body, re.IGNORECASE)
    if signoff:
        return email_body[:signoff.start()] + block + "\n" + email_body[signoff.start():]
    return email_body + "\n" + block


def _build_blog_card(blog, lead_in=None):
    """Render one blog card in code, matching the markup the nurture prompt uses."""
    esc = lambda v: _html.escape(str(v or ''), quote=True)
    url, title = esc(blog.get('blog_url')), esc(blog.get('blog_title'))
    image = esc(blog.get('blog_featured_image'))
    fit = esc(blog.get('email_image_fit') or 'cover')
    source = _blog_source_label(blog.get('blog_url'))
    blurb = blog.get('email_card_blurb')
    parts = []
    if lead_in:
        parts.append('<p style="margin: 0 0 8px 0; font-size: 15px; color: #6b7280; '
                     f'line-height: 1.5;">{esc(lead_in)}</p>')
    parts.append(
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="width: 100%; margin: 0 0 20px 0; border-collapse: collapse;">\n  <tr>')
    if image:
        parts.append(
            '    <td width="160" style="width: 160px; vertical-align: top; padding-right: 16px;">\n'
            f'      <a href="{url}" style="text-decoration: none;">\n'
            f'        <img src="{image}" alt="{title}" width="160" height="92" '
            f'style="width: 160px; height: 92px; object-fit: {fit}; border-radius: 10px; '
            'display: block; border: 0;">\n      </a>\n    </td>')
    body = [f'      <a href="{url}" style="font-size: 15px; font-weight: 600; color: #101828; '
            'text-decoration: none; line-height: 1.35; display: block; margin: 0 0 4px 0;">'
            f'{title}</a>']
    if source:
        body.append('      <div style="font-size: 12px; font-weight: 500; color: #6b7280; '
                    f'line-height: 1.4; margin: 0 0 6px 0;">{esc(source)}</div>')
    if blurb:
        body.append('      <p style="font-size: 13px; color: #6b7280; line-height: 1.45; '
                    f'margin: 0;">{esc(blurb)}</p>')
    parts.append('    <td style="vertical-align: top;">\n' + "\n".join(body) + '\n    </td>')
    parts.append('  </tr>\n</table>')
    return "\n".join(parts)


def _build_campaign_card(campaign):
    """Render the campaign image + CTA in code.

    Kept out of the LLM for the same reason as the signature: the image URL and
    CTA href must render exactly as configured, never paraphrased or invented.
    """
    image_url = (campaign.get('image_url') or '').strip()
    cta_label = (campaign.get('cta_label') or '').strip()
    cta_url = (campaign.get('cta_url') or '').strip()
    alt = (campaign.get('image_alt') or campaign.get('name') or '').strip()
    if not image_url and not cta_url:
        return ''

    parts = ['<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
             'border="0" style="width:100%; border-collapse:collapse; margin:8px 0 20px 0;">']
    if image_url:
        img = (f'<img src="{image_url}" alt="{alt}" width="600" '
               'style="display:block; width:100%; max-width:600px; height:auto; '
               'border-radius:8px; border:0; outline:none; text-decoration:none;" />')
        if cta_url:
            img = f'<a href="{cta_url}" style="text-decoration:none;">{img}</a>'
        parts.append(f'  <tr><td style="padding:0;">{img}</td></tr>')
    if cta_url and cta_label:
        parts.append(
            '  <tr><td style="padding:14px 0 0 0;">'
            f'<a href="{cta_url}" style="font-size:15px; color:#2563eb; '
            f'text-decoration:underline;">{cta_label}</a>'
            '</td></tr>')
    parts.append('</table>')
    return "\n".join(parts)


def _campaign_prompt_block(campaign):
    """The campaign section injected into the email system prompt."""
    facts = campaign.get('key_facts') or []
    facts_block = "\n".join(f"- {f}" for f in facts) if facts else "(none)"
    tone = (campaign.get('tone_notes') or '').strip()
    cta_label = (campaign.get('cta_label') or '').strip()
    return f"""

---

## CAMPAIGN MODE — THIS SECTION OVERRIDES THE RULES ABOVE

This email is a client campaign. Where anything above conflicts with this section,
this section wins. Specifically, and overriding the objective/structure above:

- There are NO curated articles or blog posts in this email. Do not reference,
  summarise, or promise any.
- The word limit above does not apply. Cover the source content properly;
  roughly 120-220 words of prose is right.
- The body of this email IS the source content below, rewritten for this
  candidate. Do not replace it with a generic check-in. An email that opens with
  a line about the candidate and then closes without conveying the source
  content is a FAILURE.

Structure: greeting, one or two sentences connecting to the candidate, then the
campaign content, then the sign-off.

FORMATTING (overrides the formatting rules above):
- Emoji: keep the source content's emoji, in the same places. Any "no emojis"
  rule above does not apply to campaigns -- the client wrote them deliberately.
- Lists: when the source presents items as a list, render each item as its own
  line, never run together inside one paragraph. Emit them as consecutive
  paragraph tags with no blank line between them, like:
  <p style="margin: 0 0 8px 0; font-size: 15px; color: #111827; line-height: 1.6;">🎯 49% of reps are over 100% attainment</p>
  <p style="margin: 0 0 8px 0; font-size: 15px; color: #111827; line-height: 1.6;">🚀 Ramped reps average 117% attainment</p>
  Keep the leading emoji on each line if the source has one.
  Never put a list item on the same line as the sentence introducing it --
  the lead-in sentence ends, then each item starts its own line.

You are writing this email from client-supplied source material. Rewrite it so it
reads naturally for THIS candidate -- vary the phrasing, adjust emphasis to their
background -- but the substance, claims, and offer must stay exactly as given.

SOURCE CONTENT:
\"\"\"
{(campaign.get('source_content') or '').strip()}
\"\"\"

MUST APPEAR VERBATIM (copy these exactly; never round, reword, or drop them):
{facts_block}

{f"TONE: {tone}" if tone else ""}

RULES:
- Do NOT invent statistics, customers, benefits, or claims beyond the source content.
- Do NOT emit any image tag, blog card, or link yourself. Instead place the literal
  token {CAMPAIGN_CARD_TOKEN} on its own line where the image belongs (usually after
  the opening paragraphs). It is replaced with the real image and call-to-action.
- Do NOT write your own call-to-action link{f' (the CTA "{cta_label}" is added for you)' if cta_label else ''}.
- Keep the greeting and sign-off conventions described above.
"""


def _select_campaign_subject(subjects, first_name, current_title, current_company):
    """Pick one of the client's subject lines and return it unchanged.

    The client wrote and approved these, so the model chooses between them rather
    than writing its own -- left to generate freely it paraphrases them into
    something the client never signed off on.
    """
    subjects = [s for s in subjects if (s or '').strip()]
    if not subjects:
        return None
    if len(subjects) == 1:
        return subjects[0]
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(subjects))
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"A recruiter is emailing {first_name}, a {current_title} at "
                f"{current_company}. Which ONE of these subject lines fits them best?\n\n"
                f"{numbered}\n\nReply with the number only."
            )}],
            temperature=0.7,
            max_tokens=5,
        )
        choice = re.search(r'\d+', resp.choices[0].message.content or '')
        if choice:
            idx = int(choice.group()) - 1
            if 0 <= idx < len(subjects):
                return subjects[idx]
    except Exception as e:
        logger.warning(f"Campaign subject selection failed ({e}); using the first line")
    return subjects[0]


def _missing_key_facts(email_body, campaign):
    """Return key facts absent from the generated body.

    LLM rewriting can silently round '49%' to 'nearly half' or drop a figure, which
    would publish inaccurate claims about a real company, so generation is checked
    rather than trusted.
    """
    missing = []
    haystack = re.sub(r'<[^>]+>', ' ', email_body or '')
    haystack = re.sub(r'\s+', ' ', haystack)
    for fact in (campaign.get('key_facts') or []):
        needle = re.sub(r'\s+', ' ', str(fact)).strip()
        if needle and needle.lower() not in haystack.lower():
            missing.append(fact)
    return missing


# Company-scoped pinned blogs: ALWAYS shown first, with the remaining slot(s)
# auto-matched per candidate. Contrast COMPANY_FORCED_BLOGS, which replaces
# matching entirely. Same entry shape and per-card overrides as that dict, and
# URLs must likewise already exist in blog_posts for the same company.
COMPANY_PINNED_BLOGS = {
    "Genesys": [
        {
            "url": "https://www.youtube.com/watch?v=VnEow5S2QJ8",
            "card_blurb": (
                "Enterprise Account Director Henry Finbow on why he joined Genesys "
                "and what it's like building AI-powered experience orchestration."
            ),
            # Nurture lead-in. It's an employer-brand video, so it's framed as
            # something shared, not as a match to the candidate's interests.
            "intro": "I wanted to share a short video from our team: Henry Finbow on why "
                     "he chose Genesys and what it's like building what's next in AI.",
            # Lead-in when the email is job-focused.
            "job_email_intro": "In the meantime, here's a 71-second look at what it's "
                               "like to build what's next at Genesys:",
        },
    ],
}


def _apply_blog_overrides(blogs, entries):
    """Copy per-card overrides (intro, card_blurb, image_fit) onto matched blogs."""
    overrides = {e['url']: e for e in entries if isinstance(e, dict) and e.get('url')}
    for b in blogs:
        e = overrides.get(b.get('blog_url'))
        if not e:
            continue
        if e.get('intro'):
            b['email_intro'] = e['intro']
        if e.get('card_blurb'):
            b['email_card_blurb'] = e['card_blurb']
        if e.get('image_fit'):
            b['email_image_fit'] = e['image_fit']
    return blogs


def match_blogs_for_candidate_internal(candidate_id, company=None):
    """
    Internal: Find matching blogs for a candidate using hybrid approach
    Returns: list of LLM-selected blog matches (top 2), or the company's forced
    blogs verbatim when company is configured in COMPANY_FORCED_BLOGS.
    """
    try:
        # Company-forced override: return exactly the configured blogs, skip matching.
        forced_entries = COMPANY_FORCED_BLOGS.get(company, []) if company else []
        if forced_entries:
            # Entries may be plain URL strings or {url, intro} dicts.
            forced_urls = [e['url'] if isinstance(e, dict) else e for e in forced_entries]
            forced = matcher.get_pinned_blogs_details(forced_urls, company=company)
            if forced:
                _apply_blog_overrides(forced, forced_entries)
                logger.info(f"Using {len(forced)} company-forced blog(s) for '{company}'; skipping auto-match")
                return forced
            logger.warning(f"Forced blog URLs for '{company}' not found in blog_posts; falling back to auto-match")

        logger.info(f"Finding blog matches for {candidate_id} using hybrid LLM approach...")

        # Use hybrid approach: embeddings get top 30, LLM selects best 3
        # Company pins lead; the matcher fills the remaining slot(s) per candidate.
        pinned_entries = COMPANY_PINNED_BLOGS.get(company, []) if company else []
        pinned_urls = [e['url'] if isinstance(e, dict) else e for e in pinned_entries]
        selected_blogs = matcher.find_blogs_for_candidate_hybrid(
            candidate_id,
            match_threshold=0.25,
            top_n_embeddings=30,  # LLM reviews 30 candidates
            final_n_llm=2,         # LLM selects best 2 (total, including any pinned)
            company=company,
            extra_pinned_urls=pinned_urls
        )
        if selected_blogs and pinned_entries:
            _apply_blog_overrides(selected_blogs, pinned_entries)

        if not selected_blogs:
            logger.info(f"No blog matches found for {candidate_id}")
            return []

        logger.info(f"LLM selected {len(selected_blogs)} blogs from 30 candidates")
        return selected_blogs
    except Exception as e:
        logger.error(f"Error matching blogs: {str(e)}")
        return []




def _candidate_work_history(candidate_profile):
    """Return (history_lines, total_years) for a candidate, or ([], None).

    The RPC that loads candidates for matching returns only name/title/summary --
    no dates and no employment history -- so the evaluator was rejecting senior
    people for "possibly not meeting the years requirement" while having no way
    to see how long they had actually worked. Pull the history out of the stored
    raw_profile instead.
    """
    candidate_id = candidate_profile.get('candidate_id')
    if not candidate_id:
        return [], None
    try:
        row = matcher.supabase.table('candidate_profiles').select('raw_profile') \
            .eq('candidate_id', candidate_id).execute().data
    except Exception as e:
        logger.warning(f"Could not load work history for {candidate_id}: {e}")
        return [], None
    if not row:
        return [], None
    raw = row[0].get('raw_profile')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [], None
    if not isinstance(raw, dict):
        return [], None

    def _parse(d):
        if not d:
            return None
        try:
            return datetime.strptime(str(d)[:10], "%Y-%m-%d")
        except ValueError:
            return None

    entries = []
    for w in raw.get('workexp') or []:
        company = ((w.get('company') or {}).get('name') or '').strip()
        projects = w.get('projects') or []
        title = ''
        if projects:
            title = ((projects[0].get('role_and_group') or {}).get('title') or '').strip()
        dur = w.get('duration') or {}
        start = _parse(dur.get('start_date'))
        end = _parse(dur.get('end_date'))
        present = bool(dur.get('to_present')) or (dur.get('end_date') is None and start is not None)
        if not (company or title):
            continue
        entries.append({'company': company, 'title': title, 'start': start,
                        'end': end, 'present': present})
    if not entries:
        return [], None

    starts = [e['start'] for e in entries if e['start']]
    if starts:
        earliest = min(starts)
        ends = [e['end'] for e in entries if e['end']]
        latest = datetime.utcnow() if any(e['present'] for e in entries) else (max(ends) if ends else None)
        total_years = round((latest - earliest).days / 365.25, 1) if latest else None
    else:
        total_years = None

    entries.sort(key=lambda e: e['start'] or datetime.min, reverse=True)
    lines = []
    for e in entries[:8]:
        span = ''
        if e['start']:
            span = e['start'].strftime('%Y-%m') + ' to ' + (
                'present' if e['present'] else (e['end'].strftime('%Y-%m') if e['end'] else '?'))
        lines.append(f"- {e['title'] or 'Role'} at {e['company'] or 'Unknown'}"
                     + (f" ({span})" if span else ""))
    return lines, total_years


def evaluate_job_match_with_llm(candidate_profile, job, semantic_similarity):
    """
    Use LLM to evaluate if candidate is a genuine match for the job
    Returns: dict with is_match, confidence, reasoning, or None if evaluation fails

    `semantic_similarity` is deliberately NOT shown to the model. When it was,
    the returned match_score tracked it almost one-for-one -- the same profile
    scored 39-45 when shown 39%, 60 when shown 60%, and 85 when shown 85% --
    so this stage echoed stage 1 instead of judging fit on the evidence. Stage 1
    already gates on similarity; this stage must be independent of it.
    """
    try:
        # Extract candidate information
        candidate_name = candidate_profile.get('full_name', 'Candidate')
        candidate_title = candidate_profile.get('current_title', '')
        candidate_summary = candidate_profile.get('professional_summary', '')
        candidate_preferences = candidate_profile.get('job_preferences', '')

        # Real employment history, so seniority and years-of-experience are
        # judged on evidence rather than inferred from the job title.
        history_lines, total_years = _candidate_work_history(candidate_profile)
        history_block = "\n".join(history_lines) if history_lines else "- Not available"

        # Skills were never reaching the evaluator, so requirements like
        # "knowledge of the telecommunications industry" were judged blind --
        # a candidate listing GSM and Mobile Communications was rejected as
        # having no telecom exposure.
        candidate_skills = candidate_profile.get('skills') or []
        if isinstance(candidate_skills, str):
            try:
                candidate_skills = json.loads(candidate_skills)
            except json.JSONDecodeError:
                candidate_skills = [candidate_skills]
        seen_skills, skill_list = set(), []
        for sk in candidate_skills if isinstance(candidate_skills, list) else []:
            label = str(sk).strip()
            if label and label.lower() not in seen_skills:
                seen_skills.add(label.lower())
                skill_list.append(label)
        skills_line = ", ".join(skill_list[:40]) if skill_list else "Not available"
        experience_line = (f"{total_years} years (earliest role to present)"
                           if total_years is not None else "Not available")

        # Extract job information
        job_title = job.get('position', '')
        job_description = job.get('about_role', '')
        job_requirements = job.get('requirements', {})

        # Parse requirements if it's a string
        if isinstance(job_requirements, str):
            try:
                job_requirements = json.loads(job_requirements)
            except:
                job_requirements = {}

        must_have = job_requirements.get('must_have', []) if isinstance(job_requirements, dict) else []
        nice_to_have = job_requirements.get('nice_to_have', []) if isinstance(job_requirements, dict) else []

        # Build evaluation prompt
        evaluation_prompt = f"""Evaluate if this candidate is a genuine match for this job opening.

CANDIDATE:
Name: {candidate_name}
Current Title: {candidate_title}
Professional Summary: {candidate_summary[:400]}
Job Preferences: {candidate_preferences}
Skills: {skills_line}
Total Professional Experience: {experience_line}
Work History (most recent first):
{history_block}

JOB OPENING:
Position: {job_title}
About Role: {job_description[:400]}
Must-Have Requirements: {', '.join(must_have[:5]) if must_have else 'Not specified'}
Nice-to-Have: {', '.join(nice_to_have[:3]) if nice_to_have else 'Not specified'}

EVALUATION CRITERIA:
1. **Role Type Match** (CRITICAL): Does the candidate's core profession align with the job type?
   - Engineer should match Engineer roles (regardless of specific tech stack)
   - Designer should match Designer roles
   - PM should match PM roles
   - REJECT if core profession mismatches (e.g., Designer applying to Engineer role)

2. **Seniority Match**: Does the candidate's level appropriately match the job level?
   - A single level step up is EXPECTED and ACCEPTABLE. Outreach exists to find
     people ready for their next role. A Senior Director applying to an Executive
     Director role, or a Director to a Senior Director role, is a normal
     progression -- ACCEPT it when the other criteria are met.
   - Do NOT reject solely because the candidate's current title differs from the
     posted title, and do not invent concerns about "executive presence" or
     "strategic oversight" that the profile simply does not speak to.
   - Reject on seniority ONLY for a gap of two or more levels (e.g. an individual
     contributor applying to a VP role) or a clear step down.
   - Use the Total Professional Experience and Work History above to judge years
     of experience. Do NOT speculate that the candidate may not meet a years
     requirement when the stated total already satisfies it, and do not treat a
     missing detail as a shortfall.

3. **Transferable Skills**: For senior technical roles, evaluate based on:
   - Strong fundamentals and problem-solving ability matter more than specific tech
   - Domain expertise is valuable but not always required
   - Senior engineers can learn new stacks/tools quickly

4. **Core Requirements**: Do they meet the fundamental must-have requirements?
   - When a requirement lists alternatives ("Government, Strategic, or
     Enterprise"), meeting ANY ONE of them satisfies it. Do not require all of
     them, and do not reject for lacking one alternative when another is met.
   - A title or summary naming the segment (e.g. "Enterprise", "Global
     Enterprise", "Strategic Accounts", "Public Sector") is evidence of it.
   - A requirement for KNOWLEDGE of an industry can be evidenced by relevant
     skills or by work at a company in that industry; it is not the same as
     requiring years employed in that industry. Check the Skills line before
     calling it missing. If there is genuinely no evidence, it is a real gap.
   - Focus on core competencies, not specific technologies
   - "Strong coding skills" matters more than "experience with Tool X"

5. **Career Logic**: Would this role make sense for their career trajectory?

Respond ONLY with valid JSON in this exact format:
{{
  "is_match": true/false,
  "confidence": "high/medium/low",
  "match_score": 0-100,
  "reasoning": "1-2 sentence explanation focusing on the key factor",
  "key_alignments": ["alignment1", "alignment2"],
  "concerns": ["concern1", "concern2"]
}}

IMPORTANT: Be realistic about senior roles - strong fundamentals and domain match matter more than an exact title match. ONLY reject if there's a core profession mismatch (e.g., Designer for Engineer role), a genuine shortfall against a stated must-have (such as a required degree the candidate does not hold), or a seniority gap of two or more levels. A one-level step up is not a reason to reject."""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter evaluating candidate-job fit. Be precise and honest in your assessments."},
                {"role": "user", "content": evaluation_prompt}
            ],
            # Deterministic on purpose: this call decides whether a candidate gets
            # a job email or a nurture email. At 0.3 a borderline profile flipped
            # between the two on identical input (5/5 job-focused, then 1/5 an
            # hour later, with nothing changed).
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        evaluation = json.loads(response.choices[0].message.content.strip())
        return evaluation

    except Exception as e:
        logger.error(f"Error in LLM job evaluation: {str(e)}")
        return None


def match_candidate_to_jobs(candidate_id, match_threshold=0.35, company=None):
    """
    Internal: Match candidate to open job postings using two-stage process:
    1. Semantic similarity search (threshold: 35%)
    2. LLM evaluation for genuine role fit
    Returns: list of LLM-confirmed matching jobs (max 2 best matches)
    """
    try:
        logger.info(f"Matching candidate {candidate_id} to open jobs...")

        # Get candidate embedding and profile
        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            logger.warning(f"Candidate {candidate_id} not found")
            return []

        # Get professional summary embedding (primary matching signal)
        prof_embedding = candidate_profile.get('professional_summary_embedding')
        if not prof_embedding:
            # Fallback to legacy embedding
            prof_embedding = candidate_profile.get('embedding')

        if not prof_embedding:
            logger.warning(f"No embedding found for candidate {candidate_id}")
            return []

        # Convert string representation to list if needed (Supabase may return as string)
        if isinstance(prof_embedding, str):
            try:
                prof_embedding = json.loads(prof_embedding)
                logger.info(f"Converted embedding from string to list ({len(prof_embedding)} dimensions)")
            except json.JSONDecodeError:
                logger.error(f"Failed to parse embedding string for candidate {candidate_id}")
                return []

        # Get all active jobs
        supabase = matcher.supabase
        query = supabase.table('job_postings')\
            .select('*')\
            .eq('status', 'active')

        if company:
            query = query.eq('company', company)

        active_jobs = query.execute()

        if not active_jobs.data:
            logger.info("No active jobs found")
            return []

        logger.info(f"Found {len(active_jobs.data)} active jobs")

        # STAGE 1: Semantic similarity search
        logger.info("Stage 1: Running semantic similarity search...")
        semantic_candidates = []

        for job in active_jobs.data:
            # Create comprehensive job text for matching
            job_text = f"{job['position']}\n{job['about_role']}"

            # Add requirements if available
            if job.get('requirements'):
                reqs = json.loads(job['requirements']) if isinstance(job['requirements'], str) else job['requirements']
                must_have = reqs.get('must_have', [])
                if must_have:
                    job_text += f"\n\nRequired: {', '.join(must_have[:5])}"

            # Generate embedding for job
            job_embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=job_text
            )
            job_embedding = job_embedding_response.data[0].embedding

            # Calculate cosine similarity
            prof_vec = np.array(prof_embedding)
            job_vec = np.array(job_embedding)
            similarity = np.dot(prof_vec, job_vec) / (np.linalg.norm(prof_vec) * np.linalg.norm(job_vec))

            if similarity >= match_threshold:
                semantic_candidates.append({
                    'job': job,
                    'similarity': float(similarity)
                })

        logger.info(f"Stage 1 complete: {len(semantic_candidates)} jobs passed semantic threshold")

        if not semantic_candidates:
            logger.info("No jobs met semantic similarity threshold")
            return []

        # Sort by similarity
        semantic_candidates.sort(key=lambda x: x['similarity'], reverse=True)

        # STAGE 2: LLM evaluation for top candidates
        logger.info("Stage 2: Running LLM evaluation on semantic matches...")
        confirmed_matches = []

        for candidate in semantic_candidates[:5]:  # Evaluate top 5 semantic matches
            job = candidate['job']
            similarity = candidate['similarity']

            logger.info(f"  Evaluating: {job['position']} (semantic: {similarity:.2%})")

            # Ask LLM to evaluate the match
            evaluation = evaluate_job_match_with_llm(candidate_profile, job, similarity)

            if evaluation and evaluation.get('is_match'):
                # Include ALL job data from database (including JSONB fields)
                job_match = dict(job)
                job_match['similarity'] = similarity
                job_match['llm_evaluation'] = {
                    'confidence': evaluation.get('confidence', 'unknown'),
                    'match_score': evaluation.get('match_score', 0),
                    'reasoning': evaluation.get('reasoning', ''),
                    'key_alignments': evaluation.get('key_alignments', []),
                    'concerns': evaluation.get('concerns', [])
                }
                confirmed_matches.append(job_match)

                logger.info(f"    ✅ CONFIRMED by LLM (confidence: {evaluation.get('confidence')})")
                logger.info(f"    Reasoning: {(evaluation.get('reasoning') or '')[:100]}")
            else:
                reason = evaluation.get('reasoning', 'No match') if evaluation else 'Evaluation failed'
                logger.info(f"    ❌ REJECTED by LLM: {reason[:100]}")

        # Return top 2 LLM-confirmed matches
        top_matches = confirmed_matches[:2]

        if top_matches:
            logger.info(f"Stage 2 complete: {len(top_matches)} jobs confirmed by LLM")
            for job in top_matches:
                logger.info(f"  - {job['position']} (semantic: {job['similarity']:.2%}, LLM confidence: {job['llm_evaluation']['confidence']})")
        else:
            logger.info("No jobs confirmed by LLM evaluation")

        return top_matches

    except Exception as e:
        logger.error(f"Error matching candidate to jobs: {str(e)}", exc_info=True)
        return []


# A line that opens with a bullet glyph, a dash, a number, or a leading emoji is
# treated as a list item and kept on its own line.
_EMOJI_CLASS = (r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF'
                r'\U0001F1E6-\U0001F1FF]')
# A colon followed by a leading-emoji list item, mid-line.
_LEADIN_ITEM = re.compile(r':\s+(?=' + _EMOJI_CLASS + r'+\s)')

_IS_LIST_LINE = re.compile(
    r'^(?:[\u2022\u2023\u25E6\u2043\u2219*]|[-\u2013\u2014]\s|\d+[.)]\s'
    r'|[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\U0001F1E6-\U0001F1FF]+\s)'
)


def _wrap_bare_paragraphs(body):
    """Guarantee consistent paragraph spacing regardless of LLM compliance.

    The model is instructed to wrap each prose paragraph in a styled <p>, but it
    sometimes emits bare text separated by blank lines instead — which email
    clients collapse to a single space, destroying paragraph spacing. This splits
    the body on blank lines and wraps any block that isn't already HTML.
    """
    para_style = "margin: 0 0 16px 0; font-size: 15px; color: #111827; line-height: 1.6;"
    item_style = "margin: 0 0 8px 0; font-size: 15px; color: #111827; line-height: 1.6;"
    out = []
    for block in re.split(r'\n\s*\n', body.strip()):
        s = block.strip()
        if not s:
            continue
        if s.startswith('<'):
            out.append(s)  # already HTML (a <p>, the card <table>, etc.)
            continue
        # Join wrapped prose lines into one paragraph, but keep list items on
        # their own lines: joining them produced run-together stats like
        # "Kong: - 49% of reps ... - Ramped reps ...".
        run = []
        lines = []
        for raw in s.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            # Models reliably glue the first item onto its lead-in sentence
            # ("Here's what it looks like: 🎯 49% ..."), which no prompt wording
            # fixed; split it back apart here.
            m = _LEADIN_ITEM.search(raw)
            if m and not _IS_LIST_LINE.match(raw):
                lines.append(raw[:m.start() + 1].strip())
                lines.append(raw[m.end():].strip())
            else:
                lines.append(raw)
        for line in lines:
            if not line:
                continue
            if _IS_LIST_LINE.match(line):
                if run:
                    out.append(f'<p style="{para_style}">{" ".join(run)}</p>')
                    run = []
                out.append(f'<p style="{item_style}">{line}</p>')
            else:
                run.append(line)
        if run:
            out.append(f'<p style="{para_style}">{" ".join(run)}</p>')
    return '\n'.join(out)


def _blog_source_label(url):
    """Return a human label when a blog URL points to a social media post, else None."""
    u = (url or '').lower()
    if 'linkedin.com' in u:
        return 'LinkedIn post'
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'YouTube video'
    if 'x.com' in u or 'twitter.com' in u:
        return 'X post'
    return None


def generate_email_content(candidate_info, blog_recommendations, semantic_summary, job_matches=None, email_feedback=None, company=None, campaign=None):
    """
    Internal: Generate personalized nurture email using LLM

    Args:
        candidate_info: Candidate profile information
        blog_recommendations: List of matching blog posts
        semantic_summary: Combined candidate summaries
        job_matches: Optional list of matching job openings
        email_feedback: Optional dict keyed by email type ('job-focused', 'relationship-nurture') with feedback strings
        company: Optional sender company name; used to append the company's stored email signature
    """
    # Extract candidate details
    name = candidate_info.get('full_name', 'there')
    first_name = name.split()[0] if name else 'there'
    current_title = candidate_info.get('current_title', '')
    current_company = candidate_info.get('current_company', '')

    # Extract and format work history
    work_exp = candidate_info.get('work_experience', [])
    work_history_formatted = []
    if work_exp and isinstance(work_exp, list):
        for exp in work_exp[:3]:  # Top 3 positions
            if isinstance(exp, dict):
                company_name = exp.get('company', {}).get('name', '') if isinstance(exp.get('company'), dict) else exp.get('company', '')
                job_title = exp.get('title', '')
                if company_name and job_title:
                    work_history_formatted.append(f"{company_name}: {job_title}")

    work_history_str = '\n'.join(work_history_formatted) if work_history_formatted else f"{current_company}: {current_title}"

    # Split semantic_summary into its three components
    # semantic_summary is combined_summary which contains: professional_summary + job_preferences + interests
    summary_parts = semantic_summary.split('\n\n', 2)
    professional_summary = summary_parts[0] if len(summary_parts) > 0 else semantic_summary
    job_preferences = summary_parts[1] if len(summary_parts) > 1 else ''
    professional_interests = summary_parts[2] if len(summary_parts) > 2 else ''

    # Format blog posts for LLM
    blog_list = []
    for blog in blog_recommendations:
        entry = {
            'title': blog['blog_title'],
            'url': blog['blog_url'],
            'featured_image': blog.get('blog_featured_image', 'https://via.placeholder.com/200x120/2563eb/ffffff?text=Blog'),
            'excerpt': (blog.get('best_matching_chunk') or '')[:200]
        }
        # Optional per-blog framing that overrides the default "why relevant" line.
        if blog.get('email_intro'):
            entry['suggested_intro'] = blog['email_intro']
        # Source label for social posts (rendered under the card title).
        source_label = _blog_source_label(blog['blog_url'])
        if source_label:
            entry['source'] = source_label
        # Optional short blurb rendered under the card title.
        if blog.get('email_card_blurb'):
            entry['card_blurb'] = blog['email_card_blurb']
        # Optional image fit override ('contain' to avoid cropping); default 'cover'.
        if blog.get('email_image_fit'):
            entry['image_fit'] = blog['email_image_fit']
        blog_list.append(entry)

    # Job matches have already been evaluated by LLM in match_candidate_to_open_jobs()
    # No need for additional evaluation - use the matches that were already confirmed
    job_list = []
    if job_matches and len(job_matches) > 0:
        for job in job_matches[:3]:  # Max 3 jobs for email
            entry = {
                'position': job['position'],
                'company': job.get('company', ''),
                'location_type': job.get('location_type', ''),
                'location': f"{job.get('location_city') or ''}, {job.get('location_country') or ''}".strip(', '),
                'about_role': (job.get('about_role') or '')[:250],
                'application_link': job.get('application_link', ''),
                'match_score': f"{(job.get('similarity') or 0) * 100:.0f}%",
                'similarity': job.get('similarity') or 0,
                'llm_reasoning': job.get('llm_evaluation', {}).get('reasoning', '') if isinstance(job.get('llm_evaluation'), dict) else ''
            }
            # Many postings publish no salary. The columns are then NULL, and
            # .get(key, 0) returns None rather than 0, so formatting crashed
            # generation for every job-focused email. Omit the field instead of
            # showing "Not disclosed", which invites the model to comment on it.
            comp_min, comp_max = job.get('compensation_min'), job.get('compensation_max')
            if isinstance(comp_min, (int, float)) and isinstance(comp_max, (int, float)):
                entry['compensation'] = (f"{job.get('compensation_currency') or ''} "
                                         f"{comp_min:,.0f} - {comp_max:,.0f}").strip()
            job_list.append(entry)

    # Decide which email approach to use
    # If jobs were confirmed by the matching LLM, use job-focused approach
    use_job_focused_approach = len(job_list) > 0

    # A campaign supplies its own content and its own card, so it takes over the
    # body entirely: no blog cards, and the nurture voice unless it says otherwise.
    if campaign:
        blog_list = []
        if (campaign.get('email_type') or 'nurture') != 'job':
            use_job_focused_approach = False

    # Build context for email generation (using clearer variable names)
    # A campaign replaces the curated-article section as the email's subject matter;
    # otherwise the model sees an empty blog list and writes a contentless note.
    if campaign:
        facts = campaign.get('key_facts') or []
        content_section = (
            "CAMPAIGN CONTENT — this is what this email is about. Cover this "
            "material; do not substitute your own topic:\n\"\"\"\n"
            + (campaign.get('source_content') or '').strip()
            + "\n\"\"\"\n\nMUST APPEAR VERBATIM: "
            + (", ".join(str(f) for f in facts) if facts else "(none)")
        )
    else:
        content_section = "Recommended Blog Posts:\n" + json.dumps(blog_list, indent=2)

    email_context = f"""Candidate Name: {name}
Current Role: {current_title} at {current_company}

Professional Summary:
{professional_summary}

Job Preferences:
{job_preferences}

Professional Interests:
{professional_interests}

Work History:
{work_history_str}

Matching Job Openings (if any):
{json.dumps(job_list, indent=2) if job_list else 'No matching jobs found'}

{content_section}
"""

    # Use LLM to generate the email
    # Choose prompt based on email approach
    if use_job_focused_approach:
        # JOB-FOCUSED APPROACH: Lead with opportunity
        system_prompt = """You are a recruiter reaching out about a specific job opportunity that matches the candidate's background. Your tone is direct, professional, and opportunity-focused while remaining personable.

TONE & STYLE:
- Direct and clear about the opportunity
- Professional but warm — you're excited about this match
- Confident that this role aligns with their career trajectory
- Personal touches still matter — show you understand their background
- No emojis

STRUCTURE:
- GREETING LINE: Start with their first name: "Hi [Name],"
- OPENING (2-3 sentences): Directly introduce why you're reaching out — mention the specific role and why their background caught your attention for THIS position
- JOB CARD SECTION: Present the job opportunity prominently
- BRIEF CONTEXT (2-3 sentences): Explain why this role fits their background
- CLEO MENTION (1 sentence): "If you have any questions about the role, feel free to reach out to Cleo."
- CLOSING: Clear call-to-action to discuss the opportunity

OPENING EXAMPLES:

Example 1:
"Hi [Name],

I'm reaching out because we have a [Position Title] role at [Company] that seems like a strong match for your background. Given your experience in [specific domain/skill], I thought this might be worth exploring."

Example 2:
"Hi [Name],

Your experience as [current role] at [company], particularly your work in [specific area], caught my attention for our [Position Title] opening. I think there's a compelling fit here."

Example 3:
"Hi [Name],

I wanted to reach out about a [Position Title] opportunity at [Company]. With your background spanning [domain A] and [domain B], you're exactly the kind of professional we're looking for."

JOB CARD FORMAT (use this HTML structure for EACH job - if multiple jobs, include multiple cards):
<div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0; background: #ffffff;">
  <h2 style="margin: 0 0 8px 0; font-size: 18px; color: #1f2937; font-weight: 600;">
    <a href="[APPLICATION_LINK]" style="color: #2563eb; text-decoration: none;">[POSITION]</a>
  </h2>
  <div style="color: #6b7280; font-size: 14px; margin-bottom: 8px;">
    <strong style="color: #374151;">[COMPANY]</strong> • [LOCATION_TYPE] • [LOCATION]
  </div>
  <div style="color: #059669; font-size: 14px; font-weight: 600; margin-bottom: 10px;">
    [COMPENSATION]
  </div>
  <p style="color: #374151; font-size: 15px; line-height: 1.5; margin: 0 0 10px 0;">
    [2-3 key highlights about the role from about_role - make it specific and compelling]
  </p>
  <div style="margin-top: 12px;">
    <a href="[APPLICATION_LINK]" style="display: inline-block; background: #2563eb; color: white; padding: 10px 24px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 14px;">
      View Full Details
    </a>
  </div>
</div>

BRIEF CONTEXT (after job card - keep it short):
- 2-3 sentences max explaining why this role fits
- Reference their specific experience or skills

Example:
"Your background in [specific domain] and experience at [company] align well with what we're looking for. This role would let you [key opportunity]."

CLEO MENTION (exactly as shown):
"If you have any questions about the role, feel free to reach out to Cleo."

CLOSING EXAMPLES (clear CTA):
- "Would you be open to a 15-minute call this week to discuss?"
- "If this sounds interesting, I'd love to set up a quick call to share more details."
- "Let me know if you'd like to chat — happy to walk through the role and answer any questions."
- "Are you available for a brief conversation in the next few days?"

Sign-off: "Best,"

CRITICAL RULES:
- NO subject line in the email body (will be generated separately)
- NO signature name after "Best," - just "Best,"
- Lead with the job opportunity — that's the primary purpose
- Use job card HTML format EXACTLY as shown for EACH job in the context
- If multiple jobs are provided, include a card for each
- Keep content after job card CONCISE
- ALWAYS include: "If you have any questions about the role, feel free to reach out to Cleo."
- Clear call-to-action at the end
- Keep overall email focused and not too long
- DO NOT include any blog posts or articles — this is purely about the job opportunity"""

    else:
        # RELATIONSHIP-NURTURE APPROACH: Warm Professional Career Check-In
        system_prompt = """# Nurture Email System Prompt — v2

You are a relationship-driven recruiter writing to warm, experienced candidates you've
engaged with before. Your tone is that of a trusted peer who understands their work and is
checking in — personal but professional, never salesy or fawning.

Every email must read as custom-written. Vary openings, sentence structure, and phrasing so
no two emails feel templated.

---

## INPUT DATA CONTRACT

You will be given structured facts about the candidate (current company, role, recent
work/launches, tenure, prior roles, focus areas, the curated blog list with titles/URLs/images).

- Use ONLY facts you are actually given. Never infer, embellish, or invent accomplishments,
  motivations, or "knacks."
- If a specific hook (a launch, a named project, a notable transition) is NOT in the data,
  do NOT manufacture praise to fill the gap. Use a neutral, grounded opener instead
  (see OPENING fallback).
- Never emit an unfilled placeholder like [Company] or [field] in the final email. If a
  required fact is missing, rephrase around it.

---

## OBJECTIVE

A concise, authentic career check-in that:
- Opens with something specific and true about their work or path
- Optionally asks one genuine, forward-looking question (omit if it would feel forced)
- Shares 1–2 curated articles (never more than 2), each with a personal reason it's relevant to THEM
- Ends with a light, open invitation to reconnect

Length: under 200 words of prose before the blog section.

---

## 0. GREETING (required, always first)

Always begin the email with a greeting line addressed to the candidate by their FIRST name:
`Hi [First Name],` (e.g. "Hi Rob,"). Use the candidate's actual first name from the provided
data — never leave a literal placeholder like [First Name] or [candidate_name] in the output.
This greeting is its own paragraph and must come before the opening.

## 1. OPENING (2–3 sentences)

Pick ONE angle and ground it in a specific fact from the data:
- A specific recent launch, project, or result they own
- A specific, non-obvious move in their path (a role change, a domain shift)
- A specific industry development that intersects their actual work

FALLBACK (use when no specific hook exists in the data): a short, honest, low-key opener that
doesn't pretend to insider knowledge. E.g. "Been following the space you're in at [Company] and
wanted to stay in touch." Better a plain true sentence than invented praise.

DO NOT WRITE (these are banned patterns — they read as AI-generated flattery):
- "Your tenure at X really underscores your knack for…"
- "It's impressive how you've harnessed…"
- "X years at Y really speaks to your depth in…"
- Any sentence whose only content is praise with no specific fact behind it.

## 2. CAREER QUESTION (optional, 1 sentence)

If — and only if — you can ask something that shows real understanding of their trajectory,
ask ONE short, open question. Otherwise omit it entirely; a forced question is worse than none.

- NEVER use a forced either/or ("are you focused on A or B?"). Real people don't answer those.
- Prefer genuinely open questions: "What's the kind of problem you're most interested in next?"

## 3. TRANSITION (1 line) — vary every time

E.g. "A few things I came across that felt relevant:" / "Sharing a couple of reads in case
they're useful:" / "Thought these were worth passing along:"

Match the count: for a SINGLE article do not use plural phrasing ("these", "a couple",
"a few"). OMIT the transition line entirely when there is only one article OR when that
article has a "suggested_intro" — in those cases the intro sentence is the lead-in and a
separate transition would be redundant.

## 4. BLOG SECTION — use this EXACT HTML per article

For each blog, write ONE specific sentence on why it's relevant to THIS person (tie it to a
named fact, or state a concrete takeaway from the piece — not vague "this could offer
perspective"), then the card.

EXCEPTION — if a blog includes a "suggested_intro" field, use that intro as the lead-in
sentence instead (you may lightly adapt the wording for flow, but keep its meaning and intent).
Frame it as something you're highlighting or sharing ("I wanted to highlight…", "Thought you'd
enjoy a look at…"), NOT as a match to their interests — do NOT write "given your interest in…"
or "this aligns with your background" for these.

```html
<p style="margin: 0 0 8px 0; font-size: 15px; color: #6b7280; line-height: 1.5;">[Why this matters to them — specific.]</p>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width: 100%; margin: 0 0 20px 0; border-collapse: collapse;">
  <tr>
    <td width="160" style="width: 160px; vertical-align: top; padding-right: 16px;">
      <a href="[BLOG_URL]" style="text-decoration: none;">
        <img src="[FEATURED_IMAGE_URL]" alt="[BLOG_TITLE]" width="160" height="92" style="width: 160px; height: 92px; object-fit: [IMAGE_FIT]; border-radius: 10px; display: block; border: 0;">
      </a>
    </td>
    <td style="vertical-align: top;">
      <a href="[BLOG_URL]" style="font-size: 15px; font-weight: 600; color: #101828; text-decoration: none; line-height: 1.35; display: block; margin: 0 0 4px 0;">[BLOG_TITLE]</a>
      <div style="font-size: 12px; font-weight: 500; color: #6b7280; line-height: 1.4; margin: 0 0 6px 0;">[SOURCE_LABEL]</div>
      <p style="font-size: 13px; color: #6b7280; line-height: 1.45; margin: 0;">[CARD_BLURB]</p>
    </td>
  </tr>
</table>
```

Conditional card lines (per blog data):
- [SOURCE_LABEL]: include this <div> ONLY if the blog has a "source" field; use its value
  verbatim (e.g. "LinkedIn post"). If there is no "source" field, OMIT the entire <div> line.
- [CARD_BLURB]: include this <p> ONLY if the blog has a "card_blurb" field; use its value
  verbatim (do not paraphrase). If there is no "card_blurb" field, OMIT the entire <p> line.

Image rules (do not change): use `<table>`, never `display:flex`. Keep `width`/`height` as
HTML attributes AND in the style. Keep `display:block` and `border:0`. Always include `alt`.
[IMAGE_FIT]: use the blog's "image_fit" value if provided, otherwise "cover". ("contain"
shows the entire image without cropping; "cover" fills the box and may crop.)
If no featured image is available, use: https://via.placeholder.com/160x92/2563eb/ffffff?text=Read

## 5. BODY PARAGRAPH FORMATTING

Wrap EACH prose paragraph (greeting, opening, question, transition, closing) in:
`<p style="margin: 0 0 16px 0; font-size: 15px; color: #111827; line-height: 1.6;">...</p>`
This guarantees consistent spacing across clients. Do not emit bare text outside a <p>.

## 6. CLOSING (1 line + sign-off) — vary every time

E.g. "Glad to compare notes whenever." / "Open to reconnecting when you have a window." /
"Around if it's ever useful to talk."
Sign-off: "Best," (no name — added separately)

---

## STYLE RULES

- Use contractions. Confident, not eager.
- Vary punctuation. Do NOT lean on em-dashes; avoid the "not just X, but Y" and "shifting from
  X to Y" constructions — they read as AI.
- Ground every compliment in a fact. No standalone praise.
- Avoid filler: "just reaching out," "touching base," "I wanted to," "I'm curious —."
- Never reuse the same opener, transition, or closing across consecutive emails.

## CRITICAL

- NO subject line in the body. NO name after "Best,". Under 200 words of prose.
- The HTML structure in sections 4 and 5 is FIXED and must be reproduced exactly.
- Do NOT mention specific jobs in this approach."""

    # Inject email feedback into system prompt if provided
    email_type = 'job-focused' if use_job_focused_approach else 'relationship-nurture'
    feedback_text = (email_feedback or {}).get(email_type, '').strip() if email_feedback else ''
    if feedback_text:
        system_prompt += f"""

## User Email Preferences (for {email_type} emails) — OVERRIDE
The user has specified the following preferences for how {email_type} emails should be written.
These preferences TAKE PRIORITY over any conflicting instructions above (including structure,
length, tone, paragraph count, and formatting rules). Where the user's preferences conflict
with the base prompt, follow the user's preferences.

"{feedback_text}"
"""

    if campaign:
        system_prompt = system_prompt + _campaign_prompt_block(campaign)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_context}
            ],
            temperature=0.85,
            max_tokens=2200
        )

        email_body = response.choices[0].message.content.strip()

        # Strip any accidental markdown code fences around the HTML
        if email_body.startswith("```"):
            email_body = re.sub(r'^```[a-zA-Z]*\n?', '', email_body)
            email_body = re.sub(r'\n?```$', '', email_body).strip()

        # Guarantee paragraph spacing even if the model emitted bare prose text.
        email_body = _wrap_bare_paragraphs(email_body)

        if campaign:
            missing = _missing_key_facts(email_body, campaign)
            if missing:
                logger.warning(
                    f"Campaign '{campaign.get('key')}': {len(missing)} key fact(s) "
                    f"missing from generated body: {missing}")

            # Swap the token for the real card. _wrap_bare_paragraphs may have
            # wrapped the token in a <p>, so match it with or without that wrapper.
            card_html = _build_campaign_card(campaign)
            token = re.escape(CAMPAIGN_CARD_TOKEN)
            pattern = rf'(?:<p[^>]*>\s*{token}\s*</p>|{token})'
            if re.search(pattern, email_body):
                email_body = re.sub(pattern, lambda _m: card_html, email_body, count=1)
                # Drop any stray extra tokens the model emitted.
                email_body = re.sub(pattern, '', email_body)
            elif card_html:
                # Model omitted the token; place the card before the sign-off if we
                # can find one, else append it.
                email_body = _insert_before_signoff(email_body, card_html)
                logger.info(f"Campaign '{campaign.get('key')}': card token missing, "
                            "inserted card automatically")

        # A company's pinned blogs are meant to appear in EVERY email. The job-focused
        # template has no blog section, so without this a candidate who matched the
        # job lost the pinned card. Built in code so the URL and image can't drift.
        if use_job_focused_approach and not campaign and company in COMPANY_PINNED_BLOGS:
            pinned_cfg = {e['url']: e for e in COMPANY_PINNED_BLOGS[company] if isinstance(e, dict)}
            pinned_blogs = [b for b in (blog_recommendations or []) if b.get('blog_url') in pinned_cfg]
            for b in pinned_blogs:
                cfg = pinned_cfg[b['blog_url']]
                intro = (cfg.get('job_email_intro') or cfg.get('intro')
                         or f"In the meantime, here's a quick look at life at {company}:")
                email_body = _insert_before_signoff(email_body, _build_blog_card(b, lead_in=intro))
            if pinned_blogs:
                logger.info(f"Added {len(pinned_blogs)} pinned card(s) to job-focused email for {company}")

        # Append the sender company's stored signature after the sign-off.
        # Kept outside the LLM so names/links/images render exactly as provided.
        if company:
            try:
                sig_result = matcher.supabase.table('customer_preferences').select(
                    'signature_html'
                ).eq('company_name', company).execute()
                signature_html = (sig_result.data[0].get('signature_html') or '').strip() if sig_result.data else ''
                if signature_html:
                    email_body = f"""{email_body}
<div style="margin-top: 16px;">
{signature_html}
</div>"""
            except Exception as sig_err:
                logger.warning(f"Could not load signature for company '{company}': {sig_err}")

        # Constrain the email to a readable, fixed max width (600px) so it does
        # not span the full width of wide inboxes/preview panes. Use a centered
        # table wrapper (most email-client-safe approach).
        email_body = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; border-collapse: collapse;">
  <tr>
    <td align="center" style="padding: 0;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width: 600px; max-width: 600px; border-collapse: collapse;">
        <tr>
          <td style="padding: 0; text-align: left;">
{email_body}
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""

        # A campaign's subject lines are client-approved copy: choose one verbatim
        # instead of generating, and skip the generation call entirely.
        campaign_subject = None
        if campaign:
            campaign_subject = _select_campaign_subject(
                campaign.get('subject_examples') or [],
                first_name, current_title, current_company)

        # Generate subject line separately for better control.
        # Falls back to neutral phrasing so a missing company never leaks another
        # company's name into the subject.
        sender_company_label = company or 'our company'
        if use_job_focused_approach:
            # Job-focused subject line
            job_title = job_list[0]['position'] if job_list else 'opportunity'
            subject_prompt = f"""Generate a direct, professional subject line for a job opportunity email to {first_name}, a {current_title} at {current_company}.

The email is about a {job_title} role at {sender_company_label} that matches their background.

Style examples:
- "{job_title} opportunity at {sender_company_label}"
- "Thought of you for our {job_title} role"
- "{first_name}: {job_title} role that matches your background"
- "Great fit for you: {job_title} at {sender_company_label}"
- "{job_title} opening — thought you'd be interested"

Keep it under 60 characters, no quotation marks, use title case. Be clear it's about a specific role."""
        else:
            # Relationship-nurture subject line
            subject_prompt = f"""Generate a warm, personal subject line for {first_name}, a {current_title} at {current_company}.

It should feel like you're reaching out to someone you know and respect — personal, not salesy.

Style examples:
- "Been thinking about your next move, {first_name}"
- "{first_name}, would love to hear what's next for you"
- "Thought of you when I saw these, {first_name}"
- "Curious where you're headed next, {first_name}"
- "{first_name}, wanted to reach out"

Keep it under 60 characters, no quotation marks, use title case."""

        if campaign_subject:
            # Client-approved copy: used exactly as written, emoji and all.
            subject = campaign_subject
        else:
            subject_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": subject_prompt}
                ],
                temperature=0.9,
                max_tokens=25
            )

            # Strip wrapping quotes the model sometimes adds, but keep internal
            # apostrophes — blanket-removing them produced subjects like "Youre".
            subject = subject_response.choices[0].message.content.strip()
            subject = subject.replace('"', '').strip().strip("'").strip()
            subject = subject.replace("[Company]", company or 'our company')

        logger.info(f"Generated {'job-focused' if use_job_focused_approach else 'relationship-nurture'} email for {name}")

        return {
            'subject': subject,
            'body': email_body,
            'candidate_name': name,
            'candidate_title': current_title,
            'blog_count': len(blog_recommendations),
            'email_approach': 'job-focused' if use_job_focused_approach else 'relationship-nurture',
            'job_count': len(job_list)
        }

    except Exception as e:
        logger.error(f"Error generating email: {str(e)}")
        # Fallback to basic email
        subject = f"Thought you'd find these interesting, {first_name}"

        email_body = f"""Hi {first_name},

I came across your background as {current_title} at {current_company} and thought these articles might resonate with you:

"""
        for blog in blog_recommendations:
            email_body += f"{blog['blog_title']}\n{blog['blog_url']}\n\n"

        email_body += f"I'd love to hear what you're thinking about for your next career move.\n\nBest,"

        return {
            'subject': subject,
            'body': email_body,
            'candidate_name': name,
            'candidate_title': current_title,
            'blog_count': len(blog_recommendations),
            'email_approach': 'relationship-nurture',
            'job_count': 0
        }


def format_blog_response(blogs):
    """Internal: Format blog matches for API response"""
    return [
        {
            'title': blog['blog_title'],
            'url': blog['blog_url'],
            'featured_image': blog.get('blog_featured_image', ''),
            'relevance': round(blog.get('max_similarity', 0) * 100, 1),
            'author': blog.get('blog_author', ''),
            'excerpt': (blog.get('best_matching_chunk') or '')[:200] + '...'
        }
        for blog in blogs
    ]


# ============================================================================
# PUBLIC API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')


@app.route('/api/process-candidate', methods=['POST'])
def process_candidate():
    """
    All-in-one endpoint: Process a new candidate

    Flow:
    1. Extract candidate info
    2. Create three summaries (professional, preferences, interests)
    3. Vectorize all three and store
    4. Match blogs using three embeddings
    5. Generate email

    Request:
    {
        "candidate": { ... full candidate JSON ... }
    }

    Response:
    {
        "success": true,
        "candidate": { id, name, title, company, location },
        "candidate_profile": { ... full raw candidate JSON ... },
        "professional_summary": "...",
        "job_preferences": "...",
        "interests": "...",
        "blog_matches": [...],
        "email": { subject, body, ... },
        "timestamp": "..."
    }
    """
    try:
        # Authentication
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        # Validate request
        data = request.json
        if not data or 'candidate' not in data:
            return jsonify({'error': 'Invalid request. Please provide candidate JSON.'}), 400

        company = data.get('company')
        if not company:
            return jsonify({'error': 'Missing required field: company'}), 400

        candidate_data = data['candidate']
        logger.info("Processing candidate request...")

        # Step 1: Extract candidate info
        candidate_info = vectorizer.extract_candidate_info(candidate_data)
        candidate_id = candidate_info['candidate_id']

        if not candidate_id:
            return jsonify({'error': 'Candidate missing ID (ref field)'}), 400

        logger.info(f"Extracted candidate: {candidate_info['full_name']} ({candidate_id})")

        # Step 2: Create three separate summaries
        logger.info("Creating three-field summaries...")
        summaries = create_candidate_summaries(candidate_info)

        # Step 3: Vectorize all three fields and store
        logger.info("Vectorizing candidate with three embeddings...")
        success = vectorize_candidate_summaries(candidate_data, summaries)
        if not success:
            return jsonify({'error': 'Failed to vectorize candidate profile'}), 500

        # Step 4: Match blogs using three embeddings
        logger.info("Finding matching blogs using three-embedding search...")
        top_blogs = match_blogs_for_candidate_internal(candidate_id, company=company)
        if not top_blogs:
            logger.warning(f"No matching blog posts found for {candidate_id} (company={company})")
            top_blogs = []

        # Step 4.5: Match candidate to open jobs
        logger.info("Matching candidate to open jobs...")
        job_matches = match_candidate_to_jobs(candidate_id, match_threshold=0.35, company=company)

        # Step 5: Generate email (use combined context)
        logger.info("Generating email...")
        # Combine all three summaries for email generation context
        combined_summary = f"{summaries['professional_summary']}\n\n{summaries['job_preferences']}\n\n{summaries['interests']}"
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary, job_matches=job_matches, company=company)

        # Store generated email in database
        try:
            supabase = vectorizer.supabase
            email_record = {
                'candidate_id': candidate_id,
                'email_type': email_content.get('email_approach', 'unknown'),
                'status': 'generated',
                'email_subject': email_content.get('subject', ''),
                'email_html': email_content.get('body', ''),
                'company': company
            }
            if job_matches and email_content.get('email_approach') == 'job-focused':
                email_record['job_matches'] = [job['job_id'] for job in job_matches]
            supabase.table('generated_emails').insert(email_record).execute()
            logger.info(f"Stored generated email for candidate {candidate_id}")
        except Exception as store_err:
            logger.error(f"Failed to store generated email: {str(store_err)}")

        # Return response
        response = {
            'success': True,
            'candidate': {
                'id': candidate_id,
                'name': candidate_info['full_name'],
                'title': candidate_info['current_title'],
                'company': candidate_info['current_company'],
                'location': candidate_info['location']
            },
            'candidate_profile': candidate_data,  # Full raw candidate JSON for external use
            'professional_summary': summaries['professional_summary'],
            'job_preferences': summaries['job_preferences'],
            'interests': summaries['interests'],
            'blog_matches': format_blog_response(top_blogs),
            'email': email_content,
            'timestamp': datetime.now().isoformat()
        }

        # Only include job_matches if there are actual matches
        if job_matches:
            response['job_matches'] = job_matches

        logger.info("Successfully processed candidate with three-field embeddings!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error processing candidate: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/update-context', methods=['POST'])
def update_context():
    """
    Append new context to a specific section of candidate's knowledge base

    Flow:
    1. Get candidate from DB
    2. Retrieve existing section content
    3. Append new context with timestamp
    4. Re-vectorize that section
    5. Store updated embedding

    Request:
    {
        "candidate_id": "pub_lnkd_123",
        "additional_context": "They mentioned interest in platform engineering and learning Kubernetes...",
        "section": "interests"  // Options: "job_preferences" or "interests" (default: "interests")
    }

    Response:
    {
        "success": true,
        "candidate_id": "...",
        "section_updated": "interests",
        "updated_content": "Full accumulated knowledge for that section...",
        "context_added": "They mentioned interest in...",
        "timestamp": "..."
    }

    Note: This endpoint APPENDS to the specified section rather than replacing it.
    The professional_summary is not updatable via this endpoint (it's derived from profile data).
    """
    try:
        # Authentication
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        # Validate request
        data = request.json
        if not data or 'candidate_id' not in data or 'additional_context' not in data:
            return jsonify({'error': 'Invalid request. Provide candidate_id and additional_context.'}), 400

        candidate_id = data['candidate_id']
        additional_context = data['additional_context']
        section = data.get('section', 'interests')  # Default to interests

        # Validate section
        if section not in ['job_preferences', 'interests']:
            return jsonify({'error': 'Invalid section. Must be "job_preferences" or "interests".'}), 400

        logger.info(f"Updating {section} for candidate {candidate_id}")

        # Get candidate from database
        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            return jsonify({'error': f'Candidate {candidate_id} not found in database'}), 404

        # Step 1: Get existing section content from database
        logger.info(f"Retrieving existing {section} from database...")

        if section == 'job_preferences':
            existing_content = candidate_profile.get('job_preferences', '')
            field_name = 'job_preferences'
            embedding_field = 'job_preferences_embedding'
        else:  # interests
            existing_content = candidate_profile.get('interests', '')
            field_name = 'interests'
            embedding_field = 'interests_embedding'

        if not existing_content:
            logger.warning(f"No existing {section} found, starting fresh")
            existing_content = ""

        # Step 2: Append new context with timestamp
        logger.info(f"Appending new context to {section}...")

        timestamp = datetime.now().strftime('%Y-%m-%d')
        if existing_content:
            updated_content = f"{existing_content}\n\n[Updated {timestamp}] {additional_context}"
        else:
            updated_content = f"[{timestamp}] {additional_context}"

        logger.info(f"Updated {section} length: {len(updated_content)} characters")

        # Step 3: Re-vectorize the updated section
        logger.info(f"Re-vectorizing {section}...")

        try:
            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=updated_content
            )
            updated_embedding = embedding_response.data[0].embedding

            # Update the specific section and its embedding in database
            supabase = matcher.supabase
            update_data = {
                field_name: updated_content,
                embedding_field: updated_embedding
            }

            result = supabase.table('candidate_embeddings').update(
                update_data
            ).eq('candidate_profile_id', candidate_profile['profile_id']).execute()

            logger.info(f"Updated {section} embedding in database ({len(updated_content)} chars)")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error updating {section} embedding: {error_msg}", exc_info=True)
            return jsonify({'error': f'Failed to update {section} embedding: {error_msg}'}), 500

        # Return response
        response = {
            'success': True,
            'candidate_id': candidate_id,
            'section_updated': section,
            'updated_content': updated_content,
            'context_added': additional_context,
            'content_length': len(updated_content),
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"Successfully updated {section} for candidate {candidate_id}!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error updating context: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/generate-email', methods=['POST'])
def generate_email():
    """
    Generate email for an existing candidate

    Flow:
    1. Get candidate from DB (including raw profile JSON)
    2. Match blogs using current embeddings
    3. Generate email

    Request:
    {
        "candidate_id": "pub_lnkd_123"
    }

    Response:
    {
        "success": true,
        "candidate": { id, name, title, company, location },
        "candidate_profile": { ... full raw candidate JSON ... },
        "professional_summary": "...",
        "job_preferences": "...",
        "interests": "...",
        "blog_matches": [...],
        "email": { subject, body, ... },
        "timestamp": "..."
    }
    """
    try:
        # Authentication
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        # Validate request
        data = request.json
        if not data or 'candidate_id' not in data:
            return jsonify({'error': 'Invalid request. Provide candidate_id.'}), 400

        company = data.get('company')
        if not company:
            return jsonify({'error': 'Missing required field: company'}), 400

        candidate_id = data['candidate_id']
        logger.info(f"Generating email for {candidate_id}")

        # Get candidate from database
        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            return jsonify({'error': f'Candidate {candidate_id} not found in database'}), 404

        # Fetch raw_profile JSON from candidate_profiles table
        supabase = matcher.supabase
        raw_profile_data = supabase.table('candidate_profiles').select('raw_profile').eq(
            'id', candidate_profile['profile_id']
        ).execute()

        raw_profile_json = None
        if raw_profile_data.data and raw_profile_data.data[0].get('raw_profile'):
            raw_profile_json = raw_profile_data.data[0]['raw_profile']

        # Build candidate_info object
        candidate_info = {
            'candidate_id': candidate_id,
            'full_name': candidate_profile.get('full_name', ''),
            'current_title': candidate_profile.get('current_title', ''),
            'current_company': candidate_profile.get('current_company', ''),
            'location': candidate_profile.get('location', ''),
            'about_me': candidate_profile.get('about_me', ''),
            'skills': [],
            'work_experience': []
        }

        # Get three-field summaries from database
        try:
            supabase = matcher.supabase
            embedding_data = supabase.table('candidate_embeddings').select(
                'professional_summary, job_preferences, interests, embedding_text'
            ).eq('candidate_profile_id', candidate_profile['profile_id']).execute()

            if embedding_data.data:
                professional_summary = embedding_data.data[0].get('professional_summary', '')
                job_preferences = embedding_data.data[0].get('job_preferences', '')
                interests = embedding_data.data[0].get('interests', '')

                # Fallback to legacy field if new fields not available
                if not professional_summary:
                    professional_summary = embedding_data.data[0].get('embedding_text', '')
            else:
                professional_summary = f"{candidate_info['full_name']} - {candidate_info['current_title']}"
                job_preferences = ""
                interests = ""

        except Exception as e:
            logger.error(f"Error retrieving summaries: {str(e)}")
            professional_summary = f"{candidate_info['full_name']} - {candidate_info['current_title']}"
            job_preferences = ""
            interests = ""

        # Combine summaries for email generation
        combined_summary = professional_summary
        if job_preferences:
            combined_summary += f"\n\n{job_preferences}"
        if interests:
            combined_summary += f"\n\n{interests}"

        # Optional client-authored campaign. Resolved before blog matching because
        # a campaign supplies its own content and card, making the blog match (an
        # embedding search plus an LLM selection call) wasted work.
        campaign_key = data.get('campaign_key')
        campaign = None
        if campaign_key:
            campaign = get_company_campaign(company, campaign_key)
            if not campaign:
                return jsonify({
                    'error': f"Campaign '{campaign_key}' not found or inactive for company '{company}'"
                }), 404
            logger.info(f"Using campaign '{campaign_key}' for {company}")

        # Match blogs (skipped when a campaign provides the content)
        top_blogs = []
        if not campaign:
            logger.info("Finding matching blogs...")
            top_blogs = match_blogs_for_candidate_internal(candidate_id, company=company)
            if not top_blogs:
                logger.warning(f"No matching blog posts found for {candidate_id} (company={company})")
                top_blogs = []

        # Match candidate to open jobs
        logger.info("Matching candidate to open jobs...")
        job_matches = match_candidate_to_jobs(candidate_id, match_threshold=0.35, company=company)

        # Extract optional email feedback
        email_feedback = data.get('email_feedback')

        # Generate email
        logger.info("Generating email...")
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary, job_matches=job_matches, email_feedback=email_feedback, company=company, campaign=campaign)

        # Store generated email in database
        try:
            supabase = matcher.supabase
            email_record = {
                'candidate_id': candidate_id,
                'email_type': email_content.get('email_approach', 'unknown'),
                'status': 'generated',
                'email_subject': email_content.get('subject', ''),
                'email_html': email_content.get('body', ''),
                'company': company
            }
            if job_matches and email_content.get('email_approach') == 'job-focused':
                email_record['job_matches'] = [job['job_id'] for job in job_matches]
            supabase.table('generated_emails').insert(email_record).execute()
            logger.info(f"Stored generated email for candidate {candidate_id}")
        except Exception as store_err:
            logger.error(f"Failed to store generated email: {str(store_err)}")

        # Return response
        response = {
            'success': True,
            'candidate': {
                'id': candidate_id,
                'name': candidate_info['full_name'],
                'title': candidate_info['current_title'],
                'company': candidate_info['current_company'],
                'location': candidate_info['location']
            },
            'candidate_profile': raw_profile_json,  # Full raw candidate JSON for external use
            'professional_summary': professional_summary,
            'job_preferences': job_preferences,
            'interests': interests,
            'blog_matches': format_blog_response(top_blogs),
            'email': email_content,
            'timestamp': datetime.now().isoformat()
        }

        # Only include job_matches if there are actual matches
        if job_matches:
            response['job_matches'] = job_matches

        logger.info("Successfully generated email!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error generating email: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/process-and-email', methods=['POST'])
def process_and_email():
    """
    Check if a candidate has been processed, and if so generate an email.

    Request:
    {
        "candidate_id": "pub_lnkd_123"
    }

    Returns 404 if candidate hasn't been processed yet (caller should use
    /api/process-candidate first). Otherwise generates and returns the email.
    """
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        data = request.json
        if not data or 'candidate_id' not in data:
            return jsonify({'error': 'Invalid request. Provide candidate_id.'}), 400

        company = data.get('company')
        if not company:
            return jsonify({'error': 'Missing required field: company'}), 400

        candidate_id = data['candidate_id']
        logger.info(f"process-and-email: checking if {candidate_id} exists...")

        # Check if candidate already exists in candidate_profiles
        supabase = vectorizer.supabase
        existing = supabase.table('candidate_profiles').select('id').eq(
            'candidate_id', candidate_id
        ).execute()

        if not existing.data:
            return jsonify({
                'exists': False,
                'error': f'Candidate {candidate_id} has not been processed yet. Use /api/process-candidate first.'
            }), 404

        # Candidate exists — generate email using existing data
        logger.info(f"Candidate {candidate_id} found, generating email")

        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            return jsonify({'error': f'Candidate {candidate_id} not found in database'}), 404

        # Fetch raw_profile
        raw_profile_data = supabase.table('candidate_profiles').select('raw_profile').eq(
            'id', candidate_profile['profile_id']
        ).execute()
        raw_profile_json = None
        if raw_profile_data.data and raw_profile_data.data[0].get('raw_profile'):
            raw_profile_json = raw_profile_data.data[0]['raw_profile']

        candidate_info = {
            'candidate_id': candidate_id,
            'full_name': candidate_profile.get('full_name', ''),
            'current_title': candidate_profile.get('current_title', ''),
            'current_company': candidate_profile.get('current_company', ''),
            'location': candidate_profile.get('location', ''),
            'about_me': candidate_profile.get('about_me', ''),
            'skills': [],
            'work_experience': []
        }

        # Get three-field summaries
        try:
            embedding_data = supabase.table('candidate_embeddings').select(
                'professional_summary, job_preferences, interests, embedding_text'
            ).eq('candidate_profile_id', candidate_profile['profile_id']).execute()

            if embedding_data.data:
                professional_summary = embedding_data.data[0].get('professional_summary', '')
                job_preferences = embedding_data.data[0].get('job_preferences', '')
                interests = embedding_data.data[0].get('interests', '')
                if not professional_summary:
                    professional_summary = embedding_data.data[0].get('embedding_text', '')
            else:
                professional_summary = f"{candidate_info['full_name']} - {candidate_info['current_title']}"
                job_preferences = ""
                interests = ""
        except Exception as e:
            logger.error(f"Error retrieving summaries: {str(e)}")
            professional_summary = f"{candidate_info['full_name']} - {candidate_info['current_title']}"
            job_preferences = ""
            interests = ""

        combined_summary = professional_summary
        if job_preferences:
            combined_summary += f"\n\n{job_preferences}"
        if interests:
            combined_summary += f"\n\n{interests}"

        campaign_key = data.get('campaign_key')
        campaign = None
        if campaign_key:
            campaign = get_company_campaign(company, campaign_key)
            if not campaign:
                return jsonify({
                    'error': f"Campaign '{campaign_key}' not found or inactive for company '{company}'"
                }), 404
            logger.info(f"Using campaign '{campaign_key}' for {company}")

        top_blogs = []
        if not campaign:
            top_blogs = match_blogs_for_candidate_internal(candidate_id, company=company)
            if not top_blogs:
                logger.warning(f"No matching blog posts found for {candidate_id} (company={company})")
                top_blogs = []

        job_matches = match_candidate_to_jobs(candidate_id, match_threshold=0.35, company=company)

        # Extract optional email feedback
        email_feedback = data.get('email_feedback')

        email_content = generate_email_content(candidate_info, top_blogs, combined_summary, job_matches=job_matches, email_feedback=email_feedback, company=company, campaign=campaign)

        # Store generated email
        try:
            email_record = {
                'candidate_id': candidate_id,
                'email_type': email_content.get('email_approach', 'unknown'),
                'status': 'generated',
                'email_subject': email_content.get('subject', ''),
                'email_html': email_content.get('body', ''),
                'company': company
            }
            if job_matches and email_content.get('email_approach') == 'job-focused':
                email_record['job_matches'] = [job['job_id'] for job in job_matches]
            supabase.table('generated_emails').insert(email_record).execute()
            logger.info(f"Stored generated email for candidate {candidate_id}")
        except Exception as store_err:
            logger.error(f"Failed to store generated email: {str(store_err)}")

        response = {
            'success': True,
            'exists': True,
            'candidate': {
                'id': candidate_id,
                'name': candidate_info['full_name'],
                'title': candidate_info['current_title'],
                'company': candidate_info['current_company'],
                'location': candidate_info['location']
            },
            'candidate_profile': raw_profile_json,
            'professional_summary': professional_summary,
            'job_preferences': job_preferences,
            'interests': interests,
            'blog_matches': format_blog_response(top_blogs),
            'email': email_content,
            'timestamp': datetime.now().isoformat()
        }

        if job_matches:
            response['job_matches'] = job_matches

        logger.info(f"Successfully generated email for candidate {candidate_id}!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error in process-and-email: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'candidate-email-generator',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# EMAIL MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/emails/check', methods=['GET'])
def check_emails():
    """Check if generated emails exist for a candidate"""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        candidate_id = request.args.get('candidate_id')
        if not candidate_id:
            return jsonify({'error': 'candidate_id query parameter is required'}), 400

        company = request.args.get('company')
        if not company:
            return jsonify({'error': 'company query parameter is required'}), 400

        supabase = vectorizer.supabase
        query = supabase.table('generated_emails').select('id', count='exact').eq('candidate_id', candidate_id).eq('company', company)

        email_type = request.args.get('email_type')
        if email_type:
            query = query.eq('email_type', email_type)

        status = request.args.get('status')
        if status:
            query = query.eq('status', status)

        result = query.execute()
        count = result.count if result.count is not None else len(result.data)

        return jsonify({
            'exists': count > 0,
            'count': count
        })

    except Exception as e:
        logger.error(f"Error checking emails: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/emails', methods=['GET'])
def get_emails():
    """Retrieve email records for a candidate"""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        candidate_id = request.args.get('candidate_id')
        if not candidate_id:
            return jsonify({'error': 'candidate_id query parameter is required'}), 400

        company = request.args.get('company')
        if not company:
            return jsonify({'error': 'company query parameter is required'}), 400

        supabase = vectorizer.supabase
        query = supabase.table('generated_emails').select('*').eq('candidate_id', candidate_id).eq('company', company)

        email_type = request.args.get('email_type')
        if email_type:
            query = query.eq('email_type', email_type)

        status = request.args.get('status')
        if status:
            query = query.eq('status', status)

        result = query.order('created_at', desc=True).execute()

        return jsonify({
            'success': True,
            'emails': result.data,
            'count': len(result.data)
        })

    except Exception as e:
        logger.error(f"Error fetching emails: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/emails/<int:email_id>/status', methods=['PATCH'])
def update_email_status(email_id):
    """Update the status of a specific email record"""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        data = request.json
        if not data or 'status' not in data:
            return jsonify({'error': 'Request body must include status'}), 400

        new_status = data['status']

        supabase = vectorizer.supabase
        result = supabase.table('generated_emails').update({
            'status': new_status
        }).eq('id', email_id).execute()

        if not result.data:
            return jsonify({'error': f'Email record {email_id} not found'}), 404

        return jsonify({
            'success': True,
            'id': email_id,
            'status': new_status
        })

    except Exception as e:
        logger.error(f"Error updating email status: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/candidate/<candidate_id>', methods=['GET'])
def get_candidate(candidate_id):
    """Fetch candidate enrichment data without generating an email. Read-only, no side effects."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        company = request.args.get('company')
        if not company:
            return jsonify({'error': 'company query parameter is required'}), 400

        # Get candidate from database
        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            return jsonify({'error': f'Candidate {candidate_id} not found in database'}), 404

        # Fetch raw_profile JSON from candidate_profiles table
        supabase = matcher.supabase
        raw_profile_data = supabase.table('candidate_profiles').select('raw_profile').eq(
            'id', candidate_profile['profile_id']
        ).execute()

        raw_profile_json = None
        if raw_profile_data.data and raw_profile_data.data[0].get('raw_profile'):
            raw_profile_json = raw_profile_data.data[0]['raw_profile']

        # Parse raw_profile if it's a string so response is always a dict
        candidate_profile_parsed = {}
        if raw_profile_json:
            if isinstance(raw_profile_json, str):
                try:
                    candidate_profile_parsed = json.loads(raw_profile_json)
                except json.JSONDecodeError:
                    candidate_profile_parsed = {'raw': raw_profile_json}
            else:
                candidate_profile_parsed = raw_profile_json

        # Build candidate_info object
        candidate_info = {
            'id': candidate_id,
            'name': candidate_profile.get('full_name', ''),
            'title': candidate_profile.get('current_title', ''),
            'company': candidate_profile.get('current_company', ''),
            'location': candidate_profile.get('location', ''),
        }

        # Get three-field summaries from database
        professional_summary = ""
        interests = ""
        job_preferences = ""
        try:
            embedding_data = supabase.table('candidate_embeddings').select(
                'professional_summary, job_preferences, interests, embedding_text'
            ).eq('candidate_profile_id', candidate_profile['profile_id']).execute()

            if embedding_data.data:
                professional_summary = embedding_data.data[0].get('professional_summary', '')
                job_preferences = embedding_data.data[0].get('job_preferences', '')
                interests = embedding_data.data[0].get('interests', '')

                # Fallback to legacy field if new fields not available
                if not professional_summary:
                    professional_summary = embedding_data.data[0].get('embedding_text', '')
        except Exception as e:
            logger.error(f"Error retrieving summaries: {str(e)}")

        # Match blogs — return empty array if none found
        top_blogs = match_blogs_for_candidate_internal(candidate_id, company=company)
        blog_matches = format_blog_response(top_blogs) if top_blogs else []

        return jsonify({
            'success': True,
            'candidate': candidate_info,
            'candidate_profile': candidate_profile_parsed,
            'professional_summary': professional_summary,
            'interests': interests,
            'job_preferences': job_preferences,
            'blog_matches': blog_matches
        })

    except Exception as e:
        logger.error(f"Error fetching candidate data: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Fetch full job details by job_id. Read-only, no side effects."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        company = request.args.get('company')
        if not company:
            return jsonify({'error': 'company query parameter is required'}), 400

        supabase = matcher.supabase
        result = supabase.table('job_postings').select('*').eq('job_id', job_id).eq('company', company).execute()

        if not result.data:
            return jsonify({'error': f'Job {job_id} not found'}), 404

        return jsonify({
            'success': True,
            'job': result.data[0]
        })

    except Exception as e:
        logger.error(f"Error fetching job details: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


# ============================================================================
# COMPANY PREFERENCES HELPERS
# ============================================================================

# camelCase (API) <-> snake_case (DB) field mappings
_PREF_API_TO_DB = {
    'goal': 'goal',
    'doNotContactReasons': 'do_not_contact_reasons',
    'nurtureEmailFeedback': 'nurture_email_feedback',
    'jobEmailFeedback': 'job_email_feedback',
    'signatureHtml': 'signature_html',
    'campaigns': 'campaigns',
}

_PREF_DB_TO_API = {v: k for k, v in _PREF_API_TO_DB.items()}

# Mutable fields (excludes id, company_name, timestamps)
_PREF_MUTABLE_FIELDS = set(_PREF_API_TO_DB.keys())

# Default values for new/reset rows
_PREF_DEFAULTS = {
    'goal': 'both',
    'do_not_contact_reasons': [],
    'nurture_email_feedback': '',
    'job_email_feedback': '',
    'signature_html': '',
    'campaigns': [],
}

VALID_GOALS = {'applicants', 'warm', 'both'}


def _prefs_db_to_api(row):
    """Convert a DB row dict to the API response shape."""
    return {
        'id': row['id'],
        'companyName': row['company_name'],
        'goal': row['goal'],
        'doNotContactReasons': row['do_not_contact_reasons'],
        'nurtureEmailFeedback': row['nurture_email_feedback'],
        'jobEmailFeedback': row['job_email_feedback'],
        # Both were stored but never returned, so callers could not read back
        # what they had written.
        'signatureHtml': row.get('signature_html') or '',
        'campaigns': row.get('campaigns') or [],
        'createdAt': row['created_at'],
    }


def _prefs_api_to_db(data):
    """Convert request body to DB columns, only mapping known mutable fields."""
    result = {}
    for api_key, db_key in _PREF_API_TO_DB.items():
        if api_key in data:
            result[db_key] = data[api_key]
    return result


# ============================================================================
# COMPANY PREFERENCES ENDPOINTS
# ============================================================================

@app.route('/api/company-preferences/<company_name>', methods=['GET'])
def get_company_preferences(company_name):
    """Fetch company preferences by company_name or by id query param."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        supabase = vectorizer.supabase

        # If ?id=<int> is provided, look up by ID instead
        pref_id = request.args.get('id')
        if pref_id is not None:
            try:
                pref_id = int(pref_id)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid id parameter; must be an integer'}), 400
            result = supabase.table('customer_preferences').select('*').eq('id', pref_id).execute()
        else:
            result = supabase.table('customer_preferences').select('*').eq('company_name', company_name).execute()

        if not result.data:
            return jsonify({'error': f'Preferences not found for company: {company_name}'}), 404

        return jsonify({
            'success': True,
            'preferences': _prefs_db_to_api(result.data[0])
        })

    except Exception as e:
        logger.error(f"Error fetching company preferences: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/company-preferences/<company_name>', methods=['PUT'])
def put_company_preferences(company_name):
    """Create or fully replace company preferences. All mutable fields required."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate all mutable fields are present
        missing = _PREF_MUTABLE_FIELDS - set(data.keys())
        if missing:
            return jsonify({'error': f'Missing required fields: {", ".join(sorted(missing))}'}), 400

        # Validate goal
        if data.get('goal') not in VALID_GOALS:
            return jsonify({'error': f'Invalid goal. Must be one of: {", ".join(sorted(VALID_GOALS))}'}), 400

        # Validate doNotContactReasons is a list
        if not isinstance(data.get('doNotContactReasons'), list):
            return jsonify({'error': 'doNotContactReasons must be a list'}), 400

        db_fields = _prefs_api_to_db(data)
        db_fields['company_name'] = company_name

        supabase = vectorizer.supabase

        # Check if row exists
        existing = supabase.table('customer_preferences').select('id').eq('company_name', company_name).execute()

        if existing.data:
            result = supabase.table('customer_preferences').update(db_fields).eq('company_name', company_name).execute()
        else:
            result = supabase.table('customer_preferences').insert(db_fields).execute()

        return jsonify({
            'success': True,
            'preferences': _prefs_db_to_api(result.data[0])
        })

    except Exception as e:
        logger.error(f"Error saving company preferences: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/company-preferences/<company_name>', methods=['PATCH'])
def patch_company_preferences(company_name):
    """Partially update company preferences. Only provided fields are changed."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate only provided fields
        if 'goal' in data and data['goal'] not in VALID_GOALS:
            return jsonify({'error': f'Invalid goal. Must be one of: {", ".join(sorted(VALID_GOALS))}'}), 400

        if 'doNotContactReasons' in data and not isinstance(data['doNotContactReasons'], list):
            return jsonify({'error': 'doNotContactReasons must be a list'}), 400

        db_fields = _prefs_api_to_db(data)
        if not db_fields:
            return jsonify({'error': 'No valid fields provided'}), 400

        supabase = vectorizer.supabase

        # Check if row exists
        existing = supabase.table('customer_preferences').select('id').eq('company_name', company_name).execute()

        if existing.data:
            result = supabase.table('customer_preferences').update(db_fields).eq('company_name', company_name).execute()
        else:
            # Insert with defaults + overrides
            insert_data = dict(_PREF_DEFAULTS)
            insert_data.update(db_fields)
            insert_data['company_name'] = company_name
            result = supabase.table('customer_preferences').insert(insert_data).execute()

        return jsonify({
            'success': True,
            'preferences': _prefs_db_to_api(result.data[0])
        })

    except Exception as e:
        logger.error(f"Error updating company preferences: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/company-preferences/<company_name>', methods=['DELETE'])
def delete_company_preferences(company_name):
    """Reset company preferences to defaults (keeps the row)."""
    try:
        if not check_api_key():
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

        supabase = vectorizer.supabase

        # Check if row exists
        existing = supabase.table('customer_preferences').select('id').eq('company_name', company_name).execute()

        if not existing.data:
            return jsonify({'error': f'Preferences not found for company: {company_name}'}), 404

        # Reset to defaults (preserves id and created_at)
        result = supabase.table('customer_preferences').update(dict(_PREF_DEFAULTS)).eq('company_name', company_name).execute()

        return jsonify({
            'success': True,
            'message': 'Preferences reset to defaults',
            'preferences': _prefs_db_to_api(result.data[0])
        })

    except Exception as e:
        logger.error(f"Error resetting company preferences: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


# ============================================================================
# RUN APP
# ============================================================================

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'

    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
