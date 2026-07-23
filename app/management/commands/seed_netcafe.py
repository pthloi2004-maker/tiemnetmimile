import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from app.models import Machine, Service


class Command(BaseCommand):
    help = "Create the initial MiMi Le net-cafe machines and services safely."

    def handle(self, *args, **options):
        machines = [
            ("PC01", "thuong", 10000, True, False, 8, "May thuong - khu A"),
            ("PC02", "thuong", 10000, True, False, 8, "May thuong - khu A"),
            ("PC03", "thuong", 10000, True, True, 16, "May thuong - khu A"),
            ("PC04", "thuong", 10000, True, True, 16, "May thuong - khu A"),
            ("PC05", "gaming", 15000, True, True, 32, "May gaming - khu B"),
            ("PC06", "gaming", 15000, True, True, 32, "May gaming - khu B"),
            ("PC07", "gaming", 15000, True, True, 32, "May gaming - khu B"),
            ("PC08", "vip", 20000, True, True, 64, "Phong VIP - khu C"),
            ("PC09", "vip", 20000, True, True, 64, "Phong VIP - khu C"),
            ("PC10", "vip", 20000, True, True, 64, "Phong VIP - khu C"),
        ]
        created_machines = 0
        for name, machine_type, hourly_rate, headset, account, ram, note in machines:
            machine, created = Machine.objects.get_or_create(
                name=name,
                defaults={
                    "machine_type": machine_type,
                    "status": "trong",
                    "hourly_rate": hourly_rate,
                    "has_headset": headset,
                    "has_account": account,
                    "ram_gb": ram,
                    "note": note,
                },
            )
            if machine.image:
                # Machine thumbnails are shipped as static files so they work on Render.
                machine.image = ""
                machine.save(update_fields=["image"])
            created_machines += created

        services = [
            ("Mi ly", "do_an", 30000, 50),
            ("Nuoc suoi", "do_uong", 10000, 100),
            ("Sting", "do_uong", 15000, 80),
            ("Coca-Cola", "do_uong", 15000, 80),
            ("Snack", "do_an", 20000, 40),
            ("Xuc xich", "do_an", 15000, 40),
        ]
        created_services = 0
        for name, category, price, stock in services:
            _, created = Service.objects.get_or_create(
                name=name,
                defaults={"category": category, "price": price, "stock": stock, "available": True},
            )
            created_services += created

        username = os.environ.get("INITIAL_ADMIN_USERNAME")
        password = os.environ.get("INITIAL_ADMIN_PASSWORD")
        if username and password:
            user_model = get_user_model()
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"is_staff": True, "is_superuser": True},
            )
            if created:
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created admin user: {username}"))
            else:
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=["password", "is_staff", "is_superuser"])
                self.stdout.write(self.style.SUCCESS(f"Updated admin user: {username}"))

        self.stdout.write(self.style.SUCCESS(
            f"Net-cafe seed complete: {created_machines} machine(s), {created_services} service(s) created."
        ))
