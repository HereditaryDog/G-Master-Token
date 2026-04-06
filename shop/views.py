from decimal import Decimal

from django.contrib import messages
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import (
    AccountOrderFilterForm,
    AddToCartForm,
    CardCodeBatchForm,
    GuestOrderLookupForm,
    MerchantInventoryFilterForm,
    MerchantOrderFilterForm,
    MerchantProductFilterForm,
    MerchantUserFilterForm,
    MerchantSupportTicketFilterForm,
    MerchantSupportTicketReplyForm,
    ProductForm,
    StorefrontSearchForm,
    SupportTicketCreateForm,
    SupportTicketReplyForm,
)
from .models import (
    CardCode,
    DeliveryRecord,
    HelpArticle,
    InventoryImportBatch,
    Order,
    Product,
    ProductCategory,
    SensitiveOperationLog,
    SiteAnnouncement,
    SupportTicket,
    SupportTicketMessage,
)
from .deployment_checks import run_readiness_checks
from .security import (
    build_guest_order_access_token,
    get_safe_next_url,
    get_request_ip,
    is_merchant_user,
    is_request_ip_allowed,
    load_guest_order_access_token,
    mask_secret,
)
from .services.order_flow import (
    create_single_item_order,
    mark_order_checkout_created,
    mark_order_paid,
    mark_order_payment_failed,
    retry_order_fulfillment,
)
from .services.payment import (
    create_checkout_session,
    get_default_gateway_code,
    list_active_payment_gateways,
    list_reserved_payment_gateways,
    PaymentGatewayError,
    PaymentGatewayUnavailable,
    verify_payment_callback,
)
from accounts.models import User
from accounts.rate_limits import consume_request


def collect_delivery_codes(order):
    return [delivery.reveal_display_code() for item in order.items.all() for delivery in item.deliveries.all()]


def is_paid_checkout_session_for_order(order, checkout_data, *, session_id=""):
    if not checkout_data or checkout_data.get("payment_status") != "paid":
        return False
    if session_id and checkout_data.get("id") and checkout_data["id"] != session_id:
        return False
    metadata = checkout_data.get("metadata") or {}
    return metadata.get("order_no") == order.order_no


def load_order_from_checkout_metadata(session_payload):
    metadata = session_payload.get("metadata") or {}
    order_no = metadata.get("order_no")
    order_id = metadata.get("order_id")
    if not order_no:
        return None
    queryset = Order.objects.filter(order_no=order_no)
    if order_id:
        queryset = queryset.filter(pk=order_id)
    return queryset.first()


def log_sensitive_operation(request, action, *, order=None, card_code=None, delivery_record=None, note="", metadata=None):
    SensitiveOperationLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        order=order,
        card_code=card_code,
        delivery_record=delivery_record,
        ip_address=get_request_ip(request),
        note=note,
        metadata=metadata or {},
    )


def send_delivery_reminder_email(order, request=None):
    recipient = order.contact_email or order.user.email
    if not recipient:
        raise ValueError("当前订单没有可用的收件邮箱。")
    if not collect_delivery_codes(order):
        raise ValueError("当前订单还没有可重发的发货内容。")

    if settings.SITE_BASE_URL:
        lookup_url = f"{settings.SITE_BASE_URL}/order-lookup/"
        account_url = f"{settings.SITE_BASE_URL}/me/"
    elif request is not None:
        lookup_url = request.build_absolute_uri("/order-lookup/")
        account_url = request.build_absolute_uri("/me/")
    else:
        lookup_url = "/order-lookup/"
        account_url = "/me/"

    content_lines = [
        f"订单号：{order.order_no}",
        f"用户：{order.user.username}",
        "",
        "为了降低卡密在邮件链路中泄露的风险，本站不会通过邮件直接重发完整发货内容。",
        "你可以使用以下方式重新查看：",
        f"1. 登录后进入账号中心：{account_url}",
        f"2. 或使用订单号 + 邮箱在查单页查看：{lookup_url}",
        "",
        "如果这不是你的操作，可以忽略这封邮件。",
        settings.SITE_NAME,
    ]
    send_mail(
        subject=f"{settings.SITE_NAME} 订单查看提醒 - {order.order_no}",
        message="\n".join(content_lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
    return recipient


def ticket_detail_url(ticket, request=None):
    path = reverse("shop:support_ticket_detail", args=[ticket.ticket_no])
    if settings.SITE_BASE_URL:
        return f"{settings.SITE_BASE_URL}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def send_support_ticket_notification(ticket, body, request=None):
    if not ticket.contact_email:
        return
    lines = [
        f"工单号：{ticket.ticket_no}",
        f"标题：{ticket.subject}",
        f"当前状态：{ticket.get_status_display()}",
        "",
        body,
        "",
        f"查看工单：{ticket_detail_url(ticket, request=request)}",
        settings.SITE_NAME,
    ]
    send_mail(
        subject=f"{settings.SITE_NAME} 工单更新 - {ticket.ticket_no}",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[ticket.contact_email],
        fail_silently=True,
    )


def append_support_message(ticket, *, sender=None, sender_role, body, status, assignee=None):
    normalized_body = (body or "").strip()
    if not normalized_body:
        return None
    message = SupportTicketMessage.objects.create(
        ticket=ticket,
        sender=sender,
        sender_role=sender_role,
        body=normalized_body,
    )
    ticket.status = status
    ticket.last_message_at = timezone.now()
    ticket.closed_at = timezone.now() if status == SupportTicket.Status.CLOSED else None
    if assignee is not None:
        ticket.merchant_assignee = assignee
    ticket.save(update_fields=["status", "last_message_at", "closed_at", "merchant_assignee", "updated_at"])
    return message


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
                    Q(title__icontains=keyword)
                    | Q(summary__icontains=keyword)
                    | Q(description__icontains=keyword)
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
            checkout_data = verify_payment_callback(order.payment_provider, session_id=session_id)
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
            .filter(Q(contact_email__iexact=email) | Q(user__email__iexact=email))
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
                    Q(order_no__icontains=query)
                    | Q(items__product_title__icontains=query)
                    | Q(payment_reference__icontains=query)
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


class MerchantDashboardView(MerchantContextMixin, TemplateView):
    template_name = "shop/merchant_dashboard.html"
    merchant_tab = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = Order.objects.prefetch_related("items", "user")
        products = Product.objects.select_related("category").filter(is_deleted=False)
        low_stock_products = [
            product
            for product in products
            if (
                product.delivery_method == Product.DeliveryMethod.STOCK_CARD
                and product.low_stock_threshold > 0
                and (product.inventory_count or 0) <= product.low_stock_threshold
            )
        ]
        context.update(
            {
                "recent_orders": orders[:8],
                "product_count": products.count(),
                "category_count": ProductCategory.objects.filter(is_active=True).count(),
                "article_count": HelpArticle.objects.filter(is_published=True).count(),
                "paid_order_count": orders.filter(payment_status=Order.PaymentStatus.PAID).count(),
                "pending_order_count": orders.filter(status=Order.Status.PENDING_PAYMENT).count(),
                "card_stock_count": CardCode.objects.filter(status=CardCode.Status.AVAILABLE).count(),
                "low_stock_products": low_stock_products,
                "pending_support_ticket_count": SupportTicket.objects.filter(status=SupportTicket.Status.PENDING_SUPPORT).count(),
            }
        )
        return context


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
        money_zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=10, decimal_places=2))
        return (
            self.get_customer_base_queryset()
            .annotate(
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
            .order_by("-date_joined", "-id")
        )

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
        money_zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=10, decimal_places=2))
        return User.objects.filter(is_staff=False, is_superuser=False, is_merchant=False).annotate(
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


class MerchantSupportTicketListView(MerchantContextMixin, ListView):
    template_name = "shop/merchant_support_tickets.html"
    context_object_name = "tickets"
    merchant_tab = "support"

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = MerchantSupportTicketFilterForm(self.request.GET or None)
        return self._filter_form

    def get_queryset(self):
        queryset = (
            SupportTicket.objects.select_related("user", "order", "merchant_assignee")
            .prefetch_related("messages")
            .order_by("-last_message_at")
        )
        form = self.get_filter_form()
        if form.is_valid():
            query = form.cleaned_data["query"]
            status = form.cleaned_data["status"]
            category = form.cleaned_data["category"]
            priority = form.cleaned_data["priority"]
            if query:
                queryset = queryset.filter(
                    Q(ticket_no__icontains=query)
                    | Q(subject__icontains=query)
                    | Q(contact_email__icontains=query)
                    | Q(user__username__icontains=query)
                    | Q(order__order_no__icontains=query)
                )
            if status:
                queryset = queryset.filter(status=status)
            if category:
                queryset = queryset.filter(category=category)
            if priority:
                queryset = queryset.filter(priority=priority)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.get_filter_form()
        tickets = SupportTicket.objects.all()
        context["ticket_stats"] = {
            "pending_support": tickets.filter(status=SupportTicket.Status.PENDING_SUPPORT).count(),
            "pending_user": tickets.filter(status=SupportTicket.Status.PENDING_USER).count(),
            "resolved": tickets.filter(status=SupportTicket.Status.RESOLVED).count(),
            "closed": tickets.filter(status=SupportTicket.Status.CLOSED).count(),
        }
        return context


class MerchantSupportTicketDetailView(MerchantContextMixin, DetailView):
    template_name = "shop/merchant_support_ticket_detail.html"
    context_object_name = "ticket"
    slug_field = "ticket_no"
    slug_url_kwarg = "ticket_no"
    merchant_tab = "support"

    def get_queryset(self):
        return (
            SupportTicket.objects.select_related("user", "order", "merchant_assignee")
            .prefetch_related("messages__sender")
            .all()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("reply_form") or MerchantSupportTicketReplyForm(initial={"status": self.object.status})
        context["reply_form"] = form
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = MerchantSupportTicketReplyForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(reply_form=form))

        status = form.cleaned_data["status"]
        body = form.cleaned_data["body"]
        if body.strip():
            append_support_message(
                self.object,
                sender=request.user,
                sender_role=SupportTicketMessage.SenderRole.SUPPORT,
                body=body,
                status=status,
                assignee=request.user,
            )
            send_support_ticket_notification(
                self.object,
                body=f"客服回复：\n{body.strip()}",
                request=request,
            )
        else:
            system_message = f"工单状态已更新为：{SupportTicket.Status(status).label}"
            append_support_message(
                self.object,
                sender=request.user,
                sender_role=SupportTicketMessage.SenderRole.SYSTEM,
                body=system_message,
                status=status,
                assignee=request.user,
            )
            send_support_ticket_notification(
                self.object,
                body=system_message,
                request=request,
            )
        messages.success(request, f"工单 {self.object.ticket_no} 已更新。")
        return redirect("shop:merchant_support_ticket_detail", ticket_no=self.object.ticket_no)


class MerchantProductListView(MerchantContextMixin, ListView):
    template_name = "shop/merchant_products.html"
    context_object_name = "products"
    merchant_tab = "products"

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = MerchantProductFilterForm(self.request.GET or None)
        return self._filter_form

    def get_queryset(self):
        queryset = Product.objects.select_related("category").filter(is_deleted=False).order_by("-is_active", "-is_featured", "price")
        form = self.get_filter_form()
        if form.is_valid():
            query = form.cleaned_data["query"]
            active = form.cleaned_data["active"]
            if query:
                queryset = queryset.filter(
                    Q(title__icontains=query)
                    | Q(slug__icontains=query)
                    | Q(summary__icontains=query)
                    | Q(provider_sku__icontains=query)
                )
            if active == "active":
                queryset = queryset.filter(is_active=True)
            elif active == "inactive":
                queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.get_filter_form()
        return context


class MerchantProductToggleStatusView(MerchantRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk, is_deleted=False)
        product.is_active = not product.is_active
        product.save(update_fields=["is_active", "updated_at"])
        state_label = "上架" if product.is_active else "下架"
        messages.success(request, f"{product.title} 已切换为{state_label}状态。")
        return redirect(get_safe_next_url(request, request.POST.get("next"), reverse("shop:merchant_products")))


class MerchantProductBatchActionView(MerchantRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        next_url = get_safe_next_url(request, request.POST.get("next"), reverse("shop:merchant_products"))
        selected_ids = []
        for raw_id in request.POST.getlist("product_ids"):
            try:
                selected_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue

        if not selected_ids:
            messages.error(request, "请先选择至少一个商品。")
            return redirect(next_url)

        products = list(Product.objects.filter(pk__in=selected_ids).order_by("id"))
        if not products:
            messages.error(request, "未找到可操作的商品。")
            return redirect(next_url)

        action = request.POST.get("action", "").strip()
        product_ids = [product.id for product in products]

        if action == "activate":
            updated_count = Product.objects.filter(pk__in=product_ids).exclude(is_active=True).update(is_active=True)
            messages.success(request, f"已批量上架 {updated_count} 个商品。")
            return redirect(next_url)

        if action == "deactivate":
            updated_count = Product.objects.filter(pk__in=product_ids).exclude(is_active=False).update(is_active=False)
            messages.success(request, f"已批量下架 {updated_count} 个商品。")
            return redirect(next_url)

        if action == "delete":
            deleted_count = Product.objects.filter(pk__in=product_ids, is_deleted=False).update(
                is_deleted=True,
                is_active=False,
                is_featured=False,
            )
            messages.success(request, f"已删除 {deleted_count} 个商品。历史订单仍会保留，但商品已从后台列表和前台隐藏。")
            return redirect(next_url)

        messages.error(request, "不支持的批量操作。")
        return redirect(next_url)


class MerchantProductCreateView(MerchantContextMixin, CreateView):
    template_name = "shop/merchant_product_form.html"
    form_class = ProductForm
    success_url = reverse_lazy("shop:merchant_products")
    merchant_tab = "products"

    def form_valid(self, form):
        messages.success(self.request, "商品已创建。")
        return super().form_valid(form)


class MerchantProductUpdateView(MerchantContextMixin, UpdateView):
    template_name = "shop/merchant_product_form.html"
    form_class = ProductForm
    model = Product
    success_url = reverse_lazy("shop:merchant_products")
    merchant_tab = "products"

    def get_queryset(self):
        return Product.objects.filter(is_deleted=False)

    def form_valid(self, form):
        messages.success(self.request, "商品已更新。")
        return super().form_valid(form)


class MerchantInventoryView(MerchantContextMixin, FormView):
    template_name = "shop/merchant_inventory.html"
    form_class = CardCodeBatchForm
    success_url = reverse_lazy("shop:merchant_inventory")
    merchant_tab = "inventory"

    def get_import_preview(self):
        return getattr(self, "import_preview", None)

    def get_initial(self):
        initial = super().get_initial()
        product_id = self.request.GET.get("product", "").strip()
        if product_id.isdigit():
            initial["product"] = product_id
        return initial

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = MerchantInventoryFilterForm(self.request.GET or None)
        return self._filter_form

    def get_inventory_queryset(self):
        queryset = CardCode.objects.select_related("product").filter(
            product__is_deleted=False,
            product__delivery_method=Product.DeliveryMethod.STOCK_CARD,
        )
        form = self.get_filter_form()
        if form.is_valid():
            product = form.cleaned_data["product"]
            status = form.cleaned_data["status"]
            query = form.cleaned_data["query"]
            if product:
                queryset = queryset.filter(product=product)
            if status:
                queryset = queryset.filter(status=status)
            if query:
                queryset = queryset.filter(
                    Q(product__title__icontains=query)
                    | Q(product__slug__icontains=query)
                    | Q(note__icontains=query)
                )
        return queryset.order_by("-created_at")

    def get_inventory_products(self):
        return Product.objects.filter(
            is_deleted=False,
            delivery_method=Product.DeliveryMethod.STOCK_CARD,
        ).annotate(
            available_count=Count("card_codes", filter=Q(card_codes__status=CardCode.Status.AVAILABLE), distinct=True),
            sold_count=Count("card_codes", filter=Q(card_codes__status=CardCode.Status.SOLD), distinct=True),
            total_count=Count("card_codes", distinct=True),
        ).order_by("-available_count", "title")

    def get_page_obj(self, inventory_queryset):
        paginator = Paginator(inventory_queryset, 50)
        return paginator.get_page(self.request.GET.get("page") or 1)

    def form_valid(self, form):
        product = form.cleaned_data["product"]
        note = form.cleaned_data["note"]
        preview = form.build_preview()
        self.import_preview = preview
        intent = self.request.POST.get("intent", "import")
        if intent == "preview":
            messages.info(self.request, "已生成导入预览，请确认后再执行导入。")
            return self.render_to_response(self.get_context_data(form=form))

        codes = preview["importable_codes"]
        if not codes:
            form.add_error("codes", "没有可导入的新卡密，重复内容已在预览中列出。")
            return self.render_to_response(self.get_context_data(form=form))
        cards = []
        for code in codes:
            card = CardCode(product=product, note=note)
            card.set_plaintext_code(code)
            cards.append(card)
        CardCode.objects.bulk_create(cards, batch_size=100)
        duplicate_sample = "\n".join(mask_secret(code) for code in preview["duplicate_samples"])
        InventoryImportBatch.objects.create(
            product=product,
            operator=self.request.user,
            note=note,
            total_submitted=preview["total_submitted"],
            imported_count=preview["importable_count"],
            duplicate_count=preview["duplicate_count"],
            duplicate_sample=duplicate_sample,
        )
        if preview["duplicate_count"]:
            messages.warning(
                self.request,
                f"已导入 {len(codes)} 条新卡密，忽略 {preview['duplicate_count']} 条重复内容。",
            )
        else:
            messages.success(self.request, f"已导入 {len(codes)} 条卡密到 {product.title}。")
        return redirect(f"{self.success_url}?product={product.id}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inventory_queryset = self.get_inventory_queryset()
        page_obj = self.get_page_obj(inventory_queryset)
        filter_form = self.get_filter_form()
        selected_product = None
        if filter_form.is_valid():
            selected_product = filter_form.cleaned_data["product"]
        inventory_products = self.get_inventory_products()
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["card_codes"] = page_obj.object_list
        context["products"] = inventory_products
        context["filter_form"] = filter_form
        context["current_product_id"] = str(selected_product.id) if selected_product else ""
        context["import_preview"] = self.get_import_preview()
        import_history = InventoryImportBatch.objects.select_related("product", "operator")
        if selected_product:
            import_history = import_history.filter(product=selected_product)
        context["import_history"] = import_history[:12]
        context["inventory_metrics"] = {
            "product_count": inventory_products.count(),
            "available_count": CardCode.objects.filter(
                product__is_deleted=False,
                product__delivery_method=Product.DeliveryMethod.STOCK_CARD,
                status=CardCode.Status.AVAILABLE,
            ).count(),
            "sold_count": CardCode.objects.filter(
                product__is_deleted=False,
                product__delivery_method=Product.DeliveryMethod.STOCK_CARD,
                status=CardCode.Status.SOLD,
            ).count(),
            "filtered_count": inventory_queryset.count(),
        }
        context["page_obj"] = page_obj
        context["is_paginated"] = page_obj.paginator.num_pages > 1
        context["pagination_query"] = query_params.urlencode()
        return context


class MerchantInventoryCodeRevealView(MerchantRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        card = get_object_or_404(CardCode.objects.select_related("product"), pk=pk)
        plaintext = card.reveal_code()
        log_sensitive_operation(
            request,
            SensitiveOperationLog.Action.REVEAL_CARD_CODE,
            card_code=card,
            note="商家在库存列表中查看卡密。",
            metadata={"product_id": card.product_id},
        )
        return JsonResponse({"ok": True, "code": plaintext, "masked_code": card.masked_code})


class MerchantInventoryBatchActionView(MerchantRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        next_url = get_safe_next_url(request, request.POST.get("next"), reverse("shop:merchant_inventory"))
        selected_ids = []
        for raw_id in request.POST.getlist("card_code_ids"):
            try:
                selected_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue

        if not selected_ids:
            messages.error(request, "请先选择至少一条卡密。")
            return redirect(next_url)

        action = request.POST.get("action", "").strip()
        queryset = CardCode.objects.select_related("product").filter(
            pk__in=selected_ids,
            product__is_deleted=False,
            product__delivery_method=Product.DeliveryMethod.STOCK_CARD,
        )
        if not queryset.exists():
            messages.error(request, "未找到可操作的卡密记录。")
            return redirect(next_url)

        if action == "delete":
            deletable_queryset = queryset.filter(status=CardCode.Status.AVAILABLE)
            deleted_count = deletable_queryset.count()
            skipped_count = queryset.count() - deleted_count
            deletable_queryset.delete()
            if deleted_count:
                messages.success(request, f"已删除 {deleted_count} 条可售卡密。")
            if skipped_count:
                messages.warning(request, f"有 {skipped_count} 条卡密已售出，未执行删除。")
            return redirect(next_url)

        messages.error(request, "不支持的库存操作。")
        return redirect(next_url)


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
                    Q(order_no__icontains=query)
                    | Q(user__username__icontains=query)
                    | Q(user__email__icontains=query)
                    | Q(contact_email__icontains=query)
                    | Q(payment_reference__icontains=query)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
        checkout_data = verify_payment_callback(
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
