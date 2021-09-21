import os
import django
from channels.routing import get_default_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
os.environ["ASGI_THREADS"] = "4"
application = get_default_application()
