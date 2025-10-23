# LLM-Based Job Matching System

## Overview

The system now uses an intelligent LLM evaluation step to determine which job matches are truly good fits, replacing the previous hard similarity threshold approach.

## How It Works

### Previous Approach (Hard Threshold)
```
Job Similarity Scores → Filter by 80% threshold → Email Decision
❌ Problem: High similarity doesn't always mean good fit
```

### New Approach (LLM Evaluation)
```
Job Similarity Scores → Top 10 Matches → LLM Evaluation → Email Decision
✓ Considers: skills, seniority, domain, trajectory, role type
```

## Process Flow

### Step 1: Semantic Similarity
- Vector search finds top 10 closest job matches by semantic similarity
- Similarity scores range from 0.0 to 1.0

### Step 2: LLM Evaluation
The LLM evaluates each of the top 10 jobs considering:

**Evaluation Criteria:**
1. **Skills Alignment** - Do they have the right technical/functional skills?
2. **Seniority Level** - Is the role at the right level (not too junior, not too senior)?
3. **Domain Fit** - Does their experience align with the role's domain/industry?
4. **Career Trajectory** - Does this role make sense as their next move?
5. **Role Type Compatibility** - Does their background suggest they'd succeed?

**LLM Instructions:**
- Be selective - only approve truly strong matches
- High similarity score ≠ guaranteed good fit
- Consider realistic interest and qualifications
- Maximum 3 jobs recommended
- Return empty list if no jobs are suitable

### Step 3: Email Approach Decision

**If LLM approves ≥1 job:**
→ **Job-Focused Email**
- Direct, opportunity-focused tone
- Leads with job opportunity
- Rich HTML job cards
- Subject mentions specific role
- Blogs as company context

**If LLM approves 0 jobs:**
→ **Relationship-Nurture Email**
- Warm, conversational tone
- Focuses on relationship building
- Blogs are primary content
- Personal subject line
- No job mentions

## Example LLM Evaluation

### Input to LLM:
```json
{
  "candidate": {
    "name": "Jacob Wang",
    "current_title": "Senior Software Engineer",
    "current_company": "Google",
    "work_history": ["Google: Senior Software Engineer"],
    "career_context": "Senior engineer with distributed systems expertise..."
  },
  "top_10_jobs": [
    {
      "job_number": 1,
      "position": "Senior Software Engineer - Insomnia Team",
      "company": "Kong Inc.",
      "similarity_score": "89.3%",
      "about_role": "Build desktop Insomnia application..."
    },
    {
      "job_number": 2,
      "position": "Junior Developer",
      "similarity_score": "82.1%",
      ...
    },
    ...
  ]
}
```

### LLM Output:
```json
{
  "recommended_jobs": [1, 4],
  "reasoning": {
    "1": "Strong match - Senior level aligns with experience, distributed systems background fits well with API tools",
    "4": "Good fit - Staff level matches career progression, cloud infrastructure aligns with Google background"
  },
  "rejected_reasoning": "Jobs 2,3,5-10 rejected: Job 2 too junior for candidate's level, Jobs 3,5-7 in different domains (marketing/sales), Jobs 8-10 require specialized domain knowledge candidate lacks"
}
```

## Benefits of LLM Evaluation

### ✓ More Intelligent Matching
- Considers nuanced factors beyond vector similarity
- Evaluates career trajectory and seniority alignment
- Catches mismatches (e.g., high similarity but wrong seniority level)

### ✓ Better Candidate Experience
- Only sends job-focused emails when truly relevant
- Reduces "spam" feeling from irrelevant job matches
- More personalized and thoughtful outreach

### ✓ Higher Quality Pipeline
- Candidates receive only strong-fit opportunities
- Increases likelihood of engagement
- Better conversion rates

## Implementation Details

### Function: `evaluate_job_matches_with_llm()`
**Location:** `app.py:535-680`

**Parameters:**
- `candidate_info`: Candidate profile data
- `job_matches`: Top 10 jobs by similarity (from vector search)
- `semantic_summary`: Career context summary

**Returns:**
- List of LLM-approved jobs (0-3 jobs)
- Each job includes `llm_reasoning` field

**Model:** GPT-4o with temperature=0.3 (consistent evaluation)

**Fallback:** If LLM fails, falls back to top 3 jobs with similarity ≥ 0.80

### Integration Point: `generate_email_content()`
**Location:** `app.py:728-751`

```python
# Old approach:
high_quality_jobs = [job for job in job_matches if job.get('similarity', 0) >= 0.80]

# New approach:
llm_approved_jobs = evaluate_job_matches_with_llm(candidate_info, job_matches, semantic_summary)
use_job_focused_approach = len(llm_approved_jobs) > 0
```

## API Response Changes

The email generation API now returns:

```json
{
  "email": {
    "subject": "Senior Software Engineer Opportunity at Kong",
    "body": "...",
    "email_approach": "job-focused",  // or "relationship-nurture"
    "job_count": 2
  },
  "jobs": [
    {
      "position": "Senior Software Engineer - Insomnia Team",
      "llm_reasoning": "Strong match - Senior level aligns with experience...",
      ...
    }
  ]
}
```

## Configuration

**Max Jobs Evaluated:** 10 (top by similarity)
**Max Jobs Returned:** 3 (LLM selects best matches)
**LLM Model:** gpt-4o
**Temperature:** 0.3 (lower for consistent decisions)
**Fallback Threshold:** 0.80 (if LLM fails)

## Testing

To test the system:

1. **High-quality match scenario:**
   - Candidate: Senior engineer with distributed systems experience
   - Jobs: Senior roles in cloud/API domain
   - Expected: LLM approves → Job-focused email

2. **Low-quality match scenario:**
   - Candidate: Senior engineer
   - Jobs: Only junior roles or different domains
   - Expected: LLM rejects → Relationship-nurture email

3. **Mixed scenario:**
   - Candidate: Mid-level designer
   - Jobs: Mix of design, engineering, and marketing roles
   - Expected: LLM selects only design roles → Job-focused with filtered jobs

## Monitoring

Check logs for LLM evaluation decisions:
```
INFO:__main__:LLM evaluated 10 jobs, approved 2
INFO:__main__:Approved jobs: ['Senior Software Engineer - Insomnia Team', 'Staff Engineer - API Gateway']
```

Or when no matches:
```
INFO:__main__:LLM evaluated 10 jobs, approved 0
INFO:__main__:Rejection reason: All roles are either too junior for candidate's senior level or in unrelated domains
```
