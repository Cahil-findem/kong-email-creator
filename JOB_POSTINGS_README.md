# Job Postings System

Store and manage available job positions for matching with candidates.

## Setup

### 1. Create the Database Table

Run the SQL schema in your Supabase SQL Editor:

```bash
# Copy contents of job_postings_schema.sql and run in Supabase
```

Or if you have `psql` access:
```bash
psql -h your-db-host -U postgres -d postgres -f job_postings_schema.sql
```

### 2. Verify Table Creation

```sql
SELECT * FROM job_postings LIMIT 1;
SELECT * FROM active_jobs_summary;
```

## Usage

### Insert a Single Job Posting

```bash
python insert_job_posting.py sample_job_posting.json
```

### Insert Multiple Job Postings

Create a JSON array file with multiple jobs:

```json
[
  {
    "position": "Senior Software Engineer - Insomnia Team",
    "company": "Kong Inc.",
    ...
  },
  {
    "position": "Product Manager - API Platform",
    "company": "Kong Inc.",
    ...
  }
]
```

Then run:
```bash
python insert_job_posting.py multiple_jobs.json
```

### Query Job Postings Programmatically

```python
from insert_job_posting import JobPostingManager

manager = JobPostingManager()

# Get all active jobs
active_jobs = manager.get_active_jobs(limit=50)

# Get specific job by ID
job = manager.get_job_posting('40d0693f-2727-4662-9e1c-86c80581292a')

# Update job status
manager.update_job_status('40d0693f-2727-4662-9e1c-86c80581292a', 'filled')
```

## Database Schema

### Main Fields

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | text | Unique identifier (auto-generated from application link) |
| `position` | text | Job title |
| `company` | text | Company name |
| `location_type` | text | Remote, Hybrid, On-site |
| `compensation_min` | numeric | Minimum salary |
| `compensation_max` | numeric | Maximum salary |
| `about_role` | text | Job description |
| `raw_job_data` | jsonb | Full job posting JSON |
| `status` | text | active, inactive, filled, closed |

### Sample Queries

**Get all remote jobs:**
```sql
SELECT position, location_country, compensation_range_formatted
FROM job_postings
WHERE status = 'active' AND location_type = 'Remote';
```

**Search by keyword:**
```sql
SELECT position, about_role
FROM job_postings
WHERE status = 'active'
  AND (about_role ILIKE '%API%' OR raw_job_data::text ILIKE '%microservices%');
```

**Get jobs by compensation:**
```sql
SELECT position, compensation_currency, compensation_min, compensation_max
FROM job_postings
WHERE status = 'active'
  AND compensation_currency = 'USD'
  AND compensation_min >= 120000
ORDER BY compensation_max DESC;
```

## Job Data Structure

The system expects job data in this format:

```json
{
  "position": "Job Title",
  "company": "Company Name",
  "location": {
    "city": "City",
    "country": "Country",
    "type": "Remote/Hybrid/On-site"
  },
  "employment": {
    "type": "Full time/Part time/Contract",
    "department": "Department Name"
  },
  "compensation": {
    "currency": "USD",
    "min": 120000,
    "max": 180000
  },
  "about_role": "Job description...",
  "responsibilities": ["Responsibility 1", "Responsibility 2"],
  "requirements": {
    "must_have": ["Requirement 1"],
    "nice_to_have": ["Bonus skill 1"]
  },
  "metadata": {
    "application_link": "https://...",
    "posting_code": "CODE-123"
  }
}
```

## Status Management

Jobs have 4 possible statuses:

- **active** - Currently accepting applications
- **inactive** - Temporarily not accepting applications
- **filled** - Position has been filled
- **closed** - Position is no longer available

Update status:
```python
manager.update_job_status('job-id-here', 'filled')
```

Or via SQL:
```sql
UPDATE job_postings
SET status = 'filled'
WHERE job_id = 'job-id-here';
```

## Future Enhancements

Potential additions to consider:

1. **Job Vectorization** - Create embeddings from job descriptions for semantic matching with candidates
2. **Job-Candidate Matching** - Use vector similarity to match candidates with relevant jobs
3. **Job Recommendation API** - Endpoint to get personalized job recommendations for candidates
4. **Job Change Tracking** - Track when jobs are updated (salary changes, requirements changes, etc.)
5. **Job Analytics** - Track views, applications, and conversion rates

## Related Files

- `job_postings_schema.sql` - Database schema
- `insert_job_posting.py` - Python script for managing job postings
- `sample_job_posting.json` - Example job data

## Notes

- Job IDs are auto-generated from the application link or position + company hash
- Updating a job with the same `job_id` will update the existing record
- All timestamps are in UTC
- Full job JSON is stored in `raw_job_data` for flexibility
- Key fields are extracted for efficient querying
