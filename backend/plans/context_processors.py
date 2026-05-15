"""Template context processors for the credits app."""

from .services import get_or_create_balance, is_admin_role


def credits_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    try:
        balance = get_or_create_balance(user)
    except Exception:
        return {"is_admin_role": False}
    return {
        "credit_balance": balance,
        "is_admin_role": is_admin_role(user),
    }
