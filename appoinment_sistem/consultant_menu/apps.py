from django.apps import AppConfig


class ConsultantMenuConfig(AppConfig):
    name = "consultant_menu"

    def ready(self):
        import consultant_menu.signals  # noqa: F401
