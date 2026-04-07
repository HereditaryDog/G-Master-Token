from shop.models import SensitiveOperationLog
from shop.security import get_request_ip


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
