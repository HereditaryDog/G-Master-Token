from django.urls import path

from .views import (
    AccountPasswordChangeDoneView,
    AccountPasswordChangeView,
    AccountPasswordResetCompleteView,
    AccountPasswordResetConfirmView,
    AccountPasswordResetDoneView,
    AccountPasswordResetView,
)

urlpatterns = [
    path("password_change/", AccountPasswordChangeView.as_view(), name="password_change"),
    path("password_change/done/", AccountPasswordChangeDoneView.as_view(), name="password_change_done"),
    path("password_reset/", AccountPasswordResetView.as_view(), name="password_reset"),
    path("password_reset/done/", AccountPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", AccountPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", AccountPasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
