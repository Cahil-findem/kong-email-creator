# Candidate Profile Vectorization & Blog Matching

This system vectorizes candidate profiles and matches them with relevant blog content for personalized nurture campaigns.

## Overview

The system works in three steps:

1. **Vectorize Candidates**: Convert candidate profiles into embeddings using OpenAI
2. **Match to Blogs**: Find most relevant blog posts for each candidate using vector similarity
3. **Generate Emails**: Create personalized content recommendations for nurture campaigns

## Architecture

```
Candidate JSON → Extract & Format → OpenAI Embedding → Supabase (pgvector)
                                                              ↓
Blog Chunks (already vectorized) ←─── Vector Similarity Search
                                                              ↓
                                        Ranked Blog Recommendations
```

## Setup

### 1. Run Database Schema

Execute `candidate_schema.sql` in your Supabase SQL Editor:

```bash
# Copy the contents of candidate_schema.sql and run in Supabase
```

This creates:
- `candidate_profiles` table - stores candidate metadata
- `candidate_embeddings` table - stores profile embeddings
- Helper functions for searching and matching

### 2. Prepare Your Candidate Data

Save your candidate data as a JSON file. The system supports two formats:

**Format 1: Dict with IDs as keys**
```json
{
  "68d193fecb73815f93cc0e45": {
    "candidate": {
      "full_name": "John Doe",
      "about_me": "Experienced developer...",
      ...
    },
    "skills": ["Python", "JavaScript", ...],
    "workexp": [...],
    ...
  }
}
```

**Format 2: Array of candidates**
```json
[
  {
    "ref": "68d193fecb73815f93cc0e45",
    "candidate": {...},
    "skills": [...],
    ...
  }
]
```

### 3. Verify Environment Variables

Make sure your `.env` file has:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=sk-your-openai-key
```

## Usage

### Step 1: Vectorize Candidate Profiles

```bash
python vectorize_candidates.py candidates.json
```

This will:
- Extract candidate information (bio, skills, experience, education)
- Format into optimized text for embedding
- Generate embeddings using OpenAI `text-embedding-3-small`
- Save profiles and embeddings to Supabase
- Log progress to `vectorize_candidates.log`

**What gets embedded:**
```
Candidate: John Doe
Location: San Francisco, CA
Current Role: Senior Engineer at Tech Co

Professional Summary:
Experienced software engineer with 8+ years...

Skills and Expertise:
Python, JavaScript, React, Node.js, AWS, Docker...

Work Experience:
- Tech Co (San Francisco, CA)
  Senior Software Engineer
  January 2020 - Present
  Led development of microservices architecture...

- Previous Co
  Software Engineer
  June 2017 - December 2019
  ...

Education:
- Bachelor of Science in Computer Science from Stanford University (2013 - 2017)
```

### Step 2: Match Candidates to Blog Posts

**For a single candidate:**
```bash
python match_candidates_to_blogs.py 68d193fecb73815f93cc0e45
```

**For a specific number of recommendations:**
```bash
python match_candidates_to_blogs.py 68d193fecb73815f93cc0e45 10
```

**For all candidates (batch mode):**
```bash
python match_candidates_to_blogs.py --all
```

This generates `candidate_recommendations.json`:
```json
[
  {
    "candidate": {
      "name": "John Doe",
      "email": "john@example.com",
      "current_title": "Senior Engineer"
    },
    "recommended_articles": [
      {
        "title": "Building Microservices with Python",
        "url": "https://konghq.com/blog/...",
        "author": "Jane Smith",
        "published_date": "2024-03-15",
        "relevance_score": 87.3,
        "excerpt": "Learn how to build scalable microservices..."
      },
      ...
    ]
  }
]
```

### Step 3: Use Recommendations for Email Campaigns

The output JSON is ready to use in your email nurture system. Example email template:

```html
Hi {{candidate.name}},

Based on your background in {{candidate.current_title}}, we thought you'd find these articles interesting:

{{#each recommended_articles}}
📚 {{this.title}}
   {{this.url}}
   {{this.excerpt}}
{{/each}}

Happy reading!
```

## Configuration

### Matching Thresholds

Adjust similarity thresholds in `match_candidates_to_blogs.py`:

```python
# More strict matching (higher quality, fewer results)
match_threshold=0.75

# More lenient matching (more results, lower quality)
match_threshold=0.60

# Default balanced matching
match_threshold=0.65
```

### Number of Recommendations

```python
# Fewer, more relevant articles
num_articles=3

# More articles for longer emails
num_articles=10
```

## Database Queries

### Check Vectorization Status

```sql
-- View all candidates with embeddings
SELECT * FROM candidate_profiles_summary;

-- Count candidates by embedding status
SELECT
  has_embedding,
  COUNT(*) as count
FROM candidate_profiles_summary
GROUP BY has_embedding;
```

### Manual Matching Query

```sql
-- Get recommendations for a specific candidate
SELECT * FROM search_top_blogs_for_candidate(
  (SELECT embedding FROM candidate_embeddings WHERE candidate_profile_id = 1),
  0.65,  -- match_threshold
  5      -- match_count
);
```

### Find Candidates by Skill/Interest

```sql
-- Find candidates with specific skills
SELECT
  full_name,
  current_title,
  skills
FROM candidate_profiles
WHERE skills::text ILIKE '%python%'
  AND skills::text ILIKE '%api%';
```

## Advanced Usage

### Custom Matching with Filters

```python
from match_candidates_to_blogs import CandidateBlogMatcher

matcher = CandidateBlogMatcher()

# Get recommendations
recommendations = matcher.generate_email_recommendations(
    candidate_id='68d193fecb73815f93cc0e45',
    num_articles=5,
    match_threshold=0.70
)

# Filter by date or other criteria
recent_articles = [
    article for article in recommendations['recommended_articles']
    if '2024' in article['published_date']
]
```

### Re-vectorize Updated Profiles

If candidate profiles are updated:

```bash
# Re-vectorize all (updates existing embeddings)
python vectorize_candidates.py candidates.json

# The script automatically updates existing profiles
```

### Export for Email Service

```python
import json

# Load recommendations
with open('candidate_recommendations.json', 'r') as f:
    recommendations = json.load(f)

# Convert to your email service format (e.g., Mailchimp, SendGrid)
for rec in recommendations:
    email_data = {
        'to': rec['candidate']['email'],
        'subject': f"Recommended reading for {rec['candidate']['name']}",
        'articles': rec['recommended_articles']
    }
    # Send via your email service
```

## Cost Estimation

**OpenAI Embedding Costs:**
- Model: `text-embedding-3-small`
- Price: $0.020 per 1M tokens
- Average candidate profile: ~500-800 tokens
- **100 candidates ≈ 60,000 tokens ≈ $0.001** (very cheap!)

**Matching Costs:**
- Matching is free (uses existing blog embeddings)
- No API calls needed for matching

## Monitoring

### Watch Progress

```bash
# Monitor vectorization
tail -f vectorize_candidates.log

# Monitor matching
tail -f candidate_matching.log
```

### Check Stats

```sql
-- Total candidates vectorized
SELECT COUNT(*) FROM candidate_embeddings;

-- Average token count per profile
SELECT AVG(token_count) FROM candidate_embeddings;

-- Most recently vectorized
SELECT
  cp.full_name,
  cp.current_title,
  ce.created_at
FROM candidate_profiles cp
JOIN candidate_embeddings ce ON cp.id = ce.candidate_profile_id
ORDER BY ce.created_at DESC
LIMIT 10;
```

## Troubleshooting

### "Candidate not found or has no embedding"
- Make sure you've run `vectorize_candidates.py` first
- Check that the candidate_id matches the `ref` field in your JSON

### "No matching blogs found"
- Lower the `match_threshold` (try 0.5 or 0.55)
- Make sure you've vectorized blog posts first (see `VECTORIZATION_README.md`)
- Check that blog_chunks table has data

### "relation 'candidate_profiles' does not exist"
- Run `candidate_schema.sql` in Supabase SQL Editor first

## Email Campaign Best Practices

1. **Frequency**: Send recommendations weekly or bi-weekly
2. **Personalization**: Use candidate's name and role in subject line
3. **Context**: Explain why these articles are relevant to them
4. **Diversity**: Mix different topics (avoid all articles about same thing)
5. **Freshness**: Prioritize recent blog posts when possible
6. **Tracking**: Include UTM parameters to track engagement

## Next Steps

1. ✅ Run `candidate_schema.sql` in Supabase
2. ✅ Prepare your candidate JSON file
3. ✅ Run `vectorize_candidates.py candidates.json`
4. ✅ Test matching with `match_candidates_to_blogs.py <candidate_id>`
5. ✅ Generate batch recommendations with `--all` flag
6. 🔜 Integrate with your email service
7. 🔜 Track engagement and refine matching thresholds

## Files Reference

- `candidate_schema.sql` - Database schema for candidates
- `vectorize_candidates.py` - Vectorizes candidate profiles
- `match_candidates_to_blogs.py` - Matches candidates to blogs
- `vectorize_candidates.log` - Vectorization logs
- `candidate_matching.log` - Matching logs
- `candidate_recommendations.json` - Output recommendations

---

**Questions?** Check out the main `VECTORIZATION_README.md` for blog vectorization details.

Happy nurturing! 📧✨
