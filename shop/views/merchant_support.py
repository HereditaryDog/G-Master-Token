from django.contrib import messages
from django.db import models
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView

from shop.emails import send_support_ticket_notification
from shop.forms import MerchantSupportTicketFilterForm, MerchantSupportTicketReplyForm
from shop.models import SupportTicket, SupportTicketMessage
from shop.services.support import append_support_message

from .merchant_base import MerchantContextMixin


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
                    models.Q(ticket_no__icontains=query)
                    | models.Q(subject__icontains=query)
                    | models.Q(contact_email__icontains=query)
                    | models.Q(user__username__icontains=query)
                    | models.Q(order__order_no__icontains=query)
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
