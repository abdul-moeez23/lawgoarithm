import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lawyer_platform.settings")

try:
    import django
    django.setup()
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        print(f"Database connection successful: {row}")
except Exception as e:
    print(f"Database connection failed: {e}")
    import traceback
    traceback.print_exc()
