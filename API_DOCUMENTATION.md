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

The API is designed with modular endpoints for flexibility:

1. **`/api/process-candidate`** - All-in-one convenience endpoint for initial processing
2. **`/api/update-context`** - Update candidate understanding with new information
3. **`/api/generate-email`** - Generate email from existing candidate data
4. **`/api/health`** - Health check

### Common Workflows

**Initial candidate processing:**
```
POST /api/process-candidate
```

**Iterative refinement (after learning new info about candidate):**
```
1. POST /api/update-context
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

Orchestrates the full flow: extract info → generate summary → vectorize → match blogs → generate email.

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
  "semantic_summary": "John is a senior software engineer with deep expertise in Python, JavaScript, and API architecture...",
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
  "timestamp": "2025-10-10T14:30:00.000Z"
}
```

---

### 2. Update Candidate Context

**POST** `/api/update-context`

Updates a candidate's semantic understanding with new information. Re-generates summary and updates vector embeddings.

**Use case:** After a conversation, phone call, or learning new details about the candidate.

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
  "additional_context": "They mentioned they're interested in moving to platform engineering roles and have been exploring Kubernetes and cloud-native technologies.",
  "previous_summary": "John is a senior software engineer with deep expertise in Python, JavaScript, and API architecture..."
}
```

**Fields:**
- `candidate_id` (required): The candidate's unique identifier
- `additional_context` (required): New information about the candidate
- `previous_summary` (optional): Current semantic summary. If not provided, will retrieve from database.

#### Response (Success - 200 OK)

```json
{
  "success": true,
  "candidate_id": "candidate_id_123",
  "semantic_summary": "John is a senior software engineer with deep expertise in Python, JavaScript, and API architecture. He is now exploring platform engineering and has expressed strong interest in Kubernetes and cloud-native technologies.",
  "context_applied": "They mentioned they're interested in moving to platform engineering roles and have been exploring Kubernetes and cloud-native technologies.",
  "timestamp": "2025-10-10T14:35:00.000Z"
}
```

---

### 3. Generate Email

**POST** `/api/generate-email`

Generates a personalized email for an existing candidate using their current semantic profile and embeddings.

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
  "semantic_summary": "John is a senior software engineer with deep expertise in Python, JavaScript, and API architecture. He is now exploring platform engineering...",
  "blog_matches": [
    {
      "title": "Kubernetes Best Practices",
      "url": "https://konghq.com/blog/engineering/k8s-best-practices",
      "relevance": 91.5,
      "author": "Sarah Lee",
      "excerpt": "Learn how to deploy and manage Kubernetes clusters..."
    },
    {
      "title": "Platform Engineering at Scale",
      "url": "https://konghq.com/blog/engineering/platform-engineering",
      "relevance": 88.2,
      "author": "Mike Chen",
      "excerpt": "Building internal developer platforms..."
    },
    {
      "title": "Cloud-Native Architecture Patterns",
      "url": "https://konghq.com/blog/engineering/cloud-native",
      "relevance": 85.7,
      "author": "Anna Kim",
      "excerpt": "Designing cloud-native applications..."
    }
  ],
  "email": {
    "subject": "Platform engineering—interested in making the leap, John?",
    "body": "Hi John,\n\nHope you're doing great! I know you've been exploring Kubernetes...",
    "candidate_name": "John Doe",
    "candidate_title": "Senior Software Engineer",
    "blog_count": 3
  },
  "timestamp": "2025-10-10T14:36:00.000Z"
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
  "timestamp": "2025-10-10T14:30:00.000Z"
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

  return await response.json();
}
```

**Update context and regenerate:**
```typescript
async function updateAndRegenerate(candidateId: string, newContext: string, previousSummary: string) {
  // Step 1: Update context
  const updateResponse = await fetch('https://kong-email-creator.vercel.app/api/update-context', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-secret-api-key'
    },
    body: JSON.stringify({
      candidate_id: candidateId,
      additional_context: newContext,
      previous_summary: previousSummary
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

    return response.json()
```

**Update context and regenerate:**
```python
def update_and_regenerate(candidate_id, new_context, previous_summary):
    base_url = "https://kong-email-creator.vercel.app"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "your-secret-api-key"
    }

    # Step 1: Update context
    update_response = requests.post(
        f"{base_url}/api/update-context",
        json={
            "candidate_id": candidate_id,
            "additional_context": new_context,
            "previous_summary": previous_summary
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

**Update context:**
```bash
curl -X POST https://kong-email-creator.vercel.app/api/update-context \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "candidate_id": "candidate_id_123",
    "additional_context": "Interested in platform engineering and Kubernetes",
    "previous_summary": "Senior software engineer..."
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
- **Timeout:** 30 seconds
- **Rate Limit:** None (recommended to add if needed)

### Processing Times

| Endpoint | Average Time | Steps |
|----------|--------------|-------|
| `/api/process-candidate` | 5-8s | Extract → Summary → Vectorize → Match → Email |
| `/api/update-context` | 2-3s | Update summary → Re-vectorize → Update DB |
| `/api/generate-email` | 4-5s | Fetch profile → Match blogs → Generate email |

### Processing Steps Detail

**`/api/process-candidate`:**
1. Extract candidate information from JSON (~instant)
2. Generate semantic summary using GPT-4o-mini (~2s)
3. Create vector embedding using OpenAI (~1s)
4. Search 750+ blog posts for matches (~1s)
5. Filter for diversity (remove generic posts) (~instant)
6. Generate personalized email with GPT-4o (~3s)
7. Generate subject line with GPT-4o-mini (~1s)

**`/api/update-context`:**
1. Merge new context with previous summary using GPT-4o-mini (~2s)
2. Create new vector embedding (~1s)
3. Update database (~instant)

**`/api/generate-email`:**
1. Retrieve candidate profile and embeddings from DB (~instant)
2. Search 750+ blog posts for matches (~1s)
3. Filter for diversity (~instant)
4. Generate personalized email with GPT-4o (~3s)
5. Generate subject line with GPT-4o-mini (~1s)

---

## Cost

- **`/api/process-candidate`:** ~$0.002 per request
- **`/api/update-context`:** ~$0.001 per request
- **`/api/generate-email`:** ~$0.002 per request

---

## Required Candidate Fields

**Minimum required:**
- `ref` - Unique candidate identifier
- `candidate.full_name` - Candidate's full name

**Recommended for better results:**
- `candidate.about_me` - Professional summary/bio
- `candidate.location` - City, state, country
- `skills` - Array of professional skills
- `workexp` - Work experience history
- `education` - Educational background

The more information provided, the better the email personalization and blog matching.

---

## Integration Checklist

- [ ] Get API endpoint URL from team lead
- [ ] Get API key (if authentication is enabled)
- [ ] Test with sample candidate JSON
- [ ] Handle success response (200 OK)
- [ ] Handle error responses (400, 401, 404, 500)
- [ ] Implement retry logic for timeouts
- [ ] Display email subject and body to user
- [ ] Optionally display blog matches and semantic summary
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

**4. Request timeout**
- Normal processing takes 5-8 seconds
- Retry the request if timeout occurs

**5. Invalid JSON format error**
- Validate your JSON before sending
- Ensure candidate object structure matches the documentation

**6. CORS errors (browser-based apps)**
- CORS is enabled on the API
- If issues persist, contact team lead

For additional support:
- Check API health: `GET /api/health`
- Review your request JSON structure
- Contact: [Your Team Contact]

---

Last Updated: October 10, 2025
API Version: 2.0 (Modular Architecture)
Documentation maintained by: Kong Email Generator Team
