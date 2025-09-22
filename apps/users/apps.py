from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"   # ← full path of the package
    label = "users"       # internal label (optional, but useful)
