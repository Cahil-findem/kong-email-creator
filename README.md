# NetApp Blog Crawler

A Python web crawler that scrapes blog posts from the NetApp blog (https://www.netapp.com/blog/) and stores them in a Supabase database.

## Features

- Crawls NetApp blog listing pages to discover blog posts
- Scrapes individual blog post content including:
  - Title
  - Full content (text and HTML)
  - Author
  - Published date
  - Featured image
  - Tags/categories
  - Metadata
- Stores scraped data in Supabase
- Includes retry logic and error handling
- Respects rate limiting with configurable delays
- Comprehensive logging to file and console
- Prevents duplicate entries using URL as unique identifier

## Prerequisites

- Python 3.8 or higher
- A Supabase account and project
- pip (Python package manager)

## Installation

1. Clone or download this project

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Supabase database:
   - Log into your Supabase dashboard
   - Go to the SQL Editor
   - Copy and paste the contents of `schema.sql`
   - Run the SQL to create the `blog_posts` table

4. Configure environment variables:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your Supabase credentials:
     ```
     SUPABASE_URL=your_supabase_project_url
     SUPABASE_KEY=your_supabase_anon_key
     ```

   You can find these values in your Supabase project settings:
   - Go to Project Settings > API
   - Copy the Project URL (SUPABASE_URL)
   - Copy the `anon` `public` key (SUPABASE_KEY)

## Usage

### Basic Usage

Run the crawler to scrape all blog posts:

```bash
python crawler.py
```

### Advanced Usage

You can modify the crawler behavior by editing the `main()` function in `crawler.py`:

```python
def main():
    crawler = NetAppBlogCrawler()

    # Parameters:
    # - max_posts: limit number of posts to crawl (None for all)
    # - delay: seconds to wait between requests (default: 2.0)

    crawler.crawl(max_posts=10, delay=3.0)  # Crawl only 10 posts with 3s delay
```

### Programmatic Usage

You can also use the crawler in your own Python scripts:

```python
from crawler import NetAppBlogCrawler

# Initialize crawler
crawler = NetAppBlogCrawler()

# Crawl all posts
crawler.crawl()

# Or crawl with limits
crawler.crawl(max_posts=5, delay=2.0)

# Scrape a specific blog post
post_data = crawler.scrape_blog_post('https://www.netapp.com/blog/specific-post-url')
if post_data:
    crawler.save_to_supabase(post_data)
```

## Database Schema

The crawler creates the following table structure in Supabase:

```sql
blog_posts (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT,
    content         TEXT,
    html_content    TEXT,
    excerpt         TEXT,
    meta_description TEXT,
    author          TEXT,
    published_date  TEXT,
    featured_image  TEXT,
    tags            TEXT[],
    scraped_at      TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE,
    updated_at      TIMESTAMP WITH TIME ZONE
)
```

## Logging

The crawler logs all activities to:
- Console (stdout) - for real-time monitoring
- `crawler.log` file - for persistent logging

Log levels include INFO, WARNING, and ERROR messages to help you track the crawling progress and debug any issues.

## Configuration Options

### Crawler Settings

In `crawler.py`, you can modify:

- `delay` parameter: Adjust the delay between requests (recommended: 2-5 seconds)
- `max_posts` parameter: Limit the number of posts to crawl
- `max_retries`: Number of retry attempts for failed requests (default: 3)
- `timeout`: Request timeout in seconds (default: 30)

### Request Headers

The crawler uses browser-like headers to avoid being blocked. These are configured in the `__init__` method of the `NetAppBlogCrawler` class.

## Troubleshooting

### 403 Forbidden Errors

If you encounter 403 errors, the website may have updated its bot protection. Try:
- Increasing the delay between requests
- Updating the User-Agent string in the headers
- Running the crawler at different times

### No Blog Posts Found

If the crawler can't find blog posts, the website structure may have changed. You may need to:
- Inspect the blog page HTML
- Update the CSS selectors in `extract_blog_posts_from_listing()`
- Update the selectors in `scrape_blog_post()`

### Supabase Connection Issues

If you can't connect to Supabase:
- Verify your credentials in the `.env` file
- Check that your Supabase project is active
- Ensure the table was created correctly using `schema.sql`
- Verify Row Level Security (RLS) policies allow your operations

## Best Practices

1. **Be Respectful**: Use appropriate delays between requests to avoid overwhelming the server
2. **Monitor Logs**: Check `crawler.log` regularly for errors or issues
3. **Test First**: Run with `max_posts=5` first to test before crawling everything
4. **Schedule Wisely**: If running periodically, use reasonable intervals (e.g., daily, not every minute)
5. **Handle Errors**: The crawler will continue even if some posts fail, but review the logs

## Data Usage

The scraped data is stored in your Supabase database. Make sure to:
- Comply with NetApp's terms of service
- Use the data responsibly
- Respect copyright and intellectual property rights
- Follow applicable laws and regulations

## Project Structure

```
NetApp Blog Crawler/
├── crawler.py          # Main crawler script
├── requirements.txt    # Python dependencies
├── schema.sql         # Supabase database schema
├── .env.example       # Environment variables template
├── .env              # Your credentials (not in git)
├── .gitignore        # Git ignore rules
├── crawler.log       # Log file (generated)
└── README.md         # This file
```

## License

This is a personal project. Use at your own risk and responsibility.

## Contributing

This is a personal project, but feel free to fork and modify for your own use.

## Support

For issues or questions, please review:
- The log files for error messages
- The Supabase documentation: https://supabase.com/docs
- The Beautiful Soup documentation: https://www.crummy.com/software/BeautifulSoup/bs4/doc/
