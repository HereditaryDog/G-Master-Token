import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from django.core import signing
from django.conf import settings


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


def build_guest_order_access_token(order, email):
    return signing.dumps(
        {"order_id": order.id, "email": email.lower()},
        salt="guest-order-access",
    )


def load_guest_order_access_token(token, max_age=1800):
    return signing.loads(token, salt="guest-order-access", max_age=max_age)
