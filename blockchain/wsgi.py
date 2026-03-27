"""
WSGI entry point for production servers (gunicorn, uWSGI, etc.)

Usage:
    gunicorn wsgi:app --workers 4 --bind 0.0.0.0:8000

Behind nginx with a Unix socket:
    gunicorn wsgi:app --workers 4 --bind unix:/tmp/medisure.sock --timeout 120
"""

import os
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'production'))
