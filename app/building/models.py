import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from django.db.models import Q
from django.core.exceptions import ValidationError

from mptt.models import MPTTModel, TreeForeignKey


class RemoteReference(str):
    """String UUID with a tiny object-like surface for legacy `.id` usage."""

    def __new__(cls, value, name=None):
        obj = str.__new__(cls, str(value))
        obj.id = value
        obj.name = name or str(value)
        return obj


def _reference_id(value):
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value.get("id") or value.get("uuid") or value.get("pk")
    return getattr(value, "id", value)


class RemoteCompanyReferenceMixin:
    @property
    def company(self):
        company_id = getattr(self, "company_id", None)
        if not company_id:
            return None
        return RemoteReference(company_id, getattr(self, "company_name", None))

    @company.setter
    def company(self, value):
        self.company_id = _reference_id(value)


class RemoteBranchReferenceMixin:
    @property
    def branch(self):
        branch_id = getattr(self, "branch_id", None)
        if not branch_id:
            return None
        return RemoteReference(branch_id)

    @branch.setter
    def branch(self, value):
        self.branch_id = _reference_id(value)


class RemoteCompanyBranchReferenceMixin(RemoteCompanyReferenceMixin, RemoteBranchReferenceMixin):
    pass


REMOTE_USER_PERMISSION_FIELDS = (
    "can_view_employees",
    "can_view_building_analytics",
    "can_view_building_cash_register",
    "can_view_building_clients",
    "can_view_building_department",
    "can_view_building_employess",
    "can_view_building_notification",
    "can_view_building_procurement",
    "can_view_building_projects",
    "can_view_building_salary",
    "can_view_building_sell",
    "can_view_building_stock",
    "can_view_building_treaty",
    "can_view_building_work_process",
    "can_view_building_objects",
)


class RemoteUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email=email, password=password, **extra_fields)

    def sync_from_profile(self, profile: dict):
        remote_id = profile.get("id") or profile.get("user_id")
        if not remote_id:
            raise ValueError("NurCRM profile has no user id.")

        company_value = profile.get("company_id") or profile.get("company")
        company_name = profile.get("company_name")
        if isinstance(company_value, dict):
            company_name = company_name or company_value.get("name")
        company_id = _reference_id(company_value)

        defaults = {
            "email": self.normalize_email(profile.get("email") or f"{remote_id}@nurcrm.local"),
            "first_name": profile.get("first_name") or "",
            "last_name": profile.get("last_name") or "",
            "avatar": profile.get("avatar") or "",
            "phone_number": profile.get("phone_number") or "",
            "track_number": profile.get("track_number") or "",
            "company_id": company_id,
            "company_name": company_name or "",
            "role": profile.get("role") or "",
            "branch_ids": [str(x) for x in (profile.get("branch_ids") or [])],
            "primary_branch_id": _reference_id(profile.get("primary_branch_id")),
            "is_active": bool(profile.get("is_active", True)),
            "is_staff": bool(profile.get("is_staff", False)),
            "is_superuser": bool(profile.get("is_superuser", False)),
        }
        for field in REMOTE_USER_PERMISSION_FIELDS:
            defaults[field] = bool(profile.get(field, False))

        user, _ = self.update_or_create(id=remote_id, defaults=defaults)
        if not user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user


class RemoteUser(AbstractBaseUser, PermissionsMixin):
    """Local shadow user synced from NurCRM JWT/profile data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    email = models.EmailField(unique=True, verbose_name="Email")
    first_name = models.CharField(max_length=64, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=64, blank=True, verbose_name="Фамилия")
    avatar = models.URLField(blank=True, verbose_name="Аватар")
    phone_number = models.CharField(max_length=64, blank=True, verbose_name="Телефон")
    track_number = models.CharField(max_length=64, blank=True, verbose_name="Номер машины")

    company_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID Компании NurCRM")
    company_name = models.CharField(max_length=255, blank=True, verbose_name="Компания NurCRM")
    role = models.CharField(max_length=32, blank=True, verbose_name="Роль NurCRM")
    branch_ids = models.JSONField(default=list, blank=True, verbose_name="ID филиалов NurCRM")
    primary_branch_id = models.UUIDField(null=True, blank=True, verbose_name="Основной филиал NurCRM")

    for_permission_docs = "Permissions are synced from NurCRM."
    can_view_employees = models.BooleanField(default=False, verbose_name="Доступ к сотрудникам")
    can_view_building_analytics = models.BooleanField(default=False, verbose_name="Building: Аналитика")
    can_view_building_cash_register = models.BooleanField(default=False, verbose_name="Building: Касса")
    can_view_building_clients = models.BooleanField(default=False, verbose_name="Building: Клиенты")
    can_view_building_department = models.BooleanField(default=False, verbose_name="Building: Отделы")
    can_view_building_employess = models.BooleanField(default=False, verbose_name="Building: Сотрудники")
    can_view_building_notification = models.BooleanField(default=False, verbose_name="Building: Уведомления")
    can_view_building_procurement = models.BooleanField(default=False, verbose_name="Building: Закупки")
    can_view_building_projects = models.BooleanField(default=False, verbose_name="Building: Проекты")
    can_view_building_salary = models.BooleanField(default=False, verbose_name="Building: Зарплата")
    can_view_building_sell = models.BooleanField(default=False, verbose_name="Building: Продажи")
    can_view_building_stock = models.BooleanField(default=False, verbose_name="Building: Склад")
    can_view_building_treaty = models.BooleanField(default=False, verbose_name="Building: Договора")
    can_view_building_work_process = models.BooleanField(default=False, verbose_name="Building: Процесс работы")
    can_view_building_objects = models.BooleanField(default=False, verbose_name="Building: Квартиры/Объекты")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = RemoteUserManager()

    class Meta:
        verbose_name = "Пользователь NurCRM"
        verbose_name_plural = "Пользователи NurCRM"
        indexes = [
            models.Index(fields=["company_id", "role"]),
            models.Index(fields=["company_id", "is_active"]),
        ]

    @property
    def company(self):
        if not self.company_id:
            return None
        return RemoteReference(self.company_id, self.company_name)

    @property
    def owned_company_id(self):
        if self.is_superuser or self.role in ("owner", "admin"):
            return self.company_id
        return None

    @property
    def owned_company(self):
        if not self.owned_company_id:
            return None
        return RemoteReference(self.owned_company_id, self.company_name)

    @property
    def allowed_branch_ids(self):
        return self.branch_ids or []

    @property
    def primary_branch(self):
        if not self.primary_branch_id:
            return None
        return RemoteReference(self.primary_branch_id)

    @property
    def role_display(self):
        return self.role or "Без роли"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.email


# -----------------------
# Касса Building (собственная система)
# -----------------------


class BuildingCashbox(RemoteCompanyBranchReferenceMixin, models.Model):
    """Касса модуля Building — учёт наличных для ЗП, рассрочек и т.п."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    branch_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID Филиала")

    name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Название кассы")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, null=True, blank=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Касса (Building)"
        verbose_name_plural = "Кассы (Building)"
        indexes = [
            models.Index(fields=["company_id"]),
            models.Index(fields=["company_id", "branch_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("branch_id", "name"),
                name="uq_building_cashbox_name_per_branch",
                condition=Q(branch_id__isnull=False) & Q(name__isnull=False),
            ),
            models.UniqueConstraint(
                fields=("company_id", "name"),
                name="uq_building_cashbox_name_global_per_company",
                condition=Q(branch_id__isnull=True) & Q(name__isnull=False),
            ),
        ]

    def __str__(self):
        if self.branch_id:
            base = f"Касса Building филиала {self.branch_id}"
            return f"{base}{f' ({self.name})' if self.name else ''}"
        return self.name or f"Касса Building {self.company_id}"


class BuildingCashFlow(RemoteCompanyBranchReferenceMixin, models.Model):
    """Движение по кассе (Building)."""

    class Type(models.TextChoices):
        INCOME = "income", "Приход"
        EXPENSE = "expense", "Расход"

    class Status(models.TextChoices):
        PENDING = "pending", "В ожидании"
        APPROVED = "approved", "Успешно"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    branch_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID Филиала")

    cashbox = models.ForeignKey(
        BuildingCashbox,
        on_delete=models.CASCADE,
        related_name="flows",
        verbose_name="Касса",
    )
    type = models.CharField(max_length=10, choices=Type.choices, verbose_name="Тип")
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Наименование")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="Статус")

    source_business_operation_id = models.CharField(max_length=36, null=True, blank=True, verbose_name="ID бизнес-операции")

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cash_flows",
        verbose_name="Кассир",
    )

    class Meta:
        verbose_name = "Движение по кассе (Building)"
        verbose_name_plural = "Движения по кассе (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "created_at"]),
            models.Index(fields=["company_id", "branch_id", "created_at"]),
            models.Index(fields=["cashbox", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["cashbox", "status", "type", "created_at"], name="ix_bld_flow_cb_stat_type"),
            models.Index(fields=["cashier", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(amount__gt=0), name="ck_building_cashflow_amount_positive"),
        ]

    def save(self, *args, **kwargs):
        if self.cashbox_id:
            self.company_id = self.cashbox.company_id
            self.branch_id = self.cashbox.branch_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} ({self.status})"


# -----------------------
# Заявки на кассу (Cash Register Requests)
# -----------------------


def building_cash_register_request_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/cash-register-requests/{instance.request_id}/files/{uuid.uuid4().hex}.{ext}"


def building_cashflow_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/cashflows/{instance.cashflow_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingCashRegisterRequest(RemoteCompanyBranchReferenceMixin, models.Model):
    """
    Заявка на кассу — создаётся бизнес-модулем (продажа, рассрочка, оплата подрядчику и т.д.)
    и должна быть одобрена кассой перед созданием CashFlow.
    """

    class RequestType(models.TextChoices):
        APARTMENT_SALE = "apartment_sale", "Продажа квартиры"
        INSTALLMENT_INITIAL_PAYMENT = "installment_initial_payment", "Первоначальный взнос по рассрочке"
        INSTALLMENT_PAYMENT = "installment_payment", "Платёж по рассрочке"
        CONTRACTOR_PAYMENT = "contractor_payment", "Оплата подрядчику"
        PROCUREMENT_PAYMENT = "procurement_payment", "Оплата закупки"
        ADVANCE = "advance", "Аванс по ЗП"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает одобрения"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"
        CANCELLED = "cancelled", "Отменено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    branch_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID Филиала")

    request_type = models.CharField(
        max_length=32,
        choices=RequestType.choices,
        db_index=True,
        verbose_name="Тип заявки",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="Статус",
    )

    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма")
    comment = models.TextField(blank=True, verbose_name="Комментарий")

    cashbox = models.ForeignKey(
        BuildingCashbox,
        on_delete=models.CASCADE,
        related_name="cash_register_requests",
        verbose_name="Касса",
    )
    shift = models.CharField(max_length=36, blank=True, null=True, verbose_name="UUID смены (опционально)")

    # Связи с бизнес-объектами (в зависимости от request_type)
    residential_complex = models.ForeignKey(
        "ResidentialComplex",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Жилой комплекс",
    )
    treaty = models.ForeignKey(
        "BuildingTreaty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Договор",
    )
    apartment = models.ForeignKey(
        "ResidentialComplexApartment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Квартира",
    )
    client = models.ForeignKey(
        "BuildingClient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Клиент",
    )
    installment = models.ForeignKey(
        "BuildingTreatyInstallment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Платёж рассрочки",
    )
    work_entry = models.ForeignKey(
        "BuildingWorkEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Процесс работ",
    )
    contractor = models.ForeignKey(
        "BuildingContractor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_requests",
        verbose_name="Подрядчик",
    )

    cashflow = models.OneToOneField(
        BuildingCashFlow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_register_request",
        verbose_name="Созданное движение",
    )

    reject_reason = models.TextField(blank=True, verbose_name="Причина отклонения")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата одобрения")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cash_register_requests_approved",
        verbose_name="Кто одобрил",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cash_register_requests_created",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Заявка на кассу (Building)"
        verbose_name_plural = "Заявки на кассу (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["company_id", "request_type", "status"]),
            models.Index(fields=["cashbox", "status"]),
            models.Index(fields=["residential_complex", "created_at"]),
            models.Index(fields=["treaty", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_request_type_display()} {self.amount} ({self.status})"


class BuildingCashRegisterRequestFile(models.Model):
    """Файл, прикреплённый к заявке на кассу."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    request = models.ForeignKey(
        BuildingCashRegisterRequest,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Заявка",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_cash_register_request_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cash_register_request_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл заявки на кассу"
        verbose_name_plural = "Файлы заявок на кассу"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["request", "created_at"]),
        ]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


class BuildingCashFlowFile(models.Model):
    """Файл, прикреплённый к движению по кассе (CashFlow)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    cashflow = models.ForeignKey(
        BuildingCashFlow,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Движение по кассе",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_cashflow_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cashflow_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл движения по кассе"
        verbose_name_plural = "Файлы движений по кассе"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["cashflow", "created_at"]),
        ]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


# -----------------------
# Residential complex and related
# -----------------------


class ResidentialComplex(RemoteCompanyReferenceMixin, models.Model):
    """
    Жилой комплекс (ЖК) — объект строительной компании.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")

    name = models.CharField(max_length=255, verbose_name="Название ЖК")
    address = models.CharField(max_length=512, blank=True, null=True, verbose_name="Адрес")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")

    # Касса, из которой по умолчанию идут выплаты ЗП по этому ЖК
    salary_cashbox = models.ForeignKey(
        BuildingCashbox,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_residential_complexes",
        verbose_name="Касса для ЗП по ЖК",
    )

    is_active = models.BooleanField(default=True, verbose_name="Активен")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Жилой комплекс (ЖК)"
        verbose_name_plural = "Жилые комплексы (ЖК)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id"]),
            models.Index(fields=["company_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} (Company ID: {self.company_id})"


class ResidentialComplexMember(models.Model):
    """
    Назначение сотрудника на конкретный ЖК.

    Если у пользователя есть хотя бы одно активное назначение,
    то в building он видит данные только по назначенным ЖК.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="Жилой комплекс",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="building_residential_complex_memberships",
        verbose_name="Сотрудник",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активно")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_residential_complex_memberships_added",
        verbose_name="Кто назначил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата назначения")

    class Meta:
        verbose_name = "Сотрудник ЖК (Building)"
        verbose_name_plural = "Сотрудники ЖК (Building)"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["residential_complex", "user"], name="uq_building_rc_member_rc_user"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["residential_complex", "is_active"]),
        ]

    def __str__(self):
        return f"{self.residential_complex_id} -> {self.user_id}"


def residential_complex_drawing_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/residential-complexes/{instance.residential_complex_id}/drawings/{uuid.uuid4().hex}.{ext}"


class ResidentialComplexDrawing(models.Model):
    """
    Чертеж, привязанный к конкретному жилому комплексу.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="drawings",
        verbose_name="Жилой комплекс",
    )
    title = models.CharField(max_length=255, verbose_name="Название чертежа")
    file = models.FileField(upload_to=residential_complex_drawing_upload_to, verbose_name="Файл чертежа")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Чертеж ЖК"
        verbose_name_plural = "Чертежи ЖК"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["residential_complex"]),
            models.Index(fields=["residential_complex", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.residential_complex.name})"


class ResidentialComplexWarehouse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    residential_complex = models.OneToOneField(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="warehouse",
        verbose_name="Жилой комплекс",
    )
    name = models.CharField(max_length=255, verbose_name="Название склада")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Склад ЖК"
        verbose_name_plural = "Склады ЖК"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.residential_complex.name})"


class ResidentialComplexApartment(models.Model):
    """
    Квартира в рамках конкретного ЖК.
    Используется для продажи/брони через BuildingTreaty.
    """

    class Status(models.TextChoices):
        AVAILABLE = "available", "Доступна"
        RESERVED = "reserved", "Забронирована"
        SOLD = "sold", "Продана"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="apartments",
        verbose_name="Жилой комплекс",
    )

    floor = models.IntegerField(verbose_name="Этаж")
    number = models.CharField(max_length=32, verbose_name="Номер квартиры")

    # Блок/подъезд/секция — вводится вручную, отдельной сущности не создаём.
    block = models.CharField(max_length=64, null=True, blank=True, db_index=True, verbose_name="Блок")
    block_normalized = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Блок (норм.)",
        help_text="Для устойчивой фильтрации (lowercase/trim). Заполняется автоматически.",
    )

    rooms = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Кол-во комнат")
    area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Площадь (м²)")
    price = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Цена")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
        verbose_name="Статус",
    )
    notes = models.TextField(blank=True, verbose_name="Заметки")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Квартира (Building)"
        verbose_name_plural = "Квартиры (Building)"
        ordering = ["residential_complex", "floor", "number"]
        indexes = [
            models.Index(fields=["residential_complex", "floor"]),
            models.Index(fields=["residential_complex", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["residential_complex", "number"],
                name="uq_building_apartment_per_complex_number",
            )
        ]

    def __str__(self):
        return f"Кв. {self.number}, {self.floor} этаж ({self.residential_complex.name})"

    def save(self, *args, **kwargs):
        if self.block is not None:
            b = (self.block or "").strip()
            self.block = b or None
            self.block_normalized = (b.lower() if b else None)
        else:
            self.block_normalized = None
        super().save(*args, **kwargs)


# -----------------------
# Подрядчики (Contractors)
# -----------------------


class BuildingContractor(RemoteCompanyReferenceMixin, models.Model):
    """Подрядчик — справочник для процесса работ и оплат."""

    class ContractorType(models.TextChoices):
        SUBCONTRACTOR = "subcontractor", "Субподрядчик"
        GENERAL_CONTRACTOR = "general_contractor", "Генподрядчик"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        INACTIVE = "inactive", "Неактивен"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    company_name = models.CharField(max_length=255, verbose_name="Название организации")
    contractor_type = models.CharField(
        max_length=32,
        choices=ContractorType.choices,
        default=ContractorType.SUBCONTRACTOR,
        verbose_name="Тип подрядчика",
    )
    tax_id = models.CharField(max_length=32, blank=True, verbose_name="ИНН")
    registration_number = models.CharField(max_length=64, blank=True, verbose_name="Рег. номер")
    year_founded = models.PositiveIntegerField(null=True, blank=True, verbose_name="Год основания")

    contact_person = models.CharField(max_length=255, blank=True, verbose_name="Контактное лицо")
    phone = models.CharField(max_length=64, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")

    city = models.CharField(max_length=128, blank=True, verbose_name="Город")
    address = models.CharField(max_length=512, blank=True, verbose_name="Адрес")

    specializations = models.JSONField(default=list, blank=True, verbose_name="Специализации")
    employees = models.PositiveIntegerField(null=True, blank=True, verbose_name="Кол-во сотрудников")
    equipment = models.JSONField(default=list, blank=True, verbose_name="Оборудование")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Подрядчик (Building)"
        verbose_name_plural = "Подрядчики (Building)"
        ordering = ["company_name"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["company_id", "company_name"]),
        ]

    def __str__(self):
        return self.company_name


def building_contractor_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/contractors/{instance.contractor_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingContractorFile(models.Model):
    """Файл, прикреплённый к подрядчику."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    contractor = models.ForeignKey(
        BuildingContractor,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Подрядчик",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_contractor_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_contractor_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл подрядчика"
        verbose_name_plural = "Файлы подрядчиков"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


# -----------------------
# Поставщики (Suppliers)
# -----------------------


class BuildingSupplier(RemoteCompanyReferenceMixin, models.Model):
    """Поставщик строительных материалов."""

    class SupplierType(models.TextChoices):
        MATERIALS_SUPPLIER = "materials_supplier", "Поставщик материалов"
        EQUIPMENT_SUPPLIER = "equipment_supplier", "Поставщик оборудования"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        INACTIVE = "inactive", "Неактивен"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    company_name = models.CharField(max_length=255, verbose_name="Название организации")
    supplier_type = models.CharField(
        max_length=32,
        choices=SupplierType.choices,
        default=SupplierType.MATERIALS_SUPPLIER,
        verbose_name="Тип поставщика",
    )
    tax_id = models.CharField(max_length=32, blank=True, verbose_name="ИНН")
    registration_number = models.CharField(max_length=64, blank=True, verbose_name="Рег. номер")
    year_founded = models.PositiveIntegerField(null=True, blank=True, verbose_name="Год основания")

    contact_person = models.CharField(max_length=255, blank=True, verbose_name="Контактное лицо")
    position = models.CharField(max_length=128, blank=True, verbose_name="Должность")
    phone = models.CharField(max_length=64, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    website = models.URLField(blank=True, verbose_name="Сайт")

    city = models.CharField(max_length=128, blank=True, verbose_name="Город")
    address = models.CharField(max_length=512, blank=True, verbose_name="Адрес")
    postal_code = models.CharField(max_length=32, blank=True, verbose_name="Индекс")

    bank_details = models.JSONField(default=dict, blank=True, verbose_name="Банковские реквизиты")
    supplied_materials = models.JSONField(default=list, blank=True, verbose_name="Поставляемые материалы")
    delivery = models.JSONField(default=dict, blank=True, verbose_name="Доставка")
    warehouse = models.JSONField(default=dict, blank=True, verbose_name="Склад")

    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name="Рейтинг")
    completed_orders = models.PositiveIntegerField(default=0, verbose_name="Выполнено заказов")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Поставщик (Building)"
        verbose_name_plural = "Поставщики (Building)"
        ordering = ["company_name"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["company_id", "company_name"]),
        ]

    def __str__(self):
        return self.company_name


def building_supplier_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/suppliers/{instance.supplier_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingSupplierFile(models.Model):
    """Файл, прикреплённый к поставщику."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    supplier = models.ForeignKey(
        BuildingSupplier,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Поставщик",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_supplier_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_supplier_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл поставщика"
        verbose_name_plural = "Файлы поставщиков"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


class BuildingSupplierBarterSettlement(RemoteCompanyReferenceMixin, models.Model):
    """Бартерный взаимозачёт с поставщиком или подрядчиком в разрезе ЖК."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        CONFIRMED = "confirmed", "Подтверждён"
        CANCELLED = "cancelled", "Отменён"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    supplier = models.ForeignKey(
        BuildingSupplier,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="barter_settlements",
        verbose_name="Поставщик",
    )
    contractor = models.ForeignKey(
        "BuildingContractor",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="barter_settlements",
        verbose_name="Подрядчик",
    )
    residential_complex = models.ForeignKey(
        "ResidentialComplex",
        on_delete=models.CASCADE,
        related_name="supplier_barter_settlements",
        verbose_name="Жилой комплекс",
    )
    date = models.DateField(default=timezone.now, verbose_name="Дата зачёта")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус",
    )
    amount_total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Сумма зачёта",
    )
    currency = models.CharField(max_length=8, default="KZT", verbose_name="Валюта")
    comment = models.TextField(blank=True, verbose_name="Комментарий")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_supplier_barter_settlements_created",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Бартерный зачёт"
        verbose_name_plural = "Бартерные зачёты"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["company_id", "supplier", "date"]),
            models.Index(fields=["company_id", "contractor", "date"]),
            models.Index(fields=["company_id", "residential_complex", "date"]),
            models.Index(fields=["status", "date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(supplier__isnull=False, contractor__isnull=True)
                    | models.Q(supplier__isnull=True, contractor__isnull=False)
                ),
                name="ck_barter_settlement_supplier_xor_contractor",
            ),
        ]

    def __str__(self):
        who = self.supplier or self.contractor
        return f"Бартер {who} на {self.amount_total} {self.currency} от {self.date}"


class BuildingSupplierBarterPurchaseItem(models.Model):
    """Строка закупки, погашаемая бартерным зачётом."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    settlement = models.ForeignKey(
        BuildingSupplierBarterSettlement,
        on_delete=models.CASCADE,
        related_name="purchase_items",
        verbose_name="Бартерный зачёт",
    )
    procurement_item = models.ForeignKey(
        "BuildingProcurementItem",
        on_delete=models.CASCADE,
        related_name="barter_items",
        verbose_name="Позиция закупки",
    )
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        verbose_name="Сумма по строке в зачёте",
    )

    class Meta:
        verbose_name = "Строка закупки в бартерном зачёте"
        verbose_name_plural = "Строки закупок в бартерных зачётах"
        indexes = [
            models.Index(fields=["settlement"]),
            models.Index(fields=["procurement_item"]),
        ]

    def __str__(self):
        return f"{self.procurement_item_id}: {self.amount}"


class BuildingSupplierBarterCounterDelivery(models.Model):
    """Встречная поставка/услуга в рамках бартерного зачёта."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    settlement = models.ForeignKey(
        BuildingSupplierBarterSettlement,
        on_delete=models.CASCADE,
        related_name="counter_deliveries",
        verbose_name="Бартерный зачёт",
    )
    description = models.CharField(max_length=512, verbose_name="Описание")
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        verbose_name="Сумма по встречной поставке",
    )

    class Meta:
        verbose_name = "Встречная поставка по бартеру"
        verbose_name_plural = "Встречные поставки по бартеру"
        indexes = [
            models.Index(fields=["settlement"]),
        ]

    def __str__(self):
        return f"{self.description} ({self.amount})"


# -----------------------
# Товары (Products)
# -----------------------


class BuildingProduct(RemoteCompanyReferenceMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    name = models.CharField(max_length=255, verbose_name="Название")
    article = models.CharField(max_length=64, blank=True, verbose_name="Артикул")
    barcode = models.CharField(max_length=64, blank=True, verbose_name="Штрихкод")
    unit = models.CharField(max_length=64, default="шт.", verbose_name="Единица измерения")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Товар (Building)"
        verbose_name_plural = "Товары (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "name"]),
            models.Index(fields=["company_id", "barcode"]),
            models.Index(fields=["company_id", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("company_id", "barcode"),
                condition=~models.Q(barcode=""),
                name="uq_building_product_company_barcode_not_empty",
            )
        ]

    def __str__(self):
        return self.name


class BuildingProcurementRequest(models.Model):
    class PaymentMode(models.TextChoices):
        CASH = "cash", "Наличные"
        DEBT = "debt", "В долг"
        BARTER = "barter", "Бартер"
        MIXED = "mixed", "Смешанная"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED_TO_CASH = "submitted_to_cash", "Отправлено в кассу"
        CASH_APPROVED = "cash_approved", "Одобрено кассой"
        CASH_REJECTED = "cash_rejected", "Отклонено кассой"
        TRANSFER_CREATED = "transfer_created", "Передача создана"
        TRANSFERRED = "transferred", "Передано на склад"
        PARTIALLY_TRANSFERRED = "partially_transferred", "Передано частично"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="procurements",
        verbose_name="Жилой комплекс",
    )
    supplier = models.ForeignKey(
        "BuildingSupplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurements",
        verbose_name="Поставщик",
    )
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_procurement_requests",
        verbose_name="Инициатор закупки",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название закупки")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    payment_mode = models.CharField(
        max_length=16,
        choices=PaymentMode.choices,
        default=PaymentMode.CASH,
        db_index=True,
        verbose_name="Режим оплаты",
    )
    treaty = models.ForeignKey(
        "BuildingTreaty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurements",
        verbose_name="Договор",
    )
    treaty_auto_create = models.BooleanField(default=False, verbose_name="Автосоздать договор")
    treaty_type = models.CharField(max_length=32, blank=True, verbose_name="Тип создаваемого договора")
    treaty_title = models.CharField(max_length=255, blank=True, verbose_name="Название создаваемого договора")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус",
    )
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Сумма")
    submitted_to_cash_at = models.DateTimeField(null=True, blank=True, verbose_name="Отправлено в кассу")
    cash_decided_at = models.DateTimeField(null=True, blank=True, verbose_name="Решение кассы")
    cash_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_procurement_cash_decisions",
        verbose_name="Кто принял решение в кассе",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Заявка на закупку"
        verbose_name_plural = "Заявки на закупку"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["residential_complex", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["residential_complex", "payment_mode"]),
            models.Index(fields=["treaty"]),
        ]

    def __str__(self):
        return self.title or f"Закупка {self.id}"

    def recalculate_totals(self):
        total = self.items.aggregate(total=Coalesce(Sum("line_total"), Decimal("0.00"))).get("total") or Decimal("0.00")
        type(self).objects.filter(pk=self.pk).update(total_amount=total)
        self.total_amount = total
        return total


class BuildingProcurementItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    procurement = models.ForeignKey(
        BuildingProcurementRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Закупка",
    )
    product = models.ForeignKey(
        BuildingProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurement_items",
        verbose_name="Товар",
    )
    name = models.CharField(max_length=255, verbose_name="Наименование")
    unit = models.CharField(max_length=64, verbose_name="Единица измерения")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Количество")
    price = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Цена")
    line_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Сумма")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Позиция закупки"
        verbose_name_plural = "Позиции закупки"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["procurement", "order"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    def save(self, *args, **kwargs):
        if self.product_id:
            if not self.name:
                self.name = self.product.name
            if not self.unit:
                self.unit = self.product.unit
        qty = Decimal(self.quantity or 0)
        price = Decimal(self.price or 0)
        self.line_total = (qty * price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        if self.procurement_id:
            self.procurement.recalculate_totals()

    def delete(self, *args, **kwargs):
        procurement = self.procurement
        super().delete(*args, **kwargs)
        if procurement:
            procurement.recalculate_totals()


def building_procurement_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/procurements/{instance.procurement_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingProcurementFile(models.Model):
    """Файл, прикреплённый к закупке (счета, договоры, накладные)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    procurement = models.ForeignKey(
        BuildingProcurementRequest,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Закупка",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_procurement_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_procurement_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл закупки (Building)"
        verbose_name_plural = "Файлы закупок (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["procurement", "created_at"]),
        ]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


class BuildingProcurementCashDecision(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    procurement = models.OneToOneField(
        BuildingProcurementRequest,
        on_delete=models.CASCADE,
        related_name="cash_decision",
        verbose_name="Закупка",
    )
    decision = models.CharField(max_length=16, choices=Decision.choices, verbose_name="Решение")
    reason = models.TextField(blank=True, verbose_name="Причина")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_cash_decisions",
        verbose_name="Кто принял решение",
    )
    decided_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата решения")

    class Meta:
        verbose_name = "Решение кассы по закупке"
        verbose_name_plural = "Решения кассы по закупкам"
        indexes = [
            models.Index(fields=["decision", "decided_at"]),
        ]

    def __str__(self):
        return f"{self.procurement_id} - {self.decision}"


class BuildingTransferRequest(models.Model):
    class Status(models.TextChoices):
        PENDING_RECEIPT = "pending_receipt", "Ожидает приемку"
        ACCEPTED = "accepted", "Принято"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    procurement = models.ForeignKey(
        BuildingProcurementRequest,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name="Закупка",
    )
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name="Склад ЖК",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_created_transfers",
        verbose_name="Кто создал передачу",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_decided_transfers",
        verbose_name="Кто принял решение",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_RECEIPT,
        db_index=True,
        verbose_name="Статус",
    )
    note = models.TextField(blank=True, verbose_name="Комментарий")
    rejection_reason = models.TextField(blank=True, verbose_name="Причина отказа")
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Сумма")
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата приемки")
    rejected_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата отказа")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Передача на склад ЖК"
        verbose_name_plural = "Передачи на склад ЖК"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["warehouse", "status"]),
            models.Index(fields=["procurement", "status"]),
        ]

    def __str__(self):
        return f"Передача {self.id} ({self.get_status_display()})"

    def recalculate_totals(self):
        total = self.items.aggregate(total=Coalesce(Sum("line_total"), Decimal("0.00"))).get("total") or Decimal("0.00")
        type(self).objects.filter(pk=self.pk).update(total_amount=total)
        self.total_amount = total
        return total


class BuildingTransferItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    transfer = models.ForeignKey(
        BuildingTransferRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Передача",
    )
    procurement_item = models.ForeignKey(
        BuildingProcurementItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_items",
        verbose_name="Позиция закупки",
    )
    name = models.CharField(max_length=255, verbose_name="Наименование")
    unit = models.CharField(max_length=64, verbose_name="Единица измерения")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Количество")
    price = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Цена")
    line_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Сумма")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Позиция передачи"
        verbose_name_plural = "Позиции передачи"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["transfer", "order"]),
            models.Index(fields=["procurement_item"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    def save(self, *args, **kwargs):
        qty = Decimal(self.quantity or 0)
        price = Decimal(self.price or 0)
        self.line_total = (qty * price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        if self.transfer_id:
            self.transfer.recalculate_totals()

    def delete(self, *args, **kwargs):
        transfer = self.transfer
        super().delete(*args, **kwargs)
        if transfer:
            transfer.recalculate_totals()


def building_transfer_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/transfers/{instance.transfer_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingTransferRequestFile(models.Model):
    """Файл, прикреплённый к передаче на склад (приёмка)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    transfer = models.ForeignKey(
        BuildingTransferRequest,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Передача",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_transfer_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_transfer_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл передачи на склад"
        verbose_name_plural = "Файлы передач на склад"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


# -----------------------
# Заявки на материалы со склада (из процесса работ)
# -----------------------


class BuildingWarehouseRequest(models.Model):
    """Заявка на выдачу материалов со склада из процесса работ."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает обработки"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"
        PARTIALLY_APPROVED = "partially_approved", "Частично обработано"
        COMPLETED = "completed", "Завершена (всё выдано)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    work_entry = models.ForeignKey(
        "BuildingWorkEntry",
        on_delete=models.CASCADE,
        related_name="warehouse_requests",
        verbose_name="Процесс работ",
    )
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.CASCADE,
        related_name="warehouse_requests",
        verbose_name="Склад",
    )
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="Статус",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_warehouse_requests_created",
        verbose_name="Кто создал",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_warehouse_requests_decided",
        verbose_name="Кто принял решение",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Заявка на материалы со склада"
        verbose_name_plural = "Заявки на материалы со склада"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["work_entry", "status"]),
            models.Index(fields=["warehouse", "status"]),
        ]

    def __str__(self):
        return f"Заявка {self.id} ({self.get_status_display()})"


class BuildingWarehouseRequestItem(models.Model):
    """Позиция заявки на материалы."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    request = models.ForeignKey(
        BuildingWarehouseRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заявка",
    )
    stock_item = models.ForeignKey(
        "BuildingWarehouseStockItem",
        on_delete=models.CASCADE,
        related_name="warehouse_request_items",
        verbose_name="Позиция склада",
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Количество")
    unit = models.CharField(max_length=64, verbose_name="Единица измерения")
    approved_quantity = models.DecimalField(
        max_digits=16,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Одобрено количество",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Позиция заявки на материалы"
        verbose_name_plural = "Позиции заявок на материалы"
        ordering = ["request", "created_at"]

    def __str__(self):
        return f"{self.stock_item.name} x {self.quantity}"


# -----------------------
# Акт сверки материалов (из процесса работ)
# -----------------------


class BuildingReconciliationAct(models.Model):
    """Акт сверки материалов при завершении/отмене процесса работ."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    work_entry = models.ForeignKey(
        "BuildingWorkEntry",
        on_delete=models.CASCADE,
        related_name="reconciliation_acts",
        verbose_name="Процесс работ",
    )
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_reconciliation_acts_created",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Акт сверки материалов"
        verbose_name_plural = "Акты сверки материалов"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["work_entry"]),
        ]

    def __str__(self):
        return f"Акт сверки {self.id} ({self.work_entry_id})"


class BuildingReconciliationActItem(models.Model):
    """Возвращаемая позиция в акте сверки."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    act = models.ForeignKey(
        BuildingReconciliationAct,
        on_delete=models.CASCADE,
        related_name="returned_items",
        verbose_name="Акт сверки",
    )
    stock_item = models.ForeignKey(
        "BuildingWarehouseStockItem",
        on_delete=models.CASCADE,
        related_name="reconciliation_act_items",
        verbose_name="Позиция склада",
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Количество")
    unit = models.CharField(max_length=64, verbose_name="Единица измерения")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Возврат в акте сверки"
        verbose_name_plural = "Возвраты в актах сверки"
        ordering = ["act", "created_at"]

    def __str__(self):
        return f"{self.stock_item.name} x {self.quantity}"


# -----------------------
# Движения склада (списание, передача)
# -----------------------


class BuildingWarehouseMovement(RemoteCompanyReferenceMixin, models.Model):
    """Движение по складу: списание, передача подрядчику, передача в процесс работ."""

    class MovementType(models.TextChoices):
        WRITE_OFF = "write_off", "Списание"
        TRANSFER_TO_CONTRACTOR = "transfer_to_contractor", "Передача подрядчику"
        TRANSFER_TO_WORK_ENTRY = "transfer_to_work_entry", "Передача в процесс работ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.CASCADE,
        related_name="warehouse_movements",
        verbose_name="Склад",
    )
    movement_type = models.CharField(
        max_length=32,
        choices=MovementType.choices,
        db_index=True,
        verbose_name="Тип движения",
    )
    contractor = models.ForeignKey(
        "BuildingContractor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_movements",
        verbose_name="Подрядчик",
    )
    work_entry = models.ForeignKey(
        "BuildingWorkEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_movements",
        verbose_name="Процесс работ",
    )
    warehouse_request = models.ForeignKey(
        "BuildingWarehouseRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name="Заявка на материалы",
    )
    issued_to = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Кому передали",
        help_text="Свободная строка (ФИО/кому выдали материалы).",
    )
    reason = models.TextField(blank=True, verbose_name="Причина/комментарий")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_warehouse_movements_created",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Движение склада (Building)"
        verbose_name_plural = "Движения склада (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "movement_type"]),
            models.Index(fields=["warehouse", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.id}"


class BuildingWarehouseMovementItem(models.Model):
    """Позиция движения склада."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    movement = models.ForeignKey(
        BuildingWarehouseMovement,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Движение",
    )
    stock_item = models.ForeignKey(
        "BuildingWarehouseStockItem",
        on_delete=models.CASCADE,
        related_name="movement_items",
        verbose_name="Позиция склада",
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Количество")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Позиция движения склада"
        verbose_name_plural = "Позиции движений склада"
        ordering = ["movement", "created_at"]

    def __str__(self):
        return f"{self.stock_item.name} x {self.quantity}"


def building_warehouse_movement_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/warehouse-movements/{instance.movement_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingWarehouseMovementFile(models.Model):
    """Файл, прикреплённый к движению склада."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    movement = models.ForeignKey(
        BuildingWarehouseMovement,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Движение",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_warehouse_movement_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_warehouse_movement_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл движения склада"
        verbose_name_plural = "Файлы движений склада"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


class BuildingWarehouseStockItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.CASCADE,
        related_name="stock_items",
        verbose_name="Склад ЖК",
    )
    name = models.CharField(max_length=255, verbose_name="Наименование")
    unit = models.CharField(max_length=64, verbose_name="Единица измерения")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=Decimal("0.000"), verbose_name="Остаток")
    last_price = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Последняя цена")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Остаток склада ЖК"
        verbose_name_plural = "Остатки склада ЖК"
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "name", "unit"],
                name="uq_building_warehouse_stock_item",
            )
        ]
        indexes = [
            models.Index(fields=["warehouse", "name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"


class BuildingWarehouseStockMove(models.Model):
    class MoveType(models.TextChoices):
        INCOMING = "incoming", "Приход"
        WRITE_OFF = "write_off", "Списание"
        TRANSFER_TO_CONTRACTOR = "transfer_to_contractor", "Передача подрядчику"
        TRANSFER_TO_WORK_ENTRY = "transfer_to_work_entry", "Передача в процесс работ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.CASCADE,
        related_name="stock_moves",
        verbose_name="Склад ЖК",
    )
    stock_item = models.ForeignKey(
        BuildingWarehouseStockItem,
        on_delete=models.CASCADE,
        related_name="moves",
        verbose_name="Остаток",
    )
    transfer = models.ForeignKey(
        BuildingTransferRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_moves",
        verbose_name="Передача",
    )
    movement = models.ForeignKey(
        "BuildingWarehouseMovement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_moves",
        verbose_name="Движение склада",
    )
    contractor = models.ForeignKey(
        "BuildingContractor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_stock_moves",
        verbose_name="Подрядчик",
    )
    work_entry = models.ForeignKey(
        "BuildingWorkEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_stock_moves",
        verbose_name="Процесс работ",
    )
    move_type = models.CharField(max_length=32, choices=MoveType.choices, verbose_name="Тип движения")
    quantity_delta = models.DecimalField(max_digits=16, decimal_places=3, verbose_name="Изменение количества")
    price = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Цена")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_stock_moves",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Движение остатка склада ЖК"
        verbose_name_plural = "Движения остатков склада ЖК"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["warehouse", "created_at"]),
            models.Index(fields=["stock_item", "created_at"]),
        ]


class BuildingWorkflowEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    procurement = models.ForeignKey(
        BuildingProcurementRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Закупка",
    )
    procurement_item = models.ForeignKey(
        BuildingProcurementItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Позиция закупки",
    )
    transfer = models.ForeignKey(
        BuildingTransferRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Передача",
    )
    transfer_item = models.ForeignKey(
        BuildingTransferItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Позиция передачи",
    )
    warehouse = models.ForeignKey(
        ResidentialComplexWarehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Склад ЖК",
    )
    stock_item = models.ForeignKey(
        BuildingWarehouseStockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_events",
        verbose_name="Остаток склада",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_workflow_events",
        verbose_name="Кто выполнил действие",
    )
    action = models.CharField(max_length=64, verbose_name="Действие")
    from_status = models.CharField(max_length=64, blank=True, null=True, verbose_name="Статус до")
    to_status = models.CharField(max_length=64, blank=True, null=True, verbose_name="Статус после")
    message = models.TextField(blank=True, verbose_name="Комментарий")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Данные события")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата события")

    class Meta:
        verbose_name = "Событие процесса закупки"
        verbose_name_plural = "События процесса закупки"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["procurement", "created_at"]),
            models.Index(fields=["transfer", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} ({self.created_at:%Y-%m-%d %H:%M:%S})"


class BuildingClient(RemoteCompanyReferenceMixin, models.Model):
    """
    Клиент (в рамках building).

    Не зависит от CRM, чтобы модуль building был самодостаточным.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    name = models.CharField(max_length=255, verbose_name="Клиент (ФИО/компания)")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    inn = models.CharField(max_length=32, blank=True, verbose_name="ИНН")
    address = models.CharField(max_length=512, blank=True, verbose_name="Адрес")
    notes = models.TextField(blank=True, verbose_name="Заметки")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Клиент (Building)"
        verbose_name_plural = "Клиенты (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "is_active"]),
            models.Index(fields=["company_id", "name"]),
            models.Index(fields=["company_id", "phone"]),
        ]

    def __str__(self):
        return self.name


def building_client_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/clients/{instance.client_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingClientFile(models.Model):
    """Файл, прикреплённый к клиенту."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    client = models.ForeignKey(
        BuildingClient,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Клиент",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_client_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_client_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл клиента (Building)"
        verbose_name_plural = "Файлы клиентов (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "created_at"]),
        ]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


class BuildingTreatyNumberSequence(RemoteCompanyReferenceMixin, models.Model):
    """
    Счётчик для безопасной автогенерации номера договора внутри компании.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(unique=True, verbose_name="ID Компании")
    next_value = models.PositiveIntegerField(default=1, verbose_name="Следующее значение")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Счётчик номера договора (Building)"
        verbose_name_plural = "Счётчики номеров договоров (Building)"

    def __str__(self):
        return f"{self.company_id}: next={self.next_value}"


def building_treaty_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/treaties/{instance.treaty_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingTreaty(RemoteCompanyReferenceMixin, models.Model):
    """
    Договор (в рамках building).
    """

    class OperationType(models.TextChoices):
        SALE = "sale", "Продажа"
        BOOKING = "booking", "Бронь"
        OTHER = "other", "Прочие"

    class TreatyType(models.TextChoices):
        CONSTRUCTION_DEPARTMENT = "construction_department", "Строительный отдел"
        SALE = "sale", "Продажа"
        BOOKING = "booking", "Бронь"
        PROCUREMENT = "procurement", "Закупки"
        OTHER = "other", "Прочее"

    class PaymentType(models.TextChoices):
        FULL = "full", "Полная оплата"
        INSTALLMENT = "installment", "Рассрочка"

    class PaymentMode(models.TextChoices):
        CASH = "cash", "Деньги"
        INSTALLMENT = "installment", "Рассрочка"
        BARTER = "barter", "Бартер"
        MIXED = "mixed", "Смешанная"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "active", "Активен"
        SIGNED = "signed", "Подписан"
        CANCELLED = "cancelled", "Отменён"

    class ErpSyncStatus(models.TextChoices):
        NOT_REQUESTED = "not_requested", "Не отправляли"
        REQUESTED = "requested", "Запрошено"
        SYNCED = "synced", "Создано в ERP"
        FAILED = "failed", "Ошибка"
        NOT_CONFIGURED = "not_configured", "ERP не настроена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID Компании")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="treaties",
        null=True,
        blank=True,
        verbose_name="Жилой комплекс",
    )
    client = models.ForeignKey(
        BuildingClient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treaties",
        verbose_name="Клиент",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="building_treaties_created",
        verbose_name="Кто создал",
    )

    number = models.CharField(max_length=64, blank=True, verbose_name="Номер договора")
    client_name = models.CharField(max_length=255, blank=True, verbose_name="Название контрагента (если нет client)")
    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание/условия")
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Сумма")

    # Бизнес-категория договора (строительство/продажа/закупки и т.п.). Не путать с operation_type.
    treaty_type = models.CharField(
        max_length=32,
        choices=TreatyType.choices,
        default=TreatyType.SALE,
        db_index=True,
        verbose_name="Категория договора",
    )

    apartment = models.ForeignKey(
        ResidentialComplexApartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treaties",
        verbose_name="Квартира",
    )
    operation_type = models.CharField(
        max_length=16,
        choices=OperationType.choices,
        default=OperationType.SALE,
        db_index=True,
        verbose_name="Тип операции",
    )
    payment_type = models.CharField(
        max_length=16,
        choices=PaymentType.choices,
        default=PaymentType.FULL,
        db_index=True,
        verbose_name="Тип оплаты",
    )

    payment_mode = models.CharField(
        max_length=16,
        choices=PaymentMode.choices,
        default=PaymentMode.CASH,
        db_index=True,
        verbose_name="Режим оплаты",
        help_text="cash/installment/barter/mixed — для поддержки бартера и смешанных оплат.",
    )

    group = models.ForeignKey(
        "BuildingTreatyGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treaties",
        verbose_name="Папка/группа",
    )

    down_payment = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Первоначальный взнос")
    payment_terms = models.TextField(blank=True, verbose_name="Условия оплаты")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="Статус")
    signed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата подписания")

    auto_create_in_erp = models.BooleanField(default=False, verbose_name="Автосоздание в ERP")
    erp_sync_status = models.CharField(
        max_length=32,
        choices=ErpSyncStatus.choices,
        default=ErpSyncStatus.NOT_REQUESTED,
        db_index=True,
        verbose_name="ERP: статус",
    )
    erp_external_id = models.CharField(max_length=128, blank=True, verbose_name="ERP: внешний ID")
    erp_last_error = models.TextField(blank=True, verbose_name="ERP: последняя ошибка")
    erp_requested_at = models.DateTimeField(null=True, blank=True, verbose_name="ERP: запрос отправки")
    erp_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="ERP: синхронизировано")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Договор (Building)"
        verbose_name_plural = "Договоры (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["residential_complex", "status"]),
            models.Index(fields=["residential_complex", "operation_type", "created_at"]),
            models.Index(fields=["residential_complex", "payment_type", "created_at"]),
            models.Index(fields=["residential_complex", "treaty_type", "created_at"]),
            models.Index(fields=["group", "created_at"]),
            models.Index(fields=["erp_sync_status", "created_at"]),
        ]

    def __str__(self):
        base = self.number or (self.title or "Договор")
        rc_name = self.residential_complex.name if self.residential_complex_id else str(self.company_id)
        return f"{base} ({rc_name})" if rc_name else base


class BuildingTreatyInstallment(models.Model):
    """
    Платёж рассрочки по договору.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирован"
        PAID = "paid", "Оплачен"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    treaty = models.ForeignKey(
        BuildingTreaty,
        on_delete=models.CASCADE,
        related_name="installments",
        verbose_name="Договор",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    due_date = models.DateField(verbose_name="Дата платежа")
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED, db_index=True, verbose_name="Статус")
    paid_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Оплачено")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата оплаты")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Платёж рассрочки (Building)"
        verbose_name_plural = "Платежи рассрочки (Building)"
        ordering = ["order", "due_date", "created_at"]
        indexes = [
            models.Index(fields=["treaty", "order"]),
            models.Index(fields=["treaty", "due_date"]),
            models.Index(fields=["status", "due_date"]),
        ]


class BuildingTreatyInstallmentPayment(models.Model):
    """История оплат по взносам рассрочки (отдельные записи)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    installment = models.ForeignKey(
        BuildingTreatyInstallment,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Взнос",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма оплаты")
    paid_at = models.DateTimeField(default=timezone.now, verbose_name="Дата оплаты")
    cashbox = models.ForeignKey(
        "BuildingCashbox",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="treaty_installment_payments",
        verbose_name="Касса",
    )
    cashflow = models.ForeignKey(
        "BuildingCashFlow",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="treaty_installment_payments",
        verbose_name="Движение по кассе",
    )
    external_payment_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        verbose_name="Внешний ID платежа",
        help_text="Для идемпотентности (если передаётся).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_treaty_installment_payments_created",
        verbose_name="Кто провёл",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Оплата взноса рассрочки"
        verbose_name_plural = "Оплаты взносов рассрочки"
        ordering = ["-paid_at", "-created_at"]
        indexes = [
            models.Index(fields=["installment", "paid_at"]),
            models.Index(fields=["external_payment_id"]),
        ]

    def clean(self):
        super().clean()
        if self.amount is None or Decimal(self.amount or 0) <= 0:
            raise ValidationError({"amount": "Сумма должна быть > 0."})


class BuildingTreatyGroup(RemoteCompanyReferenceMixin, MPTTModel):
    """Группы/папки договоров (иерархия)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    residential_complex = models.ForeignKey(
        "ResidentialComplex",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="treaty_groups",
        verbose_name="ЖК (опционально)",
    )
    parent = TreeForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="children",
        verbose_name="Родительская папка",
    )
    title = models.CharField(max_length=255, verbose_name="Название")
    order = models.IntegerField(null=True, blank=True, verbose_name="Порядок")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class MPTTMeta:
        order_insertion_by = ["order", "title"]

    class Meta:
        verbose_name = "Папка договоров (Building)"
        verbose_name_plural = "Папки договоров (Building)"
        ordering = ["tree_id", "lft"]
        indexes = [
            models.Index(fields=["company_id", "is_active"]),
            models.Index(fields=["company_id", "residential_complex"]),
        ]

    def clean(self):
        super().clean()
        # Защита от циклов (MPTT тоже контролирует, но даём понятную ошибку).
        if self.parent_id and self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "Нельзя указать папку родителем самой себя."})

    def save(self, *args, **kwargs):
        self.title = (self.title or "").strip()
        super().save(*args, **kwargs)


class BuildingTreatyFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    treaty = models.ForeignKey(
        BuildingTreaty,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Договор",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_treaty_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_treaty_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл договора (Building)"
        verbose_name_plural = "Файлы договоров (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["treaty", "created_at"]),
        ]

    def __str__(self):
        return self.title or str(getattr(self.file, "name", "")) or str(self.id)


def building_work_entry_photo_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"building/work-entries/{instance.entry_id}/photos/{uuid.uuid4().hex}.{ext}"


class BuildingWorkEntry(models.Model):
    """
    Запись в "процессе работ" по ЖК.
    Мастера/прорабы/технадзор пишут свои работы, владелец видит весь процесс.
    """

    class Category(models.TextChoices):
        NOTE = "note", "Заметка"
        TREATY = "treaty", "Договор"
        DEFECT = "defect", "Недостатки/дефекты"
        REPORT = "report", "Отчёт"
        OTHER = "other", "Другое"

    class WorkStatus(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        IN_PROGRESS = "in_progress", "В работе"
        PAUSED = "paused", "Приостановлено"
        COMPLETED = "completed", "Завершено"
        CANCELLED = "cancelled", "Отменено"

    class PaymentMode(models.TextChoices):
        CASH = "cash", "Наличные"
        DEBT = "debt", "В долг"
        BARTER = "barter", "Бартер"
        MIXED = "mixed", "Смешанная"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="work_entries",
        verbose_name="Жилой комплекс",
    )
    contractor = models.ForeignKey(
        "BuildingContractor",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="work_entries",
        verbose_name="Подрядчик",
    )
    contract_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True, blank=True,
        verbose_name="Сумма договора",
    )
    contract_term_start = models.DateField(null=True, blank=True, verbose_name="Начало работ")
    contract_term_end = models.DateField(null=True, blank=True, verbose_name="Окончание работ")
    work_status = models.CharField(
        max_length=16,
        choices=WorkStatus.choices,
        default=WorkStatus.PLANNED,
        db_index=True,
        verbose_name="Статус работ",
    )
    client = models.ForeignKey(
        BuildingClient,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="work_entries",
        verbose_name="Клиент",
    )
    treaty = models.ForeignKey(
        BuildingTreaty,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="work_entries",
        verbose_name="Договор",
    )
    payment_mode = models.CharField(
        max_length=16,
        choices=PaymentMode.choices,
        default=PaymentMode.CASH,
        db_index=True,
        verbose_name="Режим оплаты",
    )
    treaty_auto_create = models.BooleanField(default=False, verbose_name="Автосоздать договор")
    treaty_type = models.CharField(max_length=32, blank=True, verbose_name="Тип создаваемого договора")
    treaty_title = models.CharField(max_length=255, blank=True, verbose_name="Название создаваемого договора")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_work_entries_created",
        verbose_name="Кто добавил",
    )
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.NOTE,
        db_index=True,
        verbose_name="Категория",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Описание")
    occurred_at = models.DateTimeField(default=timezone.now, verbose_name="Дата/время события")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Процесс работ: запись"
        verbose_name_plural = "Процесс работ: записи"
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["residential_complex", "occurred_at"]),
            models.Index(fields=["residential_complex", "category", "occurred_at"]),
            models.Index(fields=["created_by", "occurred_at"]),
            models.Index(fields=["contractor", "occurred_at"]),
            models.Index(fields=["work_status"]),
        ]

    def __str__(self):
        return self.title or f"{self.get_category_display()} ({self.residential_complex.name})"


class BuildingWorkEntryPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    entry = models.ForeignKey(
        BuildingWorkEntry,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Запись процесса работ",
    )
    image = models.ImageField(upload_to=building_work_entry_photo_upload_to, verbose_name="Фото")
    caption = models.CharField(max_length=255, blank=True, verbose_name="Подпись")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_work_entry_photos_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Фото процесса работ"
        verbose_name_plural = "Фото процесса работ"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entry", "created_at"]),
        ]


def building_work_entry_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/work-entries/{instance.entry_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingWorkEntryFile(models.Model):
    """Файл (документ), прикреплённый к записи процесса работ."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    entry = models.ForeignKey(
        BuildingWorkEntry,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Запись процесса работ",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_work_entry_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_work_entry_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл процесса работ"
        verbose_name_plural = "Файлы процесса работ"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entry", "created_at"]),
        ]


class BuildingTask(RemoteCompanyReferenceMixin, models.Model):
    """
    Напоминание/задача внутри компании (Building).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Открыта"
        DONE = "done", "Выполнена"
        CANCELLED = "cancelled", "Отменена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_tasks_created",
        verbose_name="Кто создал",
    )

    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
        verbose_name="Жилой комплекс",
    )
    client = models.ForeignKey(
        BuildingClient,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
        verbose_name="Клиент",
    )
    treaty = models.ForeignKey(
        BuildingTreaty,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
        verbose_name="Договор",
    )

    title = models.CharField(max_length=255, verbose_name="Задача")
    description = models.TextField(blank=True, verbose_name="Описание")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True, verbose_name="Статус")
    due_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Срок")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Выполнено")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Задача/напоминание (Building)"
        verbose_name_plural = "Задачи/напоминания (Building)"
        ordering = ["status", "due_at", "-created_at"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["company_id", "due_at"]),
            models.Index(fields=["company_id", "created_at"]),
        ]


def building_task_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/tasks/{instance.task_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingTaskFile(models.Model):
    """Файл, прикреплённый к задаче."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    task = models.ForeignKey(
        BuildingTask,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Задача",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_task_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_task_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл задачи (Building)"
        verbose_name_plural = "Файлы задач (Building)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task", "created_at"]),
        ]


class BuildingTaskAssignee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    task = models.ForeignKey(
        BuildingTask,
        on_delete=models.CASCADE,
        related_name="assignees",
        verbose_name="Задача",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="building_tasks_assigned",
        verbose_name="Сотрудник",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_task_assignees_added",
        verbose_name="Кто отметил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Исполнитель задачи (Building)"
        verbose_name_plural = "Исполнители задач (Building)"
        constraints = [
            models.UniqueConstraint(fields=["task", "user"], name="uq_building_task_assignee_task_user"),
        ]


class BuildingTaskChecklistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    task = models.ForeignKey(
        BuildingTask,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        verbose_name="Задача",
    )
    text = models.CharField(max_length=255, verbose_name="Пункт")
    is_done = models.BooleanField(default=False, db_index=True, verbose_name="Выполнено")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_task_checklist_done",
        verbose_name="Кто отметил",
    )
    done_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда отметил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Чек-лист задачи (Building)"
        verbose_name_plural = "Чек-листы задач (Building)"
        ordering = ["order", "created_at"]


class BuildingEmployeeCompensation(RemoteCompanyReferenceMixin, models.Model):
    class SalaryType(models.TextChoices):
        MONTHLY = "monthly", "Оклад (месяц)"
        MONTHLY_PLUS_PERCENT = "monthly_pct", "Оклад + % от продаж"
        DAILY = "daily", "Ставка (день)"
        HOURLY = "hourly", "Ставка (час)"

    class SaleCommissionType(models.TextChoices):
        NONE = "none", "Нет"
        FIXED = "fixed", "Фикс за сделку"
        PERCENT = "percent", "Процент от продажи"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="building_compensation",
        verbose_name="Сотрудник",
    )
    salary_type = models.CharField(max_length=16, choices=SalaryType.choices, default=SalaryType.MONTHLY, verbose_name="Тип оплаты")
    base_salary = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Оклад/ставка")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    notes = models.TextField(blank=True, verbose_name="Заметки")
    sale_commission_type = models.CharField(
        max_length=16,
        choices=SaleCommissionType.choices,
        default=SaleCommissionType.NONE,
        blank=True,
        verbose_name="Начисление от продаж: тип",
    )
    sale_commission_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True, blank=True,
        verbose_name="Начисление от продаж: значение (сумма или %)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "ЗП: настройки сотрудника (Building)"
        verbose_name_plural = "ЗП: настройки сотрудников (Building)"
        constraints = [
            models.UniqueConstraint(fields=["company_id", "user"], name="uq_building_compensation_company_user"),
        ]


class BuildingPayrollPeriod(RemoteCompanyReferenceMixin, models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        APPROVED = "approved", "Начислено"
        PAID = "paid", "Выплачено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    residential_complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.CASCADE,
        related_name="payroll_periods",
        null=True, blank=True,
        verbose_name="Жилой комплекс",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    period_start = models.DateField(verbose_name="Период с")
    period_end = models.DateField(verbose_name="Период по")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="Статус")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_payrolls_created",
        verbose_name="Кто создал",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_payrolls_approved",
        verbose_name="Кто начислил",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата начисления")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "ЗП: период начисления (Building)"
        verbose_name_plural = "ЗП: периоды начислений (Building)"
        ordering = ["-period_end", "-created_at"]


class BuildingPayrollLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    payroll = models.ForeignKey(
        BuildingPayrollPeriod,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Период",
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="building_payroll_lines",
        verbose_name="Сотрудник",
    )
    base_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Оклад/база")
    bonus_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Бонусы")
    deduction_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Удержания")
    advance_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Авансы")
    net_to_pay = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="К выплате")
    paid_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"), verbose_name="Выплачено")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "ЗП: строка начисления (Building)"
        verbose_name_plural = "ЗП: строки начислений (Building)"
        constraints = [
            models.UniqueConstraint(fields=["payroll", "employee"], name="uq_building_payroll_line_payroll_employee"),
        ]

    def recalculate_totals(self):
        a = self.adjustments.aggregate(
            bonus=Coalesce(Sum("amount", filter=models.Q(type=BuildingPayrollAdjustment.Type.BONUS)), Decimal("0.00")),
            deduction=Coalesce(Sum("amount", filter=models.Q(type=BuildingPayrollAdjustment.Type.DEDUCTION)), Decimal("0.00")),
            advance=Coalesce(
                Sum(
                    "amount",
                    filter=models.Q(
                        type=BuildingPayrollAdjustment.Type.ADVANCE,
                        status=BuildingPayrollAdjustment.Status.COMPLETED,
                    ),
                ),
                Decimal("0.00"),
            ),
        )
        bonus = a.get("bonus") or Decimal("0.00")
        deduction = a.get("deduction") or Decimal("0.00")
        advance = a.get("advance") or Decimal("0.00")
        net = (Decimal(self.base_amount or 0) + Decimal(bonus or 0) - Decimal(deduction or 0) - Decimal(advance or 0)).quantize(Decimal("0.01"))
        type(self).objects.filter(pk=self.pk).update(
            bonus_total=bonus,
            deduction_total=deduction,
            advance_total=advance,
            net_to_pay=net,
            updated_at=timezone.now(),
        )
        self.bonus_total = bonus
        self.deduction_total = deduction
        self.advance_total = advance
        self.net_to_pay = net
        return net

    def recalculate_paid_total(self):
        paid = self.payments.filter(status=BuildingPayrollPayment.Status.POSTED).aggregate(
            s=Coalesce(Sum("amount"), Decimal("0.00"))
        ).get("s") or Decimal("0.00")
        paid = Decimal(paid or 0).quantize(Decimal("0.01"))
        type(self).objects.filter(pk=self.pk).update(paid_total=paid, updated_at=timezone.now())
        self.paid_total = paid
        return paid


class BuildingPayrollAdjustment(models.Model):
    class Type(models.TextChoices):
        BONUS = "bonus", "Бонус"
        DEDUCTION = "deduction", "Удержание"
        ADVANCE = "advance", "Аванс"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        COMPLETED = "completed", "Проведено"
        REJECTED = "rejected", "Отклонено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    line = models.ForeignKey(
        BuildingPayrollLine,
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name="Строка начисления",
    )
    type = models.CharField(max_length=16, choices=Type.choices, db_index=True, verbose_name="Тип")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COMPLETED,
        db_index=True,
        verbose_name="Статус",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма")
    source_treaty = models.ForeignKey(
        BuildingTreaty,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="payroll_adjustments",
        verbose_name="Источник: договор",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_payroll_adjustments_created",
        verbose_name="Кто добавил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")


class BuildingPayrollPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает одобрения в кассе"
        POSTED = "posted", "Проведено"
        VOID = "void", "Отменено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    line = models.ForeignKey(
        BuildingPayrollLine,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Строка начисления",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма")
    paid_at = models.DateTimeField(default=timezone.now, verbose_name="Дата выплаты")
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_payroll_payments_made",
        verbose_name="Кто выплатил",
    )
    cashbox = models.ForeignKey(
        BuildingCashbox,
        on_delete=models.PROTECT,
        related_name="building_salary_payments",
        verbose_name="Касса",
    )
    cashflow = models.ForeignKey(
        BuildingCashFlow,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_salary_payments",
        verbose_name="Движение кассы",
    )
    advance_adjustment = models.ForeignKey(
        BuildingPayrollAdjustment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="payment",
        verbose_name="Аванс",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="Статус")
    void_reason = models.TextField(blank=True, verbose_name="Причина отмены")
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_payroll_payments_voided",
        verbose_name="Кто отменил",
    )
    voided_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда отменил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")


# -----------------------
# Долги (единый ledger AP/AR)
# -----------------------


def building_debt_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/debts/{instance.entry_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingDebtLedgerEntry(RemoteCompanyReferenceMixin, models.Model):
    class Direction(models.TextChoices):
        PAYABLE = "payable", "Мы должны"
        RECEIVABLE = "receivable", "Нам должны"

    class EntryType(models.TextChoices):
        CHARGE = "charge", "Начисление"
        PAYMENT = "payment", "Оплата"
        BARTER = "barter", "Бартер"
        ADJUSTMENT = "adjustment", "Корректировка"
        WRITEOFF = "writeoff", "Списание"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        APPROVED = "approved", "Подтверждено"
        CANCELLED = "cancelled", "Отменено"

    class CounterpartyType(models.TextChoices):
        CLIENT = "client", "Клиент"
        SUPPLIER = "supplier", "Поставщик"
        CONTRACTOR = "contractor", "Подрядчик"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    direction = models.CharField(max_length=16, choices=Direction.choices, db_index=True, verbose_name="Направление")
    counterparty_type = models.CharField(max_length=16, choices=CounterpartyType.choices, db_index=True, verbose_name="Тип контрагента")
    counterparty_id = models.UUIDField(db_index=True, verbose_name="ID контрагента")

    entry_type = models.CharField(max_length=16, choices=EntryType.choices, db_index=True, verbose_name="Тип записи")
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Сумма")
    currency = models.CharField(max_length=8, default="KGS", verbose_name="Валюта")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.APPROVED, db_index=True, verbose_name="Статус")

    residential_complex = models.ForeignKey(
        "ResidentialComplex",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="debt_entries",
        verbose_name="ЖК",
    )
    source_type = models.CharField(max_length=32, blank=True, db_index=True, verbose_name="Источник (тип)")
    source_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="Источник (id)")

    comment = models.TextField(blank=True, verbose_name="Комментарий")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Дата операции")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_debt_entries_created",
        verbose_name="Кто создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Долг: запись реестра"
        verbose_name_plural = "Долги: реестр"
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["company_id", "direction", "counterparty_type", "counterparty_id"]),
            models.Index(fields=["company_id", "status", "occurred_at"]),
        ]


class BuildingDebtLedgerFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    entry = models.ForeignKey(
        BuildingDebtLedgerEntry,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Запись реестра",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_debt_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_debt_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")


# -----------------------
# Бартер (унифицированные позиции)
# -----------------------


def building_barter_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/barter/{instance.source_type}/{instance.source_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingBarterItem(RemoteCompanyReferenceMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    title = models.CharField(max_length=255, verbose_name="Название")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True, verbose_name="Количество")
    unit = models.CharField(max_length=64, null=True, blank=True, verbose_name="Ед. изм.")
    unit_price = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True, verbose_name="Цена за ед.")
    total_price = models.DecimalField(max_digits=16, decimal_places=2, verbose_name="Итог (оценка)")
    currency = models.CharField(max_length=8, default="KGS", verbose_name="Валюта")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    source_type = models.CharField(max_length=32, db_index=True, verbose_name="Источник (тип)")
    source_id = models.UUIDField(db_index=True, verbose_name="Источник (id)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Бартер: позиция"
        verbose_name_plural = "Бартер: позиции"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "source_type", "source_id"]),
        ]


class BuildingBarterFile(RemoteCompanyReferenceMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    company_id = models.UUIDField(db_index=True, verbose_name="ID Компании")
    source_type = models.CharField(max_length=32, db_index=True, verbose_name="Источник (тип)")
    source_id = models.UUIDField(db_index=True, verbose_name="Источник (id)")
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_barter_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_barter_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")


# -----------------------
# АВР (акт выполненных работ) для WorkEntry
# -----------------------


def building_work_entry_acceptance_file_upload_to(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building/work-entry-acceptance/{instance.acceptance_id}/files/{uuid.uuid4().hex}.{ext}"


class BuildingWorkEntryAcceptance(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SIGNED = "signed", "Подписан"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    work_entry = models.OneToOneField(
        "BuildingWorkEntry",
        on_delete=models.CASCADE,
        related_name="acceptance",
        verbose_name="Процесс работ",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="Статус")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    signed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата подписания")

    class Meta:
        verbose_name = "АВР (акт выполненных работ)"
        verbose_name_plural = "АВР (акты выполненных работ)"


class BuildingWorkEntryAcceptanceFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")
    acceptance = models.ForeignKey(
        BuildingWorkEntryAcceptance,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="АВР",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название файла")
    file = models.FileField(upload_to=building_work_entry_acceptance_file_upload_to, verbose_name="Файл")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="building_work_entry_acceptance_files_created",
        verbose_name="Кто загрузил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Файл АВР"
        verbose_name_plural = "Файлы АВР"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["acceptance", "created_at"]),
        ]
