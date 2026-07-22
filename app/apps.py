from django.apps import AppConfig


class AppConfig(AppConfig):
    name = 'app'
    verbose_name = 'Quán Net Mimi Lê'

    def ready(self):
        # Create default groups/roles if they do not exist
        from django.db.models.signals import post_migrate
        from django.contrib.auth.models import Group

        def create_default_groups(sender, **kwargs):
            role_names = ['owner', 'staff', 'tech', 'customer']
            for role in role_names:
                Group.objects.get_or_create(name=role)

        post_migrate.connect(create_default_groups, sender=self)
