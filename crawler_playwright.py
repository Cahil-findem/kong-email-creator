from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime
import os
from dotenv import load_dotenv
from supabase import create_client, Client

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


class NetAppBlogCrawler:
    """Crawler for NetApp blog posts using Playwright"""

    def __init__(self):
        self.base_url = "https://www.netapp.com/blog/"

        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Database operations will be skipped.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialized")

    def fetch_page(self, page, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page with retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{max_retries})")

                # Navigate to the page
                response = page.goto(url, wait_until='networkidle', timeout=60000)

                if response and response.status == 200:
                    # Wait for content to load
                    page.wait_for_timeout(3000)  # Wait 3 seconds for dynamic content

                    # Get the page content
                    content = page.content()
                    soup = BeautifulSoup(content, 'lxml')
                    logger.info(f"Successfully fetched: {url}")
                    return soup
                else:
                    logger.error(f"Failed with status {response.status if response else 'None'}")

            except PlaywrightTimeout:
                logger.error(f"Timeout fetching {url}")
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None

        return None

    def extract_blog_posts_from_listing(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract blog post URLs and metadata from the listing page"""
        posts = []

        # Try multiple selectors to find blog posts
        selectors = [
            'article',
            '.blog-post',
            '.post',
            '.card',
            'div[class*="blog"]',
            'div[class*="post"]',
            'a[href*="/blog/"]'
        ]

        articles = []
        for selector in selectors:
            articles = soup.select(selector)
            if articles:
                logger.info(f"Found {len(articles)} elements with selector: {selector}")
                break

        if not articles:
            logger.warning("No blog posts found on the listing page")
            return posts

        for article in articles:
            try:
                post_data = {}

                # Try to find the link
                link = article.find('a', href=True)
                if link and '/blog/' in link['href']:
                    post_url = link['href']
                    if not post_url.startswith('http'):
                        post_url = f"https://www.netapp.com{post_url}"
                    post_data['url'] = post_url

                    # Extract title
                    title = (
                        article.find(['h1', 'h2', 'h3', 'h4']) or
                        link
                    )
                    if title:
                        post_data['title'] = title.get_text(strip=True)

                    # Extract excerpt/description
                    excerpt = article.find(['p', 'div'], class_=lambda x: x and ('excerpt' in x.lower() or 'description' in x.lower()))
                    if excerpt:
                        post_data['excerpt'] = excerpt.get_text(strip=True)

                    # Extract date if available
                    date_elem = article.find(['time', 'span'], class_=lambda x: x and 'date' in x.lower())
                    if date_elem:
                        post_data['published_date'] = date_elem.get_text(strip=True)

                    # Extract author if available
                    author = article.find(class_=lambda x: x and 'author' in x.lower())
                    if author:
                        post_data['author'] = author.get_text(strip=True)

                    # Extract featured image from listing if available
                    img = article.find('img', src=True)
                    if img and img.get('src'):
                        img_url = img['src']
                        # Ensure the image URL is absolute
                        if not img_url.startswith('http'):
                            if img_url.startswith('//'):
                                img_url = f"https:{img_url}"
                            elif img_url.startswith('/'):
                                img_url = f"https://www.netapp.com{img_url}"
                            else:
                                img_url = f"https://www.netapp.com/{img_url}"
                        post_data['featured_image'] = img_url

                    if post_data.get('url'):
                        posts.append(post_data)
                        logger.info(f"Extracted: {post_data.get('title', 'Untitled')}")

            except Exception as e:
                logger.error(f"Error extracting post data: {str(e)}")
                continue

        logger.info(f"Total posts extracted: {len(posts)}")
        return posts

    def scrape_blog_post(self, page, url: str) -> Optional[Dict]:
        """Scrape individual blog post content"""
        soup = self.fetch_page(page, url)
        if not soup:
            return None

        post_data = {'url': url, 'scraped_at': datetime.utcnow().isoformat()}

        try:
            # Extract title
            title = soup.find(['h1', 'h2'], class_=lambda x: x and ('title' in x.lower() or 'heading' in x.lower()))
            if not title:
                title = soup.find('h1')
            if title:
                post_data['title'] = title.get_text(strip=True)

            # Extract content
            content_selectors = [
                'article',
                'div[class*="content"]',
                'div[class*="post"]',
                'div[class*="article"]',
                'main'
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

            # Extract tags/categories
            tags = []
            tag_selectors = [
                'a[rel="tag"]',
                'a[class*="tag"]',
                'a[class*="category"]'
            ]

            for selector in tag_selectors:
                tag_elems = soup.select(selector)
                if tag_elems:
                    tags.extend([tag.get_text(strip=True) for tag in tag_elems])
                    break

            if tags:
                post_data['tags'] = tags

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
                if featured_image.startswith('//'):
                    featured_image = f"https:{featured_image}"
                elif featured_image.startswith('/'):
                    featured_image = f"https://www.netapp.com{featured_image}"
                else:
                    featured_image = f"https://www.netapp.com/{featured_image}"

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
        """Main crawl method using Playwright"""
        logger.info("Starting NetApp blog crawl with Playwright...")

        with sync_playwright() as p:
            # Launch browser (headless=False to see what's happening, set to True for production)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()

            try:
                # Fetch the main blog listing page
                soup = self.fetch_page(page, self.base_url)
                if not soup:
                    logger.error("Failed to fetch the main blog page. Exiting.")
                    return

                # Extract blog post URLs from listing
                posts = self.extract_blog_posts_from_listing(soup)

                if not posts:
                    logger.error("No blog posts found. The page structure might have changed.")
                    return

                # Limit number of posts if specified
                if max_posts:
                    posts = posts[:max_posts]
                    logger.info(f"Limiting to {max_posts} posts")

                # Crawl individual posts
                successful = 0
                failed = 0

                for i, post_preview in enumerate(posts, 1):
                    logger.info(f"Processing post {i}/{len(posts)}: {post_preview.get('url')}")

                    # Scrape full post content
                    post_data = self.scrape_blog_post(page, post_preview['url'])

                    if post_data:
                        # Merge preview data with scraped data
                        for key, value in post_preview.items():
                            if key not in post_data and value:
                                post_data[key] = value

                        # Save to Supabase
                        if self.save_to_supabase(post_data):
                            successful += 1
                        else:
                            failed += 1
                    else:
                        failed += 1

                    # Be polite - add delay between requests
                    if i < len(posts):
                        logger.info(f"Waiting {delay} seconds before next request...")
                        time.sleep(delay)

                logger.info(f"\nCrawl completed!")
                logger.info(f"Successful: {successful}")
                logger.info(f"Failed: {failed}")
                logger.info(f"Total: {len(posts)}")

            finally:
                browser.close()


def main():
    """Main entry point"""
    crawler = NetAppBlogCrawler()

    # Crawl with optional parameters
    # max_posts: limit number of posts to crawl (None for all)
    # delay: seconds to wait between requests (be polite!)
    crawler.crawl(max_posts=None, delay=2.0)


if __name__ == "__main__":
    main()
