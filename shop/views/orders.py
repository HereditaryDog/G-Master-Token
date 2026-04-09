from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, FormView

from accounts.rate_limits import consume_request
from shop.forms import GuestOrderLookupForm
from shop.models import DeliveryRecord, Order, SensitiveOperationLog
from shop.security import (
    build_guest_order_access_token,
    get_request_ip,
    is_merchant_user,
    is_request_ip_allowed,
    load_guest_order_access_token,
)
from shop.services.audit import log_sensitive_operation
from shop.services.order_flow import create_single_item_order


class OrderDetailView(LoginRequiredMixin, DetailView):
    template_name = "shop/order_detail.html"
    context_object_name = "order"
    slug_field = "order_no"
    slug_url_kwarg = "order_no"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items__deliveries")


class GuestOrderLookupView(FormView):
    template_name = "shop/order_lookup.html"
    form_class = GuestOrderLookupForm
    success_url = reverse_lazy("shop:order_lookup")
    not_found_message = "查询条件不匹配，请检查后重试。"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = kwargs.get("order")
        context["guest_access_token"] = kwargs.get("guest_access_token", "")
        return context

    def form_valid(self, form):
        ip_decision = consume_request("order_lookup_ip", get_request_ip(self.request))
        if ip_decision.blocked:
            form.add_error(None, ip_decision.message)
            return self.form_invalid(form)

        order_no = form.cleaned_data["order_no"].strip()
        email = form.cleaned_data["email"].strip().lower()
        order = (
            Order.objects.select_related("user")
            .prefetch_related("items__deliveries")
            .filter(order_no=order_no)
            .filter(models.Q(contact_email__iexact=email) | models.Q(user__email__iexact=email))
            .first()
        )
        if not order:
            form.add_error(None, self.not_found_message)
            return self.form_invalid(form)
        access_token = build_guest_order_access_token(order, email)
        return self.render_to_response(self.get_context_data(form=form, order=order, guest_access_token=access_token))


class DeliveryRecordRevealView(View):
    def post(self, request, order_no, delivery_id, *args, **kwargs):
        delivery = get_object_or_404(
            DeliveryRecord.objects.select_related("order_item__order", "order_item__order__user"),
            pk=delivery_id,
            order_item__order__order_no=order_no,
        )
        order = delivery.order_item.order

        if request.user.is_authenticated:
            user = request.user
            if not (user == order.user or is_merchant_user(user)):
                return JsonResponse({"ok": False, "message": "无权查看该发货内容。"}, status=403)
            if is_merchant_user(user) and not is_request_ip_allowed(request, settings.MERCHANT_ALLOWED_IPS):
                return JsonResponse({"ok": False, "message": "当前 IP 无权查看该发货内容。"}, status=403)
            access_type = "merchant" if is_merchant_user(user) else "user"
        else:
            token = request.POST.get("access_token", "").strip()
            if not token:
                return JsonResponse({"ok": False, "message": "缺少访客访问令牌。"}, status=403)
            try:
                payload = load_guest_order_access_token(token)
            except signing.BadSignature:
                return JsonResponse({"ok": False, "message": "访问令牌无效或已过期。"}, status=403)
            if payload.get("order_id") != order.id:
                return JsonResponse({"ok": False, "message": "访问令牌无效。"}, status=403)
            expected_emails = {value.lower() for value in (order.contact_email, order.user.email) if value}
            if payload.get("email", "").lower() not in expected_emails:
                return JsonResponse({"ok": False, "message": "访问令牌无效。"}, status=403)
            access_type = "guest"

        plaintext = delivery.reveal_display_code()
        log_sensitive_operation(
            request,
            SensitiveOperationLog.Action.REVEAL_DELIVERY_CODE,
            order=order,
            delivery_record=delivery,
            note="查看订单发货内容。",
            metadata={"access_type": access_type},
        )
        return JsonResponse({"ok": True, "code": plaintext, "masked_code": delivery.masked_display_code})


class ReorderView(LoginRequiredMixin, View):
    def post(self, request, order_no, *args, **kwargs):
        order = get_object_or_404(
            Order.objects.prefetch_related("items__product"),
            order_no=order_no,
            user=request.user,
        )
        first_item = order.items.select_related("product").first()
        if not first_item or not first_item.product:
            messages.error(request, "原订单没有可复购的商品。")
            return redirect("shop:account_center")
        if not first_item.product.is_active:
            messages.error(request, "该商品当前已下架，暂时无法再次购买。")
            return redirect("shop:order_detail", order_no=order.order_no)

        new_order = create_single_item_order(request.user, first_item.product, first_item.quantity)
        messages.success(request, f"已根据历史订单创建新订单 {new_order.order_no}。")
        return redirect("shop:checkout", order_no=new_order.order_no)
