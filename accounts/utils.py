import hashlib
import hmac
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationCode


LOCAL_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
}

LOGIN_CAPTCHA_SESSION_KEY = "login_captcha_state"


def generate_numeric_code(length=6):
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_captcha(length=4):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _hash_captcha_answer(answer):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        answer.strip().upper().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_captcha_svg(answer):
    palette = ("#0b312c", "#1c5248", "#225d53", "#0f4c81")
    text_nodes = []
    for index, char in enumerate(answer):
        x = 18 + index * 18
        y = 30 + secrets.randbelow(8)
        rotate = secrets.randbelow(21) - 10
        color = secrets.choice(palette)
        text_nodes.append(
            f"<text x='{x}' y='{y}' fill='{color}' font-size='24' font-family='monospace' "
            f"font-weight='700' transform='rotate({rotate} {x} {y})'>{char}</text>"
        )

    line_nodes = []
    for _ in range(4):
        x1 = secrets.randbelow(96)
        y1 = 8 + secrets.randbelow(32)
        x2 = secrets.randbelow(96)
        y2 = 8 + secrets.randbelow(32)
        color = secrets.choice(palette)
        line_nodes.append(
            f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' stroke-opacity='0.22' stroke-width='1.4' />"
        )

    dot_nodes = []
    for _ in range(10):
        cx = secrets.randbelow(96)
        cy = 8 + secrets.randbelow(32)
        radius = 0.8 + secrets.randbelow(3) * 0.45
        color = secrets.choice(palette)
        dot_nodes.append(f"<circle cx='{cx}' cy='{cy}' r='{radius:.2f}' fill='{color}' fill-opacity='0.18' />")

    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='96' height='42' viewBox='0 0 96 42' role='img' "
        "aria-label='图形验证码'>"
        "<rect width='96' height='42' rx='12' fill='#f4f7fb' />"
        "<rect x='1' y='1' width='94' height='40' rx='11' fill='none' stroke='#c9d7e6' stroke-width='1' />"
        + "".join(line_nodes)
        + "".join(dot_nodes)
        + "".join(text_nodes)
        + "</svg>"
    )


def _store_login_captcha_state(session, answer, expires_at=None):
    ttl_seconds = int(getattr(settings, "LOGIN_CAPTCHA_TTL_SECONDS", 300))
    session[LOGIN_CAPTCHA_SESSION_KEY] = {
        "answer_hash": _hash_captcha_answer(answer),
        "expires_at": int((expires_at or (timezone.now() + timedelta(seconds=ttl_seconds))).timestamp()),
    }
    session.modified = True


def prime_login_captcha(session, answer, expires_at=None):
    _store_login_captcha_state(session, answer, expires_at=expires_at)


def clear_login_captcha(request):
    request.session.pop(LOGIN_CAPTCHA_SESSION_KEY, None)
    request.session.modified = True


def normalize_email_address(email):
    normalized = email.strip().lower()
    validate_email(normalized)
    return normalized


def refresh_login_captcha(request):
    captcha = generate_captcha()
    _store_login_captcha_state(request.session, captcha)
    return _build_captcha_svg(captcha)


def validate_login_captcha(request, candidate):
    state = request.session.get(LOGIN_CAPTCHA_SESSION_KEY) or {}
    clear_login_captcha(request)
    if not candidate or not state:
        return False
    expires_at = int(state.get("expires_at", 0) or 0)
    if expires_at < int(timezone.now().timestamp()):
        return False
    return hmac.compare_digest(state.get("answer_hash", ""), _hash_captcha_answer(candidate))


def send_signup_email_code(email):
    email = normalize_email_address(email)
    expiry_minutes = getattr(settings, "EMAIL_CODE_EXPIRY_MINUTES", 10)

    code = generate_numeric_code()
    verification = EmailVerificationCode.objects.create(
        email=email,
        purpose=EmailVerificationCode.Purpose.SIGNUP,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
    )
    try:
        send_mail(
            subject=f"{settings.SITE_NAME} 注册邮箱验证码",
            message=f"你的注册验证码是：{code}\n\n{expiry_minutes} 分钟内有效，请勿泄露给他人。",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        verification.delete()
        raise
    return verification


def get_signup_code_delivery_meta():
    if settings.EMAIL_BACKEND in LOCAL_EMAIL_BACKENDS:
        return {
            "delivery_mode": "local_mail",
            "message": "验证码已生成，但当前测试站未配置真实邮件发送，所以不会投递到你的邮箱。",
            "initial_hint": "当前测试站未配置真实邮件发送，点击后验证码只会写入服务器日志，不会投递到真实邮箱。",
        }
    return {
        "delivery_mode": "email",
        "message": "验证码已发送，请查收邮箱。",
        "initial_hint": "验证码会发送到你填写的邮箱地址。",
    }


def build_signup_code_response_payload(verification):
    delivery_meta = get_signup_code_delivery_meta()
    payload = {
        "ok": True,
        "message": delivery_meta["message"],
        "cooldown_seconds": settings.EMAIL_CODE_COOLDOWN_SECONDS,
        "expiry_minutes": settings.EMAIL_CODE_EXPIRY_MINUTES,
        "delivery_mode": delivery_meta["delivery_mode"],
    }
    return payload
