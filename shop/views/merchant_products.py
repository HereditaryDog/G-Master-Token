from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from shop.forms import MerchantProductFilterForm, ProductForm
from shop.models import Product
from shop.security import get_safe_next_url

from .merchant_base import MerchantContextMixin, MerchantRequiredMixin


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
                    models.Q(title__icontains=query)
                    | models.Q(slug__icontains=query)
                    | models.Q(summary__icontains=query)
                    | models.Q(provider_sku__icontains=query)
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
