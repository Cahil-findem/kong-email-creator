"""
Flask app for candidate email generation
Provides a web interface to vectorize candidates and generate personalized emails
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
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


def match_blogs_for_candidate_internal(candidate_id):
    """
    Internal: Find matching blogs for a candidate using hybrid approach
    Returns: list of LLM-selected blog matches (top 3)
    """
    try:
        logger.info(f"Finding blog matches for {candidate_id} using hybrid LLM approach...")

        # Use hybrid approach: embeddings get top 30, LLM selects best 3
        selected_blogs = matcher.find_blogs_for_candidate_hybrid(
            candidate_id,
            match_threshold=0.25,
            top_n_embeddings=30,  # LLM reviews 30 candidates
            final_n_llm=3          # LLM selects best 3
        )

        if not selected_blogs:
            logger.info(f"No blog matches found for {candidate_id}")
            return []

        logger.info(f"LLM selected {len(selected_blogs)} blogs from 30 candidates")
        return selected_blogs
    except Exception as e:
        logger.error(f"Error matching blogs: {str(e)}")
        return []




def evaluate_job_match_with_llm(candidate_profile, job, semantic_similarity):
    """
    Use LLM to evaluate if candidate is a genuine match for the job
    Returns: dict with is_match, confidence, reasoning, or None if evaluation fails
    """
    try:
        # Extract candidate information
        candidate_name = candidate_profile.get('full_name', 'Candidate')
        candidate_title = candidate_profile.get('current_title', '')
        candidate_summary = candidate_profile.get('professional_summary', '')
        candidate_preferences = candidate_profile.get('job_preferences', '')

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

JOB OPENING:
Position: {job_title}
About Role: {job_description[:400]}
Must-Have Requirements: {', '.join(must_have[:5]) if must_have else 'Not specified'}
Nice-to-Have: {', '.join(nice_to_have[:3]) if nice_to_have else 'Not specified'}

Semantic Similarity Score: {semantic_similarity:.1%}

EVALUATION CRITERIA:
1. **Role Type Match** (CRITICAL): Does the candidate's core profession align with the job type?
   - Engineer should match Engineer roles (regardless of specific tech stack)
   - Designer should match Designer roles
   - PM should match PM roles
   - REJECT if core profession mismatches (e.g., Designer applying to Engineer role)

2. **Seniority Match**: Does the candidate's level appropriately match the job level?
   - Consider if this is a step up, lateral, or step down
   - Senior candidates can do Senior or Staff roles

3. **Transferable Skills**: For senior technical roles, evaluate based on:
   - Strong fundamentals and problem-solving ability matter more than specific tech
   - Domain expertise is valuable but not always required
   - Senior engineers can learn new stacks/tools quickly

4. **Core Requirements**: Do they meet the fundamental must-have requirements?
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

IMPORTANT: Be realistic about senior roles - strong engineering fundamentals and seniority match matters more than specific tech experience. ONLY reject if there's a core profession mismatch (e.g., Designer for Engineer role) or major seniority gap."""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter evaluating candidate-job fit. Be precise and honest in your assessments."},
                {"role": "user", "content": evaluation_prompt}
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        evaluation = json.loads(response.choices[0].message.content.strip())
        return evaluation

    except Exception as e:
        logger.error(f"Error in LLM job evaluation: {str(e)}")
        return None


def match_candidate_to_jobs(candidate_id, match_threshold=0.35):
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
        active_jobs = supabase.table('job_postings')\
            .select('*')\
            .eq('status', 'active')\
            .execute()

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
                logger.info(f"    Reasoning: {evaluation.get('reasoning', '')[:100]}")
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


def generate_email_content(candidate_info, blog_recommendations, semantic_summary, job_matches=None):
    """
    Internal: Generate personalized nurture email using LLM

    Args:
        candidate_info: Candidate profile information
        blog_recommendations: List of matching blog posts
        semantic_summary: Combined candidate summaries
        job_matches: Optional list of matching job openings
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
        blog_list.append({
            'title': blog['blog_title'],
            'url': blog['blog_url'],
            'featured_image': blog.get('blog_featured_image', 'https://via.placeholder.com/200x120/2563eb/ffffff?text=Blog'),
            'excerpt': blog.get('best_matching_chunk', '')[:200]
        })

    # Job matches have already been evaluated by LLM in match_candidate_to_open_jobs()
    # No need for additional evaluation - use the matches that were already confirmed
    job_list = []
    if job_matches and len(job_matches) > 0:
        for job in job_matches[:3]:  # Max 3 jobs for email
            job_list.append({
                'position': job['position'],
                'company': job.get('company', ''),
                'location_type': job.get('location_type', ''),
                'location': f"{job.get('location_city', '')}, {job.get('location_country', '')}".strip(', '),
                'compensation': f"{job.get('compensation_currency', '')} {job.get('compensation_min', 0):,.0f} - {job.get('compensation_max', 0):,.0f}",
                'about_role': job.get('about_role', '')[:250],
                'application_link': job.get('application_link', ''),
                'match_score': f"{job.get('similarity', 0) * 100:.0f}%",
                'similarity': job.get('similarity', 0),
                'llm_reasoning': job.get('llm_evaluation', {}).get('reasoning', '') if isinstance(job.get('llm_evaluation'), dict) else ''
            })

    # Decide which email approach to use
    # If jobs were confirmed by the matching LLM, use job-focused approach
    use_job_focused_approach = len(job_list) > 0

    # Build context for email generation (using clearer variable names)
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

Recommended Blog Posts:
{json.dumps(blog_list, indent=2)}
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
        # RELATIONSHIP-NURTURE APPROACH: Build connection, share valuable content
        system_prompt = """You are writing a warm, personal email to someone in your professional network — like reaching out to a talented friend or former colleague you genuinely respect.

Your goal is to make this feel like a real, thoughtful message from someone who's been thinking about them and their career.

TONE & STYLE:
- Warm, genuine, and conversational — like talking to someone you actually know
- Friendly but still professional — you're a peer who cares about their growth
- Personal touches matter — reference specific things about THEIR journey
- Sound human, not corporate
- No emojis, but you can be warm and friendly in your language

STRUCTURE:
- Total length: Under 180 words (excluding blog sections)
- GREETING LINE: ALWAYS start with a greeting on its own line using their first name: "Hi [Name]," or "Hey [Name],"
- FIRST PARAGRAPH: A warm, personal observation about something specific in their background (1-2 sentences max)
- SECOND PARAGRAPH: Ask a genuine question that shows you care about their path forward (1-2 sentences)
- THIRD PARAGRAPH: Share the blogs as "came across these and thought of you"
- Close with one warm, inviting sentence

OPENING EXAMPLES (greeting on its own line, then paragraphs):

Example 1:
"Hi [Name],

I've been thinking about your trajectory from [Company] to [Company] — the way you've built expertise in [domain] is really impressive.

I'm curious — as you think about what's next, are you leaning more toward [direction A] or staying deep in [current area]?"

Example 2:
"Hey [Name],

Your background in [domain] caught my attention, especially [specific thing].

What's pulling you forward right now — [aspect A] or [aspect B]?"

Example 3:
"Hi [Name],

I noticed you've been at [Company] for [X time] working on [domain] — that's a meaningful commitment.

Have you been thinking about [next level/direction], or are you still loving [current focus]?"

QUESTION EXAMPLES (sound genuinely curious):
- "I'm curious — as you think about what's next, are you leaning more toward [direction A] or staying deep in [current area]?"
- "What's pulling you forward right now — [aspect A] or [aspect B]?"
- "Have you been thinking about [next level/direction], or are you still loving [current focus]?"

BLOG TRANSITION (make it natural):
- "I came across a few pieces recently and thought they might resonate with you:"
- "Thought you might find these interesting given your work in [domain]:"
- "Been reading a few things that reminded me of you:"

BLOG SECTION FORMAT:
<p style="margin: 0 0 8px 0; font-size: 16px; color: #6b7280; line-height: 1.5;">[One personal sentence about why THIS person would find this valuable — connect it to their specific experience or interests.]</p>
<div style="display: flex; gap: 12px; align-items: center; margin-bottom: 0;">
  <img src="[FEATURED_IMAGE_URL]" alt="[BLOG_TITLE]" style="width: 250px; height: 144px; object-fit: cover; border-radius: 12px; flex-shrink: 0;">
  <div style="flex: 1; min-width: 0;">
    <a href="[BLOG_URL]" style="font-size: 16px; font-weight: 500; color: #101828; text-decoration: none; display: block; line-height: 1.4; margin: 0;">[BLOG_TITLE]</a>
  </div>
</div>

[Repeat for each blog - use featured_image from blog data, or use placeholder: https://via.placeholder.com/250x144/2563eb/ffffff?text=Blog]

CLOSING EXAMPLES (warm and genuine):
- "Would love to catch up sometime if you're open to it — always enjoy talking shop."
- "If you ever want to grab coffee (virtual or otherwise) and talk through next steps, I'm here."
- "Let's connect soon — I'd love to hear what you're thinking about."
- "Happy to be a sounding board anytime if you want to chat about where things are headed."

Sign-off: "Best,"

CRITICAL RULES:
- NO subject line in the email body (will be generated separately)
- NO signature name after "Best," - just "Best,"
- Under 180 words before blog sections
- Sound like a real person reaching out, not a templated message
- Use HTML formatting for blog sections EXACTLY as shown
- Make blog justifications PERSONAL to this specific person
- Each email should feel like it was written just for them
- Do NOT mention jobs in this approach"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_context}
            ],
            temperature=0.85,
            max_tokens=1200
        )

        email_body = response.choices[0].message.content.strip()

        # Generate subject line separately for better control
        if use_job_focused_approach:
            # Job-focused subject line
            job_title = job_list[0]['position'] if job_list else 'opportunity'
            subject_prompt = f"""Generate a direct, professional subject line for a job opportunity email to {first_name}, a {current_title} at {current_company}.

The email is about a {job_title} role that matches their background.

Style examples:
- "{job_title} opportunity at [Company]"
- "Thought of you for our {job_title} role"
- "{first_name}: {job_title} role that matches your background"
- "Great fit for you: {job_title} at [Company]"
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

        subject_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": subject_prompt}
            ],
            temperature=0.9,
            max_tokens=25
        )

        subject = subject_response.choices[0].message.content.strip().replace('"', '').replace("'", "")

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
            'excerpt': blog.get('best_matching_chunk', '')[:200] + '...'
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
        top_blogs = match_blogs_for_candidate_internal(candidate_id)
        if not top_blogs:
            return jsonify({'error': 'No matching blog posts found.'}), 404

        # Step 4.5: Match candidate to open jobs
        logger.info("Matching candidate to open jobs...")
        job_matches = match_candidate_to_jobs(candidate_id, match_threshold=0.35)

        # Step 5: Generate email (use combined context)
        logger.info("Generating email...")
        # Combine all three summaries for email generation context
        combined_summary = f"{summaries['professional_summary']}\n\n{summaries['job_preferences']}\n\n{summaries['interests']}"
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary, job_matches=job_matches)

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

        # Match blogs
        logger.info("Finding matching blogs...")
        top_blogs = match_blogs_for_candidate_internal(candidate_id)
        if not top_blogs:
            return jsonify({'error': 'No matching blog posts found.'}), 404

        # Match candidate to open jobs
        logger.info("Matching candidate to open jobs...")
        job_matches = match_candidate_to_jobs(candidate_id, match_threshold=0.35)

        # Generate email
        logger.info("Generating email...")
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary, job_matches=job_matches)

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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'candidate-email-generator',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# RUN APP
# ============================================================================

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'

    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
