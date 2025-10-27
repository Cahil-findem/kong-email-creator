"""
Manage Pinned Blogs for Candidates

This script allows you to add, remove, and view manually pinned blogs for candidates.
Pinned blogs will always be included in the candidate's recommendations.
"""

import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()


class PinnedBlogManager:
    """Manage pinned blogs for candidates"""

    def __init__(self):
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

        self.supabase: Client = create_client(supabase_url, supabase_key)

    def get_candidate_pinned_blogs(self, candidate_id: str):
        """Get current pinned blogs for a candidate"""
        try:
            result = self.supabase.table('candidate_profiles')\
                .select('candidate_id, full_name, pinned_blogs')\
                .eq('candidate_id', candidate_id)\
                .execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            else:
                print(f"❌ Candidate {candidate_id} not found")
                return None

        except Exception as e:
            print(f"❌ Error fetching candidate: {str(e)}")
            return None

    def add_pinned_blog(self, candidate_id: str, blog_url: str):
        """Add a pinned blog for a candidate"""
        try:
            # Get current pinned blogs
            candidate = self.get_candidate_pinned_blogs(candidate_id)
            if not candidate:
                return False

            current_pinned = candidate.get('pinned_blogs', [])

            # Check if already pinned
            if blog_url in current_pinned:
                print(f"⚠️  Blog already pinned: {blog_url}")
                return False

            # Add new blog
            current_pinned.append(blog_url)

            # Update database
            result = self.supabase.table('candidate_profiles')\
                .update({'pinned_blogs': current_pinned})\
                .eq('candidate_id', candidate_id)\
                .execute()

            print(f"✅ Added pinned blog for {candidate['full_name']}")
            print(f"   URL: {blog_url}")
            print(f"   Total pinned blogs: {len(current_pinned)}")
            return True

        except Exception as e:
            print(f"❌ Error adding pinned blog: {str(e)}")
            return False

    def remove_pinned_blog(self, candidate_id: str, blog_url: str):
        """Remove a pinned blog for a candidate"""
        try:
            # Get current pinned blogs
            candidate = self.get_candidate_pinned_blogs(candidate_id)
            if not candidate:
                return False

            current_pinned = candidate.get('pinned_blogs', [])

            # Check if blog exists
            if blog_url not in current_pinned:
                print(f"⚠️  Blog not found in pinned list: {blog_url}")
                return False

            # Remove blog
            current_pinned.remove(blog_url)

            # Update database
            result = self.supabase.table('candidate_profiles')\
                .update({'pinned_blogs': current_pinned})\
                .eq('candidate_id', candidate_id)\
                .execute()

            print(f"✅ Removed pinned blog for {candidate['full_name']}")
            print(f"   URL: {blog_url}")
            print(f"   Total pinned blogs: {len(current_pinned)}")
            return True

        except Exception as e:
            print(f"❌ Error removing pinned blog: {str(e)}")
            return False

    def list_pinned_blogs(self, candidate_id: str):
        """List all pinned blogs for a candidate"""
        try:
            candidate = self.get_candidate_pinned_blogs(candidate_id)
            if not candidate:
                return

            pinned_blogs = candidate.get('pinned_blogs', [])

            print(f"\n{'='*80}")
            print(f"PINNED BLOGS FOR: {candidate['full_name']}")
            print(f"Candidate ID: {candidate['candidate_id']}")
            print(f"{'='*80}")

            if not pinned_blogs:
                print("No pinned blogs configured")
            else:
                print(f"\nTotal pinned blogs: {len(pinned_blogs)}\n")
                for i, url in enumerate(pinned_blogs, 1):
                    print(f"{i}. {url}")

            print(f"{'='*80}\n")

        except Exception as e:
            print(f"❌ Error listing pinned blogs: {str(e)}")

    def clear_all_pinned_blogs(self, candidate_id: str):
        """Clear all pinned blogs for a candidate"""
        try:
            candidate = self.get_candidate_pinned_blogs(candidate_id)
            if not candidate:
                return False

            # Update database
            result = self.supabase.table('candidate_profiles')\
                .update({'pinned_blogs': []})\
                .eq('candidate_id', candidate_id)\
                .execute()

            print(f"✅ Cleared all pinned blogs for {candidate['full_name']}")
            return True

        except Exception as e:
            print(f"❌ Error clearing pinned blogs: {str(e)}")
            return False

    def search_blogs(self, search_term: str):
        """Search for blog posts by title or URL to help find URLs to pin"""
        try:
            result = self.supabase.table('blog_posts')\
                .select('id, title, url, author, published_date')\
                .ilike('title', f'%{search_term}%')\
                .limit(10)\
                .execute()

            if not result.data:
                print(f"No blogs found matching '{search_term}'")
                return

            print(f"\n{'='*80}")
            print(f"BLOG SEARCH RESULTS FOR: '{search_term}'")
            print(f"{'='*80}\n")

            for i, blog in enumerate(result.data, 1):
                print(f"{i}. {blog['title']}")
                print(f"   URL: {blog['url']}")
                print(f"   Author: {blog.get('author', 'N/A')}")
                print(f"   Published: {blog.get('published_date', 'N/A')}")
                print()

            print(f"{'='*80}\n")

        except Exception as e:
            print(f"❌ Error searching blogs: {str(e)}")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  List pinned blogs:")
        print("    python manage_pinned_blogs.py list <candidate_id>")
        print("\n  Add pinned blog:")
        print("    python manage_pinned_blogs.py add <candidate_id> <blog_url>")
        print("\n  Remove pinned blog:")
        print("    python manage_pinned_blogs.py remove <candidate_id> <blog_url>")
        print("\n  Clear all pinned blogs:")
        print("    python manage_pinned_blogs.py clear <candidate_id>")
        print("\n  Search for blogs:")
        print("    python manage_pinned_blogs.py search <search_term>")
        print("\nExamples:")
        print('  python manage_pinned_blogs.py list pub_5c7baa020cadfda94cb36a7f')
        print('  python manage_pinned_blogs.py add pub_5c7baa020cadfda94cb36a7f "https://konghq.com/blog/example"')
        print('  python manage_pinned_blogs.py search "API Gateway"')
        sys.exit(1)

    manager = PinnedBlogManager()
    command = sys.argv[1].lower()

    if command == 'list':
        if len(sys.argv) < 3:
            print("❌ Error: candidate_id required")
            sys.exit(1)
        candidate_id = sys.argv[2]
        manager.list_pinned_blogs(candidate_id)

    elif command == 'add':
        if len(sys.argv) < 4:
            print("❌ Error: candidate_id and blog_url required")
            sys.exit(1)
        candidate_id = sys.argv[2]
        blog_url = sys.argv[3]
        manager.add_pinned_blog(candidate_id, blog_url)

    elif command == 'remove':
        if len(sys.argv) < 4:
            print("❌ Error: candidate_id and blog_url required")
            sys.exit(1)
        candidate_id = sys.argv[2]
        blog_url = sys.argv[3]
        manager.remove_pinned_blog(candidate_id, blog_url)

    elif command == 'clear':
        if len(sys.argv) < 3:
            print("❌ Error: candidate_id required")
            sys.exit(1)
        candidate_id = sys.argv[2]

        # Confirm before clearing
        response = input(f"⚠️  Are you sure you want to clear all pinned blogs for {candidate_id}? (yes/no): ")
        if response.lower() == 'yes':
            manager.clear_all_pinned_blogs(candidate_id)
        else:
            print("Cancelled")

    elif command == 'search':
        if len(sys.argv) < 3:
            print("❌ Error: search_term required")
            sys.exit(1)
        search_term = sys.argv[2]
        manager.search_blogs(search_term)

    else:
        print(f"❌ Unknown command: {command}")
        print("Valid commands: list, add, remove, clear, search")
        sys.exit(1)


if __name__ == "__main__":
    main()
