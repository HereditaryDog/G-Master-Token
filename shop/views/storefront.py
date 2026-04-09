from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from shop.deployment_checks import run_readiness_checks
from shop.forms import AccountOrderFilterForm, AddToCartForm, StorefrontSearchForm
from shop.models import HelpArticle, Order, Product, SiteAnnouncement
from shop.services.order_flow import create_single_item_order


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


class HealthView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"ok": True, "service": settings.SITE_NAME})


class ReadinessView(View):
    def get(self, request, *args, **kwargs):
        result = run_readiness_checks()
        status = 200 if result["ok"] else 503
        return JsonResponse(result, status=status)
