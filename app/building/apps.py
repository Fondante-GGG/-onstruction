from django.apps import AppConfig


class BuildingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app.building"
    verbose_name = "Строительство (объекты, ЖК)"

    def ready(self):
        from django.db.models.signals import post_save

        from .models import BuildingCashFlow
        from .salary_cash import on_cashflow_approved

        def _on_cashflow_save(sender, instance, **kwargs):
            if instance.status == BuildingCashFlow.Status.APPROVED and getattr(instance, "source_business_operation_id", None):
                on_cashflow_approved(instance)

        post_save.connect(_on_cashflow_save, sender=BuildingCashFlow)
