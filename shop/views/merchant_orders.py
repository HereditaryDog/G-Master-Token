from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from shop.emails import send_delivery_reminder_email
from shop.forms import MerchantOrderFilterForm
from shop.models import Order, SensitiveOperationLog
from shop.security import get_safe_next_url
from shop.services.audit import log_sensitive_operation
from shop.services.order_flow import retry_order_fulfillment

from .merchant_base import MerchantContextMixin, MerchantRequiredMixin


class MerchantOrderListView(MerchantContextMixin, ListView):
    template_name = "shop/merchant_orders.html"
    context_object_name = "orders"
    merchant_tab = "orders"

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = MerchantOrderFilterForm(self.request.GET or None)
        return self._filter_form

    def get_queryset(self):
        queryset = Order.objects.select_related("user").prefetch_related("items__deliveries").order_by("-created_at")
        form = self.get_filter_form()
        if form.is_valid():
            query = form.cleaned_data["query"]
            status = form.cleaned_data["status"]
            payment_status = form.cleaned_data["payment_status"]
            date_from = form.cleaned_data["date_from"]
            date_to = form.cleaned_data["date_to"]
            if query:
                queryset = queryset.filter(
                    models.Q(order_no__icontains=query)
                    | models.Q(user__username__icontains=query)
                    | models.Q(user__email__icontains=query)
                    | models.Q(contact_email__icontains=query)
                    | models.Q(payment_reference__icontains=query)
                )
            if status:
                queryset = queryset.filter(status=status)
            if payment_status:
                queryset = queryset.filter(payment_status=payment_status)
            if date_from:
                queryset = queryset.filter(created_at__date__gte=date_from)
            if date_to:
                queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.get_filter_form()
        return context


class MerchantOrderActionView(MerchantRequiredMixin, View):
    def post(self, request, order_no, *args, **kwargs):
        order = get_object_or_404(
            Order.objects.select_related("user").prefetch_related("items__deliveries"),
            order_no=order_no,
        )
        next_url = get_safe_next_url(
            request,
            request.POST.get("next"),
            reverse("shop:merchant_order_detail", args=[order.order_no]),
        )
        action = request.POST.get("action", "").strip()

        if action == "mark_failed":
            merchant_note = request.POST.get("merchant_note", "").strip() or "商家手动标记为异常订单。"
            order.status = Order.Status.FAILED
            order.merchant_note = merchant_note
            order.save(update_fields=["status", "merchant_note", "updated_at"])
            messages.warning(request, f"订单 {order.order_no} 已标记为异常。")
        elif action == "retry_fulfillment":
            if order.payment_status != Order.PaymentStatus.PAID:
                messages.error(request, "只有已支付订单才能重试自动发货。")
            else:
                order = retry_order_fulfillment(order)
                if order.status == Order.Status.COMPLETED:
                    messages.success(request, f"订单 {order.order_no} 已重试发货并恢复完成。")
                else:
                    messages.warning(request, "已再次尝试自动发货，但当前仍未成功，请检查库存或供应接口。")
        elif action == "resend_delivery":
            try:
                recipient = send_delivery_reminder_email(order, request=request)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                log_sensitive_operation(
                    request,
                    SensitiveOperationLog.Action.SEND_DELIVERY_REMINDER,
                    order=order,
                    note="商家发送站内查看提醒邮件。",
                    metadata={"recipient": recipient},
                )
                messages.success(request, f"已向 {recipient} 发送查看提醒，邮件中不再直接包含卡密。")
        else:
            messages.error(request, "未识别的订单操作。")

        return redirect(next_url)


class MerchantOrderDetailView(MerchantContextMixin, DetailView):
    template_name = "shop/merchant_order_detail.html"
    context_object_name = "order"
    slug_field = "order_no"
    slug_url_kwarg = "order_no"
    merchant_tab = "orders"

    def get_queryset(self):
        return (
            Order.objects.select_related("user")
            .prefetch_related("items__deliveries", "payment_attempts")
            .all()
        )
