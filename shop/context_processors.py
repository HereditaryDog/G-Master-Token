import time

from django.conf import settings


def site_context(request):
    return {
        "site_name": settings.SITE_NAME,
        "project_version": settings.PROJECT_VERSION,
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "asset_version": f"{settings.PROJECT_VERSION}-{int(time.time())}" if settings.DEBUG else settings.PROJECT_VERSION,
    }
