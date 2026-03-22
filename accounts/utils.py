import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationCode


def generate_numeric_code(length=6):
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_captcha(length=4):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def refresh_login_captcha(request):
    captcha = generate_captcha()
    request.session["login_captcha"] = captcha
    return captcha


def get_login_captcha(request):
    captcha = request.session.get("login_captcha")
    if not captcha:
        captcha = refresh_login_captcha(request)
    return captcha


def send_signup_email_code(email):
    cooldown_seconds = getattr(settings, "EMAIL_CODE_COOLDOWN_SECONDS", 60)
    expiry_minutes = getattr(settings, "EMAIL_CODE_EXPIRY_MINUTES", 10)
    cooldown_from = timezone.now() - timedelta(seconds=cooldown_seconds)

    if EmailVerificationCode.objects.filter(
        email__iexact=email,
        purpose=EmailVerificationCode.Purpose.SIGNUP,
        created_at__gte=cooldown_from,
        consumed_at__isnull=True,
    ).exists():
        raise ValueError(f"验证码发送过于频繁，请在 {cooldown_seconds} 秒后重试。")

    code = generate_numeric_code()
    verification = EmailVerificationCode.objects.create(
        email=email,
        purpose=EmailVerificationCode.Purpose.SIGNUP,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
    )
    send_mail(
        subject="web_0.0.1 注册邮箱验证码",
        message=f"你的注册验证码是：{code}\n\n{expiry_minutes} 分钟内有效，请勿泄露给他人。",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    return verification
