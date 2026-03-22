from django.urls import path

from .views import AccountLoginView, SendSignupCodeView, SignUpView

urlpatterns = [
    path("login/", AccountLoginView.as_view(), name="login"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("signup/send-code/", SendSignupCodeView.as_view(), name="signup_send_code"),
]
