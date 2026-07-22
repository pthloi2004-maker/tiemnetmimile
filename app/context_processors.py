from .models import Session, Queue, Machine


def netcafe_context(request):
    """
    Truyền thông tin tổng quan quán net vào tất cả template.
    Dùng trong TEMPLATES > OPTIONS > context_processors.
    """
    active_sessions = Session.objects.filter(status='dang_chay').count()
    waiting_queue   = Queue.objects.filter(is_served=False).count()
    available_machines = Machine.objects.filter(status='trong').count()

    return {
        'global_active_sessions':    active_sessions,
        'global_waiting_queue':      waiting_queue,
        'global_available_machines': available_machines,
    }