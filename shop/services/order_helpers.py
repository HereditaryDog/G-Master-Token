from shop.models import Order


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
