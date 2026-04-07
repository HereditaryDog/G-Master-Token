from django.views.generic import TemplateView

from shop.models import CardCode, HelpArticle, Order, Product, ProductCategory, SupportTicket

from .merchant_base import MerchantContextMixin


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
