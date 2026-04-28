
import os
import django
from django.conf import settings

# Configure minimal Django settings
if not settings.configured:
    settings.configure(INSTALLED_APPS=['allauth', 'allauth.account', 'django.contrib.auth', 'django.contrib.contenttypes'])
    django.setup()

try:
    import allauth.account.utils
    print("Attributes in allauth.account.utils:")
    for item in dir(allauth.account.utils):
        if not item.startswith("__"):
            print(item)
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
