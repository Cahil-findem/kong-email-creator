# Candidate Email Generator - Web App

A beautiful web interface to generate personalized nurture emails for candidates based on their profiles and matching blog content.

## 🚀 Quick Start

### 1. Start the Server

```bash
python3 app.py
```

The server will start at: **http://localhost:5000**

### 2. Open in Browser

Navigate to `http://localhost:5000` in your browser.

### 3. Use the Interface

1. **Paste candidate JSON** into the left panel
2. **Click "Generate Email ✨"**
3. **View the result** in the right panel:
   - Candidate info
   - Matched blog posts with relevance scores
   - Personalized email (ready to copy)

## 📋 Features

### What It Does

1. ✅ **Accepts candidate JSON** - Paste your candidate profile data
2. ✅ **Vectorizes the profile** - Creates embeddings using OpenAI
3. ✅ **Finds matching blogs** - Searches 750+ blog posts for relevant content
4. ✅ **Generates personalized email** - Creates a nurture email with:
   - Personalized greeting based on role/company
   - Top 3 most relevant blog posts
   - Professional closing
5. ✅ **Copy to clipboard** - One-click copy for easy use

### UI Features

- 🎨 Beautiful gradient design
- 📱 Responsive layout
- ⚡ Real-time processing feedback
- 📊 Relevance scores for each blog match
- 🎯 Smart email generation based on candidate profile

## 🔧 API Endpoints

### `POST /api/process-candidate`

Process a candidate and generate an email.

**Request:**
```json
{
  "candidate": {
    "ref": "candidate_id_123",
    "candidate": {
      "full_name": "John Doe",
      "about_me": "...",
      ...
    },
    "skills": [...],
    "workexp": [...]
  }
}
```

**Response:**
```json
{
  "success": true,
  "candidate": {
    "id": "candidate_id_123",
    "name": "John Doe",
    "title": "Senior Engineer",
    "company": "Acme Corp"
  },
  "blog_matches": [
    {
      "title": "Blog Post Title",
      "url": "https://...",
      "relevance": 87.3,
      "author": "Author Name"
    }
  ],
  "email": {
    "subject": "Subject line",
    "body": "Email content...",
    "candidate_name": "John Doe",
    "blog_count": 3
  }
}
```

### `GET /api/health`

Health check endpoint.

## 📝 Example Usage

### Example Candidate JSON

```json
{
  "68d193fecb73815f93cc0e45": {
    "candidate": {
      "full_name": "Scott Haidarian",
      "about_me": "Experienced Analyst with 3+ years...",
      "location": {
        "city": "San Francisco Bay Area",
        "state": "California",
        "country": "United States"
      }
    },
    "skills": ["Salesforce.com", "API", "Compensation", "Commissions"],
    "workexp": [
      {
        "company": {
          "name": "Backblaze"
        },
        "projects": [
          {
            "role_and_group": {
              "title": "Sr. Commissions Analyst"
            }
          }
        ]
      }
    ],
    "ref": "68d193fecb73815f93cc0e45"
  }
}
```

## ⚙️ Configuration

### Environment Variables

Make sure your `.env` file contains:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=sk-your-openai-key
```

### Optional Settings

In `app.py`, you can adjust:
- `PORT` - Server port (default: 5000)
- `DEBUG` - Debug mode (default: False)

## 🎯 Matching Algorithm

The system uses semantic search to find relevant blog posts:

1. **Vectorizes** candidate profile using OpenAI embeddings
2. **Searches** blog chunks using cosine similarity
3. **Ranks** results by relevance score
4. **Deduplicates** to ensure unique blog posts
5. **Returns** top 3 most relevant matches

**Threshold:** 0.30 (30% similarity minimum)
- Lower = more results, less relevant
- Higher = fewer results, more relevant

## 🐛 Troubleshooting

### "Failed to vectorize candidate profile"
- Check that your `.env` file has valid `OPENAI_API_KEY`
- Ensure the candidate JSON has a `ref` field

### "No matching blog posts found"
- Your blog database might be empty
- Lower the `match_threshold` in `app.py` (line 92)

### "Invalid JSON format"
- Make sure your JSON is properly formatted
- Use a JSON validator if needed

### Server won't start
- Make sure Flask is installed: `pip3 install flask flask-cors`
- Check if port 5000 is already in use
- Try a different port: `PORT=8000 python3 app.py`

## 📊 Performance

**Processing Time:**
- Vectorization: ~2-3 seconds
- Blog matching: ~1-2 seconds
- Email generation: < 1 second
- **Total:** ~3-6 seconds per candidate

**Cost per Request:**
- OpenAI embedding: ~$0.0001
- Very cheap to run!

## 🔒 Security Notes

- This is a **local development server**
- For production, use a proper WSGI server (gunicorn, uwsgi)
- Add authentication if exposing publicly
- Validate and sanitize all inputs

## 📚 Tech Stack

- **Backend:** Flask (Python)
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **Database:** Supabase (PostgreSQL + pgvector)
- **AI:** OpenAI (text-embedding-3-small)
- **Vector Search:** pgvector (cosine similarity)

## 🚀 Next Steps

1. **Add batch processing** - Upload multiple candidates at once
2. **Save email history** - Track sent emails
3. **Email templates** - Multiple email styles
4. **A/B testing** - Test different email approaches
5. **Analytics dashboard** - Track open rates, clicks

---

**Happy emailing!** 📧✨
