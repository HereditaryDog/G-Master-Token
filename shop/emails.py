from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .services.order_helpers import collect_delivery_codes


def _build_absolute_url(path, request=None):
    if settings.SITE_BASE_URL:
        return f"{settings.SITE_BASE_URL}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def send_delivery_reminder_email(order, request=None):
    recipient = order.contact_email or order.user.email
    if not recipient:
        raise ValueError("当前订单没有可用的收件邮箱。")
    if not collect_delivery_codes(order):
        raise ValueError("当前订单还没有可重发的发货内容。")

    lookup_url = _build_absolute_url("/order-lookup/", request=request)
    account_url = _build_absolute_url("/me/", request=request)
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
    return _build_absolute_url(reverse("shop:support_ticket_detail", args=[ticket.ticket_no]), request=request)


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
