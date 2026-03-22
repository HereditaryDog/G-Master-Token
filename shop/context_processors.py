from django.conf import settings


def site_context(request):
    return {
        "site_name": settings.SITE_NAME,
        "project_version": settings.PROJECT_VERSION,
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
    }
