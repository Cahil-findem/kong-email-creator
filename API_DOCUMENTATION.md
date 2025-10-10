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

## Endpoints

### 1. Generate Candidate Email

**POST** `/api/process-candidate`

Generates a personalized nurture email for a candidate with matching blog recommendations.

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

#### Error Responses

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

**404 Not Found** - No matching blogs
```json
{
  "error": "No matching blog posts found. Try lowering the threshold."
}
```

**500 Internal Server Error** - Processing error
```json
{
  "error": "Server error: <error details>"
}
```

---

### 2. Health Check

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

## Code Examples

### JavaScript/TypeScript

```typescript
async function generateEmail(candidateData: any) {
  const response = await fetch('https://kong-email-creator.vercel.app/api/process-candidate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-secret-api-key'  // If auth enabled
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

### Python

```python
import requests

def generate_email(candidate_data):
    url = "https://kong-email-creator.vercel.app/api/process-candidate"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "your-secret-api-key"  # If auth enabled
    }
    
    response = requests.post(url, json={"candidate": candidate_data}, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

### cURL

```bash
curl -X POST https://kong-email-creator.vercel.app/api/process-candidate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d @candidate.json
```

---

## Performance

- **Average Response Time:** 5-8 seconds
- **Timeout:** 30 seconds
- **Rate Limit:** None (recommended to add if needed)

## Processing Steps

1. Extract candidate information from JSON
2. Generate semantic summary using GPT-4o-mini (~2s)
3. Create vector embedding using OpenAI (~1s)
4. Search 750+ blog posts for matches (~1s)
5. Filter for diversity (remove generic posts)
6. Generate personalized email with GPT-4o (~3s)
7. Generate subject line with GPT-4o-mini (~1s)

## Cost

- ~$0.002 per request (OpenAI API calls)
