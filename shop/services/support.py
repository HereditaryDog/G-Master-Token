from django.utils import timezone

from shop.models import SupportTicket, SupportTicketMessage


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
