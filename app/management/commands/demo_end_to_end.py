from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum
from app.models import Queue, Machine, Session, Service, SessionService


class Command(BaseCommand):
    help = 'Run a demo end-to-end scenario: queue -> checkin -> order -> checkout.'

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.order_by('id').first()
        if not user:
            self.stdout.write(self.style.ERROR('No user found in database. Create a staff account first.'))
            return

        service = Service.objects.filter(available=True).first()
        if not service:
            service = Service.objects.create(
                name='Mì', category='do_an', price=30000, stock=50, available=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created default service: {service.name}'))

        machine = Machine.objects.filter(status='trong').order_by('name').first()
        if not machine:
            self.stdout.write(self.style.ERROR('No available machine to allocate.'))
            return

        queue = Queue.objects.create(
            customer_name='Demo Khách',
            phone='0123456789',
            preferred_type=machine.machine_type,
            planned_minutes=60,
        )
        self.stdout.write(self.style.SUCCESS(f'Queue created: {queue.customer_name} prefers {queue.preferred_type}'))

        # Serve queue and create session automatically
        machine_alloc = Machine.objects.filter(status='trong', machine_type=queue.preferred_type).order_by('name').first()
        if not machine_alloc:
            machine_alloc = Machine.objects.filter(status='trong').order_by('name').first()

        session = Session.objects.create(
            user=user,
            customer_name=queue.customer_name,
            machine=machine_alloc,
            game_name='Demo Game',
            planned_minutes=queue.planned_minutes,
            used_headset=False,
            used_account=False,
            used_ram_gb=0,
            status='dang_chay',
        )
        queue.is_served = True
        queue.save()

        machine_alloc.status = 'dang_dung'
        machine_alloc.save()

        self.stdout.write(self.style.SUCCESS(f'Session started on {machine_alloc.name} for {session.get_customer_name()}'))

        order = SessionService.objects.create(
            session=session,
            service=service,
            quantity=1,
            price=service.price,
        )
        self.stdout.write(self.style.SUCCESS(f'Ordered service: {order.service.name} x{order.quantity}'))

        session.end_time = timezone.now()
        session.total_cost = session.calculate_cost() + session.get_service_cost()
        session.status = 'hoan_thanh'
        session.paid = True
        session.save()

        machine_alloc.status = 'trong'
        machine_alloc.save()

        self.stdout.write(self.style.SUCCESS(f'Checkout complete: total_cost={int(session.total_cost)}'))
        paid_revenue = Session.objects.filter(start_time__date=timezone.now().date(), paid=True).aggregate(total=Sum('total_cost'))['total'] or 0
        self.stdout.write(self.style.SUCCESS(f'Today paid revenue: {int(paid_revenue)}'))
