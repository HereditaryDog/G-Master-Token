from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import FormView

from shop.forms import CardCodeBatchForm, MerchantInventoryFilterForm
from shop.models import CardCode, InventoryImportBatch, Product, SensitiveOperationLog
from shop.security import get_safe_next_url, mask_secret
from shop.services.audit import log_sensitive_operation

from .merchant_base import MerchantContextMixin, MerchantRequiredMixin


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
