from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView

from .forms import AccountLoginForm, SignUpForm
from .models import User
from .utils import get_login_captcha, refresh_login_captcha, send_signup_email_code


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("shop:storefront")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class AccountLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = AccountLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["captcha_value"] = get_login_captcha(self.request)
        return context

    def form_invalid(self, form):
        refresh_login_captcha(self.request)
        return super().form_invalid(form)

    def get(self, request, *args, **kwargs):
        refresh_login_captcha(request)
        return super().get(request, *args, **kwargs)


class SendSignupCodeView(View):
    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "").strip().lower()
        if not email:
            return JsonResponse({"ok": False, "message": "请先输入邮箱地址。"}, status=400)
        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({"ok": False, "message": "该邮箱已经注册。"}, status=400)
        try:
            send_signup_email_code(email)
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
            return JsonResponse({"ok": False, "message": "验证码发送失败，请检查邮箱配置。"}, status=500)
        return JsonResponse(
            {
                "ok": True,
                "message": "验证码已发送，请查收邮箱。",
                "cooldown_seconds": settings.EMAIL_CODE_COOLDOWN_SECONDS,
                "expiry_minutes": settings.EMAIL_CODE_EXPIRY_MINUTES,
            }
        )


class RefreshLoginCaptchaView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"ok": True, "captcha": refresh_login_captcha(request)})
