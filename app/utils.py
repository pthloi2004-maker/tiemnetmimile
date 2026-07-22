from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages


def user_has_role(user, roles):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    user_groups = set(g.name for g in user.groups.all())
    return any(r in user_groups for r in roles)


def role_required(roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if user_has_role(request.user, roles):
                return view_func(request, *args, **kwargs)
            messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
            return redirect('app:dashboard')
        return _wrapped
    return decorator
