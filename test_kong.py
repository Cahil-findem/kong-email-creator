import cloudscraper
from bs4 import BeautifulSoup

# Create scraper
session = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'darwin',
        'desktop': True
    }
)

# Fetch the page
response = session.get('https://konghq.com/blog', timeout=30)
soup = BeautifulSoup(response.content, 'lxml')

# Try different selectors
print("=== Testing selectors ===\n")

selectors = [
    '.blog-post-card',
    'article',
    '.card',
    'a[href*="/blog/"]'
]

for selector in selectors:
    elements = soup.select(selector)
    print(f"{selector}: Found {len(elements)} elements")
    if elements and len(elements) > 0:
        first = elements[0]
        print(f"  First element tag: {first.name}")
        print(f"  First element classes: {first.get('class', [])}")

        # Try to find link
        if first.name == 'a':
            print(f"  Href: {first.get('href')}")
        else:
            link = first.find('a', href=True)
            if link:
                print(f"  Contains link to: {link.get('href')}")

        # Try to find title
        title_tags = first.find(['h1', 'h2', 'h3', 'h4'])
        if title_tags:
            print(f"  Title: {title_tags.get_text(strip=True)[:50]}")
        print()
