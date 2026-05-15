"""User-facing credit views.

The admin-side management (plans, user balances, transactions) lives in
the Django admin (themed with django-unfold), not here.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import render

from .models import CreditTransaction
from .services import get_or_create_balance


@login_required
def my_credits(request):
    balance = get_or_create_balance(request.user)
    tx_qs = CreditTransaction.objects.filter(user=request.user).order_by("-created_at")

    paginator = Paginator(tx_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    qs_params = params.urlencode()

    # Per-kind breakdown for the current cycle
    breakdown = (
        CreditTransaction.objects.filter(
            user=request.user,
            created_at__gte=balance.last_reset_at,
            amount__lt=0,
        )
        .values("kind")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("kind")
    )

    return render(
        request,
        "plans/my_credits.html",
        {
            "balance": balance,
            "transactions": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "breakdown": breakdown,
        },
    )
