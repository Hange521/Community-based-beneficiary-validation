
import os

from django.core.wsgi import get_wsgi_application
from bvs.settings import wsgi

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bvs.settings"
)

app = get_wsgi_application()

Default = wsgi.entrypoint(app)
