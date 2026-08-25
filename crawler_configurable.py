from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import requests
import xml.etree.ElementTree as ET
import time
import logging
import argparse
import json
import re
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin, urlparse
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ── Default config values (merged under every site entry) ──────────────────

DEFAULT_CONFIG = {
    "discovery_mode": "listing",          # "listing" | "sitemap" | "both"
    "listing_selectors": [".blog-post-card", "article", ".post-card", ".card",
                          'div[class*="blog"]', 'div[class*="post"]'],
    "article_url_contains": "/blog/",
    "article_url_excludes": ["/blog/tag/"],
    "min_path_segments": 3,
    "content_selectors": ["article", 'div[class*="content"]', 'div[class*="post"]',
                          'div[class*="article"]', "main"],
    "dynamic_wait_ms": 3000,
    "wait_for_selector": None,
    "max_retries": 3,
    "delay": 2.0,
    "headless": True,
    "wait_until": "networkidle",  # page.goto wait strategy; some sites never go idle
    "scroll_count": 0,            # times to scroll the page to trigger lazy-loaded content
    "listing_urls": None,         # optional list of listing pages (overrides single listing_url)
    "newest_first": False,        # sort discovered URLs newest-first (needs sitemap <lastmod>)
}

# ── Built-in site configurations ───────────────────────────────────────────

SITE_CONFIGS = {
    "kong": {
        "company": "kong",
        "base_url": "https://konghq.com",
        "listing_url": "https://konghq.com/blog",
        "sitemap_url": "https://konghq.com/sitemaps/blogs.xml",
        "discovery_mode": "listing",
        "listing_selectors": [".blog-post-card", "a.c-post-card-link", "article",
                              ".post-card", ".card"],
        "article_url_contains": "/blog/",
        "article_url_excludes": ["/blog/tag/"],
        "min_path_segments": 3,
        "content_selectors": ["main", "article", 'div[class*="content"]',
                              'div[class*="post"]', 'div[class*="article"]'],
    },
    "netapp": {
        "company": "netapp",
        "base_url": "https://www.netapp.com",
        "listing_url": "https://www.netapp.com/blog/",
        "discovery_mode": "listing",
        "article_url_contains": "/blog/",
        "article_url_excludes": [],
        "min_path_segments": 3,
    },
    "box": {
        "company": "Box",
        "base_url": "https://blog.box.com",
        "listing_url": "https://blog.box.com/",
        # Homepage reliably yields ~31 unique articles. Category pages
        # (news/product/ai-research/customer-stories) hold more but are
        # aggressively 403-rate-limited under rapid crawling, so they're kept
        # out of the default run and topped up separately with slow pacing.
        "listing_urls": [
            "https://blog.box.com/",
        ],
        "discovery_mode": "listing",
        # Article links live outside <article> cards too, so grab all main anchors
        # and let article_url validation filter them (flat blog.box.com/<slug>).
        "listing_selectors": ["main a", "article"],
        # Box articles are flat slugs: blog.box.com/<slug> (no /blog/ prefix).
        "article_url_contains": "blog.box.com",
        "article_url_excludes": ["/category/", "/developer", "/author/", "/tag/", "/page/"],
        "min_path_segments": 1,
        "content_selectors": ["article", "main", 'div[class*="content"]', 'div[class*="post"]'],
        # Box is bot-protected and never reaches networkidle; needs JS + scroll + retries.
        "wait_until": "domcontentloaded",
        "wait_for_selector": "article",
        "scroll_count": 3,
        "dynamic_wait_ms": 4000,
        "max_retries": 3,
        "delay": 10.0,  # gentle pacing to avoid re-triggering Box bot protection
    },
    "jsheld": {
        "company": "jsheld",
        "base_url": "https://www.jsheld.com",
        "listing_url": "https://www.jsheld.com/about-us/news",
        "discovery_mode": "listing",
        "listing_selectors": ["article", ".post-card", ".card", 'a[href*="/about-us/news/"]',
                              'div[class*="post"]', 'div[class*="card"]'],
        "article_url_contains": "/about-us/news/",
        "article_url_excludes": [],
        "article_url_regex_exclude": r"/news/p\d+$",
        "min_path_segments": 3,
        "dynamic_wait_ms": 5000,
    },
    "allstate": {
        "company": "Allstate",
        # allstatecorporation.com/newsroom.aspx is only a 12-item teaser feed that
        # links out; the real articles live on this separate WordPress site.
        "base_url": "https://www.allstatenewsroom.com",
        "listing_url": "https://www.allstatenewsroom.com/news/",
        "sitemap_url": "https://www.allstatenewsroom.com/post-sitemap.xml",
        # Yoast sitemap lists every post (262 articles, 2022-01 onward), so
        # sitemap discovery is complete and cheaper than paging the listing.
        "discovery_mode": "sitemap",
        # Flat WordPress permalinks: /news/<slug>/ -> 2 segments. min 2 drops the
        # /news/ index page, which is also present in the sitemap.
        "article_url_contains": "/news/",
        "article_url_excludes": ["/category/", "/author/", "/tag/", "/multimedia/"],
        "min_path_segments": 2,
        "content_selectors": ["article", ".entry-content", 'div[class*="entry"]',
                              'div[class*="content"]'],
        "wait_until": "domcontentloaded",
        "dynamic_wait_ms": 3000,
        "delay": 10.0,  # allstatenewsroom.com robots.txt specifies Crawl-delay: 10
        # The sitemap is ordered oldest-first and the archive is dominated by
        # older financial releases, so default to the most recent news.
        "newest_first": True,
    },
}


class ConfigurableBlogCrawler:
    """Unified Playwright-based blog crawler driven by per-site config."""

    def __init__(self, site_config: Dict):
        # Merge defaults under the site-specific overrides
        self.config = {**DEFAULT_CONFIG, **site_config}
        self.company = self.config["company"]
        self.base_url = self.config["base_url"]
        # url -> <lastmod> string, populated during sitemap discovery and used
        # to order URLs when newest_first is set.
        self._url_lastmod: Dict[str, str] = {}

        # Supabase
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Database operations will be skipped.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialized")

    # ── Page fetching ──────────────────────────────────────────────────────

    def fetch_page(self, page, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page via Playwright with retry logic."""
        max_retries = self.config["max_retries"]
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{max_retries})")
                response = page.goto(url, wait_until=self.config["wait_until"], timeout=60000)

                status = response.status if response else None
                # Accept 200 and 403 — some bot-protected sites return 403
                # but still render content via JavaScript
                if status in (200, 403):
                    if status == 403:
                        logger.warning(f"Got 403 for {url}, waiting for JS-rendered content...")

                    # Configurable wait for dynamic content
                    page.wait_for_timeout(self.config["dynamic_wait_ms"])

                    # Optionally wait for a specific selector
                    if self.config["wait_for_selector"]:
                        try:
                            page.wait_for_selector(self.config["wait_for_selector"], timeout=10000)
                        except PlaywrightTimeout:
                            logger.warning(f"Selector '{self.config['wait_for_selector']}' not found, continuing")

                    # Scroll to trigger lazy-loaded listing content
                    for _ in range(self.config["scroll_count"]):
                        page.mouse.wheel(0, 25000)
                        page.wait_for_timeout(1200)

                    content = page.content()
                    soup = BeautifulSoup(content, "lxml")

                    # Verify we got real content (not a challenge/block page)
                    if self._is_block_page(soup):
                        logger.warning(f"Detected bot-protection block page for {url}, retrying...")
                    else:
                        logger.info(f"Successfully fetched: {url} (status {status})")
                        return soup
                else:
                    logger.error(f"Failed with status {status}")

            except PlaywrightTimeout:
                logger.error(f"Timeout fetching {url}")
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None

        return None

    @staticmethod
    def _is_block_page(soup: BeautifulSoup) -> bool:
        """Detect Cloudflare / bot-protection challenge pages."""
        title = soup.find("title")
        title_text = title.get_text(strip=True).lower() if title else ""
        block_signals = [
            "blocked", "access denied", "attention required",
            "just a moment", "checking your browser", "security check",
        ]
        for signal in block_signals:
            if signal in title_text:
                return True
        body = soup.find("body")
        if not body or len(body.get_text(strip=True)) < 200:
            return True
        return False

    # ── URL discovery ──────────────────────────────────────────────────────

    def discover_urls(self, page) -> List[str]:
        """Dispatch URL discovery based on config mode."""
        mode = self.config["discovery_mode"]
        urls: List[str] = []

        if mode in ("listing", "both"):
            urls.extend(self._discover_from_listing(page))
        if mode in ("sitemap", "both"):
            urls.extend(self._discover_from_sitemap(page))

        # Deduplicate while preserving order
        seen: set = set()
        unique: List[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)

        if self.config.get("newest_first"):
            if self._url_lastmod:
                # Missing lastmod sorts last rather than crashing the sort.
                unique.sort(key=lambda u: self._url_lastmod.get(u, ""), reverse=True)
                logger.info("Ordered URLs newest-first by sitemap <lastmod>")
            else:
                logger.warning("newest_first set but no <lastmod> data available "
                               "(listing discovery?); leaving discovery order")

        logger.info(f"Total unique article URLs discovered: {len(unique)}")
        return unique

    def _discover_from_listing(self, page) -> List[str]:
        """Extract article URLs from one or more listing pages."""
        listing_urls = self.config.get("listing_urls") or [
            self.config.get("listing_url", self.base_url)]
        all_urls: List[str] = []
        for listing_url in listing_urls:
            all_urls.extend(self._discover_from_single_listing(page, listing_url))
        return all_urls

    def _discover_from_single_listing(self, page, listing_url) -> List[str]:
        """Extract article URLs from a single listing page."""
        soup = self.fetch_page(page, listing_url)
        if not soup:
            logger.error(f"Failed to fetch listing page: {listing_url}")
            return []

        selectors = self.config["listing_selectors"]
        articles = []
        for selector in selectors:
            articles = soup.select(selector)
            if articles:
                logger.info(f"Found {len(articles)} elements with selector: {selector}")
                break

        if not articles:
            # Fallback: grab all anchors matching the article URL pattern
            pattern = self.config["article_url_contains"]
            articles = soup.select(f'a[href*="{pattern}"]')
            if articles:
                logger.info(f"Fallback: found {len(articles)} links matching '{pattern}'")

        if not articles:
            logger.warning("No articles found on the listing page")
            return []

        urls: List[str] = []
        for el in articles:
            # The element itself might be an <a>, or contain one
            link = el if el.name == "a" and el.get("href") else el.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            absolute = self._make_absolute_url(href)
            if self._is_valid_article_url(absolute):
                urls.append(absolute)

        logger.info(f"Discovered {len(urls)} URLs from listing page")
        return urls

    def _discover_from_sitemap(self, page) -> List[str]:
        """Extract article URLs from an XML sitemap.

        Fetched over plain HTTP rather than through Playwright: sitemaps that
        ship an XSL stylesheet (Yoast, and most WordPress SEO plugins) get
        transformed into an HTML table by the browser, which destroys the raw
        XML. Falls back to Playwright if the direct fetch is blocked.
        """
        sitemap_url = self.config.get("sitemap_url")
        if not sitemap_url:
            logger.warning("No sitemap_url configured, skipping sitemap discovery")
            return []

        raw = self._fetch_sitemap_xml(sitemap_url, page)
        if not raw:
            return []

        try:
            urls = self._parse_sitemap_xml(raw, page)
        except ET.ParseError as e:
            logger.error(f"Error parsing sitemap XML: {e}")
            return []

        logger.info(f"Discovered {len(urls)} URLs from sitemap")
        return urls

    def _fetch_sitemap_xml(self, sitemap_url: str, page) -> Optional[str]:
        """Return raw sitemap XML text, or None. Tries HTTP, then Playwright."""
        logger.info(f"Fetching sitemap: {sitemap_url}")
        headers = {"User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")}
        try:
            resp = requests.get(sitemap_url, headers=headers, timeout=30,
                                allow_redirects=True)
            if resp.status_code == 200 and "<" in resp.text:
                return resp.text
            logger.warning(f"Sitemap HTTP fetch returned {resp.status_code}, "
                           "falling back to Playwright")
        except Exception as e:
            logger.warning(f"Sitemap HTTP fetch failed ({type(e).__name__}), "
                           "falling back to Playwright")

        # Playwright fallback (bot-protected sitemaps)
        try:
            response = page.goto(sitemap_url, wait_until=self.config["wait_until"],
                                 timeout=60000)
            if not response or response.status != 200:
                logger.error("Failed to fetch sitemap "
                             f"(status {response.status if response else 'None'})")
                return None
            text = BeautifulSoup(page.content(), "lxml").get_text()
            for marker in ("<?xml", "<urlset", "<sitemapindex"):
                idx = text.find(marker)
                if idx != -1:
                    return text[idx:]
            logger.error("Could not locate XML content in sitemap response")
            return None
        except Exception as e:
            logger.error(f"Playwright sitemap fetch failed: {e}")
            return None

    def _parse_sitemap_xml(self, raw: str, page, _depth: int = 0) -> List[str]:
        """Parse a urlset (or recurse one level into a sitemapindex)."""
        start = min((i for i in (raw.find("<?xml"), raw.find("<urlset"),
                                 raw.find("<sitemapindex")) if i != -1), default=-1)
        if start == -1:
            logger.error("Could not locate XML content in sitemap")
            return []
        root = ET.fromstring(raw[start:])
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # A sitemap index points at child sitemaps; recurse one level.
        children = root.findall(".//ns:sitemap/ns:loc", ns)
        if children and _depth == 0:
            logger.info(f"Sitemap index with {len(children)} child sitemaps")
            urls: List[str] = []
            for child in children:
                if not child.text:
                    continue
                child_raw = self._fetch_sitemap_xml(child.text.strip(), page)
                if child_raw:
                    urls.extend(self._parse_sitemap_xml(child_raw, page, _depth + 1))
            return urls

        urls = []
        for url_elem in root.findall(".//ns:url", ns):
            loc = url_elem.find("ns:loc", ns)
            if loc is None or not loc.text:
                continue
            url = loc.text.strip()
            if not self._is_valid_article_url(url):
                continue
            lastmod = url_elem.find("ns:lastmod", ns)
            if lastmod is not None and lastmod.text:
                self._url_lastmod[url] = lastmod.text.strip()
            urls.append(url)
        return urls


    # ── URL validation ─────────────────────────────────────────────────────

    def _is_valid_article_url(self, url: str) -> bool:
        """Check whether a URL matches the article pattern for this site."""
        contains = self.config["article_url_contains"]
        excludes = self.config["article_url_excludes"]
        min_segments = self.config["min_path_segments"]

        if contains and contains not in url:
            return False

        for exc in excludes:
            if exc in url:
                return False

        # Optional regex-based exclusion
        regex_exclude = self.config.get("article_url_regex_exclude")
        if regex_exclude and re.search(regex_exclude, url):
            return False

        # Count path segments (e.g. /blog/category/slug → 3)
        from urllib.parse import urlparse
        path = urlparse(url).path.strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) < min_segments:
            return False

        return True

    # ── Article scraping ───────────────────────────────────────────────────

    def scrape_blog_post(self, page, url: str) -> Optional[Dict]:
        """Scrape a single article page."""
        soup = self.fetch_page(page, url)
        if not soup:
            return None

        post_data: Dict = {"url": url, "scraped_at": datetime.utcnow().isoformat()}

        try:
            # Title
            title = soup.find(["h1", "h2"], class_=lambda x: x and ("title" in x.lower() or "heading" in x.lower()))
            if not title:
                title = soup.find("h1")
            if title:
                post_data["title"] = title.get_text(strip=True)

            # Content
            content = None
            for selector in self.config["content_selectors"]:
                content = soup.select_one(selector)
                if content:
                    break

            if content:
                for tag in content(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                post_data["content"] = content.get_text(separator="\n", strip=True)
                post_data["html_content"] = str(content)

            # Meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                post_data["meta_description"] = meta_desc["content"]

            # Publish date
            for selector in ["time[datetime]", 'meta[property="article:published_time"]',
                             'span[class*="date"]', 'div[class*="date"]']:
                date_elem = soup.select_one(selector)
                if date_elem:
                    if date_elem.name == "time" and date_elem.get("datetime"):
                        post_data["published_date"] = date_elem["datetime"]
                    elif date_elem.name == "meta" and date_elem.get("content"):
                        post_data["published_date"] = date_elem["content"]
                    else:
                        post_data["published_date"] = date_elem.get_text(strip=True)
                    # Normalize ISO 8601 timestamps to plain YYYY-MM-DD to match
                    # the format other sites store. Guarded so human-readable
                    # dates (e.g. "April 14, 2026") pass through untouched.
                    pd = post_data.get("published_date") or ""
                    if re.match(r"^\d{4}-\d{2}-\d{2}T", pd):
                        post_data["published_date"] = pd[:10]
                    break

            # Author
            for selector in ['meta[name="author"]', 'span[class*="author"]',
                             'div[class*="author"]', 'a[rel="author"]']:
                author_elem = soup.select_one(selector)
                if author_elem:
                    if author_elem.name == "meta" and author_elem.get("content"):
                        post_data["author"] = author_elem["content"]
                    else:
                        post_data["author"] = author_elem.get_text(strip=True)
                    break

            # Tags / categories
            tags: List[str] = []
            for selector in ['a[rel="tag"]', 'a[class*="tag"]', 'a[class*="category"]']:
                tag_elems = soup.select(selector)
                if tag_elems:
                    tags.extend([t.get_text(strip=True) for t in tag_elems])
                    break
            if not tags:
                # Fall back to extracting category from the URL path
                from urllib.parse import urlparse
                parts = urlparse(url).path.strip("/").split("/")
                if len(parts) >= 3:
                    tags = [parts[-2]]
            if tags:
                post_data["tags"] = tags

            # Featured image
            featured_image = self._extract_featured_image(soup, content)
            if featured_image:
                post_data["featured_image"] = featured_image

            logger.info(f"Successfully scraped: {post_data.get('title', url)}")
            return post_data

        except Exception as e:
            logger.error(f"Error scraping post {url}: {e}")
            return None

    def _extract_featured_image(self, soup: BeautifulSoup, content) -> Optional[str]:
        """Try multiple strategies to find the featured image."""
        featured_image = None

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            featured_image = og_image["content"]

        if not featured_image:
            twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
            if twitter_image and twitter_image.get("content"):
                featured_image = twitter_image["content"]

        if not featured_image and content:
            first_img = content.find("img", src=True)
            if first_img and first_img.get("src"):
                featured_image = first_img["src"]

        if not featured_image:
            hero_img = soup.find("img", class_=lambda x: x and ("featured" in x.lower() or "hero" in x.lower()))
            if hero_img and hero_img.get("src"):
                featured_image = hero_img["src"]

        if featured_image:
            featured_image = self._make_absolute_url(featured_image)
            # Many sites advertise og:image over http even though https serves the
            # same asset. Email clients block or proxy insecure images, so the card
            # renders blank — upgrade the scheme for same-host images.
            if featured_image.startswith("http://"):
                https_url = "https://" + featured_image[len("http://"):]
                if urlparse(https_url).netloc == urlparse(self.base_url).netloc:
                    featured_image = https_url

        return featured_image

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _make_absolute_url(self, url: str) -> str:
        """Convert a relative URL to absolute using the site's base_url."""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return f"https:{url}"
        return urljoin(self.base_url, url)

    # ── Persistence ────────────────────────────────────────────────────────

    def save_to_supabase(self, post_data: Dict) -> bool:
        """Save / upsert a blog post to Supabase."""
        if not self.supabase:
            logger.warning("Supabase client not initialized. Skipping save.")
            return False

        try:
            data = {
                "url": post_data.get("url"),
                "title": post_data.get("title"),
                "content": post_data.get("content"),
                "html_content": post_data.get("html_content"),
                "excerpt": post_data.get("excerpt"),
                "meta_description": post_data.get("meta_description"),
                "author": post_data.get("author"),
                "published_date": post_data.get("published_date"),
                "featured_image": post_data.get("featured_image"),
                "tags": post_data.get("tags"),
                "scraped_at": post_data.get("scraped_at"),
                "company": self.company,
            }
            data = {k: v for k, v in data.items() if v is not None}

            self.supabase.table("blog_posts").upsert(data, on_conflict="url").execute()
            logger.info(f"Saved to Supabase: {post_data.get('title', 'Untitled')}")
            return True

        except Exception as e:
            logger.error(f"Error saving to Supabase: {e}")
            return False

    # ── Main crawl loop ────────────────────────────────────────────────────

    def crawl(self, max_posts: Optional[int] = None, dry_run: bool = False):
        """Run the full crawl pipeline."""
        logger.info(f"Starting crawl for '{self.company}' (mode={self.config['discovery_mode']}, "
                     f"dry_run={dry_run})")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.config["headless"],
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            # Remove navigator.webdriver flag to avoid bot detection
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()

            try:
                # Discover article URLs
                article_urls = self.discover_urls(page)

                if not article_urls:
                    logger.error("No article URLs discovered. Exiting.")
                    return

                if max_posts:
                    article_urls = article_urls[:max_posts]
                    logger.info(f"Limiting to {max_posts} posts")

                if dry_run:
                    logger.info("DRY RUN — discovered URLs:")
                    for i, url in enumerate(article_urls, 1):
                        logger.info(f"  {i}. {url}")
                    logger.info(f"Total: {len(article_urls)} URLs")
                    return

                # Scrape & save each article
                successful = 0
                failed = 0
                delay = self.config["delay"]

                for i, url in enumerate(article_urls, 1):
                    logger.info(f"Processing post {i}/{len(article_urls)}: {url}")

                    post_data = self.scrape_blog_post(page, url)
                    if post_data:
                        if self.save_to_supabase(post_data):
                            successful += 1
                        else:
                            failed += 1
                    else:
                        failed += 1

                    if i < len(article_urls):
                        logger.info(f"Waiting {delay}s before next request...")
                        time.sleep(delay)

                logger.info("Crawl completed!")
                logger.info(f"Successful: {successful}")
                logger.info(f"Failed: {failed}")
                logger.info(f"Total: {len(article_urls)}")

            finally:
                browser.close()


# ── CLI ────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configurable Playwright-based blog crawler"
    )
    parser.add_argument(
        "--site", type=str, default=None,
        help=f"Built-in site key ({', '.join(SITE_CONFIGS.keys())})"
    )
    parser.add_argument(
        "--config-file", type=str, default=None,
        help="Path to a JSON file with site config (overrides --site)"
    )
    parser.add_argument(
        "--max-posts", type=int, default=None,
        help="Max number of posts to scrape"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only discover URLs, don't scrape or save"
    )
    parser.add_argument(
        "--discovery", type=str, default=None,
        choices=["listing", "sitemap", "both"],
        help="Override discovery mode"
    )
    parser.add_argument(
        "--delay", type=float, default=None,
        help="Seconds between requests (default: 2.0)"
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="Run browser in visible (non-headless) mode"
    )
    parser.add_argument(
        "--newest-first", action="store_true",
        help="Crawl newest articles first (uses sitemap <lastmod>); pair with "
             "--max-posts N to grab the N most recent"
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    # Resolve site config
    if args.config_file:
        with open(args.config_file, "r") as f:
            site_config = json.load(f)
        logger.info(f"Loaded config from {args.config_file}")
    elif args.site:
        if args.site not in SITE_CONFIGS:
            parser.error(f"Unknown site '{args.site}'. Choose from: {', '.join(SITE_CONFIGS.keys())}")
        site_config = SITE_CONFIGS[args.site].copy()
        logger.info(f"Using built-in config for '{args.site}'")
    else:
        parser.error("Provide --site or --config-file")
        return  # unreachable but keeps type-checkers happy

    # Apply CLI overrides
    if args.discovery:
        site_config["discovery_mode"] = args.discovery
    if args.delay is not None:
        site_config["delay"] = args.delay
    if args.no_headless:
        site_config["headless"] = False
    if args.newest_first:
        site_config["newest_first"] = True

    crawler = ConfigurableBlogCrawler(site_config)
    crawler.crawl(max_posts=args.max_posts, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
