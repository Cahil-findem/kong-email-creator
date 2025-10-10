"""
Vercel serverless function entry point
"""
import sys
from os.path import dirname, abspath

# Add parent directory to Python path
root_dir = dirname(dirname(abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import the Flask app
from app import app as application

# Vercel will use this as the serverless function handler
app = application
