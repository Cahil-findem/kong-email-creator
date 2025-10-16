"""
Flask app for candidate email generation
Provides a web interface to vectorize candidates and generate personalized emails
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import json
import logging
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

3. **interests**: A bulleted list of their professional interests, formatted as:
   • [Interest/Technology/Industry 1]
   • [Interest/Technology/Industry 2]
   • [Interest/Technology/Industry 3]
   • [Interest/Technology/Industry 4]
   • [Interest/Technology/Industry 5]

   Focus on: technical skills, industry trends, domains, technologies, tools, and professional topics they'd engage with.

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
    Internal: Find matching blogs for a candidate
    Returns: list of diverse blog matches (top 3)
    """
    try:
        logger.info(f"Finding blog matches for {candidate_id}...")

        # Get initial matches
        blog_matches = matcher.find_blogs_for_candidate(
            candidate_id,
            match_threshold=0.25,
            match_count=30,
            deduplicate=True
        )

        if not blog_matches:
            return []

        # Filter for diversity
        top_blogs = filter_diverse_blogs(blog_matches)
        logger.info(f"Found {len(blog_matches)} matches, selected {len(top_blogs)} diverse posts")

        return top_blogs
    except Exception as e:
        logger.error(f"Error matching blogs: {str(e)}")
        return []


def filter_diverse_blogs(blog_matches, count=3):
    """
    Internal: Filter blogs to get diverse, high-quality matches
    Prioritizes domain-specific content over generic posts
    """
    top_blogs = []
    generic_keywords = ['career', 'team', 'culture', 'life at', 'meet the engineers']

    # First pass: get specific content
    for blog in blog_matches:
        if len(top_blogs) >= count:
            break
        title_lower = blog['blog_title'].lower()
        if not any(keyword in title_lower for keyword in generic_keywords):
            top_blogs.append(blog)

    # Second pass: fill remaining slots with best matches
    for blog in blog_matches:
        if len(top_blogs) >= count:
            break
        if blog not in top_blogs:
            top_blogs.append(blog)

    return top_blogs


def generate_email_content(candidate_info, blog_recommendations, semantic_summary):
    """
    Internal: Generate personalized nurture email using LLM
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

Recommended Blog Posts:
{json.dumps(blog_list, indent=2)}
"""

    # Use LLM to generate the email
    system_prompt = """You are writing a warm, personal email to someone in your professional network — like reaching out to a talented friend or former colleague you genuinely respect.

Your goal is to make this feel like a real, thoughtful message from someone who's been thinking about them and their career.

TONE & STYLE:
- Warm, genuine, and conversational — like talking to someone you actually know
- Friendly but still professional — you're a peer who cares about their growth
- Personal touches matter — reference specific things about THEIR journey
- Sound human, not corporate
- No emojis, but you can be warm and friendly in your language

STRUCTURE:
- Total length: Under 180 words (excluding blog section)
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

BLOG SECTION FORMAT (keep this HTML structure exactly - horizontal layout with image on left):
<div style="display: flex; gap: 16px; margin-bottom: 24px; align-items: flex-start;">
  <a href="[BLOG_URL]" style="flex-shrink: 0;">
    <img src="[FEATURED_IMAGE_URL]" alt="[BLOG_TITLE]" style="width: 200px; height: 120px; object-fit: cover; border-radius: 8px;">
  </a>
  <div style="flex: 1; min-width: 0;">
    <a href="[BLOG_URL]" style="font-size: 16px; font-weight: 600; color: #2563eb; text-decoration: none; display: block; margin-bottom: 8px;">[BLOG_TITLE]</a>
    <p style="margin: 0; font-size: 14px; color: #6b7280; line-height: 1.6;">[One personal sentence about why THIS person would find this valuable — connect it to their specific experience or interests.]</p>
  </div>
</div>

[Repeat for each blog - use featured_image from blog data, or use placeholder: https://via.placeholder.com/200x120/2563eb/ffffff?text=Blog]

CLOSING EXAMPLES (warm and genuine):
- "Would love to catch up sometime if you're open to it — always enjoy talking shop."
- "If you ever want to grab coffee (virtual or otherwise) and talk through next steps, I'm here."
- "Let's connect soon — I'd love to hear what you're thinking about."
- "Happy to be a sounding board anytime if you want to chat about where things are headed."

Sign-off: "Best,"

CRITICAL RULES:
- NO subject line in the email body (will be generated separately)
- NO signature name after "Best," - just "Best,"
- Under 180 words before blog section
- Sound like a real person reaching out, not a templated message
- Use HTML formatting for blog section EXACTLY as shown
- Make blog justifications PERSONAL to this specific person
- Each email should feel like it was written just for them"""

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

        logger.info(f"Generated email for {name}")

        return {
            'subject': subject,
            'body': email_body,
            'candidate_name': name,
            'candidate_title': current_title,
            'blog_count': len(blog_recommendations)
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
            'blog_count': len(blog_recommendations)
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

        # Step 5: Generate email (use combined context)
        logger.info("Generating email...")
        # Combine all three summaries for email generation context
        combined_summary = f"{summaries['professional_summary']}\n\n{summaries['job_preferences']}\n\n{summaries['interests']}"
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary)

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

        # Generate email
        logger.info("Generating email...")
        email_content = generate_email_content(candidate_info, top_blogs, combined_summary)

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
