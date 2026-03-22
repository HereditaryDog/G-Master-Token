from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import EmailVerificationCode, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountAuthFlowTests(TestCase):
    def test_send_signup_code_creates_verification_record(self):
        client = Client()
        response = client.post(reverse("accounts:signup_send_code"), {"email": "newuser@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailVerificationCode.objects.filter(email="newuser@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_signup_requires_valid_email_code(self):
        verification = EmailVerificationCode.objects.create(
            email="verified@example.com",
            purpose=EmailVerificationCode.Purpose.SIGNUP,
            code="123456",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        client = Client()
        response = client.post(
            reverse("accounts:signup"),
            {
                "username": "verified-user",
                "email": "verified@example.com",
                "phone": "13800138000",
                "email_code": "123456",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="verified-user").exists())

    def test_signup_with_email_code_creates_verified_user(self):
        verification = EmailVerificationCode.objects.create(
            email="verified@example.com",
            purpose=EmailVerificationCode.Purpose.SIGNUP,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        client = Client()
        response = client.post(
            reverse("accounts:signup"),
            {
                "username": "verified-user",
                "email": "verified@example.com",
                "phone": "13800138000",
                "email_code": "123456",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="verified-user")
        verification.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(verification.consumed_at)

    def test_login_supports_username_or_email_with_captcha(self):
        user = User.objects.create_user(
            username="buyer",
            email="buyer@example.com",
            phone="13800138000",
            password="Buyer123!",
            email_verified=True,
        )
        self.assertIsNotNone(user.pk)

        client = Client()
        session = client.session
        session["login_captcha"] = "AB12"
        session.save()

        username_response = client.post(
            reverse("accounts:login"),
            {"username": "buyer", "password": "Buyer123!", "captcha": "AB12"},
        )
        self.assertEqual(username_response.status_code, 302)

        client.logout()
        session = client.session
        session["login_captcha"] = "CD34"
        session.save()

        email_response = client.post(
            reverse("accounts:login"),
            {"username": "buyer@example.com", "password": "Buyer123!", "captcha": "CD34"},
        )
        self.assertEqual(email_response.status_code, 302)

    def test_login_rejects_invalid_captcha(self):
        User.objects.create_user(
            username="buyer",
            email="buyer@example.com",
            phone="13800138000",
            password="Buyer123!",
            email_verified=True,
        )
        client = Client()
        session = client.session
        session["login_captcha"] = "WXYZ"
        session.save()

        response = client.post(
            reverse("accounts:login"),
            {"username": "buyer", "password": "Buyer123!", "captcha": "1234"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "验证码不正确")
