from django.core.management.base import BaseCommand
from app.models import Service


class Command(BaseCommand):
    help = 'Seed default service items for quick interface testing.'

    def handle(self, *args, **options):
        defaults = [
            {'name': 'Mì', 'category': 'do_an', 'price': 30000, 'stock': 50, 'available': True},
            {'name': 'Nước', 'category': 'do_uong', 'price': 10000, 'stock': 100, 'available': True},
            {'name': 'Snack', 'category': 'do_an', 'price': 20000, 'stock': 40, 'available': True},
            {'name': 'Phụ kiện', 'category': 'phu_kien', 'price': 50000, 'stock': 20, 'available': True},
        ]
        created = 0
        for item in defaults:
            service, created_flag = Service.objects.get_or_create(
                name=item['name'],
                defaults=item,
            )
            if created_flag:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Created service: {service.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Service already exists: {service.name}"))
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} service(s)."))
