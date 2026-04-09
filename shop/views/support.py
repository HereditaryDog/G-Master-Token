from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import DetailView, TemplateView

from shop.forms import SupportTicketCreateForm, SupportTicketReplyForm
from shop.models import SupportTicket, SupportTicketMessage
from shop.services.support import append_support_message


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
