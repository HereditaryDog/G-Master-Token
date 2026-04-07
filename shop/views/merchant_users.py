from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.views.generic import DetailView, ListView

from accounts.models import User
from shop.forms import MerchantUserFilterForm
from shop.models import Order

from .merchant_base import MerchantContextMixin


def _customer_annotation_queryset(queryset):
    money_zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=10, decimal_places=2))
    return queryset.annotate(
        order_count=Count("orders", distinct=True),
        paid_order_count=Count(
            "orders",
            filter=Q(orders__payment_status=Order.PaymentStatus.PAID),
            distinct=True,
        ),
        total_spent=Coalesce(
            Sum("orders__total_amount", filter=Q(orders__payment_status=Order.PaymentStatus.PAID)),
            money_zero,
        ),
        last_order_at=Max("orders__created_at"),
    )


class MerchantUserListView(MerchantContextMixin, ListView):
    template_name = "shop/merchant_users.html"
    context_object_name = "customers"
    merchant_tab = "users"
    paginate_by = 20

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = MerchantUserFilterForm(self.request.GET or None)
        return self._filter_form

    def get_customer_base_queryset(self):
        queryset = User.objects.filter(is_staff=False, is_superuser=False, is_merchant=False)
        form = self.get_filter_form()
        if form.is_valid():
            query = form.cleaned_data["query"]
            if query:
                queryset = queryset.filter(
                    Q(username__icontains=query)
                    | Q(display_name__icontains=query)
                    | Q(email__icontains=query)
                    | Q(phone__icontains=query)
                    | Q(orders__order_no__icontains=query)
                )
        return queryset.distinct()

    def get_queryset(self):
        return _customer_annotation_queryset(self.get_customer_base_queryset()).order_by("-date_joined", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered_users = self.get_customer_base_queryset()
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        money_zero = Decimal("0.00")
        revenue = (
            Order.objects.filter(user__in=filtered_users, payment_status=Order.PaymentStatus.PAID)
            .aggregate(total=Coalesce(Sum("total_amount"), Value(money_zero)))["total"]
        )
        context["filter_form"] = self.get_filter_form()
        context["pagination_query"] = query_params.urlencode()
        context["user_stats"] = {
            "total_count": filtered_users.count(),
            "verified_count": filtered_users.filter(email_verified=True).count(),
            "buyers_count": filtered_users.filter(orders__isnull=False).distinct().count(),
            "paid_revenue": revenue,
        }
        return context


class MerchantUserDetailView(MerchantContextMixin, DetailView):
    template_name = "shop/merchant_user_detail.html"
    context_object_name = "customer"
    merchant_tab = "users"

    def get_queryset(self):
        queryset = User.objects.filter(is_staff=False, is_superuser=False, is_merchant=False)
        return _customer_annotation_queryset(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = (
            self.object.orders.select_related("user")
            .prefetch_related("items__deliveries", "payment_attempts")
            .order_by("-created_at")
        )
        page_obj = Paginator(orders, 20).get_page(self.request.GET.get("page") or 1)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["orders"] = page_obj.object_list
        context["page_obj"] = page_obj
        context["is_paginated"] = page_obj.paginator.num_pages > 1
        context["pagination_query"] = query_params.urlencode()
        context["customer_stats"] = {
            "pending_order_count": orders.filter(status=Order.Status.PENDING_PAYMENT).count(),
            "paid_order_count": self.object.paid_order_count,
            "order_count": self.object.order_count,
            "total_spent": self.object.total_spent,
        }
        return context
