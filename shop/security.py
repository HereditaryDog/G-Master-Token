import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings
from django.core import signing
from django.core.exceptions import DisallowedHost
from django.utils.http import url_has_allowed_host_and_scheme


def _key_material():
    return (getattr(settings, "CARD_SECRET_KEY", "") or settings.SECRET_KEY).encode("utf-8")


def _derive_digest(label):
    return hashlib.sha256(label.encode("utf-8") + b":" + _key_material()).digest()


def get_card_fernet():
    return Fernet(base64.urlsafe_b64encode(_derive_digest("card-encryption")))


def is_encrypted_value(value):
    return isinstance(value, str) and value.startswith("gAAAAA")


def encrypt_secret(value):
    if value is None or value == "":
        return value
    if is_encrypted_value(value):
        return value
    return get_card_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value):
    if value is None or value == "":
        return value
    if not is_encrypted_value(value):
        return value
    return get_card_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def hash_secret(value):
    return hmac.new(_derive_digest("card-hash"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_secret(value, visible_prefix=4, visible_suffix=4):
    if not value:
        return "-"
    if len(value) <= visible_prefix + visible_suffix:
        return value
    return f"{value[:visible_prefix]}...{value[-visible_suffix:]}"


def get_request_ip(request):
    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    trusted_proxies = set(getattr(settings, "TRUSTED_PROXY_IPS", []))

    if remote_addr in trusted_proxies:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if real_ip:
            return real_ip

    return remote_addr


def is_request_ip_allowed(request, allowlist):
    if not allowlist:
        return True
    return get_request_ip(request) in allowlist


def get_safe_next_url(request, target, fallback):
    candidate = (target or "").strip()
    if not candidate:
        return fallback

    try:
        current_host = request.get_host()
    except DisallowedHost:
        current_host = ""

    allowed_hosts = {host for host in [current_host, *getattr(settings, "ALLOWED_HOSTS", [])] if host}
    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def is_merchant_user(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or getattr(user, "is_merchant", False)
        )
    )


def build_guest_order_access_token(order, email):
    return signing.dumps(
        {"order_id": order.id, "email": email.lower()},
        salt="guest-order-access",
    )


def load_guest_order_access_token(token, max_age=1800):
    return signing.loads(token, salt="guest-order-access", max_age=max_age)
