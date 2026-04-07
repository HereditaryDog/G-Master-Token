import shop.views as package_views

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.db import models
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, TemplateView

from accounts.rate_limits import consume_request
from shop.deployment_checks import run_readiness_checks
from shop.forms import (
    AccountOrderFilterForm,
    AddToCartForm,
    GuestOrderLookupForm,
    StorefrontSearchForm,
    SupportTicketCreateForm,
    SupportTicketReplyForm,
)
from shop.models import (
    DeliveryRecord,
    HelpArticle,
    Order,
    Product,
    SensitiveOperationLog,
    SiteAnnouncement,
    SupportTicket,
    SupportTicketMessage,
)
from shop.security import (
    build_guest_order_access_token,
    get_request_ip,
    is_merchant_user,
    is_request_ip_allowed,
    load_guest_order_access_token,
)
from shop.services.audit import log_sensitive_operation
from shop.services.order_flow import (
    create_single_item_order,
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
from shop.services.support import append_support_message


class StorefrontView(ListView):
    template_name = "shop/storefront.html"
    context_object_name = "products"

    def get_search_form(self):
        if not hasattr(self, "_search_form"):
            self._search_form = StorefrontSearchForm(self.request.GET or None)
        return self._search_form

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True, is_deleted=False).select_related("category")
        form = self.get_search_form()
        if form.is_valid():
            keyword = form.cleaned_data["q"]
            if keyword:
                queryset = queryset.filter(
                    models.Q(title__icontains=keyword)
                    | models.Q(summary__icontains=keyword)
                    | models.Q(description__icontains=keyword)
                )
        return queryset.order_by("-is_featured", "price")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["announcements"] = SiteAnnouncement.objects.filter(is_active=True)[:5]
        context["search_form"] = self.get_search_form()
        return context


class ProductDetailView(DetailView):
    template_name = "shop/product_detail.html"
    model = Product
    context_object_name = "product"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Product.objects.filter(is_active=True, is_deleted=False).select_related("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = AddToCartForm()
        related_queryset = Product.objects.filter(is_active=True, is_deleted=False).exclude(pk=self.object.pk)
        if self.object.category_id:
            related_queryset = related_queryset.filter(category_id=self.object.category_id)
        context["related_products"] = related_queryset.select_related("category")[:3]
        return context


class CreateOrderView(LoginRequiredMixin, View):
    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_active=True, is_deleted=False)
        form = AddToCartForm(request.POST)
        if not form.is_valid():
            messages.error(request, "购买数量不合法，请重新提交。")
            return redirect("shop:product_detail", slug=slug)

        order = create_single_item_order(request.user, product, form.cleaned_data["quantity"])
        messages.success(request, f"订单 {order.order_no} 已创建，请继续支付。")
        return redirect("shop:checkout", order_no=order.order_no)


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


class SupportView(TemplateView):
    template_name = "shop/support.html"

    def get_form(self):
        if self.request.user.is_authenticated:
            return SupportTicketCreateForm(user=self.request.user)
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ticket_form"] = kwargs.get("ticket_form") or self.get_form()
        context["recent_tickets"] = []
        if self.request.user.is_authenticated:
            context["recent_tickets"] = (
                self.request.user.support_tickets.select_related("order")
                .prefetch_related("messages")
                .order_by("-last_message_at")[:8]
            )
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        form = SupportTicketCreateForm(request.POST, user=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(ticket_form=form))

        ticket = SupportTicket.objects.create(
            user=request.user,
            order=form.cleaned_data["order"],
            contact_email=form.cleaned_data["contact_email"],
            category=form.cleaned_data["category"],
            priority=form.cleaned_data["priority"],
            subject=form.cleaned_data["subject"],
            status=SupportTicket.Status.PENDING_SUPPORT,
        )
        append_support_message(
            ticket,
            sender=request.user,
            sender_role=SupportTicketMessage.SenderRole.USER,
            body=form.cleaned_data["body"],
            status=SupportTicket.Status.PENDING_SUPPORT,
        )
        messages.success(request, f"工单 {ticket.ticket_no} 已提交，客服会尽快处理。")
        return redirect("shop:support_ticket_detail", ticket_no=ticket.ticket_no)


class SupportTicketDetailView(LoginRequiredMixin, DetailView):
    template_name = "shop/support_ticket_detail.html"
    context_object_name = "ticket"
    slug_field = "ticket_no"
    slug_url_kwarg = "ticket_no"

    def get_queryset(self):
        return (
            SupportTicket.objects.select_related("order", "merchant_assignee")
            .prefetch_related("messages__sender")
            .filter(user=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reply_form"] = kwargs.get("reply_form") or SupportTicketReplyForm()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status == SupportTicket.Status.CLOSED:
            messages.error(request, "该工单已关闭，无法继续回复。")
            return redirect("shop:support_ticket_detail", ticket_no=self.object.ticket_no)
        form = SupportTicketReplyForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(reply_form=form))
        append_support_message(
            self.object,
            sender=request.user,
            sender_role=SupportTicketMessage.SenderRole.USER,
            body=form.cleaned_data["body"],
            status=SupportTicket.Status.PENDING_SUPPORT,
        )
        messages.success(request, "你的补充说明已提交给客服。")
        return redirect("shop:support_ticket_detail", ticket_no=self.object.ticket_no)


class AnnouncementDetailView(DetailView):
    template_name = "shop/announcement_detail.html"
    model = SiteAnnouncement
    context_object_name = "announcement"

    def get_queryset(self):
        return SiteAnnouncement.objects.filter(is_active=True)


class HelpCenterView(ListView):
    template_name = "shop/help_center.html"
    context_object_name = "articles"

    def get_queryset(self):
        queryset = HelpArticle.objects.filter(is_published=True)
        section = self.request.GET.get("section", "").strip()
        valid_sections = {choice[0] for choice in HelpArticle.Section.choices}
        if section in valid_sections:
            queryset = queryset.filter(section=section)
        return queryset.order_by("section", "sort_order", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section_choices"] = HelpArticle.Section.choices
        context["current_section"] = self.request.GET.get("section", "").strip()
        context["featured_articles"] = HelpArticle.objects.filter(is_published=True, is_featured=True)[:5]
        return context


class HelpArticleDetailView(DetailView):
    template_name = "shop/help_article_detail.html"
    model = HelpArticle
    context_object_name = "article"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return HelpArticle.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related_articles"] = (
            HelpArticle.objects.filter(is_published=True, section=self.object.section)
            .exclude(pk=self.object.pk)
            .order_by("sort_order", "-created_at")[:6]
        )
        return context


class AccountCenterView(LoginRequiredMixin, TemplateView):
    template_name = "shop/account_center.html"

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = AccountOrderFilterForm(self.request.GET or None)
        return self._filter_form

    def get_filtered_orders(self):
        queryset = (
            self.request.user.orders.select_related("user")
            .prefetch_related("items__product", "items__deliveries")
            .order_by("-created_at")
        )
        form = self.get_filter_form()
        if form.is_valid():
            query = form.cleaned_data["q"]
            status = form.cleaned_data["status"]
            payment_status = form.cleaned_data["payment_status"]
            date_from = form.cleaned_data["date_from"]
            date_to = form.cleaned_data["date_to"]
            if query:
                queryset = queryset.filter(
                    models.Q(order_no__icontains=query)
                    | models.Q(items__product_title__icontains=query)
                    | models.Q(payment_reference__icontains=query)
                ).distinct()
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
        context["orders"] = self.get_filtered_orders()
        context["recent_support_tickets"] = self.request.user.support_tickets.order_by("-last_message_at")[:5]
        context["filter_form"] = self.get_filter_form()
        return context


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


class HealthView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"ok": True, "service": settings.SITE_NAME})


class ReadinessView(View):
    def get(self, request, *args, **kwargs):
        result = run_readiness_checks()
        status = 200 if result["ok"] else 503
        return JsonResponse(result, status=status)
