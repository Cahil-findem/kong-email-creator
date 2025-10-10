import cloudscraper
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
    """Crawler for NetApp blog posts"""

    def __init__(self):
        self.base_url = "https://konghq.com/blog"
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

    def extract_blog_posts_from_listing(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract blog post URLs and metadata from the listing page"""
        posts = []

        # Kong uses .blog-post-card as the main container
        articles = soup.select('.blog-post-card')

        if not articles:
            # Fallback to generic selectors
            selectors = [
                'a.c-post-card-link',
                'article',
                '.post-card',
                '.card',
            ]
            for selector in selectors:
                articles = soup.select(selector)
                if articles:
                    logger.info(f"Found {len(articles)} elements with selector: {selector}")
                    break
        else:
            logger.info(f"Found {len(articles)} blog post cards")

        if not articles:
            logger.warning("No blog posts found on the listing page")
            return posts

        for article in articles:
            try:
                post_data = {}

                # Find the link inside the blog post card
                link = article.find('a', href=True)
                if link and link.get('href'):
                    post_url = link['href']

                    # Filter out tag pages, category pages, and navigation links
                    # Only include URLs that match the pattern /blog/{category}/{slug}
                    if '/blog/' in post_url and '/blog/tag/' not in post_url:
                        # Count slashes to ensure it's a full blog post URL
                        # Format should be: /blog/category/post-slug (3 slashes)
                        url_parts = post_url.strip('/').split('/')
                        if len(url_parts) >= 3:  # blog, category, slug
                            if not post_url.startswith('http'):
                                post_url = f"https://konghq.com{post_url}"
                            post_data['url'] = post_url
                        else:
                            continue
                    else:
                        continue
                else:
                    continue

                if not post_data.get('url'):
                    continue

                # Extract title (Kong uses h2 for blog post titles)
                title = article.find('h2')
                if not title:
                    title = article.find(['h1', 'h3', 'h4'])
                if title:
                    post_data['title'] = title.get_text(strip=True)

                # Extract category (Kong uses .post-category div)
                category = article.find('div', class_='post-category')
                if not category:
                    category = article.find('div', class_='c-label')
                if category:
                    post_data['tags'] = [category.get_text(strip=True)]

                # Extract excerpt/description
                excerpt = article.find(['p', 'div'], class_=lambda x: x and ('excerpt' in x.lower() or 'description' in x.lower()))
                if excerpt:
                    post_data['excerpt'] = excerpt.get_text(strip=True)

                # Extract date (Kong uses .post-date div)
                date_elem = article.find('div', class_='post-date')
                if not date_elem:
                    date_elem = article.find(['time', 'span'], class_=lambda x: x and 'date' in x.lower())
                if date_elem:
                    post_data['published_date'] = date_elem.get_text(strip=True)

                # Extract author (Kong uses .author-name span)
                author_name = article.find('span', class_='author-name')
                if not author_name:
                    author_name = article.find(class_=lambda x: x and 'author' in x.lower())
                if author_name:
                    post_data['author'] = author_name.get_text(strip=True)

                # Extract featured image from listing
                img = article.find('img', src=True)
                if img and img.get('src'):
                    img_url = img['src']
                    # Ensure the image URL is absolute
                    if not img_url.startswith('http'):
                        if img_url.startswith('//'):
                            img_url = f"https:{img_url}"
                        elif img_url.startswith('/'):
                            img_url = f"https://konghq.com{img_url}"
                        else:
                            img_url = f"https://konghq.com/{img_url}"
                    post_data['featured_image'] = img_url

                if post_data.get('url'):
                    posts.append(post_data)
                    logger.info(f"Extracted: {post_data.get('title', 'Untitled')}")

            except Exception as e:
                logger.error(f"Error extracting post data: {str(e)}")
                continue

        logger.info(f"Total posts extracted: {len(posts)}")
        return posts

    def scrape_blog_post(self, url: str) -> Optional[Dict]:
        """Scrape individual blog post content"""
        soup = self.fetch_page(url)
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
                    featured_image = f"https://konghq.com{featured_image}"
                else:
                    featured_image = f"https://konghq.com/{featured_image}"

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
        logger.info("Starting NetApp blog crawl...")

        # Fetch the main blog listing page
        soup = self.fetch_page(self.base_url)
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
            post_data = self.scrape_blog_post(post_preview['url'])

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


def main():
    """Main entry point"""
    crawler = NetAppBlogCrawler()

    # Crawl with optional parameters
    # max_posts: limit number of posts to crawl (None for all)
    # delay: seconds to wait between requests (be polite!)
    crawler.crawl(max_posts=None, delay=2.0)


if __name__ == "__main__":
    main()
