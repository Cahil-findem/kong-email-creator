import cloudscraper
from bs4 import BeautifulSoup
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import xml.etree.ElementTree as ET

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class SitemapBlogCrawler:
    """Crawler that uses sitemap.xml to find blog posts"""

    def __init__(self, sitemap_url: str):
        self.sitemap_url = sitemap_url
        # Use cloudscraper to bypass Cloudflare protection
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )

        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Database operations will be skipped.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialized")

    def fetch_page(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page with retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'lxml')
                logger.info(f"Successfully fetched: {url}")
                return soup

            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                    return None

    def extract_blog_urls_from_sitemap(self) -> List[str]:
        """Extract blog post URLs from sitemap XML"""
        blog_urls = []

        try:
            logger.info(f"Fetching sitemap: {self.sitemap_url}")
            response = self.session.get(self.sitemap_url, timeout=30)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Handle XML namespaces
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            # Extract all URLs
            for url_elem in root.findall('.//ns:url', namespace):
                loc = url_elem.find('ns:loc', namespace)
                if loc is not None and loc.text:
                    url = loc.text.strip()

                    # Filter: only include actual blog posts, not category/tag pages
                    # Blog posts have pattern: /blog/category/post-slug (at least 3 path segments)
                    # Category pages: /blog/category (only 2 path segments)
                    if '/blog/' in url:
                        # Extract the path after /blog/
                        path_after_blog = url.split('/blog/')[-1]
                        # Count segments (category/post-slug should have at least 2 segments)
                        segments = [s for s in path_after_blog.split('/') if s]

                        # Only include if there are 2+ segments (category AND post-slug)
                        if len(segments) >= 2:
                            blog_urls.append(url)
                            logger.info(f"Found blog post: {url}")

            logger.info(f"Total blog posts found in sitemap: {len(blog_urls)}")
            return blog_urls

        except Exception as e:
            logger.error(f"Error parsing sitemap: {str(e)}")
            return []

    def scrape_blog_post(self, url: str) -> Optional[Dict]:
        """Scrape individual blog post content"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        post_data = {'url': url, 'scraped_at': datetime.utcnow().isoformat()}

        try:
            # Extract title
            title = soup.find('h1')
            if not title:
                title = soup.find(['h2'], class_=lambda x: x and ('title' in x.lower() or 'heading' in x.lower()))
            if title:
                post_data['title'] = title.get_text(strip=True)

            # Extract content (main tag gets the most complete content for Kong blog)
            content_selectors = [
                'main',
                'article',
                'div[class*="content"]',
                'div[class*="post"]',
                'div[class*="article"]'
            ]

            content = None
            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    break

            if content:
                # Remove script and style elements
                for script in content(['script', 'style', 'nav', 'header', 'footer']):
                    script.decompose()

                post_data['content'] = content.get_text(separator='\n', strip=True)
                post_data['html_content'] = str(content)

            # Extract metadata
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                post_data['meta_description'] = meta_desc['content']

            # Extract publish date
            date_selectors = [
                'time[datetime]',
                'meta[property="article:published_time"]',
                'span[class*="date"]',
                'div[class*="date"]'
            ]

            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    if date_elem.name == 'time' and date_elem.get('datetime'):
                        post_data['published_date'] = date_elem['datetime']
                    elif date_elem.name == 'meta' and date_elem.get('content'):
                        post_data['published_date'] = date_elem['content']
                    else:
                        post_data['published_date'] = date_elem.get_text(strip=True)
                    break

            # Extract author
            author_selectors = [
                'meta[name="author"]',
                'span[class*="author"]',
                'div[class*="author"]',
                'a[rel="author"]'
            ]

            for selector in author_selectors:
                author_elem = soup.select_one(selector)
                if author_elem:
                    if author_elem.name == 'meta' and author_elem.get('content'):
                        post_data['author'] = author_elem['content']
                    else:
                        post_data['author'] = author_elem.get_text(strip=True)
                    break

            # Extract tags/categories from URL
            url_parts = url.strip('/').split('/')
            if len(url_parts) >= 4:
                # Extract category from URL (e.g., /blog/engineering/post-slug -> "engineering")
                category = url_parts[-2]  # Second to last part
                post_data['tags'] = [category]

            # Extract featured image
            featured_image = None

            # Try Open Graph image first
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                featured_image = og_image['content']

            # Try Twitter image if OG not found
            if not featured_image:
                twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                if twitter_image and twitter_image.get('content'):
                    featured_image = twitter_image['content']

            # Try to find the first image in the article content
            if not featured_image and content:
                first_img = content.find('img', src=True)
                if first_img and first_img.get('src'):
                    featured_image = first_img['src']

            # Try any image with featured/hero class
            if not featured_image:
                hero_img = soup.find('img', class_=lambda x: x and ('featured' in x.lower() or 'hero' in x.lower()))
                if hero_img and hero_img.get('src'):
                    featured_image = hero_img['src']

            # Ensure the image URL is absolute
            if featured_image and not featured_image.startswith('http'):
                base_domain = '/'.join(url.split('/')[:3])  # Get https://domain.com
                if featured_image.startswith('//'):
                    featured_image = f"https:{featured_image}"
                elif featured_image.startswith('/'):
                    featured_image = f"{base_domain}{featured_image}"
                else:
                    featured_image = f"{base_domain}/{featured_image}"

            if featured_image:
                post_data['featured_image'] = featured_image

            logger.info(f"Successfully scraped: {post_data.get('title', url)}")
            return post_data

        except Exception as e:
            logger.error(f"Error scraping post {url}: {str(e)}")
            return None

    def save_to_supabase(self, post_data: Dict) -> bool:
        """Save blog post data to Supabase"""
        if not self.supabase:
            logger.warning("Supabase client not initialized. Skipping save.")
            return False

        try:
            # Prepare data for insertion
            data = {
                'url': post_data.get('url'),
                'title': post_data.get('title'),
                'content': post_data.get('content'),
                'html_content': post_data.get('html_content'),
                'excerpt': post_data.get('excerpt'),
                'meta_description': post_data.get('meta_description'),
                'author': post_data.get('author'),
                'published_date': post_data.get('published_date'),
                'featured_image': post_data.get('featured_image'),
                'tags': post_data.get('tags'),
                'scraped_at': post_data.get('scraped_at')
            }

            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}

            # Insert or update (upsert on URL)
            result = self.supabase.table('blog_posts').upsert(data, on_conflict='url').execute()

            logger.info(f"Saved to Supabase: {post_data.get('title', 'Untitled')}")
            return True

        except Exception as e:
            logger.error(f"Error saving to Supabase: {str(e)}")
            return False

    def crawl(self, max_posts: Optional[int] = None, delay: float = 2.0):
        """Main crawl method"""
        logger.info("Starting sitemap-based blog crawl...")

        # Extract blog post URLs from sitemap
        blog_urls = self.extract_blog_urls_from_sitemap()

        if not blog_urls:
            logger.error("No blog posts found in sitemap. Exiting.")
            return

        # Limit number of posts if specified
        if max_posts:
            blog_urls = blog_urls[:max_posts]
            logger.info(f"Limiting to {max_posts} posts")

        # Crawl individual posts
        successful = 0
        failed = 0

        for i, url in enumerate(blog_urls, 1):
            logger.info(f"Processing post {i}/{len(blog_urls)}: {url}")

            # Scrape full post content
            post_data = self.scrape_blog_post(url)

            if post_data:
                # Save to Supabase
                if self.save_to_supabase(post_data):
                    successful += 1
                else:
                    failed += 1
            else:
                failed += 1

            # Be polite - add delay between requests
            if i < len(blog_urls):
                logger.info(f"Waiting {delay} seconds before next request...")
                time.sleep(delay)

        logger.info(f"\nCrawl completed!")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total: {len(blog_urls)}")


def main():
    """Main entry point"""
    # Kong blog sitemap
    sitemap_url = "https://konghq.com/sitemaps/blogs.xml"

    crawler = SitemapBlogCrawler(sitemap_url)

    # Crawl with optional parameters
    # max_posts: limit number of posts to crawl (None for all)
    # delay: seconds to wait between requests (be polite!)
    crawler.crawl(max_posts=None, delay=2.0)


if __name__ == "__main__":
    main()
