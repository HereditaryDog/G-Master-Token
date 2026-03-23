from django.http import HttpResponseForbidden
from django.conf import settings


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class SensitiveAreaIPAllowlistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        client_ip = _client_ip(request)

        if path.startswith("/admin/") and settings.ADMIN_ALLOWED_IPS:
            if client_ip not in settings.ADMIN_ALLOWED_IPS:
                return HttpResponseForbidden("Admin access denied from this IP.")

        if path.startswith("/dashboard/") and settings.MERCHANT_ALLOWED_IPS:
            if client_ip not in settings.MERCHANT_ALLOWED_IPS:
                return HttpResponseForbidden("Merchant access denied from this IP.")

        return self.get_response(request)
