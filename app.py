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

def create_semantic_summary(candidate_info):
    """
    Internal: Create a semantic summary of the candidate for better embedding
    """
    # Extract key details
    name = candidate_info.get('full_name', '')
    title = candidate_info.get('current_title', '')
    company = candidate_info.get('current_company', '')
    about_me = candidate_info.get('about_me', '')
    skills = candidate_info.get('skills', [])

    # Get work history summary
    work_exp = candidate_info.get('work_experience', [])
    companies = []
    if work_exp and isinstance(work_exp, list):
        for exp in work_exp[:3]:  # Top 3 companies
            if isinstance(exp, dict):
                comp_name = exp.get('company', {}).get('name', '')
                if comp_name:
                    companies.append(comp_name)

    # Build context for LLM
    profile_context = f"""
Candidate Name: {name}
Current Role: {title} at {company}
Previous Companies: {', '.join(companies) if companies else 'N/A'}
About: {about_me[:500] if about_me else 'N/A'}
Key Skills: {', '.join(skills[:15]) if skills else 'N/A'}
"""

    # Use LLM to create semantic summary
    system_prompt = """You are an AI that creates embeddings representing a candidate's professional identity, interests, and motivations.

Given a candidate profile, extract a compact, semantically rich summary that captures the essence of who this person is professionally and what content would likely resonate with them.

Focus on:
- Domain expertise (industries, functions, seniority)
- Key skills and competencies
- Motivations and professional values inferred from their work history
- Emerging topics or themes they might engage with (e.g., automation, leadership, data, AI)

Output a single text paragraph (2–3 sentences) describing this person's professional focus and interests, suitable for vectorization.
Do not mention the JSON or refer to the structure — just describe the person naturally."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": profile_context}
            ],
            temperature=0.7,
            max_tokens=200
        )

        semantic_summary = response.choices[0].message.content.strip()
        logger.info(f"Generated semantic summary: {semantic_summary[:100]}...")
        return semantic_summary

    except Exception as e:
        logger.error(f"Error generating semantic summary: {str(e)}")
        # Fallback to basic summary
        return f"{name} is a {title} with expertise in {', '.join(skills[:5]) if skills else 'various areas'}. Currently working at {company}."


def vectorize_candidate_summary(candidate_data, semantic_summary):
    """
    Internal: Vectorize candidate and store in database
    Returns: success boolean
    """
    try:
        logger.info("Vectorizing candidate profile...")
        success = vectorizer.vectorize_candidate(candidate_data, skip_existing=False)
        return success
    except Exception as e:
        logger.error(f"Error vectorizing candidate: {str(e)}")
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

    # Format blog posts for LLM
    blog_list = []
    for blog in blog_recommendations:
        blog_list.append({
            'title': blog['blog_title'],
            'url': blog['blog_url'],
            'excerpt': blog.get('best_matching_chunk', '')[:200]
        })

    # Build context for email generation
    email_context = f"""
Candidate Name: {name}
Current Role: {current_title} at {current_company}
Semantic Summary: {semantic_summary}

Recommended Blog Posts:
{json.dumps(blog_list, indent=2)}
"""

    # Use LLM to generate the email
    system_prompt = """You are a thoughtful, relationship-focused recruiter writing personalized nurture emails. Your emails should feel like they come from someone who genuinely knows and cares about each candidate's unique career.

CRITICAL: Each email must be HIGHLY PERSONALIZED and CREATIVE based on what's most interesting about THIS candidate. Don't follow a rigid formula — adapt your approach to what makes them unique.

TONE & STYLE (reference example):
"Hope you're doing great! I've been meaning to reach out since I saw you landed at Zoom as Customer Success Operations Manager back in late 2020 — that's over 4 years now, which is a solid run, especially during Zoom's explosive growth phase."

CORE STRUCTURE (but vary the content creatively):
1. **Warm, personal greeting** - vary your opening based on what stands out
2. **Career context** - pick what's most interesting: tenure, company growth, role transition, industry shift, etc.
3. **Synthesize their unique value** - what makes THEM special? What pattern do you see in their career? Be specific and insightful.
4. **Forward-looking questions** - ask about SPECIFIC next roles/directions that fit their trajectory (not generic)
   Examples: "Are you deepening in [specialty] or exploring [adjacent role]?"
   "Curious if you're eyeing VP roles or staying hands-on?"
   "Thinking about [specific industry] or staying in [current domain]?"
5. **Transition to value-add**: "I'd love to stay tuned into your goals so I can share things that are genuinely useful (opportunities, insights, or just good reads)."
6. **Blog intro**: "Speaking of which, here are a few pieces I thought you'd appreciate:"
7. **Blog recommendations** (format below)
8. **Warm, specific closing** - vary your offer: coffee chat, compare notes, quick call, etc.
9. **Encouraging sign-off**: e.g., "Keep crushing it at [Company]!" or similar

BLOG FORMATTING (exact format required):
Blog Title — Full URL
One sentence explaining WHY this specific blog matters to THEIR background/role/interests.

[blank line between blogs]

PERSONALIZATION VARIATIONS - Choose what to emphasize based on the candidate:
- Tenure at current company (if notable)
- Company growth phase or industry trends
- Unique skill combinations they've built
- Career pivots or transitions they've made
- Specific domain expertise
- Leadership progression
- Cross-functional experience
- Industry specialization

CAREER QUESTION VARIATIONS - Make them specific to their situation:
- "Deepening in [X] vs. exploring [Y] leadership?"
- "Staying in [industry] or eyeing [adjacent space]?"
- "Thinking about IC track vs. management?"
- "Next step: [specific role A] or [specific role B]?"
- "Curious about [specific challenge] in your space?"

CLOSING VARIATIONS - Mix it up:
- "grab 15 minutes to chat about..."
- "compare notes on [specific topic]..."
- "quick call about where you're headed..."
- "coffee chat about [relevant subject]..."

CRITICAL RULES:
- NO subject line
- NO specific name signature - just "Best,"
- Each blog MUST explain WHY it's relevant to THEM
- Be conversational, warm, but professional
- 4-5 paragraphs total
- VARY your approach - don't sound formulaic!"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_context}
            ],
            temperature=0.8,
            max_tokens=800
        )

        email_body = response.choices[0].message.content.strip()

        # Generate subject line separately for better control
        subject_prompt = f"""Generate a warm, conversational email subject line for {first_name}, a {current_title} at {current_company}.

Style examples to match:
- "How's [Company] treating you, [Name]?"
- "Quick check-in about your next move"
- "Thought you'd find these interesting"
- "[Name], curious where you're headed next"

Be creative and personal. Under 60 characters. No quotes."""

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
    2. Create semantic summary
    3. Vectorize and store
    4. Match blogs
    5. Generate email

    Request:
    {
        "candidate": { ... full candidate JSON ... }
    }

    Response:
    {
        "success": true,
        "candidate": { id, name, title, company, location },
        "semantic_summary": "...",
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

        # Step 2: Create semantic summary
        logger.info("Creating semantic summary...")
        semantic_summary = create_semantic_summary(candidate_info)

        # Step 3: Vectorize and store
        logger.info("Vectorizing candidate...")
        success = vectorize_candidate_summary(candidate_data, semantic_summary)
        if not success:
            return jsonify({'error': 'Failed to vectorize candidate profile'}), 500

        # Step 4: Match blogs
        logger.info("Finding matching blogs...")
        top_blogs = match_blogs_for_candidate_internal(candidate_id)
        if not top_blogs:
            return jsonify({'error': 'No matching blog posts found.'}), 404

        # Step 5: Generate email
        logger.info("Generating email...")
        email_content = generate_email_content(candidate_info, top_blogs, semantic_summary)

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
            'semantic_summary': semantic_summary,
            'blog_matches': format_blog_response(top_blogs),
            'email': email_content,
            'timestamp': datetime.now().isoformat()
        }

        logger.info("Successfully processed candidate!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error processing candidate: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/update-context', methods=['POST'])
def update_context():
    """
    Update candidate's context/understanding

    Flow:
    1. Get candidate from DB
    2. Merge new context with previous summary
    3. Re-vectorize with updated summary
    4. Store updated embedding

    Request:
    {
        "candidate_id": "pub_lnkd_123",
        "additional_context": "They mentioned interest in platform engineering...",
        "previous_summary": "John is a senior engineer..." (optional)
    }

    Response:
    {
        "success": true,
        "candidate_id": "...",
        "semantic_summary": "Updated summary...",
        "context_applied": "...",
        "timestamp": "..."
    }
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
        previous_summary = data.get('previous_summary', '')

        logger.info(f"Updating context for {candidate_id}")

        # Get candidate from database
        candidate_profile = matcher.get_candidate_by_id(candidate_id)
        if not candidate_profile:
            return jsonify({'error': f'Candidate {candidate_id} not found in database'}), 404

        # Step 1: Update semantic summary with new context
        logger.info("Updating semantic summary...")

        update_prompt = f"""You are updating a professional summary based on new information learned about a candidate.

Previous Summary:
{previous_summary}

New Information/Context:
{additional_context}

Please create an updated 2-3 sentence professional summary that incorporates this new information.
The summary should seamlessly blend the previous understanding with the new insights.
Focus on what's most relevant for matching them with blog content and career opportunities.

Output only the updated summary, nothing else."""

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": update_prompt}
                ],
                temperature=0.7,
                max_tokens=250
            )

            updated_summary = response.choices[0].message.content.strip()
            logger.info(f"Updated summary: {updated_summary[:100]}...")
        except Exception as e:
            logger.error(f"Error updating summary: {str(e)}")
            updated_summary = f"{previous_summary} {additional_context}"

        # Step 2: Re-vectorize with updated context
        logger.info("Re-vectorizing with updated context...")

        try:
            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=updated_summary
            )
            updated_embedding = embedding_response.data[0].embedding

            # Update the embedding in database
            supabase = matcher.supabase
            supabase.table('candidate_embeddings').update({
                'embedding': updated_embedding,
                'embedding_text': updated_summary
            }).eq('candidate_profile_id', candidate_profile['id']).execute()

            logger.info("Updated embedding in database")
        except Exception as e:
            logger.error(f"Error updating embedding: {str(e)}")
            return jsonify({'error': 'Failed to update candidate embedding'}), 500

        # Return response
        response = {
            'success': True,
            'candidate_id': candidate_id,
            'semantic_summary': updated_summary,
            'context_applied': additional_context,
            'timestamp': datetime.now().isoformat()
        }

        logger.info("Successfully updated candidate context!")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error updating context: {str(e)}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/generate-email', methods=['POST'])
def generate_email():
    """
    Generate email for an existing candidate

    Flow:
    1. Get candidate from DB
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
        "semantic_summary": "...",
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

        # Get semantic summary from database
        try:
            supabase = matcher.supabase
            embedding_data = supabase.table('candidate_embeddings').select('embedding_text').eq(
                'candidate_profile_id', candidate_profile['id']
            ).execute()

            semantic_summary = embedding_data.data[0]['embedding_text'] if embedding_data.data else ''
        except Exception as e:
            logger.error(f"Error retrieving semantic summary: {str(e)}")
            semantic_summary = f"{candidate_info['full_name']} - {candidate_info['current_title']}"

        # Match blogs
        logger.info("Finding matching blogs...")
        top_blogs = match_blogs_for_candidate_internal(candidate_id)
        if not top_blogs:
            return jsonify({'error': 'No matching blog posts found.'}), 404

        # Generate email
        logger.info("Generating email...")
        email_content = generate_email_content(candidate_info, top_blogs, semantic_summary)

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
            'semantic_summary': semantic_summary,
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
