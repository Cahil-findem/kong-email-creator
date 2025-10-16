# Kong Email Generator API Documentation

## Base URL

- **Production:** `https://kong-email-creator.vercel.app`
- **Local:** `http://localhost:8000`

---

## Authentication (Optional)

If `API_KEY` environment variable is set, all requests must include authentication:

**Header method (recommended):**
```
X-API-Key: your-secret-api-key
```

**Query parameter method:**
```
?api_key=your-secret-api-key
```

---

## API Architecture

The API uses a **three-field embedding system** for enhanced candidate understanding:

1. **Professional Summary** - WHO they are professionally (used for blog matching)
2. **Job Preferences** - WHAT they want next (structured format)
3. **Interests** - WHAT content resonates (bulleted list)

### Core Endpoints

1. **`/api/process-candidate`** - All-in-one convenience endpoint for initial processing
2. **`/api/update-context`** - Update specific sections (job_preferences or interests)
3. **`/api/generate-email`** - Generate email from existing candidate data
4. **`/api/health`** - Health check

### Common Workflows

**Initial candidate processing:**
```
POST /api/process-candidate
```

**Iterative refinement (after learning new info about candidate):**
```
1. POST /api/update-context (update interests or job_preferences)
2. POST /api/generate-email
```

**Regenerate email (A/B testing, different tone, etc.):**
```
POST /api/generate-email
```

---

## Endpoints

### 1. Process Candidate (All-in-One)

**POST** `/api/process-candidate`

Orchestrates the full flow: extract info → generate three summaries → vectorize → match blogs → generate email.

#### Request

**Headers:**
```
Content-Type: application/json
X-API-Key: your-secret-api-key (if authentication enabled)
```

**Body:**
```json
{
  "candidate": {
    "ref": "candidate_id_123",
    "candidate": {
      "full_name": "John Doe",
      "about_me": "Experienced software engineer...",
      "location": {
        "city": "San Francisco",
        "state": "CA",
        "country": "USA"
      },
      "linkedin": "https://linkedin.com/in/johndoe",
      "emails": ["john@example.com"]
    },
    "skills": ["Python", "JavaScript", "API Design", "PostgreSQL"],
    "workexp": [
      {
        "company": {
          "name": "Acme Corp"
        },
        "projects": [
          {
            "role_and_group": {
              "title": "Senior Software Engineer"
            },
            "description": "Led development of..."
          }
        ],
        "duration": {
          "start_date": "2020-01-01",
          "end_date": "2024-01-01"
        }
      }
    ],
    "education": [
      {
        "school_info": {
          "name": "University of Example"
        },
        "education_details": {
          "degree": ["Bachelor of Science"],
          "major": ["Computer Science"]
        },
        "duration": {
          "start_date": "2012-09-01",
          "end_date": "2016-06-01"
        }
      }
    ]
  }
}
```

#### Response (Success - 200 OK)

```json
{
  "success": true,
  "candidate": {
    "id": "candidate_id_123",
    "name": "John Doe",
    "title": "Senior Software Engineer",
    "company": "Acme Corp",
    "location": "San Francisco, CA, USA"
  },
  "candidate_profile": {
    "ref": "candidate_id_123",
    "candidate": {
      "full_name": "John Doe",
      "about_me": "Experienced software engineer...",
      "location": {
        "city": "San Francisco",
        "state": "CA",
        "country": "USA"
      }
    },
    "skills": ["Python", "JavaScript", "API Design", "PostgreSQL"],
    "workexp": [...],
    "education": [...]
  },
  "professional_summary": "John Doe is a seasoned Senior Software Engineer with over 4 years of experience at Acme Corp, demonstrating deep expertise in backend development, API design, and database optimization. His career trajectory shows consistent growth in technical leadership and system architecture, with a strong focus on building scalable solutions.",
  "job_preferences": "Job Titles: Staff Software Engineer, Engineering Manager, Principal Engineer\nLocation: San Francisco Bay Area or Remote\nSeniority: Senior IC or Manager",
  "interests": "• API Architecture & Design\n• PostgreSQL Optimization\n• Microservices Patterns\n• Python Development\n• Cloud Infrastructure",
  "blog_matches": [
    {
      "title": "Building Scalable APIs with Kong Gateway",
      "url": "https://konghq.com/blog/engineering/scalable-apis",
      "relevance": 87.3,
      "author": "Jane Smith",
      "excerpt": "In this post, we explore patterns for building highly scalable APIs..."
    },
    {
      "title": "Microservices Best Practices",
      "url": "https://konghq.com/blog/engineering/microservices",
      "relevance": 82.1,
      "author": "Bob Johnson",
      "excerpt": "Learn how to design resilient microservices architectures..."
    },
    {
      "title": "PostgreSQL Performance Tuning",
      "url": "https://konghq.com/blog/engineering/postgres-tuning",
      "relevance": 78.9,
      "author": "Alice Chen",
      "excerpt": "Tips and tricks for optimizing your PostgreSQL database..."
    }
  ],
  "email": {
    "subject": "How's Acme treating you, John?",
    "body": "Hi John,\n\nHope you're doing great! I've been meaning to reach out...",
    "candidate_name": "John Doe",
    "candidate_title": "Senior Software Engineer",
    "blog_count": 3
  },
  "timestamp": "2025-10-14T14:30:00.000Z"
}
```

**Response Field Details:**

- **`candidate`**: Summary object with id, name, title, company, location
- **`candidate_profile`**: Full raw candidate JSON (for external services)
- **`professional_summary`**: Paragraph describing professional identity, expertise, and trajectory. Used for blog matching.
- **`job_preferences`**: Structured format with Job Titles, Location, and Seniority preferences.
- **`interests`**: Bulleted list of technologies, industries, and professional topics.
- **`blog_matches`**: Array of relevant blog posts with titles, URLs, and relevance scores
- **`email`**: Generated email with subject and body

---

### 2. Update Candidate Context

**POST** `/api/update-context`

Updates a specific section of the candidate's profile with new information. Re-generates embedding for that section only.

**Use case:** After a conversation, phone call, or learning new details about the candidate's preferences or interests.

#### Request

**Headers:**
```
Content-Type: application/json
X-API-Key: your-secret-api-key (if authentication enabled)
```

**Body:**
```json
{
  "candidate_id": "candidate_id_123",
  "additional_context": "Expressed interest in learning Terraform and GitOps practices. Currently reading 'The Phoenix Project'.",
  "section": "interests"
}
```

**Fields:**
- `candidate_id` (required): The candidate's unique identifier
- `additional_context` (required): New information to append
- `section` (optional): Either `"interests"` or `"job_preferences"`. Defaults to `"interests"`.

**Important Notes:**
- Context is **appended** with a timestamp, not replaced
- Professional summary cannot be updated via this endpoint (it's derived from profile data)
- Use `"interests"` section for: new technologies, topics, industries they're exploring
- Use `"job_preferences"` section for: new role preferences, location changes, seniority goals

#### Response (Success - 200 OK)

```json
{
  "success": true,
  "candidate_id": "candidate_id_123",
  "section_updated": "interests",
  "updated_content": "• API Architecture & Design\n• PostgreSQL Optimization\n• Microservices Patterns\n• Python Development\n• Cloud Infrastructure\n\n[Updated 2025-10-14] Expressed interest in learning Terraform and GitOps practices. Currently reading 'The Phoenix Project'.",
  "context_added": "Expressed interest in learning Terraform and GitOps practices. Currently reading 'The Phoenix Project'.",
  "content_length": 312,
  "timestamp": "2025-10-14T14:35:00.000Z"
}
```

---

### 3. Generate Email

**POST** `/api/generate-email`

Generates a personalized email for an existing candidate using their current profile and embeddings.

**Use cases:**
- After updating context via `/api/update-context`
- A/B testing different email tones
- Regenerating email with fresh blog matches

#### Request

**Headers:**
```
Content-Type: application/json
X-API-Key: your-secret-api-key (if authentication enabled)
```

**Body:**
```json
{
  "candidate_id": "candidate_id_123"
}
```

#### Response (Success - 200 OK)

```json
{
  "success": true,
  "candidate": {
    "id": "candidate_id_123",
    "name": "John Doe",
    "title": "Senior Software Engineer",
    "company": "Acme Corp",
    "location": "San Francisco, CA, USA"
  },
  "candidate_profile": {
    "ref": "candidate_id_123",
    "candidate": {
      "full_name": "John Doe",
      "about_me": "Experienced software engineer...",
      "location": {
        "city": "San Francisco",
        "state": "CA",
        "country": "USA"
      }
    },
    "skills": ["Python", "JavaScript", "API Design", "PostgreSQL"],
    "workexp": [...],
    "education": [...]
  },
  "professional_summary": "John Doe is a seasoned Senior Software Engineer with over 4 years of experience...",
  "job_preferences": "Job Titles: Staff Software Engineer, Engineering Manager, Principal Engineer\nLocation: San Francisco Bay Area or Remote\nSeniority: Senior IC or Manager",
  "interests": "• API Architecture & Design\n• PostgreSQL Optimization\n• Microservices Patterns\n• Python Development\n• Cloud Infrastructure\n\n[Updated 2025-10-14] Expressed interest in learning Terraform and GitOps practices. Currently reading 'The Phoenix Project'.",
  "blog_matches": [
    {
      "title": "GitOps with Kubernetes",
      "url": "https://konghq.com/blog/engineering/gitops-k8s",
      "relevance": 91.5,
      "author": "Sarah Lee",
      "excerpt": "Learn how to implement GitOps workflows..."
    },
    {
      "title": "Infrastructure as Code Best Practices",
      "url": "https://konghq.com/blog/engineering/iac-terraform",
      "relevance": 88.2,
      "author": "Mike Chen",
      "excerpt": "Building scalable infrastructure with Terraform..."
    },
    {
      "title": "Platform Engineering at Scale",
      "url": "https://konghq.com/blog/engineering/platform-engineering",
      "relevance": 85.7,
      "author": "Anna Kim",
      "excerpt": "Designing internal developer platforms..."
    }
  ],
  "email": {
    "subject": "Platform engineering—interested in making the leap, John?",
    "body": "Hi John,\n\nHope you're doing great! I know you've been exploring Terraform and GitOps...",
    "candidate_name": "John Doe",
    "candidate_title": "Senior Software Engineer",
    "blog_count": 3
  },
  "timestamp": "2025-10-14T14:36:00.000Z"
}
```

---

### 4. Health Check

**GET** `/api/health`

Check if the API is running.

#### Response (200 OK)

```json
{
  "status": "healthy",
  "service": "candidate-email-generator",
  "timestamp": "2025-10-14T14:30:00.000Z"
}
```

---

## Error Responses

All endpoints may return the following error responses:

**400 Bad Request** - Invalid input
```json
{
  "error": "Invalid request. Please provide candidate JSON."
}
```

**401 Unauthorized** - Invalid or missing API key
```json
{
  "error": "Unauthorized: Invalid API key"
}
```

**404 Not Found** - Resource not found
```json
{
  "error": "Candidate candidate_id_123 not found in database"
}
```

**500 Internal Server Error** - Processing error
```json
{
  "error": "Server error: <error details>"
}
```

---

## Code Examples

### JavaScript/TypeScript

**Initial candidate processing:**
```typescript
async function processCandidate(candidateData: any) {
  const response = await fetch('https://kong-email-creator.vercel.app/api/process-candidate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-secret-api-key'
    },
    body: JSON.stringify({ candidate: candidateData })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error);
  }

  const result = await response.json();

  // Access three-field system
  console.log('Professional Summary:', result.professional_summary);
  console.log('Job Preferences:', result.job_preferences);
  console.log('Interests:', result.interests);

  return result;
}
```

**Update interests and regenerate:**
```typescript
async function updateInterestsAndRegenerate(
  candidateId: string,
  newInterests: string
) {
  // Step 1: Update interests section
  const updateResponse = await fetch('https://kong-email-creator.vercel.app/api/update-context', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-secret-api-key'
    },
    body: JSON.stringify({
      candidate_id: candidateId,
      additional_context: newInterests,
      section: 'interests'  // or 'job_preferences'
    })
  });

  const updateData = await updateResponse.json();
  if (!updateResponse.ok) throw new Error(updateData.error);

  // Step 2: Generate new email
  const emailResponse = await fetch('https://kong-email-creator.vercel.app/api/generate-email', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-secret-api-key'
    },
    body: JSON.stringify({ candidate_id: candidateId })
  });

  const emailData = await emailResponse.json();
  if (!emailResponse.ok) throw new Error(emailData.error);

  return emailData;
}
```

### Python

**Initial candidate processing:**
```python
import requests

def process_candidate(candidate_data):
    url = "https://kong-email-creator.vercel.app/api/process-candidate"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "your-secret-api-key"
    }

    response = requests.post(url, json={"candidate": candidate_data}, headers=headers)
    response.raise_for_status()

    result = response.json()

    # Access three-field system
    print("Professional Summary:", result['professional_summary'])
    print("Job Preferences:", result['job_preferences'])
    print("Interests:", result['interests'])

    return result
```

**Update job preferences and regenerate:**
```python
def update_preferences_and_regenerate(candidate_id, new_preferences):
    base_url = "https://kong-email-creator.vercel.app"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "your-secret-api-key"
    }

    # Step 1: Update job_preferences section
    update_response = requests.post(
        f"{base_url}/api/update-context",
        json={
            "candidate_id": candidate_id,
            "additional_context": new_preferences,
            "section": "job_preferences"  # or 'interests'
        },
        headers=headers
    )
    update_response.raise_for_status()

    # Step 2: Generate email
    email_response = requests.post(
        f"{base_url}/api/generate-email",
        json={"candidate_id": candidate_id},
        headers=headers
    )
    email_response.raise_for_status()

    return email_response.json()
```

### cURL

**Initial processing:**
```bash
curl -X POST https://kong-email-creator.vercel.app/api/process-candidate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d @candidate.json
```

**Update interests:**
```bash
curl -X POST https://kong-email-creator.vercel.app/api/update-context \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "candidate_id": "candidate_id_123",
    "additional_context": "Interested in platform engineering and Kubernetes",
    "section": "interests"
  }'
```

**Update job preferences:**
```bash
curl -X POST https://kong-email-creator.vercel.app/api/update-context \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "candidate_id": "candidate_id_123",
    "additional_context": "Now open to remote roles. Considering Director-level positions.",
    "section": "job_preferences"
  }'
```

**Generate email:**
```bash
curl -X POST https://kong-email-creator.vercel.app/api/generate-email \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{"candidate_id": "candidate_id_123"}'
```

---

## Performance

- **Average Response Time:** 5-8 seconds
- **Timeout:** 60 seconds
- **Rate Limit:** None (recommended to add if needed)

### Processing Times

| Endpoint | Average Time | Steps |
|----------|--------------|-------|
| `/api/process-candidate` | 5-8s | Extract → 3 Summaries → Vectorize (3x) → Match → Email |
| `/api/update-context` | 2-3s | Append context → Re-vectorize section → Update DB |
| `/api/generate-email` | 4-5s | Fetch profile → Match blogs → Generate email |

### Processing Steps Detail

**`/api/process-candidate`:**
1. Extract candidate information from JSON (~instant)
2. Generate three summaries using GPT-4o-mini (~2-3s)
   - Professional summary (paragraph)
   - Job preferences (structured)
   - Interests (bulleted list)
3. Create three vector embeddings using OpenAI (~1-2s)
4. Search 750+ blog posts using professional_summary embedding (~1s)
5. Filter for diversity (remove generic posts) (~instant)
6. Generate personalized email with GPT-4o (~3s)
7. Generate subject line with GPT-4o-mini (~1s)

**`/api/update-context`:**
1. Retrieve existing section content (~instant)
2. Append new context with timestamp (~instant)
3. Create new vector embedding for that section only (~1s)
4. Update database (~instant)

**`/api/generate-email`:**
1. Retrieve candidate profile with all three embeddings from DB (~instant)
2. Search 750+ blog posts using professional_summary embedding (~1s)
3. Filter for diversity (~instant)
4. Generate personalized email with GPT-4o (~3s)
5. Generate subject line with GPT-4o-mini (~1s)

---

## Cost

- **`/api/process-candidate`:** ~$0.003 per request (3 embeddings + 2 LLM calls)
- **`/api/update-context`:** ~$0.001 per request (1 embedding)
- **`/api/generate-email`:** ~$0.002 per request (2 LLM calls)

---

## Three-Field System Details

### Professional Summary
**Format:** Natural paragraph (2-3 sentences)

**Purpose:** Blog matching via vector similarity search

**Example:**
```
Scott Haidarian is a dedicated and ambitious Senior Commissions Analyst
with over three years of experience in sales operations and financial
analysis, primarily within the tech industry. His expertise lies in CRM
systems, commission structures, and data-driven revenue optimization.
```

**Cannot be updated** - regenerated from profile data only

---

### Job Preferences
**Format:** Structured text with three lines

**Purpose:** Track evolving career goals

**Template:**
```
Job Titles: [role 1], [role 2], [role 3]
Location: [location or Remote/Flexible]
Seniority: [IC/Senior IC/Manager/Director/VP/Executive]
```

**Example:**
```
Job Titles: Sales Analyst, Financial Analyst, Revenue Operations Manager
Location: San Francisco Bay Area or Remote
Seniority: Senior IC
```

**Can be updated** via `/api/update-context` with `section: "job_preferences"`

---

### Interests
**Format:** Bulleted list of topics

**Purpose:** Track professional interests for content matching

**Example:**
```
• Sales Analytics
• Financial Forecasting
• CRM Systems
• Revenue Optimization
• Data-Driven Decision Making
```

**Can be updated** via `/api/update-context` with `section: "interests"` (default)

**Accumulation example:**
```
• Sales Analytics
• Financial Forecasting
• CRM Systems

[Updated 2025-10-14] Interested in learning Terraform and GitOps
```

---

## Required Candidate Fields

**Minimum required:**
- `ref` - Unique candidate identifier
- `candidate.full_name` - Candidate's full name

**Recommended for better results:**
- `candidate.about_me` - Professional summary/bio
- `candidate.location` - City, state, country
- `skills` - Array of professional skills
- `workexp` - Work experience history with titles and companies
- `education` - Educational background

The more information provided, the better the three-field summaries and blog matching.

---

## Integration Checklist

- [ ] Get API endpoint URL from team lead
- [ ] Get API key (if authentication is enabled)
- [ ] Test with sample candidate JSON
- [ ] Handle success response (200 OK)
- [ ] Handle error responses (400, 401, 404, 500)
- [ ] Implement retry logic for timeouts
- [ ] Display professional_summary, job_preferences, and interests
- [ ] Display email subject and body to user
- [ ] Optionally display blog matches
- [ ] Test section-based context updates (interests and job_preferences)
- [ ] Test iterative refinement flow (update context → regenerate)
- [ ] Add error logging for debugging

---

## Support & Troubleshooting

### Common Issues

**1. "Invalid API key" error**
- Check that `X-API-Key` header matches the shared key
- Ensure no extra spaces or quotes in the key

**2. "Candidate not found" error**
- Candidate must be processed via `/api/process-candidate` first
- Verify the `candidate_id` matches the `ref` field from initial processing

**3. "No matching blog posts found" error**
- Candidate profile may be too sparse
- Add more skills, work experience, or bio information
- Ensure professional_summary was generated properly

**4. "Invalid section" error in /api/update-context**
- Section must be either `"interests"` or `"job_preferences"`
- Professional summary cannot be updated via this endpoint

**5. Request timeout**
- Normal processing takes 5-8 seconds
- Retry the request if timeout occurs

**6. Invalid JSON format error**
- Validate your JSON before sending
- Ensure candidate object structure matches the documentation

**7. CORS errors (browser-based apps)**
- CORS is enabled on the API
- If issues persist, contact team lead

For additional support:
- Check API health: `GET /api/health`
- Review your request JSON structure
- Verify all three fields are returned in responses

---

## Migration from Old System

If you were using the old `semantic_summary` field:

**Old response format:**
```json
{
  "semantic_summary": "John is a senior software engineer..."
}
```

**New response format:**
```json
{
  "professional_summary": "John Doe is a seasoned Senior Software Engineer...",
  "job_preferences": "Job Titles: Staff Engineer, Engineering Manager\nLocation: Remote\nSeniority: Senior IC",
  "interests": "• API Architecture\n• PostgreSQL\n• Microservices"
}
```

**Migration steps:**
1. Update your code to use `professional_summary` instead of `semantic_summary`
2. Optionally display `job_preferences` and `interests` in your UI
3. Update context update calls to specify `section` parameter
4. Re-process existing candidates to generate three-field summaries

---

Last Updated: October 14, 2025
API Version: 3.0 (Three-Field Embedding System)
Documentation maintained by: Kong Email Generator Team
