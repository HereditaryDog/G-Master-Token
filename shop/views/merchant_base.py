from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy

from shop.security import is_merchant_user


class MerchantRequiredMixin(UserPassesTestMixin):
    login_url = reverse_lazy("accounts:merchant_login")

    def test_func(self):
        return is_merchant_user(self.request.user)


class MerchantContextMixin(MerchantRequiredMixin):
    merchant_tab = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["merchant_tab"] = self.merchant_tab
        return context
