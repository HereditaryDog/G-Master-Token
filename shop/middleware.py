from django.http import HttpResponseForbidden
from django.conf import settings

from shop.security import get_request_ip, is_request_ip_allowed


def _deny(message):
    return HttpResponseForbidden(message)


class SensitiveAreaIPAllowlistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith("/admin/") and settings.ADMIN_ALLOWED_IPS:
            if not is_request_ip_allowed(request, settings.ADMIN_ALLOWED_IPS):
                return _deny("Admin access denied from this IP.")

        if path.startswith("/dashboard/") and settings.MERCHANT_ALLOWED_IPS:
            if not is_request_ip_allowed(request, settings.MERCHANT_ALLOWED_IPS):
                return _deny("Merchant access denied from this IP.")

        return self.get_response(request)
