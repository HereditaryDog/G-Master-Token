import logging
import time

from django.contrib.auth import login
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView

from .forms import (
    AccountLoginForm,
    MerchantLoginForm,
    AccountPasswordChangeForm,
    AccountPasswordResetForm,
    AccountSetPasswordForm,
    SignUpForm,
)
from .models import User
from .rate_limits import consume_request
from .utils import (
    build_signup_code_response_payload,
    refresh_login_captcha,
    normalize_email_address,
    send_signup_email_code,
)
from shop.security import get_request_ip

logger = logging.getLogger(__name__)


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("shop:storefront")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class CaptchaLoginViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_name"] = settings.SITE_NAME
        context["project_version"] = settings.PROJECT_VERSION
        context["captcha_image_url"] = f"{reverse('accounts:login_captcha')}?ts={time.time_ns()}"
        return context


class AccountLoginView(CaptchaLoginViewMixin, LoginView):
    template_name = "registration/login.html"
    authentication_form = AccountLoginForm
    redirect_authenticated_user = True


class MerchantLoginView(CaptchaLoginViewMixin, LoginView):
    template_name = "registration/merchant_login.html"
    authentication_form = MerchantLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("shop:merchant_dashboard")


class AccountPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    form_class = AccountPasswordResetForm

    def get_extra_email_context(self):
        return {
            "site_name": settings.SITE_NAME,
            "site_base_url": settings.SITE_BASE_URL,
        }

    def form_valid(self, form):
        self.extra_email_context = self.get_extra_email_context()
        return super().form_valid(form)


class AccountPasswordResetDoneView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class AccountPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")
    form_class = AccountSetPasswordForm


class AccountPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


class AccountPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("password_change_done")
    form_class = AccountPasswordChangeForm


class AccountPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "registration/password_change_done.html"


class SendSignupCodeView(View):
    def post(self, request, *args, **kwargs):
        request_ip = get_request_ip(request)
        ip_decision = consume_request("signup_code_ip", request_ip)
        if ip_decision.blocked:
            return JsonResponse(
                {
                    "ok": False,
                    "message": ip_decision.message,
                    "cooldown_seconds": ip_decision.retry_after,
                },
                status=429,
            )

        email = request.POST.get("email", "")
        if not email:
            return JsonResponse({"ok": False, "message": "请先输入邮箱地址。"}, status=400)
        try:
            email = normalize_email_address(email)
        except ValidationError:
            return JsonResponse({"ok": False, "message": "请输入有效的邮箱地址。"}, status=400)
        email_decision = consume_request("signup_code_email", email)
        if email_decision.blocked:
            return JsonResponse(
                {
                    "ok": False,
                    "message": email_decision.message,
                    "cooldown_seconds": email_decision.retry_after,
                },
                status=429,
            )
        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({"ok": False, "message": "该邮箱已经注册。"}, status=400)
        try:
            verification = send_signup_email_code(email)
        except ValueError as exc:
            return JsonResponse(
                {
                    "ok": False,
                    "message": str(exc),
                    "cooldown_seconds": settings.EMAIL_CODE_COOLDOWN_SECONDS,
                },
                status=400,
            )
        except Exception:
            logger.exception("Failed to send signup verification code to %s", email)
            return JsonResponse({"ok": False, "message": "验证码发送失败，请检查邮箱配置。"}, status=500)
        return JsonResponse(build_signup_code_response_payload(verification))


class RefreshLoginCaptchaView(View):
    def get(self, request, *args, **kwargs):
        svg = refresh_login_captcha(request)
        response = HttpResponse(svg, content_type="image/svg+xml")
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        return response
