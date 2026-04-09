import shop.views as package_views

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, TemplateView

from shop.models import Order
from shop.services.order_flow import (
    mark_order_checkout_created,
    mark_order_paid,
    mark_order_payment_failed,
)
from shop.services.order_helpers import is_paid_checkout_session_for_order, load_order_from_checkout_metadata
from shop.services.payment import (
    PaymentGatewayError,
    PaymentGatewayUnavailable,
    create_checkout_session,
    get_default_gateway_code,
    list_active_payment_gateways,
    list_reserved_payment_gateways,
)


class CheckoutView(LoginRequiredMixin, DetailView):
    template_name = "shop/checkout.html"
    context_object_name = "order"
    slug_field = "order_no"
    slug_url_kwarg = "order_no"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items__deliveries")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payment_gateways"] = list_active_payment_gateways()
        context["reserved_payment_gateways"] = list_reserved_payment_gateways()
        context["default_payment_gateway"] = get_default_gateway_code()
        return context


class StartPaymentView(LoginRequiredMixin, View):
    def post(self, request, order_no):
        order = get_object_or_404(Order, order_no=order_no, user=request.user)
        if order.payment_status == Order.PaymentStatus.PAID:
            messages.info(request, "该订单已经支付完成。")
            return redirect("shop:order_detail", order_no=order.order_no)

        provider_code = request.POST.get("provider", "").strip()
        try:
            session = create_checkout_session(order, request, provider_code=provider_code)
        except PaymentGatewayUnavailable:
            messages.error(request, "当前选择的支付通道尚未启用，请更换其它支付方式。")
            return redirect("shop:checkout", order_no=order.order_no)
        except PaymentGatewayError as exc:
            messages.error(request, str(exc))
            return redirect("shop:checkout", order_no=order.order_no)
        order = mark_order_checkout_created(
            order,
            provider=session.provider,
            reference=session.reference,
            checkout_url=session.redirect_url,
            payload=session.raw_payload,
        )
        return redirect(session.redirect_url)


class MockPaymentView(LoginRequiredMixin, TemplateView):
    template_name = "shop/mock_pay.html"

    def dispatch(self, request, *args, **kwargs):
        if not settings.PAYMENT_ENABLE_MOCK_GATEWAY:
            raise Http404("mock payment is disabled")
        return super().dispatch(request, *args, **kwargs)

    def get_order(self):
        if not hasattr(self, "_order"):
            self._order = get_object_or_404(Order, order_no=self.kwargs["order_no"], user=self.request.user)
        return self._order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = self.get_order()
        return context

    def post(self, request, *args, **kwargs):
        order = self.get_order()
        if order.payment_status != Order.PaymentStatus.PAID:
            order = mark_order_paid(
                order,
                provider="mock",
                reference=f"mock-{order.order_no}",
                payload={"mode": "local-demo"},
            )
            if order.status == Order.Status.FAILED:
                messages.warning(request, "模拟支付已确认，但自动发货失败，请联系商家处理。")
            else:
                messages.success(request, "模拟支付成功，订单已经自动发货。")
        return redirect("shop:order_detail", order_no=order.order_no)


class PaymentSuccessView(LoginRequiredMixin, TemplateView):
    template_name = "shop/payment_result.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = get_object_or_404(Order, order_no=kwargs["order_no"], user=self.request.user)
        session_id = self.request.GET.get("session_id", "")
        if order.payment_status != Order.PaymentStatus.PAID and session_id:
            checkout_data = package_views.verify_payment_callback(order.payment_provider, session_id=session_id)
            if is_paid_checkout_session_for_order(order, checkout_data, session_id=session_id):
                order = mark_order_paid(order, provider=order.payment_provider, reference=session_id, payload=checkout_data)
        context["order"] = order
        context["result_title"] = "支付结果"
        if order.payment_status == Order.PaymentStatus.PAID and order.status == Order.Status.FAILED:
            context["result_message"] = "支付已经确认，但自动发货失败，商家会尽快处理。"
        else:
            context["result_message"] = "如果订单已经付款，系统会在几秒内完成自动发货。"
        return context


class PaymentCancelView(LoginRequiredMixin, TemplateView):
    template_name = "shop/payment_result.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = get_object_or_404(Order, order_no=kwargs["order_no"], user=self.request.user)
        context["result_title"] = "支付已取消"
        context["result_message"] = "订单仍然保留，你可以稍后继续支付。"
        return context


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    def post(self, request, *args, **kwargs):
        payload = request.body
        signature = request.headers.get("Stripe-Signature", "")
        checkout_data = package_views.verify_payment_callback(
            "stripe",
            signature_payload=payload,
            signature=signature,
            from_webhook=True,
        )
        if not checkout_data:
            return HttpResponseBadRequest("invalid payload")

        if checkout_data.get("type") in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            session = checkout_data["data"]["object"]
            order = load_order_from_checkout_metadata(session)
            if order and is_paid_checkout_session_for_order(order, session, session_id=session.get("id", "")):
                mark_order_paid(order, provider="stripe", reference=session["id"], payload=session)
        elif checkout_data.get("type") in {"checkout.session.async_payment_failed", "checkout.session.expired"}:
            session = checkout_data["data"]["object"]
            order = load_order_from_checkout_metadata(session)
            if order and order.payment_status != Order.PaymentStatus.PAID:
                mark_order_payment_failed(order, provider="stripe", reference=session.get("id", ""), payload=session)
        return HttpResponse(status=200)
