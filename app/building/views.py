from decimal import Decimal
import os
import requests

from django.db import transaction
from django.db.models import Q, Count, Case, When, Value, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.db.models.fields import CharField
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, filters, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    BuildingCashbox,
    BuildingCashFlow,
    BuildingCashFlowFile,
    BuildingCashRegisterRequest,
    BuildingCashRegisterRequestFile,
    BuildingContractor,
    BuildingContractorFile,
    BuildingSupplier,
    BuildingSupplierFile,
    BuildingSupplierBarterSettlement,
    BuildingTransferRequest,
    BuildingTransferRequestFile,
    BuildingWarehouseRequest,
    BuildingWarehouseRequestItem,
    BuildingReconciliationAct,
    BuildingReconciliationActItem,
    BuildingWarehouseMovement,
    BuildingWarehouseMovementItem,
    BuildingWarehouseMovementFile,
    BuildingWarehouseStockItem,
    ResidentialComplex,
    ResidentialComplexMember,
    ResidentialComplexDrawing,
    ResidentialComplexWarehouse,
    ResidentialComplexApartment,
    BuildingProduct,
    BuildingProcurementRequest,
    BuildingProcurementItem,
    BuildingProcurementFile,
    BuildingTransferRequest,
    BuildingWorkflowEvent,
    BuildingWarehouseStockItem,
    BuildingWarehouseStockMove,
    BuildingClient,
    BuildingClientFile,
    BuildingTaskFile,
    BuildingTreaty,
    BuildingTreatyInstallment,
    BuildingTreatyInstallmentPayment,
    BuildingTreatyGroup,
    BuildingTreatyFile,
    BuildingDebtLedgerEntry,
    BuildingDebtLedgerFile,
    BuildingBarterItem,
    BuildingBarterFile,
    BuildingWorkEntry,
    BuildingWorkEntryPhoto,
    BuildingWorkEntryFile,
    BuildingWorkEntryAcceptance,
    BuildingWorkEntryAcceptanceFile,
    BuildingTask,
    BuildingTaskChecklistItem,
    BuildingEmployeeCompensation,
    BuildingPayrollPeriod,
    BuildingPayrollLine,
    BuildingPayrollAdjustment,
    BuildingPayrollPayment,
)
from .serializers import (
    ResidentialComplexSerializer,
    ResidentialComplexCreateSerializer,
    ResidentialComplexMemberSerializer,
    ResidentialComplexMemberCreateSerializer,
    ResidentialComplexDrawingSerializer,
    ResidentialComplexWarehouseSerializer,
    ResidentialComplexApartmentSerializer,
    BuildingProductSerializer,
    BuildingProcurementSerializer,
    BuildingProcurementItemSerializer,
    BuildingTransferSerializer,
    BuildingWorkflowEventSerializer,
    BuildingWarehouseStockItemSerializer,
    BuildingWarehouseStockMoveSerializer,
    BuildingReasonSerializer,
    BuildingTransferCreateSerializer,
    BuildingTransferAcceptSerializer,
    BuildingPurchaseDocumentSerializer,
    BuildingClientSerializer,
    BuildingClientDetailSerializer,
    BuildingTreatySerializer,
    BuildingTreatyInstallmentSerializer,
    BuildingTreatyInstallmentPaymentCreateSerializer,
    BuildingTreatyFileCreateSerializer,
    BuildingTreatyGroupSerializer,
    BuildingTreatyGroupCreateUpdateSerializer,
    BuildingTreatyMoveSerializer,
    BuildingDebtLedgerEntrySerializer,
    BuildingDebtLedgerEntryCreateSerializer,
    BuildingDebtLedgerFileCreateSerializer,
    BuildingBarterItemSerializer,
    BuildingBarterItemUpsertSerializer,
    BuildingBarterFileSerializer,
    BuildingBarterFileCreateSerializer,
    BuildingWorkEntrySerializer,
    BuildingWorkEntryPhotoCreateSerializer,
    BuildingWorkEntryFileCreateSerializer,
    BuildingWorkEntryAcceptanceSerializer,
    BuildingWorkEntryAcceptanceUpsertSerializer,
    BuildingWorkEntryAcceptanceFileSerializer,
    BuildingWorkEntryAcceptanceFileCreateSerializer,
    BuildingTaskSerializer,
    BuildingTaskChecklistItemSerializer,
    BuildingTaskChecklistItemUpdateSerializer,
    BuildingSalaryEmployeeSerializer,
    BuildingEmployeeCompensationSerializer,
    BuildingPayrollPeriodSerializer,
    BuildingPayrollPeriodApproveSerializer,
    BuildingPayrollLineSerializer,
    BuildingPayrollLineCreateSerializer,
    BuildingPayrollAdjustmentSerializer,
    BuildingPayrollAdjustmentCreateSerializer,
    BuildingPayrollPaymentSerializer,
    BuildingPayrollPaymentCreateSerializer,
    BuildingPayrollPaymentApproveSerializer,
    BuildingPayrollMyLineSerializer,
    AdvanceRequestSerializer,
    AdvanceRequestApproveSerializer,
    BuildingCashboxSerializer,
    BuildingCashFlowSerializer,
    BuildingCashFlowBulkStatusSerializer,
    BuildingCashRegisterRequestSerializer,
    BuildingCashRegisterRequestCreateSerializer,
    BuildingCashRegisterRequestApproveSerializer,
    BuildingCashRegisterRequestRejectSerializer,
    BuildingCashRegisterRequestFileCreateSerializer,
    BuildingCashFlowFileSerializer,
    BuildingCashFlowFileCreateSerializer,
    BuildingContractorSerializer,
    BuildingContractorCreateSerializer,
    BuildingSupplierSerializer,
    BuildingSupplierCreateSerializer,
    BuildingSupplierBarterSettlementSerializer,
    BuildingSupplierBarterSettlementCreateUpdateSerializer,
    BuildingWarehouseRequestSerializer,
    BuildingWarehouseRequestCreateSerializer,
    BuildingReconciliationActSerializer,
    BuildingReconciliationActCreateSerializer,
    BuildingWarehouseMovementSerializer,
    BuildingWarehouseMovementWriteOffSerializer,
    BuildingWarehouseMovementTransferSerializer,
    BuildingPayrollPaymentApproveSerializer,
)
from . import services

User = get_user_model()


class CompanyQuerysetMixin:
    """Ограничение выборки объектами компании текущего пользователя."""

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        if user.is_authenticated and getattr(user, "company_id", None):
            field_names = {f.name for f in qs.model._meta.get_fields()}
            if "company" in field_names:
                return qs.filter(company_id=user.company_id)
            return qs
        return qs


def _is_owner_like(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) in ("owner", "admin"):
        return True
    if getattr(user, "owned_company_id", None):
        return True
    return False


def _can_access_task(user, task: BuildingTask) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or _is_owner_like(user):
        return True
    if task.created_by_id == getattr(user, "id", None):
        return True
    return task.assignees.filter(user_id=getattr(user, "id", None)).exists()


def _require_salary_perm(user):
    if _is_owner_like(user) or getattr(user, "is_superuser", False):
        return
    if not getattr(user, "can_view_building_salary", False):
        raise PermissionDenied("Нет прав на зарплату (Building).")


def _require_cash_register_perm(user):
    if _is_owner_like(user) or getattr(user, "is_superuser", False):
        return
    if not getattr(user, "can_view_building_cash_register", False):
        raise PermissionDenied("Нет прав кассы (Building).")


def _require_building_employees_perm(user):
    if _is_owner_like(user) or getattr(user, "is_superuser", False):
        return
    if not getattr(user, "can_view_building_employess", False) and not getattr(user, "can_view_employees", False):
        raise PermissionDenied("Нет прав на сотрудников (Building).")


def _allowed_residential_complex_ids(user):
    """
    owner/admin/superuser — None (доступ ко всем ЖК компании).
    Сотрудник с назначениями на ЖК — список id назначенных ЖК.
    Сотрудник без назначений — пустой список (ничего не показывать).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if _is_owner_like(user) or getattr(user, "is_superuser", False):
        return None
    company_id = getattr(user, "company_id", None)
    if not company_id:
        return None
    ids = list(
        ResidentialComplexMember.objects.filter(
            user_id=getattr(user, "id", None),
            is_active=True,
            residential_complex__company_id=company_id,
        ).values_list("residential_complex_id", flat=True)
    )
    # Сотрудник без назначений — возвращаем [] (доступ только к назначенным; пустой список = ничего)
    return ids

class ResidentialComplexListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """
    GET  /api/building/objects/  — список ЖК компании.
    POST /api/building/objects/  — создание ЖК (company из user).
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = ResidentialComplex.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ResidentialComplexCreateSerializer
        return ResidentialComplexSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            qs = qs.filter(id__in=allowed_ids)
        return qs


class ResidentialComplexDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/building/objects/<uuid>/
    PATCH  /api/building/objects/<uuid>/
    PUT    /api/building/objects/<uuid>/
    DELETE /api/building/objects/<uuid>/
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = ResidentialComplex.objects.all()
    serializer_class = ResidentialComplexSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            qs = qs.filter(id__in=allowed_ids)
        return qs


class ResidentialComplexMembersView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Назначения сотрудников на ЖК:
    - GET  /api/building/objects/<uuid:pk>/members/
    - POST /api/building/objects/<uuid:pk>/members/  {user, is_active?}
    - DELETE /api/building/objects/<uuid:pk>/members/<uuid:user_id>/
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = ResidentialComplex.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # назначениями управляют owner/admin/superuser или с правом employees
        if self.request.method in ("POST", "DELETE"):
            _require_building_employees_perm(user)
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            qs = qs.filter(id__in=allowed_ids)
        return qs

    def get(self, request, pk=None):
        rc = self.get_object()
        _require_building_employees_perm(request.user)
        memberships = (
            ResidentialComplexMember.objects
            .select_related("user", "added_by", "residential_complex")
            .filter(residential_complex=rc)
            .order_by("-created_at")
        )
        return Response(ResidentialComplexMemberSerializer(memberships, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk=None):
        rc = self.get_object()
        _require_building_employees_perm(request.user)
        ser = ResidentialComplexMemberCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        company_id = getattr(request.user, "company_id", None)
        user_obj = User.objects.filter(id=ser.validated_data["user"], company_id=company_id).first()
        if not user_obj:
            raise ValidationError({"user": "Сотрудник не найден (или другой компании)."})

        obj, _ = ResidentialComplexMember.objects.update_or_create(
            residential_complex=rc,
            user=user_obj,
            defaults={
                "is_active": bool(ser.validated_data.get("is_active", True)),
                "added_by": request.user,
            },
        )
        return Response(ResidentialComplexMemberSerializer(obj, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def delete(self, request, pk=None, user_id=None):
        rc = self.get_object()
        _require_building_employees_perm(request.user)
        ResidentialComplexMember.objects.filter(residential_complex=rc, user_id=user_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResidentialComplexDrawingListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """
    GET  /api/building/drawings/  — список чертежей ЖК компании.
    POST /api/building/drawings/  — создание чертежа и привязка к ЖК.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexDrawingSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = ResidentialComplexDrawing.objects.select_related("residential_complex")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["residential_complex", "is_active"]
    search_fields = ["title", "description", "residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        rc = serializer.validated_data["residential_complex"]
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        serializer.save()


class ResidentialComplexDrawingDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/building/drawings/<uuid>/
    PATCH  /api/building/drawings/<uuid>/
    PUT    /api/building/drawings/<uuid>/
    DELETE /api/building/drawings/<uuid>/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexDrawingSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = ResidentialComplexDrawing.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class ResidentialComplexWarehouseListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexWarehouseSerializer
    queryset = ResidentialComplexWarehouse.objects.select_related("residential_complex")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["residential_complex", "is_active"]
    search_fields = ["name", "residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        residential_complex = serializer.validated_data["residential_complex"]
        user = self.request.user
        if not getattr(user, "is_superuser", False) and residential_complex.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and residential_complex.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        serializer.save()


class ResidentialComplexWarehouseDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexWarehouseSerializer
    queryset = ResidentialComplexWarehouse.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class ResidentialComplexApartmentListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """
    Квартиры ЖК:
    GET  /api/building/apartments/
    POST /api/building/apartments/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexApartmentSerializer
    queryset = ResidentialComplexApartment.objects.select_related("residential_complex").prefetch_related(
        "treaties__client"
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"residential_complex": ["exact"], "floor": ["exact"], "status": ["exact"], "block": ["exact", "in"]}
    search_fields = ["number", "notes"]

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на продажи/договора (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на продажи/договора (Building).")
        rc = serializer.validated_data["residential_complex"]
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        serializer.save()


class ResidentialComplexApartmentDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/PUT/DELETE /api/building/apartments/<uuid>/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResidentialComplexApartmentSerializer
    queryset = ResidentialComplexApartment.objects.select_related("residential_complex").prefetch_related(
        "treaties__client"
    )

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на продажи/договора (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class ResidentialComplexFloorsView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Этажи по ЖК (для шага выбора этаж → квартира):
    GET /api/building/objects/<uuid:pk>/floors/
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = ResidentialComplex.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def get(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на продажи/договора (Building).")

        rc = self.get_object()
        qs = (
            ResidentialComplexApartment.objects.filter(residential_complex=rc)
            .values("floor")
            .annotate(
                total=Count("id"),
                available=Count("id", filter=Q(status=ResidentialComplexApartment.Status.AVAILABLE)),
                reserved=Count("id", filter=Q(status=ResidentialComplexApartment.Status.RESERVED)),
                sold=Count("id", filter=Q(status=ResidentialComplexApartment.Status.SOLD)),
            )
            .order_by("floor")
        )
        return Response(list(qs), status=status.HTTP_200_OK)


class ResidentialComplexBlocksStatsView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Статистика по блокам (аналогично этажам):
    GET /api/building/objects/<uuid:pk>/blocks/stats/
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = ResidentialComplex.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def get(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на продажи/договора (Building).")

        rc = self.get_object()
        qs = (
            ResidentialComplexApartment.objects.filter(residential_complex=rc)
            .exclude(block__isnull=True)
            .exclude(block__exact="")
            .values("block")
            .annotate(
                total=Count("id"),
                available=Count("id", filter=Q(status=ResidentialComplexApartment.Status.AVAILABLE)),
                reserved=Count("id", filter=Q(status=ResidentialComplexApartment.Status.RESERVED)),
                sold=Count("id", filter=Q(status=ResidentialComplexApartment.Status.SOLD)),
            )
            .order_by("block")
        )
        return Response(list(qs), status=status.HTTP_200_OK)

class BuildingProductListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProductSerializer
    queryset = BuildingProduct.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "article", "barcode", "unit"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            return qs.filter(company_id=user.company_id)
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        serializer.save(company_id=company_id)


class BuildingProductDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProductSerializer
    queryset = BuildingProduct.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            return qs.filter(company_id=user.company_id)
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingProcurementListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex", "initiator", "supplier").prefetch_related("items", "files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["residential_complex", "status"]
    search_fields = ["title", "comment", "residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        rc = serializer.validated_data["residential_complex"]
        user = self.request.user
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        serializer.save(initiator=user)
        services.log_event(action="procurement_created", actor=user, procurement=serializer.instance)


class BuildingProcurementDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex", "initiator", "supplier").prefetch_related("items", "files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingProcurementFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к закупке."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_procurement", False)):
            raise PermissionDenied("Нет прав на закупки (Building).")
        procurement = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pf = BuildingProcurementFile.objects.create(
            procurement=procurement,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=user,
        )
        # Автосоздание договора из файлов (двухшаговый сценарий)
        try:
            if getattr(procurement, "treaty_auto_create", False) and not procurement.treaty_id:
                t_type = (getattr(procurement, "treaty_type", "") or "").strip() or BuildingTreaty.TreatyType.PROCUREMENT
                t_title = (getattr(procurement, "treaty_title", "") or "").strip() or (procurement.title or "Договор закупки")
                treaty = BuildingTreaty.objects.create(
                    residential_complex=procurement.residential_complex,
                    client=None,
                    title=t_title,
                    description="",
                    amount=Decimal(procurement.total_amount or 0).quantize(Decimal("0.01")),
                    treaty_type=t_type,
                    operation_type=BuildingTreaty.OperationType.OTHER,
                    payment_type=BuildingTreaty.PaymentType.FULL,
                    payment_mode=BuildingTreaty.PaymentMode.CASH,
                    created_by=user,
                )
                BuildingTreatyFile.objects.create(
                    treaty=treaty,
                    file=pf.file,
                    title=pf.title or "",
                    created_by=user,
                )
                procurement.treaty = treaty
                procurement.save(update_fields=["treaty", "updated_at"])
            elif procurement.treaty_id:
                # Если договор уже выбран/создан — поднимаем файл в договор (для аудита)
                BuildingTreatyFile.objects.create(
                    treaty=procurement.treaty,
                    file=pf.file,
                    title=pf.title or "",
                    created_by=user,
                )
        except Exception:
            pass
        procurement.refresh_from_db()
        return Response(
            BuildingProcurementSerializer(procurement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingProcurementItemListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementItemSerializer
    queryset = BuildingProcurementItem.objects.select_related("procurement", "procurement__residential_complex")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["procurement"]
    search_fields = ["name", "unit", "note"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(procurement__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(procurement__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        procurement = serializer.validated_data["procurement"]
        user = self.request.user
        if procurement.status != BuildingProcurementRequest.Status.DRAFT:
            raise PermissionDenied("Позиции можно добавлять только в черновик.")
        if not getattr(user, "is_superuser", False) and procurement.residential_complex.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Закупка другой компании.")
        serializer.save()
        item = serializer.instance
        services.log_event(
            action="procurement_item_created",
            actor=user,
            procurement=procurement,
            procurement_item=item,
            payload={
                "name": item.name,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "price": str(item.price),
                "line_total": str(item.line_total),
            },
        )


class BuildingProcurementItemDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementItemSerializer
    queryset = BuildingProcurementItem.objects.select_related("procurement", "procurement__residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(procurement__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(procurement__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_update(self, serializer):
        item = self.get_object()
        if item.procurement.status != BuildingProcurementRequest.Status.DRAFT:
            raise PermissionDenied("Позиции можно менять только в черновике.")
        serializer.save()
        item.refresh_from_db()
        services.log_event(
            action="procurement_item_updated",
            actor=self.request.user,
            procurement=item.procurement,
            procurement_item=item,
            payload={
                "name": item.name,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "price": str(item.price),
                "line_total": str(item.line_total),
            },
        )

    def perform_destroy(self, instance):
        if instance.procurement.status != BuildingProcurementRequest.Status.DRAFT:
            raise PermissionDenied("Позиции можно удалять только из черновика.")
        services.log_event(
            action="procurement_item_deleted",
            actor=self.request.user,
            procurement=instance.procurement,
            procurement_item=instance,
            payload={"name": instance.name, "unit": instance.unit, "quantity": str(instance.quantity)},
        )
        instance.delete()


class BuildingProcurementSubmitToCashView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        procurement = self.get_object()
        services.submit_procurement_to_cash(procurement, request.user)
        procurement.refresh_from_db()
        return Response(self.get_serializer(procurement).data, status=status.HTTP_200_OK)


class BuildingCashPendingProcurementListView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex", "initiator", "supplier").prefetch_related("items", "files")

    def get_queryset(self):
        qs = super().get_queryset().filter(status=BuildingProcurementRequest.Status.SUBMITTED_TO_CASH)
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingCashApproveProcurementView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        procurement = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        services.approve_procurement_cash(procurement, request.user, reason=reason)
        procurement.refresh_from_db()
        return Response(self.get_serializer(procurement).data, status=status.HTTP_200_OK)


class BuildingCashRejectProcurementView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        procurement = self.get_object()
        ser = BuildingReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.reject_procurement_cash(procurement, request.user, reason=ser.validated_data["reason"])
        procurement.refresh_from_db()
        return Response(self.get_serializer(procurement).data, status=status.HTTP_200_OK)


class BuildingTransferCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTransferSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        procurement = self.get_object()
        ser = BuildingTransferCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        transfer = services.create_transfer_from_procurement(procurement, request.user, note=ser.validated_data.get("note", ""))
        return Response(BuildingTransferSerializer(transfer, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingTransferListView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTransferSerializer
    queryset = BuildingTransferRequest.objects.select_related(
        "procurement",
        "procurement__residential_complex",
        "warehouse",
        "created_by",
        "decided_by",
    ).prefetch_related("items", "files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "warehouse", "procurement"]
    search_fields = ["note", "warehouse__name", "procurement__title", "procurement__residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        incoming_only = self.request.query_params.get("incoming")
        if incoming_only in ("1", "true", "True"):
            qs = qs.filter(status=BuildingTransferRequest.Status.PENDING_RECEIPT)
        return qs


class BuildingTransferDetailView(CompanyQuerysetMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTransferSerializer
    queryset = BuildingTransferRequest.objects.select_related(
        "procurement",
        "procurement__residential_complex",
        "warehouse",
        "created_by",
        "decided_by",
    ).prefetch_related("items", "files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingTransferAcceptView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTransferSerializer
    queryset = BuildingTransferRequest.objects.select_related("warehouse", "warehouse__residential_complex", "procurement")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        transfer = self.get_object()
        ser = BuildingTransferAcceptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.accept_transfer(transfer, request.user, note=ser.validated_data.get("note", ""))
        transfer.refresh_from_db()
        return Response(self.get_serializer(transfer).data, status=status.HTTP_200_OK)


class BuildingTransferRejectView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTransferSerializer
    queryset = BuildingTransferRequest.objects.select_related("warehouse", "warehouse__residential_complex", "procurement")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        transfer = self.get_object()
        ser = BuildingReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.reject_transfer(transfer, request.user, reason=ser.validated_data["reason"])
        transfer.refresh_from_db()
        return Response(self.get_serializer(transfer).data, status=status.HTTP_200_OK)


class BuildingTransferFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к передаче на склад (warehouse-receipt)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingTransferRequest.objects.select_related("warehouse__residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_procurement", False)):
            raise PermissionDenied("Нет прав на закупки/склад (Building).")
        transfer = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingTransferRequestFile.objects.create(
            transfer=transfer,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        transfer.refresh_from_db()
        return Response(
            BuildingTransferSerializer(transfer, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# -----------------------
# Contractors
# -----------------------


class BuildingContractorListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingContractorSerializer
    queryset = BuildingContractor.objects.prefetch_related("files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "contractor_type"]
    search_fields = ["company_name", "contact_person", "phone", "email"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BuildingContractorCreateSerializer
        return BuildingContractorSerializer


class BuildingContractorDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingContractorSerializer
    queryset = BuildingContractor.objects.prefetch_related("files")


class BuildingContractorFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingContractor.objects.all()

    def post(self, request, pk=None):
        contractor = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingContractorFile.objects.create(
            contractor=contractor,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        contractor.refresh_from_db()
        return Response(
            BuildingContractorSerializer(contractor, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingContractorWorkHistoryView(CompanyQuerysetMixin, generics.ListAPIView):
    """История процессов работ подрядчика."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntrySerializer
    queryset = BuildingWorkEntry.objects.select_related(
        "residential_complex", "client", "treaty", "contractor", "created_by"
    ).prefetch_related("photos", "files")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["residential_complex", "work_status"]

    def get_queryset(self):
        qs = super().get_queryset()
        contractor_id = self.kwargs.get("pk")
        qs = qs.filter(contractor_id=contractor_id)
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


# -----------------------
# Suppliers
# -----------------------


class BuildingSupplierListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierSerializer
    queryset = BuildingSupplier.objects.prefetch_related("files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "supplier_type"]
    search_fields = ["company_name", "contact_person", "phone", "email"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BuildingSupplierCreateSerializer
        return BuildingSupplierSerializer


class BuildingSupplierDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierSerializer
    queryset = BuildingSupplier.objects.prefetch_related("files")


class BuildingSupplierFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingSupplier.objects.all()

    def post(self, request, pk=None):
        supplier = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingSupplierFile.objects.create(
            supplier=supplier,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        supplier.refresh_from_db()
        return Response(
            BuildingSupplierSerializer(supplier, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingSupplierPurchaseHistoryView(CompanyQuerysetMixin, generics.ListAPIView):
    """История закупок поставщика."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingProcurementSerializer
    queryset = BuildingProcurementRequest.objects.select_related(
        "residential_complex", "initiator"
    ).prefetch_related("items", "files")
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        qs = super().get_queryset()
        supplier_id = self.kwargs.get("pk")
        qs = qs.filter(supplier_id=supplier_id)
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingSupplierBarterSettlementListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """Список и создание бартерных зачётов (поставщик или подрядчик)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierBarterSettlementSerializer
    queryset = BuildingSupplierBarterSettlement.objects.select_related(
        "supplier",
        "contractor",
        "residential_complex",
        "created_by",
    )
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["supplier", "contractor", "residential_complex", "status", "date"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BuildingSupplierBarterSettlementCreateUpdateSerializer
        return BuildingSupplierBarterSettlementSerializer


class BuildingSupplierBarterSettlementDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """Детали/редактирование/удаление бартерного зачёта."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierBarterSettlementSerializer
    queryset = BuildingSupplierBarterSettlement.objects.select_related(
        "supplier",
        "contractor",
        "residential_complex",
        "created_by",
    ).prefetch_related("purchase_items", "counter_deliveries")

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return BuildingSupplierBarterSettlementCreateUpdateSerializer
        return BuildingSupplierBarterSettlementSerializer

    def perform_destroy(self, instance):
        if instance.status != BuildingSupplierBarterSettlement.Status.DRAFT:
            raise PermissionDenied("Удалять можно только бартерный зачёт в статусе draft.")
        return super().perform_destroy(instance)


class BuildingSupplierBarterSettlementConfirmView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Подтверждение бартерного зачёта (фиксируем как проведённый)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierBarterSettlementSerializer
    queryset = BuildingSupplierBarterSettlement.objects.select_related(
        "supplier", "contractor", "residential_complex"
    )

    @transaction.atomic
    def post(self, request, pk=None):
        settlement = self.get_object()
        if settlement.status != BuildingSupplierBarterSettlement.Status.DRAFT:
            return Response(
                {"status": ["Подтвердить можно только зачёт в статусе draft."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if settlement.amount_total and Decimal(str(settlement.amount_total)) > 0:
            counterparty_type = (
                BuildingDebtLedgerEntry.CounterpartyType.CONTRACTOR
                if settlement.contractor_id
                else BuildingDebtLedgerEntry.CounterpartyType.SUPPLIER
            )
            counterparty_id = settlement.contractor_id or settlement.supplier_id
            BuildingDebtLedgerEntry.objects.create(
                company_id=settlement.company_id,
                direction=BuildingDebtLedgerEntry.Direction.PAYABLE,
                counterparty_type=counterparty_type,
                counterparty_id=counterparty_id,
                entry_type=BuildingDebtLedgerEntry.EntryType.BARTER,
                amount=Decimal(str(settlement.amount_total)).quantize(Decimal("0.01")),
                currency=(settlement.currency or "KGS")[:8],
                status=BuildingDebtLedgerEntry.Status.APPROVED,
                residential_complex=settlement.residential_complex,
                source_type="barter_settlement",
                source_id=settlement.id,
                comment=(settlement.comment or f"Бартерный зачёт {settlement.id}")[:1024],
                occurred_at=timezone.now(),
                created_by=request.user if request.user.is_authenticated else None,
            )
        settlement.status = BuildingSupplierBarterSettlement.Status.CONFIRMED
        settlement.save(update_fields=["status", "updated_at"])
        settlement.refresh_from_db()
        return Response(
            BuildingSupplierBarterSettlementSerializer(settlement, context={"request": request}).data
        )


class BuildingSupplierBarterSettlementCancelView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Отмена бартерного зачёта."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSupplierBarterSettlementSerializer
    queryset = BuildingSupplierBarterSettlement.objects.select_related("supplier", "contractor", "residential_complex")

    def post(self, request, pk=None):
        settlement = self.get_object()
        if settlement.status == BuildingSupplierBarterSettlement.Status.CANCELLED:
            return Response(
                BuildingSupplierBarterSettlementSerializer(settlement, context={"request": request}).data
            )
        if settlement.status != BuildingSupplierBarterSettlement.Status.DRAFT:
            return Response(
                {"status": ["Отменить можно только зачёт в статусе draft."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        settlement.status = BuildingSupplierBarterSettlement.Status.CANCELLED
        settlement.save(update_fields=["status", "updated_at"])
        return Response(
            BuildingSupplierBarterSettlementSerializer(settlement, context={"request": request}).data
        )


class BuildingWorkflowEventListView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkflowEventSerializer
    queryset = BuildingWorkflowEvent.objects.select_related(
        "procurement",
        "transfer",
        "warehouse",
        "stock_item",
        "actor",
        "procurement_item",
        "transfer_item",
    )
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["procurement", "procurement_item", "transfer", "transfer_item", "warehouse", "stock_item", "action"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(procurement__residential_complex__company_id=user.company_id)
                | Q(transfer__warehouse__residential_complex__company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(procurement__residential_complex_id__in=allowed_ids)
                    | Q(transfer__warehouse__residential_complex_id__in=allowed_ids)
                )
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingWarehouseStockItemListView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseStockItemSerializer
    queryset = BuildingWarehouseStockItem.objects.select_related("warehouse", "warehouse__residential_complex")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["warehouse"]
    search_fields = ["name", "unit", "warehouse__name", "warehouse__residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingWarehouseStockMoveListView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseStockMoveSerializer
    queryset = BuildingWarehouseStockMove.objects.select_related(
        "warehouse",
        "warehouse__residential_complex",
        "stock_item",
        "transfer",
        "created_by",
    )
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["warehouse", "stock_item", "transfer", "move_type"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingPurchaseDocumentListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """
    Совместимый с warehouse формат закупок:
    GET/POST /api/building/documents/purchase/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPurchaseDocumentSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex", "initiator", "supplier").prefetch_related("items", "files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "residential_complex"]
    search_fields = ["comment", "title", "residential_complex__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        rc = serializer.validated_data["residential_complex"]
        user = self.request.user
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        doc = serializer.save()
        services.log_event(action="procurement_created", actor=user, procurement=doc)


class BuildingPurchaseDocumentDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Совместимый с warehouse формат закупки:
    GET/PATCH/PUT/DELETE /api/building/documents/purchase/<uuid:pk>/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPurchaseDocumentSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex", "initiator", "supplier").prefetch_related("items", "files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingPurchaseDocumentCashApproveView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPurchaseDocumentSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        doc = self.get_object()
        reason = (request.data.get("note") or request.data.get("reason") or "").strip()
        if doc.status == BuildingProcurementRequest.Status.DRAFT:
            services.submit_procurement_to_cash(doc, request.user)
            doc.refresh_from_db()
        services.approve_procurement_cash(doc, request.user, reason=reason)
        doc.refresh_from_db()
        return Response(self.get_serializer(doc).data, status=status.HTTP_200_OK)


class BuildingPurchaseDocumentCashRejectView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPurchaseDocumentSerializer
    queryset = BuildingProcurementRequest.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        doc = self.get_object()
        reason = (request.data.get("note") or request.data.get("reason") or "").strip()
        if not reason:
            return Response({"reason": ["Укажите причину отказа."]}, status=status.HTTP_400_BAD_REQUEST)
        if doc.status == BuildingProcurementRequest.Status.DRAFT:
            services.submit_procurement_to_cash(doc, request.user)
            doc.refresh_from_db()
        services.reject_procurement_cash(doc, request.user, reason=reason)
        doc.refresh_from_db()
        return Response(self.get_serializer(doc).data, status=status.HTTP_200_OK)


class BuildingWorkEntryListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntrySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = BuildingWorkEntry.objects.select_related(
        "residential_complex",
        "client",
        "treaty",
        "contractor",
        "created_by",
    ).prefetch_related("photos", "files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["residential_complex", "category", "created_by", "client", "treaty", "contractor", "work_status"]
    search_fields = ["title", "description", "residential_complex__name", "client__name", "treaty__number"]

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")

        rc = serializer.validated_data["residential_complex"]
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")

        client = serializer.validated_data.get("client")
        if client and client.company_id != rc.company_id:
            raise PermissionDenied("Клиент принадлежит другой компании.")

        treaty = serializer.validated_data.get("treaty")
        if treaty and treaty.residential_complex.company_id != rc.company_id:
            raise PermissionDenied("Договор принадлежит другой компании.")

        serializer.save(created_by=user)
        entry = serializer.instance
        # При создании можно приложить несколько фото и файлов (multipart: photos[], files[])
        for img in self.request.FILES.getlist("photos"):
            BuildingWorkEntryPhoto.objects.create(entry=entry, image=img, caption="", created_by=user)
        for f in self.request.FILES.getlist("files"):
            BuildingWorkEntryFile.objects.create(entry=entry, file=f, title="", created_by=user)


class BuildingWorkEntryDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntrySerializer
    queryset = BuildingWorkEntry.objects.select_related(
        "residential_complex",
        "client",
        "treaty",
        "contractor",
        "created_by",
    ).prefetch_related("photos", "files")

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_update(self, serializer):
        user = self.request.user
        obj = self.get_object()
        if not (_is_owner_like(user) or obj.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Изменять запись может только автор или владелец.")

        rc = serializer.validated_data.get("residential_complex") or obj.residential_complex
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")

        client = serializer.validated_data.get("client")
        if client and client.company_id != rc.company_id:
            raise PermissionDenied("Клиент принадлежит другой компании.")

        treaty = serializer.validated_data.get("treaty")
        if treaty and treaty.residential_complex.company_id != rc.company_id:
            raise PermissionDenied("Договор принадлежит другой компании.")

        old_status = obj.work_status
        serializer.save()

        new_status = serializer.instance.work_status
        if (
            old_status != BuildingWorkEntry.WorkStatus.COMPLETED
            and new_status == BuildingWorkEntry.WorkStatus.COMPLETED
            and serializer.instance.contractor_id
            and serializer.instance.contract_amount
        ):
            # Автоматически создаём черновик АВР
            try:
                BuildingWorkEntryAcceptance.objects.get_or_create(work_entry=serializer.instance)
            except Exception:
                pass

            # Процесс работ "в долг": создаём запись долга (мы должны подрядчику)
            try:
                if getattr(serializer.instance, "payment_mode", None) in ("debt", "mixed", "barter"):
                    BuildingDebtLedgerEntry.objects.create(
                        company_id=rc.company_id,
                        direction=BuildingDebtLedgerEntry.Direction.PAYABLE,
                        counterparty_type=BuildingDebtLedgerEntry.CounterpartyType.CONTRACTOR,
                        counterparty_id=serializer.instance.contractor_id,
                        entry_type=BuildingDebtLedgerEntry.EntryType.CHARGE,
                        amount=serializer.instance.contract_amount,
                        currency="KGS",
                        status=BuildingDebtLedgerEntry.Status.APPROVED,
                        residential_complex=rc,
                        source_type="work_entry",
                        source_id=serializer.instance.id,
                        comment=f"Работы в долг: {serializer.instance.title or serializer.instance.id}",
                        occurred_at=timezone.now(),
                        created_by=user,
                    )
            except Exception:
                pass

            if getattr(serializer.instance, "payment_mode", None) != "barter" and not BuildingCashRegisterRequest.objects.filter(
                work_entry=serializer.instance,
                request_type=BuildingCashRegisterRequest.RequestType.CONTRACTOR_PAYMENT,
            ).exists():
                cashbox = rc.salary_cashbox or BuildingCashbox.objects.filter(
                    company_id=rc.company_id
                ).first()
                if cashbox:
                    BuildingCashRegisterRequest.objects.create(
                        company_id=rc.company_id,
                        work_entry=serializer.instance,
                        request_type=BuildingCashRegisterRequest.RequestType.CONTRACTOR_PAYMENT,
                        status=BuildingCashRegisterRequest.Status.PENDING,
                        amount=serializer.instance.contract_amount,
                        comment=f"Оплата подрядчику по процессу работ: {serializer.instance.title or serializer.instance.id}",
                        cashbox=cashbox,
                        contractor=serializer.instance.contractor,
                        residential_complex=rc,
                        created_by=user,
                    )

    def perform_destroy(self, instance):
        user = self.request.user
        if not (_is_owner_like(user) or instance.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Удалять запись может только автор или владелец.")
        instance.delete()


class BuildingWorkEntryPhotoAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntryPhotoCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingWorkEntry.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")

        entry = self.get_object()
        if not getattr(user, "is_superuser", False) and entry.residential_complex.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")

        # Несколько фото: photos[] или одно image (обратная совместимость)
        images = request.FILES.getlist("photos") or ([request.FILES.get("image")] if request.FILES.get("image") else [])
        if not images:
            raise ValidationError({"photos": "Нужно хотя бы одно фото (photos или image)."})

        caption = (request.data.get("caption") or "").strip()
        for img in images:
            BuildingWorkEntryPhoto.objects.create(
                entry=entry,
                image=img,
                caption=caption,
                created_by=user,
            )
        entry.refresh_from_db()
        return Response(BuildingWorkEntrySerializer(entry, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingWorkEntryFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Добавление одного или нескольких файлов к записи процесса работ."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntryFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingWorkEntry.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")

        entry = self.get_object()
        if not getattr(user, "is_superuser", False) and entry.residential_complex.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")

        uploaded = request.FILES.getlist("files") or ([request.FILES.get("file")] if request.FILES.get("file") else [])
        if not uploaded:
            raise ValidationError({"files": "Нужен хотя бы один файл (files или file)."})

        created_files = []
        for f in uploaded:
            created_files.append(BuildingWorkEntryFile.objects.create(entry=entry, file=f, title="", created_by=user))

        # Автосоздание/поднятие договора из файлов
        try:
            if getattr(entry, "treaty_auto_create", False) and not entry.treaty_id:
                t_type = (getattr(entry, "treaty_type", "") or "").strip() or BuildingTreaty.TreatyType.CONSTRUCTION_DEPARTMENT
                t_title = (getattr(entry, "treaty_title", "") or "").strip() or (entry.title or "Договор по работам")
                treaty = BuildingTreaty.objects.create(
                    residential_complex=entry.residential_complex,
                    client=entry.client,
                    title=t_title,
                    description="",
                    amount=Decimal(entry.contract_amount or 0).quantize(Decimal("0.01")) if entry.contract_amount else Decimal("0.00"),
                    treaty_type=t_type,
                    operation_type=BuildingTreaty.OperationType.OTHER,
                    payment_type=BuildingTreaty.PaymentType.FULL,
                    payment_mode=BuildingTreaty.PaymentMode.CASH,
                    created_by=user,
                )
                for wf in created_files:
                    BuildingTreatyFile.objects.create(treaty=treaty, file=wf.file, title=wf.title or "", created_by=user)
                entry.treaty = treaty
                entry.save(update_fields=["treaty", "updated_at"])
            elif entry.treaty_id:
                for wf in created_files:
                    BuildingTreatyFile.objects.create(treaty=entry.treaty, file=wf.file, title=wf.title or "", created_by=user)
        except Exception:
            pass
        entry.refresh_from_db()
        return Response(BuildingWorkEntrySerializer(entry, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingWorkEntryWarehouseRequestCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Создать заявку на выдачу материалов со склада из процесса работ."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseRequestCreateSerializer
    queryset = BuildingWorkEntry.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работ (Building).")
        entry = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        warehouse = ResidentialComplexWarehouse.objects.filter(
            id=ser.validated_data["warehouse"]
        ).filter(residential_complex=entry.residential_complex).first()
        if not warehouse:
            raise ValidationError({"warehouse": "Склад не найден или не принадлежит ЖК процесса работ."})
        with transaction.atomic():
            req = BuildingWarehouseRequest.objects.create(
                work_entry=entry,
                warehouse=warehouse,
                comment=ser.validated_data.get("comment", ""),
                status=BuildingWarehouseRequest.Status.PENDING,
                created_by=request.user,
            )
            for item in ser.validated_data["items"]:
                stock_item = BuildingWarehouseStockItem.objects.get(id=item["stock_item"])
                if stock_item.warehouse_id != warehouse.id:
                    raise ValidationError({"items": f"Позиция {stock_item.name} не принадлежит выбранному складу."})
                BuildingWarehouseRequestItem.objects.create(
                    request=req,
                    stock_item=stock_item,
                    quantity=item["quantity"],
                    unit=item.get("unit", "шт"),
                )
        req.refresh_from_db()
        return Response(
            BuildingWarehouseRequestSerializer(req, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingWarehouseRequestListView(CompanyQuerysetMixin, generics.ListAPIView):
    """
    Список заявок на материалы для склада.
    GET /work-entries/warehouse-requests/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseRequestSerializer
    queryset = BuildingWarehouseRequest.objects.select_related(
        "work_entry",
        "work_entry__residential_complex",
        "warehouse",
    ).prefetch_related(
        "items",
        "items__stock_item",
    )
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["warehouse", "status", "work_entry"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()

        # Дополнительный фильтр по ЖК
        rc = self.request.query_params.get("residential_complex")
        if rc:
            qs = qs.filter(warehouse__residential_complex_id=rc)
        return qs


class BuildingWarehouseRequestDetailView(CompanyQuerysetMixin, generics.RetrieveAPIView):
    """
    Детали заявки на материалы.
    GET /work-entries/warehouse-requests/{id}/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseRequestSerializer
    queryset = BuildingWarehouseRequest.objects.select_related(
        "work_entry",
        "work_entry__residential_complex",
        "warehouse",
    ).prefetch_related(
        "items",
        "items__stock_item",
        "movements",
    )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(warehouse__residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(warehouse__residential_complex_id__in=allowed_ids)
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingWorkEntryReconciliationActCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Создать акт сверки материалов при завершении/отмене процесса работ."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingReconciliationActCreateSerializer
    queryset = BuildingWorkEntry.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работ (Building).")
        entry = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            act = BuildingReconciliationAct.objects.create(
                work_entry=entry,
                comment=ser.validated_data.get("comment", ""),
                status=BuildingReconciliationAct.Status.DRAFT,
                created_by=request.user,
            )
            for item in ser.validated_data["returned_items"]:
                stock_item = BuildingWarehouseStockItem.objects.get(id=item["stock_item"])
                BuildingReconciliationActItem.objects.create(
                    act=act,
                    stock_item=stock_item,
                    quantity=item["quantity"],
                    unit=item.get("unit", "шт"),
                )
        act.refresh_from_db()
        return Response(
            BuildingReconciliationActSerializer(act, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# -----------------------
# Warehouse movements (write-off, transfer)
# -----------------------


class BuildingWarehouseMovementWriteOffView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Списание со склада."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseMovementWriteOffSerializer
    queryset = ResidentialComplexWarehouse.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        warehouse = ResidentialComplexWarehouse.objects.filter(
            id=ser.validated_data["warehouse"]
        ).first()
        if not warehouse or warehouse not in self.get_queryset():
            raise ValidationError({"warehouse": "Склад не найден."})
        company = warehouse.residential_complex.company
        with transaction.atomic():
            movement = BuildingWarehouseMovement.objects.create(
                company=company,
                warehouse=warehouse,
                movement_type=BuildingWarehouseMovement.MovementType.WRITE_OFF,
                reason=ser.validated_data.get("reason", ""),
                created_by=request.user,
            )
            for item in ser.validated_data["items"]:
                stock_item = BuildingWarehouseStockItem.objects.get(id=item["stock_item"])
                if stock_item.warehouse_id != warehouse.id:
                    raise ValidationError({"items": f"Позиция {stock_item.name} не принадлежит выбранному складу."})
                qty = Decimal(item["quantity"])
                if qty <= 0:
                    raise ValidationError({"items": "Количество должно быть положительным."})
                BuildingWarehouseMovementItem.objects.create(
                    movement=movement,
                    stock_item=stock_item,
                    quantity=qty,
                )
                stock_item.quantity -= qty
                stock_item.save(update_fields=["quantity", "updated_at"])
                BuildingWarehouseStockMove.objects.create(
                    warehouse=warehouse,
                    stock_item=stock_item,
                    movement=movement,
                    move_type=BuildingWarehouseStockMove.MoveType.WRITE_OFF,
                    quantity_delta=-qty,
                    price=stock_item.last_price,
                    created_by=request.user,
                )
        movement.refresh_from_db()
        return Response(
            BuildingWarehouseMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingWarehouseMovementTransferToContractorView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Передача материалов подрядчику."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseMovementTransferSerializer
    queryset = ResidentialComplexWarehouse.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        contractor_id = request.data.get("contractor")
        if not contractor_id:
            raise ValidationError({"contractor": "Укажите подрядчика."})
        contractor = BuildingContractor.objects.filter(id=contractor_id, company_id=request.user.company_id).first()
        if not contractor:
            raise ValidationError({"contractor": "Подрядчик не найден."})
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        warehouse = ResidentialComplexWarehouse.objects.filter(
            id=ser.validated_data["warehouse"]
        ).first()
        if not warehouse or warehouse not in self.get_queryset():
            raise ValidationError({"warehouse": "Склад не найден."})
        company = warehouse.residential_complex.company
        with transaction.atomic():
            movement = BuildingWarehouseMovement.objects.create(
                company=company,
                warehouse=warehouse,
                movement_type=BuildingWarehouseMovement.MovementType.TRANSFER_TO_CONTRACTOR,
                contractor=contractor,
                reason=ser.validated_data.get("comment", ""),
                created_by=request.user,
            )
            for item in ser.validated_data["items"]:
                stock_item = BuildingWarehouseStockItem.objects.get(id=item["stock_item"])
                if stock_item.warehouse_id != warehouse.id:
                    raise ValidationError({"items": f"Позиция {stock_item.name} не принадлежит выбранному складу."})
                qty = Decimal(item["quantity"])
                if qty <= 0:
                    raise ValidationError({"items": "Количество должно быть положительным."})
                BuildingWarehouseMovementItem.objects.create(movement=movement, stock_item=stock_item, quantity=qty)
                stock_item.quantity -= qty
                stock_item.save(update_fields=["quantity", "updated_at"])
                BuildingWarehouseStockMove.objects.create(
                    warehouse=warehouse,
                    stock_item=stock_item,
                    movement=movement,
                    contractor=contractor,
                    move_type=BuildingWarehouseStockMove.MoveType.TRANSFER_TO_CONTRACTOR,
                    quantity_delta=-qty,
                    price=stock_item.last_price,
                    created_by=request.user,
                )
        movement.refresh_from_db()
        return Response(
            BuildingWarehouseMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingWarehouseMovementTransferToWorkEntryView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Передача материалов в процесс работ."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWarehouseMovementTransferSerializer
    queryset = ResidentialComplexWarehouse.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        work_entry_id = request.data.get("work_entry")
        warehouse_request_id_raw = request.data.get("warehouse_request")

        work_entry = None
        if work_entry_id:
            work_entry = BuildingWorkEntry.objects.filter(
                id=work_entry_id,
                residential_complex__company_id=request.user.company_id,
            ).first()
            if not work_entry:
                raise ValidationError({"work_entry": "Процесс работ не найден."})

        # Поддержка поля nomenclature для items (alias к stock_item)
        data = request.data.copy()
        items = data.get("items") or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "stock_item" not in item and "nomenclature" in item:
                    item["stock_item"] = item.get("nomenclature")

        ser = self.get_serializer(data=data)
        ser.is_valid(raise_exception=True)
        warehouse = ResidentialComplexWarehouse.objects.filter(
            id=ser.validated_data["warehouse"]
        ).first()
        if not warehouse or warehouse not in self.get_queryset():
            raise ValidationError({"warehouse": "Склад не найден."})
        warehouse_request = None
        warehouse_request_id = ser.validated_data.get("warehouse_request") or warehouse_request_id_raw
        issued_to = (ser.validated_data.get("issued_to") or "").strip() or None
        company = warehouse.residential_complex.company

        with transaction.atomic():
            if warehouse_request_id:
                warehouse_request = BuildingWarehouseRequest.objects.select_for_update().filter(
                    id=warehouse_request_id
                ).first()
                if not warehouse_request:
                    raise ValidationError({"warehouse_request": "Заявка на материалы не найдена."})
                if warehouse_request.warehouse_id != warehouse.id:
                    raise ValidationError({"warehouse_request": "Заявка принадлежит другому складу."})
                if not work_entry:
                    work_entry = warehouse_request.work_entry
                if warehouse_request.work_entry_id != getattr(work_entry, "id", None):
                    raise ValidationError({"warehouse_request": "Заявка принадлежит другому процессу работ."})
            if not work_entry:
                raise ValidationError({"work_entry": "Укажите work_entry или warehouse_request (по заявке определим work_entry)."})

            if warehouse.residential_complex_id != work_entry.residential_complex_id:
                raise ValidationError({"warehouse": "Склад должен принадлежать ЖК процесса работ."})

            movement = BuildingWarehouseMovement.objects.create(
                company=company,
                warehouse=warehouse,
                movement_type=BuildingWarehouseMovement.MovementType.TRANSFER_TO_WORK_ENTRY,
                work_entry=work_entry,
                warehouse_request=warehouse_request,
                issued_to=issued_to,
                reason=ser.validated_data.get("comment", ""),
                created_by=request.user,
            )

            for item in ser.validated_data["items"]:
                stock_item = BuildingWarehouseStockItem.objects.get(id=item["stock_item"])
                if stock_item.warehouse_id != warehouse.id:
                    raise ValidationError({"items": f"Позиция {stock_item.name} не принадлежит выбранному складу."})
                qty = Decimal(item["quantity"])
                if qty <= 0:
                    raise ValidationError({"items": "Количество должно быть положительным."})

                if warehouse_request:
                    # Проверяем, что не выдаём больше, чем запрошено по заявке
                    req_items_qs = warehouse_request.items.select_for_update().filter(stock_item=stock_item)
                    req_item = req_items_qs.first()
                    if not req_item:
                        raise ValidationError({"items": f"Позиция {stock_item.name} отсутствует в заявке."})
                    # If the DB contains duplicates, return a friendly 400 instead of 500.
                    if req_items_qs.count() > 1:
                        dup_ids = list(req_items_qs.values_list("id", flat=True)[:10])
                        raise ValidationError(
                            {
                                "items": (
                                    f"В заявке есть дубликаты позиции {stock_item.name}. "
                                    f"Найдены строки: {', '.join([str(i) for i in dup_ids])}. "
                                    "Удалите/объедините дубликаты и повторите операцию."
                                )
                            }
                        )
                    already_issued = (
                        BuildingWarehouseMovementItem.objects.filter(
                            movement__warehouse_request=warehouse_request,
                            stock_item=stock_item,
                        ).aggregate(s=Coalesce(Sum("quantity"), Decimal("0.00"))).get("s")
                        or Decimal("0.00")
                    )
                    remaining = (req_item.quantity - already_issued).quantize(Decimal("0.001"))
                    if qty > remaining:
                        raise ValidationError(
                            {"items": f"Нельзя выдать больше остатка по заявке для {stock_item.name} (осталось {remaining})."}
                        )

                BuildingWarehouseMovementItem.objects.create(movement=movement, stock_item=stock_item, quantity=qty)
                stock_item.quantity -= qty
                stock_item.save(update_fields=["quantity", "updated_at"])
                BuildingWarehouseStockMove.objects.create(
                    warehouse=warehouse,
                    stock_item=stock_item,
                    movement=movement,
                    work_entry=work_entry,
                    move_type=BuildingWarehouseStockMove.MoveType.TRANSFER_TO_WORK_ENTRY,
                    quantity_delta=-qty,
                    price=stock_item.last_price,
                    created_by=request.user,
                )

            if warehouse_request:
                # Обновляем статус заявки в зависимости от выданных количеств
                all_full = True
                any_issued = False
                for req_item in warehouse_request.items.all():
                    issued = (
                        BuildingWarehouseMovementItem.objects.filter(
                            movement__warehouse_request=warehouse_request,
                            stock_item=req_item.stock_item,
                        ).aggregate(s=Coalesce(Sum("quantity"), Decimal("0.00"))).get("s")
                        or Decimal("0.00")
                    )
                    issued = issued.quantize(Decimal("0.001"))
                    if issued > 0:
                        any_issued = True
                    if issued < req_item.quantity:
                        all_full = False

                if not any_issued:
                    warehouse_request.status = BuildingWarehouseRequest.Status.PENDING
                elif all_full:
                    warehouse_request.status = BuildingWarehouseRequest.Status.COMPLETED
                else:
                    warehouse_request.status = BuildingWarehouseRequest.Status.PARTIALLY_APPROVED
                warehouse_request.decided_by = request.user
                warehouse_request.save(update_fields=["status", "decided_by", "updated_at"])
        movement.refresh_from_db()
        return Response(
            BuildingWarehouseMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingWarehouseMovementFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к движению склада."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingWarehouseMovement.objects.select_related("warehouse__residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
        elif not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        if not (_is_owner_like(request.user) or getattr(request.user, "can_view_building_stock", False)):
            raise PermissionDenied("Нет прав на склад (Building).")
        movement = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingWarehouseMovementFile.objects.create(
            movement=movement,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        movement.refresh_from_db()
        return Response(
            BuildingWarehouseMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingClientListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingClientSerializer
    queryset = BuildingClient.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "phone", "email", "inn"]

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_clients", False)):
            raise PermissionDenied("Нет прав на клиентов (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(treaties__residential_complex_id__in=allowed_ids).distinct()
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_clients", False)):
            raise PermissionDenied("Нет прав на клиентов (Building).")
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        serializer.save(company_id=company_id)


class BuildingClientDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingClientDetailSerializer
    queryset = BuildingClient.objects.prefetch_related("files", "treaties")

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_clients", False)):
            raise PermissionDenied("Нет прав на клиентов (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(treaties__residential_complex_id__in=allowed_ids).distinct()
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs


class BuildingClientFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к клиенту."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingClient.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_clients", False)):
            return qs.none()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(treaties__residential_complex_id__in=allowed_ids).distinct()
            return qs
        return qs.none()

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_clients", False)):
            raise PermissionDenied("Нет прав на клиентов (Building).")
        client = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingClientFile.objects.create(
            client=client,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=user,
        )
        client.refresh_from_db()
        return Response(
            BuildingClientDetailSerializer(client, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingTreatyListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatySerializer
    queryset = BuildingTreaty.objects.select_related("residential_complex", "client", "created_by", "apartment").prefetch_related("files", "installments")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = [
        "residential_complex",
        "client",
        "status",
        "erp_sync_status",
        "auto_create_in_erp",
        "operation_type",
        "payment_type",
        "apartment",
        "treaty_type",
        "group",
    ]
    search_fields = ["number", "title", "description", "residential_complex__name", "client__name", "client_name", "apartment__number"]

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(residential_complex__company_id=user.company_id) | Q(company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(residential_complex_id__in=allowed_ids) | Q(residential_complex_id__isnull=True)
                )
            # include_descendants для групп/папок
            group_id = self.request.query_params.get("group")
            include_desc = (self.request.query_params.get("include_descendants") or "").lower() in ("1", "true", "yes")
            if group_id and include_desc:
                try:
                    grp = BuildingTreatyGroup.objects.filter(id=group_id, company_id=user.company_id).first()
                    if grp:
                        ids = list(grp.get_descendants(include_self=True).values_list("id", flat=True))
                        qs = qs.filter(group_id__in=ids)
                except Exception:
                    pass
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")

        rc = serializer.validated_data.get("residential_complex")
        if rc:
            if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
                raise PermissionDenied("ЖК принадлежит другой компании.")
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None and rc.id not in set(allowed_ids):
                raise PermissionDenied("Нет доступа к этому ЖК.")

        client = serializer.validated_data.get("client")
        if client and rc and client.company_id != rc.company_id:
            raise PermissionDenied("Клиент принадлежит другой компании.")
        if client and not rc and client.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Клиент принадлежит другой компании.")

        treaty = serializer.save(created_by=user)

        # Автоматически фиксируем событие в процессе работ (только при наличии ЖК)
        if rc:
            try:
                if getattr(user, "can_view_building_work_process", False) or _is_owner_like(user):
                    BuildingWorkEntry.objects.create(
                        residential_complex=rc,
                        client=client,
                        treaty=treaty,
                        created_by=user,
                        category=BuildingWorkEntry.Category.TREATY,
                        title=(treaty.title or treaty.number or "Договор"),
                        description=treaty.description or "",
                        occurred_at=getattr(treaty, "created_at", None) or None,
                    )
            except Exception:
                pass

        # Автосоздание в ERP (если включено и настроено)
        if getattr(treaty, "auto_create_in_erp", False):
            try:
                services.request_treaty_create_in_erp(treaty, user)
            except Exception:
                pass

        # Автоначисление от продажи (премия ответственному)
        if treaty.operation_type == BuildingTreaty.OperationType.SALE and treaty.status in (
            BuildingTreaty.Status.ACTIVE,
            BuildingTreaty.Status.SIGNED,
        ):
            try:
                services.create_sale_commission_adjustment(treaty)
            except Exception:
                pass


class BuildingTreatyDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatySerializer
    queryset = BuildingTreaty.objects.select_related("residential_complex", "client", "created_by", "apartment").prefetch_related("files", "installments")

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        qs = super().get_queryset()
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(residential_complex__company_id=user.company_id) | Q(company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(residential_complex_id__in=allowed_ids) | Q(residential_complex_id__isnull=True)
                )
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def perform_update(self, serializer):
        user = self.request.user
        obj = self.get_object()
        if not (_is_owner_like(user) or obj.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Изменять договор может только автор или владелец.")

        rc = serializer.validated_data.get("residential_complex") or obj.residential_complex
        if rc and not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("ЖК принадлежит другой компании.")

        client = serializer.validated_data.get("client")
        if client and rc and client.company_id != rc.company_id:
            raise PermissionDenied("Клиент принадлежит другой компании.")
        if client and not rc and client.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Клиент принадлежит другой компании.")

        with transaction.atomic():
            old_status = obj.status
            old_apartment_id = obj.apartment_id
            old_operation = obj.operation_type

            serializer.save()
            obj.refresh_from_db()

            # синхронизируем статус квартиры с договором (если привязана)
            if old_apartment_id:
                apt = ResidentialComplexApartment.objects.select_for_update().filter(id=old_apartment_id).first()
                if apt:
                    if obj.status == BuildingTreaty.Status.CANCELLED or obj.operation_type == BuildingTreaty.OperationType.OTHER:
                        has_other = (
                            BuildingTreaty.objects
                            .filter(apartment_id=apt.id)
                            .exclude(id=obj.id)
                            .exclude(status=BuildingTreaty.Status.CANCELLED)
                            .exclude(operation_type=BuildingTreaty.OperationType.OTHER)
                            .exists()
                        )
                        if not has_other:
                            apt.status = ResidentialComplexApartment.Status.AVAILABLE
                            apt.save(update_fields=["status", "updated_at"])
                    elif obj.operation_type in (BuildingTreaty.OperationType.SALE, BuildingTreaty.OperationType.BOOKING):
                        desired = (
                            ResidentialComplexApartment.Status.SOLD
                            if obj.operation_type == BuildingTreaty.OperationType.SALE
                            else ResidentialComplexApartment.Status.RESERVED
                        )
                        if apt.status != desired and (obj.operation_type != old_operation or obj.status != old_status):
                            apt.status = desired
                            apt.save(update_fields=["status", "updated_at"])

            # Автоначисление от продажи (премия ответственному)
            if obj.operation_type == BuildingTreaty.OperationType.SALE and obj.status in (
                BuildingTreaty.Status.ACTIVE,
                BuildingTreaty.Status.SIGNED,
            ):
                try:
                    services.create_sale_commission_adjustment(obj)
                except Exception:
                    pass

    def perform_destroy(self, instance):
        user = self.request.user
        if not (_is_owner_like(user) or instance.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Удалять договор может только автор или владелец.")
        with transaction.atomic():
            apt_id = instance.apartment_id
            instance.delete()
            if apt_id:
                apt = ResidentialComplexApartment.objects.select_for_update().filter(id=apt_id).first()
                if apt:
                    has_other = (
                        BuildingTreaty.objects
                        .filter(apartment_id=apt.id)
                        .exclude(status=BuildingTreaty.Status.CANCELLED)
                        .exists()
                    )
                    if not has_other:
                        apt.status = ResidentialComplexApartment.Status.AVAILABLE
                        apt.save(update_fields=["status", "updated_at"])


class BuildingTreatyFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingTreaty.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(residential_complex__company_id=user.company_id) | Q(company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(residential_complex_id__in=allowed_ids) | Q(residential_complex_id__isnull=True)
                )
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")

        treaty = self.get_object()
        treaty_company_id = getattr(treaty.residential_complex, "company_id", None) if treaty.residential_complex_id else getattr(treaty, "company_id", None)
        if not getattr(user, "is_superuser", False) and treaty_company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Договор другой компании.")

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        BuildingTreatyFile.objects.create(
            treaty=treaty,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=user,
        )
        treaty.refresh_from_db()
        return Response(BuildingTreatySerializer(treaty, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingTreatyErpCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatySerializer
    queryset = BuildingTreaty.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(residential_complex__company_id=user.company_id) | Q(company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(residential_complex_id__in=allowed_ids) | Q(residential_complex_id__isnull=True)
                )
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")

        treaty = self.get_object()
        services.request_treaty_create_in_erp(treaty, user)
        treaty.refresh_from_db()
        return Response(BuildingTreatySerializer(treaty, context={"request": request}).data, status=status.HTTP_200_OK)


class BuildingTreatyInstallmentPaymentView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyInstallmentPaymentCreateSerializer
    queryset = BuildingTreatyInstallment.objects.select_related("treaty", "treaty__residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(
                Q(treaty__residential_complex__company_id=user.company_id) | Q(treaty__company_id=user.company_id)
            )
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(
                    Q(treaty__residential_complex_id__in=allowed_ids) | Q(treaty__residential_complex_id__isnull=True)
                )
            return qs
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return qs.none()
        return qs

    def get(self, request, pk=None):
        installment = self.get_object()
        return Response(
            BuildingTreatyInstallmentSerializer(installment, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        _require_cash_register_perm(user)

        base_obj = self.get_object()
        # Postgres forbids `FOR UPDATE` on the nullable side of an OUTER JOIN.
        # `select_related()` can introduce LEFT OUTER JOINs when related FKs are nullable,
        # so we lock the installment row only and fetch related objects separately.
        installment = BuildingTreatyInstallment.objects.select_for_update(of=("self",)).get(pk=base_obj.pk)
        treaty = BuildingTreaty.objects.select_related("residential_complex").filter(pk=installment.treaty_id).first()
        if not treaty:
            raise ValidationError({"treaty": "Договор не найден."})
        installment.treaty = treaty

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        amount = ser.validated_data["amount"]
        if amount <= 0:
            raise ValidationError({"amount": "Сумма должна быть > 0."})

        rc = treaty.residential_complex

        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Договор другой компании.")

        external_payment_id = (ser.validated_data.get("external_payment_id") or "").strip()
        if external_payment_id:
            existing = BuildingTreatyInstallmentPayment.objects.filter(external_payment_id=external_payment_id).select_related("installment")
            if existing.exists():
                applied = []
                for p in existing.order_by("paid_at", "created_at"):
                    inst = p.installment
                    applied.append(
                        {
                            "installment_id": str(inst.id),
                            "amount": str(p.amount),
                            "paid_total_after": str(inst.paid_amount),
                            "status": inst.status,
                        }
                    )
                return Response(
                    {
                        "applied": applied,
                        "input_amount": str(amount),
                        "unused_amount": "0.00",
                        "idempotent": True,
                    },
                    status=status.HTTP_200_OK,
                )

        # распределяем оплату по текущему и следующим взносам
        all_installments = list(
            BuildingTreatyInstallment.objects.select_for_update()
            .filter(treaty_id=treaty.id)
            .order_by("order", "due_date", "created_at")
        )
        if not all_installments:
            raise ValidationError({"detail": "У договора нет графика рассрочки."})
        idx = next((i for i, x in enumerate(all_installments) if x.id == installment.id), None)
        if idx is None:
            raise ValidationError({"installment": "Платёж не найден в графике договора."})

        left = Decimal(amount).quantize(Decimal("0.01"))
        applied = []

        cashbox = BuildingCashbox.objects.filter(id=ser.validated_data["cashbox"]).first()
        if not cashbox:
            raise ValidationError({"cashbox": "Касса не найдена."})
        if not getattr(user, "is_superuser", False) and cashbox.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Касса другой компании.")

        paid_at = ser.validated_data.get("paid_at") or timezone.now()

        client_name = getattr(treaty.client, "name", "") if getattr(treaty, "client_id", None) else ""
        apt_number = getattr(treaty.apartment, "number", "") if getattr(treaty, "apartment_id", None) else ""
        treaty_base = treaty.number or str(treaty.id)

        for inst in all_installments[idx:]:
            if left <= 0:
                break
            inst_remaining = (Decimal(inst.amount or 0) - Decimal(inst.paid_amount or 0)).quantize(Decimal("0.01"))
            if inst_remaining <= 0:
                continue
            part = left if left <= inst_remaining else inst_remaining
            left = (left - part).quantize(Decimal("0.01"))

            name_parts = ["Рассрочка", treaty_base, f"взнос {inst.order or ''}".strip()]
            if client_name:
                name_parts.append(client_name)
            if apt_number:
                name_parts.append(f"кв. {apt_number}")
            flow_name = " / ".join([p for p in name_parts if p])

            cf = BuildingCashFlow.objects.create(
                cashbox=cashbox,
                type=BuildingCashFlow.Type.INCOME,
                name=flow_name,
                amount=abs(part),
                status=BuildingCashFlow.Status.APPROVED,
                source_business_operation_id=str(inst.id),
            )

            new_paid = (Decimal(inst.paid_amount or 0) + part).quantize(Decimal("0.01"))
            inst.paid_amount = new_paid
            if new_paid >= Decimal(inst.amount or 0):
                inst.status = BuildingTreatyInstallment.Status.PAID
                inst.paid_at = paid_at
                inst.save(update_fields=["paid_amount", "status", "paid_at", "updated_at"])
            else:
                inst.save(update_fields=["paid_amount", "updated_at"])

            BuildingTreatyInstallmentPayment.objects.create(
                installment=inst,
                amount=part,
                paid_at=paid_at,
                cashbox=cashbox,
                cashflow=cf,
                external_payment_id=external_payment_id,
                created_by=user,
            )

            applied.append(
                {
                    "installment_id": str(inst.id),
                    "amount": str(part),
                    "paid_total_after": str(inst.paid_amount),
                    "status": inst.status,
                }
            )

        return Response(
            {
                "applied": applied,
                "input_amount": str(Decimal(amount).quantize(Decimal("0.01"))),
                "unused_amount": str(left.quantize(Decimal("0.01"))),
            },
            status=status.HTTP_201_CREATED,
        )

class BuildingTaskListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """
    Задачи/напоминания:
    - видит автор и отмеченные сотрудники
    - owner/admin/superuser видит все задачи компании
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTaskSerializer
    queryset = BuildingTask.objects.select_related("created_by", "residential_complex", "client", "treaty").prefetch_related(
        "assignees__user",
        "checklist_items",
        "files",
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "residential_complex", "client", "treaty", "created_by"]
    search_fields = ["title", "description"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if getattr(user, "is_superuser", False):
            return qs

        company_id = getattr(user, "company_id", None)
        if not company_id:
            return qs.none()

        qs = qs.filter(company_id=company_id)

        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            if not allowed_ids:
                # сотрудник без назначений на ЖК — не показываем задачи
                qs = qs.none()
            else:
                # назначенные ЖК + задачи без ЖК (личные/общие)
                qs = qs.filter(Q(residential_complex_id__in=allowed_ids) | Q(residential_complex__isnull=True))

        if _is_owner_like(user):
            return qs

        # обычный пользователь: только свои и где он отмечен
        return qs.filter(Q(created_by_id=user.id) | Q(assignees__user_id=user.id)).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        if not getattr(user, "company_id", None) and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        serializer.save()


class BuildingTaskDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTaskSerializer
    queryset = BuildingTask.objects.select_related("created_by", "residential_complex", "client", "treaty").prefetch_related(
        "assignees__user",
        "checklist_items",
        "files",
    )

    def get_queryset(self):
        # фильтрацию доступа делаем на уровне get_object через _can_access_task,
        # но базово ограничим компанией
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def get_object(self):
        obj = super().get_object()
        if not _can_access_task(self.request.user, obj):
            raise PermissionDenied("Нет доступа к задаче.")
        allowed_ids = _allowed_residential_complex_ids(self.request.user)
        if allowed_ids is not None and obj.residential_complex_id and obj.residential_complex_id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")
        return obj


class BuildingTaskFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к задаче."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingTask.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def post(self, request, pk=None):
        task = self.get_object()
        if not _can_access_task(request.user, task):
            raise PermissionDenied("Нет доступа к задаче.")
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingTaskFile.objects.create(
            task=task,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        task.refresh_from_db()
        return Response(
            BuildingTaskSerializer(task, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        if not (_is_owner_like(user) or obj.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Изменять задачу может только автор или владелец.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not (_is_owner_like(user) or instance.created_by_id == getattr(user, "id", None)):
            raise PermissionDenied("Удалять задачу может только автор или владелец.")
        instance.delete()


class BuildingTaskChecklistItemAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTaskChecklistItemUpdateSerializer
    queryset = BuildingTask.objects.prefetch_related("assignees")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def post(self, request, pk=None):
        task = self.get_object()
        if not _can_access_task(request.user, task):
            raise PermissionDenied("Нет доступа к задаче.")

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item = BuildingTaskChecklistItem.objects.create(
            task=task,
            text=ser.validated_data["text"],
            is_done=bool(ser.validated_data.get("is_done", False)),
            order=int(ser.validated_data.get("order") or 0),
        )
        if item.is_done:
            item.done_by = request.user
            item.done_at = timezone.now()
            item.save(update_fields=["done_by", "done_at", "updated_at"])

        task.refresh_from_db()
        return Response(BuildingTaskSerializer(task, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingTaskChecklistItemDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTaskChecklistItemSerializer
    queryset = BuildingTaskChecklistItem.objects.select_related("task", "done_by")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(task__company_id=company_id) if company_id else qs.none()

    def get_object(self):
        obj = super().get_object()
        if not _can_access_task(self.request.user, obj.task):
            raise PermissionDenied("Нет доступа к задаче.")
        return obj

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        task = obj.task

        if not (_is_owner_like(user) or task.created_by_id == getattr(user, "id", None) or task.assignees.filter(user_id=user.id).exists()):
            raise PermissionDenied("Нет прав менять чек-лист.")

        is_done_before = obj.is_done
        serializer.save()
        obj.refresh_from_db()

        if "is_done" in serializer.validated_data:
            if obj.is_done and not is_done_before:
                obj.done_by = user
                obj.done_at = timezone.now()
                obj.save(update_fields=["done_by", "done_at", "updated_at"])
            if (not obj.is_done) and is_done_before:
                obj.done_by = None
                obj.done_at = None
                obj.save(update_fields=["done_by", "done_at", "updated_at"])


class BuildingSalaryEmployeeListView(generics.ListAPIView):
    """
    Список сотрудников компании для начисления ЗП (с настройками оклада/ставки).
    ?residential_complex=<uuid> — только сотрудники, назначенные на этот ЖК.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingSalaryEmployeeSerializer
    pagination_class = None

    def get(self, request, *args, **kwargs):
        _require_salary_perm(request.user)
        company_id = getattr(request.user, "company_id", None)
        if not company_id and not getattr(request.user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")

        users_qs = User.objects.filter(company_id=company_id).only("id", "first_name", "last_name", "email").order_by("last_name", "first_name")
        rc_id = request.query_params.get("residential_complex")
        if rc_id:
            allowed_ids = _allowed_residential_complex_ids(request.user)
            if allowed_ids is not None and rc_id and str(rc_id) not in {str(i) for i in allowed_ids}:
                raise PermissionDenied("Нет доступа к этому ЖК.")
            member_user_ids = list(
                ResidentialComplexMember.objects.filter(
                    residential_complex_id=rc_id,
                    is_active=True,
                ).values_list("user_id", flat=True)
            )
            users_qs = users_qs.filter(id__in=member_user_ids)

        users = list(users_qs)
        comps = {
            str(c.user_id): c
            for c in BuildingEmployeeCompensation.objects.filter(
                company_id=company_id,
                user_id__in=[u.id for u in users],
            ).only("id", "user_id", "salary_type", "base_salary", "is_active", "sale_commission_type", "sale_commission_value")
        }

        rows = []
        for u in users:
            full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
            display = full_name or getattr(u, "email", None) or str(u.id)
            c = comps.get(str(u.id))
            rows.append(
                {
                    "id": u.id,
                    "display": display,
                    "compensation_id": getattr(c, "id", None),
                    "salary_type": getattr(c, "salary_type", None),
                    "base_salary": getattr(c, "base_salary", None),
                    "is_active": getattr(c, "is_active", None),
                    "sale_commission_type": getattr(c, "sale_commission_type", None) or "",
                    "sale_commission_value": getattr(c, "sale_commission_value", None),
                }
            )

        return Response(self.get_serializer(rows, many=True).data, status=status.HTTP_200_OK)


class BuildingEmployeeCompensationUpsertView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingEmployeeCompensationSerializer

    def patch(self, request, user_id):
        _require_salary_perm(request.user)
        company_id = getattr(request.user, "company_id", None)
        if not company_id and not getattr(request.user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")

        employee = User.objects.filter(id=user_id, company_id=company_id).first()
        if not employee:
            raise ValidationError({"user": "Сотрудник не найден (или другой компании)."})

        obj, _ = BuildingEmployeeCompensation.objects.get_or_create(company_id=company_id, user_id=employee.id)
        ser = self.get_serializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)


class BuildingPayrollPeriodListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollPeriodSerializer
    queryset = BuildingPayrollPeriod.objects.select_related(
        "company",
        "residential_complex",
        "created_by",
        "approved_by",
    ).prefetch_related(
        "lines__employee",
        "lines__adjustments",
        "lines__payments",
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "period_start", "period_end", "residential_complex"]
    search_fields = ["title"]

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        qs = qs.filter(company_id=company_id) if company_id else qs.none()
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            qs = qs.filter(Q(residential_complex_id__in=allowed_ids) | Q(residential_complex__isnull=True))
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        _require_salary_perm(self.request.user)
        user = self.request.user
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")

        rc = serializer.validated_data.get("residential_complex")
        if not rc:
            raise ValidationError({"residential_complex": "Укажите жилой комплекс (ЖК)."})
        if not getattr(user, "is_superuser", False) and rc.company_id != company_id:
            raise PermissionDenied("ЖК принадлежит другой компании.")
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None and rc.id not in set(allowed_ids):
            raise PermissionDenied("Нет доступа к этому ЖК.")

        ps = serializer.validated_data["period_start"]
        pe = serializer.validated_data["period_end"]
        if ps > pe:
            raise ValidationError({"period_end": "period_end должен быть >= period_start"})

        payroll = serializer.save(
            company_id=rc.company_id,
            residential_complex=rc,
            created_by=user,
        )
        members = list(
            ResidentialComplexMember.objects.filter(
                residential_complex=rc,
                is_active=True,
            ).select_related("user").values_list("user_id", flat=True)
        )
        comps = {
            str(c.user_id): c
            for c in BuildingEmployeeCompensation.objects.filter(
                company_id=rc.company_id,
                user_id__in=members,
            )
        }
        for user_id in members:
            comp = comps.get(str(user_id))
            base_amount = (getattr(comp, "base_salary", None) or Decimal("0.00")) if comp else Decimal("0.00")
            line = BuildingPayrollLine.objects.create(
                payroll=payroll,
                employee_id=user_id,
                base_amount=base_amount,
            )
            line.recalculate_totals()
            line.recalculate_paid_total()


class BuildingPayrollPeriodDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollPeriodSerializer
    queryset = BuildingPayrollPeriod.objects.select_related(
        "company",
        "residential_complex",
        "created_by",
        "approved_by",
    ).prefetch_related(
        "lines__employee",
        "lines__adjustments",
        "lines__payments",
    )

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def perform_update(self, serializer):
        _require_salary_perm(self.request.user)
        obj = self.get_object()
        if obj.status != BuildingPayrollPeriod.Status.DRAFT:
            raise PermissionDenied("Редактировать можно только период в draft.")
        ps = serializer.validated_data.get("period_start") or obj.period_start
        pe = serializer.validated_data.get("period_end") or obj.period_end
        if ps > pe:
            raise ValidationError({"period_end": "period_end должен быть >= period_start"})
        serializer.save()

    def perform_destroy(self, instance):
        _require_salary_perm(self.request.user)
        if instance.status != BuildingPayrollPeriod.Status.DRAFT:
            raise PermissionDenied("Удалять можно только период в draft.")
        instance.delete()


class BuildingPayrollPeriodApproveView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollPeriodApproveSerializer
    queryset = BuildingPayrollPeriod.objects.all()

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    @transaction.atomic
    def post(self, request, pk=None):
        payroll = self.get_object()
        _require_salary_perm(request.user)
        if payroll.status != BuildingPayrollPeriod.Status.DRAFT:
            raise ValidationError({"status": "Начислить можно только период в draft."})

        payroll.status = BuildingPayrollPeriod.Status.APPROVED
        payroll.approved_by = request.user
        payroll.approved_at = timezone.now()
        payroll.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

        for line in payroll.lines.all():
            line.recalculate_totals()
            line.recalculate_paid_total()

        payroll.refresh_from_db()
        return Response(BuildingPayrollPeriodSerializer(payroll, context={"request": request}).data, status=status.HTTP_200_OK)


class BuildingPayrollLineListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollLineSerializer
    queryset = BuildingPayrollLine.objects.select_related("payroll", "employee").prefetch_related("adjustments", "payments")

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        # фильтрация по компании + по конкретному payroll_id из URL
        if getattr(user, "is_superuser", False):
            base_qs = qs
        else:
            company_id = getattr(user, "company_id", None)
            base_qs = qs.filter(payroll__company_id=company_id) if company_id else qs.none()

        payroll_id = self.kwargs.get("payroll_id")
        if payroll_id:
            base_qs = base_qs.filter(payroll_id=payroll_id)
        return base_qs

    @transaction.atomic
    def post(self, request, payroll_id=None):
        _require_salary_perm(request.user)
        payroll = BuildingPayrollPeriod.objects.select_for_update().filter(id=payroll_id).first()
        if not payroll:
            raise ValidationError({"payroll": "Период не найден."})
        if not getattr(request.user, "is_superuser", False) and payroll.company_id != getattr(request.user, "company_id", None):
            raise PermissionDenied("Период другой компании.")
        if payroll.status != BuildingPayrollPeriod.Status.DRAFT:
            raise PermissionDenied("Добавлять строки можно только в draft.")

        ser = BuildingPayrollLineCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        employee = User.objects.filter(id=ser.validated_data["employee"], company_id=payroll.company_id).first()
        if not employee:
            raise ValidationError({"employee": "Сотрудник не найден (или другой компании)."})

        base_amount = ser.validated_data.get("base_amount", None)
        if base_amount is None:
            comp = BuildingEmployeeCompensation.objects.filter(company_id=payroll.company_id, user_id=employee.id, is_active=True).first()
            base_amount = getattr(comp, "base_salary", None) or Decimal("0.00")

        line = BuildingPayrollLine.objects.create(
            payroll=payroll,
            employee=employee,
            base_amount=base_amount,
            comment=ser.validated_data.get("comment", "") or "",
        )
        line.recalculate_totals()
        line.recalculate_paid_total()

        return Response(BuildingPayrollLineSerializer(line, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingPayrollLineDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollLineSerializer
    queryset = BuildingPayrollLine.objects.select_related("payroll", "employee").prefetch_related("adjustments", "payments")

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(payroll__company_id=company_id) if company_id else qs.none()

    def perform_update(self, serializer):
        _require_salary_perm(self.request.user)
        obj = self.get_object()
        if obj.payroll.status != BuildingPayrollPeriod.Status.DRAFT:
            raise PermissionDenied("Редактировать строку можно только в draft периоде.")
        serializer.save()
        obj.refresh_from_db()
        obj.recalculate_totals()

    def perform_destroy(self, instance):
        _require_salary_perm(self.request.user)
        if instance.payroll.status != BuildingPayrollPeriod.Status.DRAFT:
            raise PermissionDenied("Удалять строку можно только в draft периоде.")
        instance.delete()


class BuildingPayrollAdjustmentCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollAdjustmentCreateSerializer
    queryset = BuildingPayrollLine.objects.select_related("payroll").prefetch_related("payments", "adjustments")

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(payroll__company_id=company_id) if company_id else qs.none()

    def get(self, request, pk=None):
        _require_salary_perm(request.user)
        line = self.get_object()
        adjustments = line.adjustments.select_related("created_by", "source_treaty").order_by("-created_at")
        return Response(
            BuildingPayrollAdjustmentSerializer(adjustments, many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, pk=None):
        _require_salary_perm(request.user)
        line = self.get_object()
        if line.payroll.status == BuildingPayrollPeriod.Status.PAID:
            raise PermissionDenied("Нельзя менять начисления в периоде paid.")

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        adj_type = ser.validated_data["type"]
        title = (ser.validated_data.get("comment") or ser.validated_data.get("title") or "").strip()
        amount = ser.validated_data["amount"]

        if adj_type == BuildingPayrollAdjustment.Type.ADVANCE:
            _require_cash_register_perm(request.user)
            if line.payroll.status not in (
                BuildingPayrollPeriod.Status.DRAFT,
                BuildingPayrollPeriod.Status.APPROVED,
            ):
                raise PermissionDenied("Авансы разрешены только в периоде draft или approved.")
            line.recalculate_totals()
            line.recalculate_paid_total()
            remaining = (Decimal(line.net_to_pay or 0) - Decimal(line.paid_total or 0)).quantize(Decimal("0.01"))
            if remaining <= 0:
                raise ValidationError({"amount": "По строке не осталось суммы к выплате."})
            if amount > remaining:
                raise ValidationError({"amount": f"Сумма аванса не должна превышать остаток ({remaining})."})
            cashbox_id = ser.validated_data.get("cashbox")
            if not cashbox_id:
                raise ValidationError({"cashbox": "Для аванса укажите кассу."})
            cashbox = BuildingCashbox.objects.filter(id=cashbox_id).first()
            if not cashbox:
                raise ValidationError({"cashbox": "Касса не найдена."})
            if not getattr(request.user, "is_superuser", False) and cashbox.company_id != getattr(request.user, "company_id", None):
                raise PermissionDenied("Касса другой компании.")
            paid_at = ser.validated_data.get("paid_at") or timezone.now()

            adj = BuildingPayrollAdjustment.objects.create(
                line=line,
                type=BuildingPayrollAdjustment.Type.ADVANCE,
                status=BuildingPayrollAdjustment.Status.PENDING,
                title=title or "Аванс",
                amount=amount,
                created_by=request.user,
            )
            emp = line.employee
            emp_name = f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip() if emp else ""
            emp_display = emp_name or getattr(emp, "email", None) or getattr(emp, "username", None) or str(getattr(emp, "id", ""))
            payment = BuildingPayrollPayment.objects.create(
                line=line,
                amount=amount,
                paid_at=paid_at,
                paid_by=request.user,
                cashbox=cashbox,
                status=BuildingPayrollPayment.Status.PENDING,
                advance_adjustment=adj,
            )
            cf = BuildingCashFlow.objects.create(
                cashbox=cashbox,
                type=BuildingCashFlow.Type.EXPENSE,
                name=f"ЗП аванс: {emp_display}",
                amount=abs(amount),
                status=BuildingCashFlow.Status.PENDING,
                source_business_operation_id=str(payment.id),
            )
            payment.cashflow = cf
            payment.save(update_fields=["cashflow"])
        else:
            adj = BuildingPayrollAdjustment.objects.create(
                line=line,
                type=adj_type,
                title=title,
                amount=amount,
                created_by=request.user,
            )
            line.refresh_from_db()
            line.recalculate_totals()
            line.recalculate_paid_total()
            if line.net_to_pay < line.paid_total:
                raise ValidationError({"amount": "Корректировка приводит к переплате (paid_total > net_to_pay)."})

        return Response(BuildingPayrollAdjustmentSerializer(adj, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingPayrollAdjustmentDetailView(CompanyQuerysetMixin, generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollAdjustmentSerializer
    queryset = BuildingPayrollAdjustment.objects.select_related("line", "line__payroll", "created_by")

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(line__payroll__company_id=company_id) if company_id else qs.none()

    @transaction.atomic
    def perform_destroy(self, instance):
        _require_salary_perm(self.request.user)
        if instance.line.payroll.status == BuildingPayrollPeriod.Status.PAID:
            raise PermissionDenied("Нельзя менять начисления в периоде paid.")
        if instance.type == BuildingPayrollAdjustment.Type.ADVANCE and instance.status == BuildingPayrollAdjustment.Status.COMPLETED:
            raise PermissionDenied("Нельзя отменить проведённый аванс (уже выплачен через кассу).")
        line = instance.line
        instance.delete()
        line.refresh_from_db()
        line.recalculate_totals()
        line.recalculate_paid_total()
        if line.net_to_pay < line.paid_total:
            raise ValidationError({"detail": "Удаление корректировки приводит к переплате (paid_total > net_to_pay)."})


class BuildingPayrollPaymentListCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollPaymentCreateSerializer
    queryset = BuildingPayrollLine.objects.select_related("payroll", "employee").prefetch_related("payments")

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(payroll__company_id=company_id) if company_id else qs.none()

    def get(self, request, pk=None):
        _require_salary_perm(request.user)
        line = self.get_object()
        payments = line.payments.select_related("paid_by", "cashbox", "cashflow").all().order_by("-paid_at", "-created_at")
        return Response(BuildingPayrollPaymentSerializer(payments, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk=None):
        _require_salary_perm(request.user)
        _require_cash_register_perm(request.user)
        line = self.get_object()

        payroll = BuildingPayrollPeriod.objects.select_for_update().get(id=line.payroll_id)
        if payroll.status != BuildingPayrollPeriod.Status.APPROVED:
            raise PermissionDenied("Выплачивать можно только из периода в статусе approved.")

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        amount = ser.validated_data["amount"]
        if amount <= 0:
            raise ValidationError({"amount": "Сумма должна быть > 0."})

        line.recalculate_totals()
        line.recalculate_paid_total()
        remaining = (Decimal(line.net_to_pay or 0) - Decimal(line.paid_total or 0)).quantize(Decimal("0.01"))
        if remaining <= 0:
            raise ValidationError({"amount": "По строке уже всё выплачено."})
        if amount > remaining:
            raise ValidationError({"amount": f"Нельзя выплатить больше остатка ({remaining})."})

        cashbox = BuildingCashbox.objects.filter(id=ser.validated_data["cashbox"]).first()
        if not cashbox:
            raise ValidationError({"cashbox": "Касса не найдена."})
        if not getattr(request.user, "is_superuser", False) and cashbox.company_id != getattr(request.user, "company_id", None):
            raise PermissionDenied("Касса другой компании.")

        paid_at = ser.validated_data.get("paid_at") or timezone.now()
        status_flag = (ser.validated_data.get("status") or "approved").lower()

        with transaction.atomic():
            payment = BuildingPayrollPayment.objects.create(
                line=line,
                amount=amount,
                paid_at=paid_at,
                paid_by=request.user,
                cashbox=cashbox,
                status=BuildingPayrollPayment.Status.PENDING,
            )

            # Черновик: не создаём движение кассы, не трогаем paid_total.
            if status_flag == "draft":
                return Response(
                    BuildingPayrollPaymentSerializer(payment, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )

            # Одобренная выплата: сразу создаём одобренный CashFlow и проводим выплату.
            emp = line.employee
            emp_name = (
                f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip() if emp else ""
            )
            emp_display = (
                emp_name
                or getattr(emp, "email", None)
                or getattr(emp, "username", None)
                or str(getattr(emp, "id", ""))
            )
            cf = BuildingCashFlow.objects.create(
                company=cashbox.company,
                branch=cashbox.branch,
                cashbox=cashbox,
                type=BuildingCashFlow.Type.EXPENSE,
                name=f"ЗП: {emp_display} / {payroll.period_start} - {payroll.period_end}",
                amount=abs(amount),
                status=BuildingCashFlow.Status.APPROVED,
                source_business_operation_id=str(payment.id),
                cashier=request.user if getattr(request.user, "id", None) else None,
            )
            payment.cashflow = cf
            payment.save(update_fields=["cashflow"])

            # Сразу проводим выплату так же, как при on_cashflow_approved.
            from .salary_cash import on_cashflow_approved

            on_cashflow_approved(cf)
            payment.refresh_from_db()

        return Response(
            BuildingPayrollPaymentSerializer(payment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuildingPayrollMyLinesView(CompanyQuerysetMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollMyLineSerializer
    queryset = BuildingPayrollLine.objects.select_related("payroll", "payroll__residential_complex").prefetch_related("payments")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["payroll__status"]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(employee_id=getattr(user, "id", None))
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        qs = qs.filter(payroll__company_id=company_id) if company_id else qs.none()
        allowed_ids = _allowed_residential_complex_ids(user)
        if allowed_ids is not None:
            qs = qs.filter(payroll__residential_complex_id__in=allowed_ids)
        return qs


class AdvanceRequestListView(CompanyQuerysetMixin, generics.ListAPIView):
    """
    Список заявок на аванс (pending) для оператора кассы.
    GET /salary/advance-requests/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AdvanceRequestSerializer
    queryset = BuildingPayrollAdjustment.objects.filter(
        type=BuildingPayrollAdjustment.Type.ADVANCE,
        status=BuildingPayrollAdjustment.Status.PENDING,
    ).select_related(
        "line",
        "line__employee",
        "line__payroll",
        "line__payroll__residential_complex",
    ).prefetch_related(
        Prefetch(
            "payment",
            queryset=BuildingPayrollPayment.objects.select_related("cashbox"),
        ),
    ).order_by("-created_at")

    def get_queryset(self):
        _require_cash_register_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            company_id = getattr(user, "company_id", None)
            if company_id:
                qs = qs.filter(line__payroll__company_id=company_id)
            else:
                qs = qs.none()
        cashbox = self.request.query_params.get("cashbox")
        if cashbox:
            qs = qs.filter(payment__cashbox_id=cashbox)
        residential_complex = self.request.query_params.get("residential_complex")
        if residential_complex:
            qs = qs.filter(line__payroll__residential_complex_id=residential_complex)
        payroll = self.request.query_params.get("payroll")
        if payroll:
            qs = qs.filter(line__payroll_id=payroll)
        return qs.distinct()


class BuildingPayrollPaymentApproveView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Одобрить черновую выплату ЗП.
    POST /salary/payments/{id}/approve/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingPayrollPaymentApproveSerializer
    queryset = BuildingPayrollPayment.objects.select_related(
        "line",
        "line__payroll",
        "cashbox",
    )

    def get_queryset(self):
        _require_salary_perm(self.request.user)
        _require_cash_register_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(line__payroll__company_id=company_id) if company_id else qs.none()

    @transaction.atomic
    def post(self, request, pk=None):
        _require_salary_perm(request.user)
        _require_cash_register_perm(request.user)
        payment = self.get_object()
        line = payment.line
        payroll = BuildingPayrollPeriod.objects.select_for_update().get(id=line.payroll_id)
        if payroll.status != BuildingPayrollPeriod.Status.APPROVED:
            raise PermissionDenied("Выплачивать можно только из периода в статусе approved.")
        if payment.status != BuildingPayrollPayment.Status.PENDING:
            raise ValidationError({"detail": "Выплата уже проведена или отменена."})
        if payment.cashflow_id:
            raise ValidationError({"detail": "Для выплаты уже существует движение кассы."})

        # Пересчитываем остаток перед проведением
        line.recalculate_totals()
        line.recalculate_paid_total()
        remaining = (Decimal(line.net_to_pay or 0) - Decimal(line.paid_total or 0)).quantize(Decimal("0.01"))
        if payment.amount > remaining:
            raise ValidationError({"amount": f"Нельзя провести выплату больше остатка ({remaining})."})

        ser = self.get_serializer(data=request.data or {}, partial=True)
        ser.is_valid(raise_exception=True)
        paid_at = ser.validated_data.get("paid_at") or payment.paid_at or timezone.now()
        payment.paid_at = paid_at
        payment.save(update_fields=["paid_at"])

        cashbox = payment.cashbox
        if not getattr(request.user, "is_superuser", False) and cashbox.company_id != getattr(
            request.user, "company_id", None
        ):
            raise PermissionDenied("Касса другой компании.")

        emp = line.employee
        emp_name = (
            f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip() if emp else ""
        )
        emp_display = (
            emp_name
            or getattr(emp, "email", None)
            or getattr(emp, "username", None)
            or str(getattr(emp, "id", ""))
        )

        cf = BuildingCashFlow.objects.create(
            company=cashbox.company,
            branch=cashbox.branch,
            cashbox=cashbox,
            type=BuildingCashFlow.Type.EXPENSE,
            name=f"ЗП: {emp_display} / {payroll.period_start} - {payroll.period_end}",
            amount=abs(payment.amount),
            status=BuildingCashFlow.Status.APPROVED,
            source_business_operation_id=str(payment.id),
            cashier=request.user if getattr(request.user, "id", None) else None,
        )
        payment.cashflow = cf
        payment.save(update_fields=["cashflow"])

        from .salary_cash import on_cashflow_approved

        on_cashflow_approved(cf)
        payment.refresh_from_db()

        return Response(
            BuildingPayrollPaymentSerializer(payment, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class AdvanceRequestApproveView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Одобрить заявку на аванс. Сумма снимается с net_to_pay, движение кассы проводится.
    POST /salary/advance-requests/{id}/approve/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AdvanceRequestApproveSerializer
    queryset = BuildingPayrollAdjustment.objects.filter(
        type=BuildingPayrollAdjustment.Type.ADVANCE,
        status=BuildingPayrollAdjustment.Status.PENDING,
    ).select_related("line", "line__payroll")

    def get_queryset(self):
        _require_cash_register_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            company_id = getattr(user, "company_id", None)
            if company_id:
                qs = qs.filter(line__payroll__company_id=company_id)
            else:
                qs = qs.none()
        return qs

    @transaction.atomic
    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        adj = self.get_object()
        payment = adj.payment.first()
        if not payment:
            raise ValidationError({"detail": "У заявки нет связанной выплаты."})
        if payment.status != BuildingPayrollPayment.Status.PENDING:
            raise ValidationError({"detail": "Заявка уже обработана."})
        cf = payment.cashflow
        if not cf:
            raise ValidationError({"detail": "У выплаты нет движения кассы."})

        ser = self.get_serializer(data=request.data or {}, partial=True)
        ser.is_valid(raise_exception=True)
        paid_at = ser.validated_data.get("paid_at")
        if paid_at:
            payment.paid_at = paid_at
            payment.save(update_fields=["paid_at"])

        cf.status = BuildingCashFlow.Status.APPROVED
        cf.save(update_fields=["status"])
        # post_save signal вызовет on_cashflow_approved

        adj.refresh_from_db()
        adj = BuildingPayrollAdjustment.objects.select_related(
            "line", "line__employee", "line__payroll", "line__payroll__residential_complex"
        ).prefetch_related(
            Prefetch("payment", queryset=BuildingPayrollPayment.objects.select_related("cashbox")),
        ).get(pk=adj.pk)
        return Response(
            AdvanceRequestSerializer(adj, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class AdvanceRequestRejectView(CompanyQuerysetMixin, generics.GenericAPIView):
    """
    Отклонить заявку на аванс.
    POST /salary/advance-requests/{id}/reject/
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingPayrollAdjustment.objects.filter(
        type=BuildingPayrollAdjustment.Type.ADVANCE,
        status=BuildingPayrollAdjustment.Status.PENDING,
    ).select_related("line", "line__payroll")

    def get_queryset(self):
        _require_cash_register_perm(self.request.user)
        qs = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            company_id = getattr(user, "company_id", None)
            if company_id:
                qs = qs.filter(line__payroll__company_id=company_id)
            else:
                qs = qs.none()
        return qs

    @transaction.atomic
    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        adj = self.get_object()
        payment = adj.payment.first()
        if payment and payment.cashflow_id:
            cf = payment.cashflow
            cf.status = BuildingCashFlow.Status.REJECTED
            cf.save(update_fields=["status"])
        adj.status = BuildingPayrollAdjustment.Status.REJECTED
        adj.save(update_fields=["status"])
        return Response({"status": "rejected"}, status=status.HTTP_200_OK)


# -----------------------
# Building Cash API (касса Building — своя система)
# -----------------------


class BuildingCashboxListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """Список и создание касс Building."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashboxSerializer
    queryset = BuildingCashbox.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        if not getattr(user, "company_id", None) and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        serializer.save(company_id=user.company_id)


class BuildingCashboxDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """Детали кассы Building."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashboxSerializer
    queryset = BuildingCashbox.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()


class BuildingCashFlowListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """Список и создание движений Building."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashFlowSerializer
    queryset = BuildingCashFlow.objects.select_related("cashbox", "cashier").prefetch_related("files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            pass
        else:
            company_id = getattr(user, "company_id", None)
            qs = qs.filter(company_id=company_id) if company_id else qs.none()
        cashbox_id = self.request.query_params.get("cashbox")
        if cashbox_id:
            qs = qs.filter(cashbox_id=cashbox_id)
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        cashbox = serializer.validated_data.get("cashbox")
        if cashbox:
            serializer.save(company=cashbox.company, branch=cashbox.branch)
        else:
            serializer.save()


class BuildingCashFlowDetailView(CompanyQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    """Детали движения Building."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashFlowSerializer
    queryset = BuildingCashFlow.objects.select_related("cashbox", "cashier").prefetch_related("files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()


class BuildingCashFlowBulkStatusUpdateView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Массовое обновление статуса движений (одобрение/отклонение)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashFlowBulkStatusSerializer

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        _require_cash_register_perm(request.user)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        items = ser.validated_data.get("items") or []
        if not items:
            return Response({"count": 0, "updated_ids": []}, status=status.HTTP_200_OK)

        id_to_status = {it["id"]: it["status"] for it in items}
        ids = list(id_to_status.keys())

        qs = BuildingCashFlow.objects.filter(id__in=ids)
        company_id = getattr(request.user, "company_id", None)
        if not getattr(request.user, "is_superuser", False) and company_id:
            qs = qs.filter(company_id=company_id)

        existing_ids = set(qs.values_list("id", flat=True))
        missing = [str(i) for i in ids if i not in existing_ids]
        if missing:
            raise ValidationError({"missing_ids": missing})

        whens = [When(id=_id, then=Value(id_to_status[_id])) for _id in ids]
        qs.update(status=Case(*whens, output_field=CharField()))

        return Response(
            {"count": len(ids), "updated_ids": [str(x) for x in ids]},
            status=status.HTTP_200_OK,
        )


# -----------------------
# Cash Register Requests
# -----------------------


def _cash_register_request_queryset(user):
    qs = BuildingCashRegisterRequest.objects.select_related(
        "cashbox", "residential_complex", "treaty", "apartment", "client",
        "installment", "work_entry", "cashflow", "approved_by", "created_by",
    ).prefetch_related("files")
    if getattr(user, "is_superuser", False):
        return qs
    company_id = getattr(user, "company_id", None)
    if company_id:
        return qs.filter(company_id=company_id)
    return qs.none()


class CashRegisterRequestListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    """Список и создание заявок на кассу."""
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["request_type", "status", "cashbox", "residential_complex", "treaty", "client"]

    def get_queryset(self):
        return _cash_register_request_queryset(self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BuildingCashRegisterRequestCreateSerializer
        return BuildingCashRegisterRequestSerializer

    def create(self, request, *args, **kwargs):
        _require_cash_register_perm(request.user)
        ser = BuildingCashRegisterRequestCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        cashbox = data["cashbox"]
        company = cashbox.company
        branch = cashbox.branch

        residential_complex = None
        if data.get("treaty"):
            residential_complex = data["treaty"].residential_complex
        elif data.get("apartment"):
            residential_complex = data["apartment"].residential_complex
        elif data.get("installment"):
            residential_complex = data["installment"].treaty.residential_complex
        elif data.get("work_entry"):
            residential_complex = data["work_entry"].residential_complex

        allowed_rc = _allowed_residential_complex_ids(request.user)
        if allowed_rc is not None and residential_complex and residential_complex.id not in allowed_rc:
            raise PermissionDenied("Нет доступа к этому ЖК.")

        req = BuildingCashRegisterRequest.objects.create(
            company=company,
            branch=branch,
            request_type=data["request_type"],
            status=BuildingCashRegisterRequest.Status.PENDING,
            amount=data["amount"],
            comment=data.get("comment") or "",
            cashbox=cashbox,
            shift=data.get("shift") or None,
            residential_complex=residential_complex,
            treaty=data.get("treaty"),
            apartment=data.get("apartment"),
            client=data.get("client"),
            installment=data.get("installment"),
            work_entry=data.get("work_entry"),
            created_by=request.user,
        )
        req.refresh_from_db()
        return Response(
            BuildingCashRegisterRequestSerializer(req, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CashRegisterRequestDetailView(CompanyQuerysetMixin, generics.RetrieveAPIView):
    """Детали заявки на кассу."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashRegisterRequestSerializer
    queryset = BuildingCashRegisterRequest.objects.all()

    def get_queryset(self):
        return _cash_register_request_queryset(self.request.user)


class CashRegisterRequestApproveView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Одобрить заявку на кассу."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashRegisterRequestApproveSerializer
    queryset = BuildingCashRegisterRequest.objects.select_related("cashbox", "treaty", "installment", "work_entry")

    def get_queryset(self):
        return _cash_register_request_queryset(self.request.user)

    @transaction.atomic
    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        req = self.get_object()
        if req.status != BuildingCashRegisterRequest.Status.PENDING:
            raise ValidationError({"status": "Заявка уже обработана."})

        ser = BuildingCashRegisterRequestApproveSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        cashbox = data.get("cashbox") or req.cashbox
        paid_at = data.get("paid_at") or timezone.now()

        is_income = req.request_type in (
            BuildingCashRegisterRequest.RequestType.APARTMENT_SALE,
            BuildingCashRegisterRequest.RequestType.INSTALLMENT_INITIAL_PAYMENT,
            BuildingCashRegisterRequest.RequestType.INSTALLMENT_PAYMENT,
        )
        flow_type = BuildingCashFlow.Type.INCOME if is_income else BuildingCashFlow.Type.EXPENSE

        source_id = None
        name_parts = [req.get_request_type_display(), str(req.amount)]
        if req.treaty_id:
            source_id = str(req.treaty_id)
            name_parts.insert(0, f"Договор {req.treaty.number or req.treaty_id}")
        elif req.installment_id:
            source_id = str(req.installment_id)
            name_parts.insert(0, f"Рассрочка {req.installment_id}")
        elif req.work_entry_id:
            source_id = str(req.work_entry_id)
            name_parts.insert(0, f"Работы {req.work_entry_id}")

        cf = BuildingCashFlow.objects.create(
            cashbox=cashbox,
            type=flow_type,
            name=" / ".join(name_parts),
            amount=req.amount,
            status=BuildingCashFlow.Status.APPROVED,
            source_business_operation_id=source_id or str(req.id),
            cashier=request.user,
        )

        req.cashflow = cf
        req.status = BuildingCashRegisterRequest.Status.APPROVED
        req.approved_at = paid_at
        req.approved_by = request.user
        req.reject_reason = ""
        req.save(update_fields=["cashflow", "status", "approved_at", "approved_by", "reject_reason", "updated_at"])

        if req.request_type == BuildingCashRegisterRequest.RequestType.INSTALLMENT_PAYMENT and req.installment_id:
            inst = req.installment
            new_paid = (Decimal(inst.paid_amount or 0) + req.amount).quantize(Decimal("0.01"))
            inst.paid_amount = new_paid
            if new_paid >= Decimal(inst.amount or 0):
                inst.status = BuildingTreatyInstallment.Status.PAID
                inst.paid_at = paid_at
                inst.save(update_fields=["paid_amount", "status", "paid_at", "updated_at"])
            else:
                inst.save(update_fields=["paid_amount", "updated_at"])

        elif req.request_type == BuildingCashRegisterRequest.RequestType.INSTALLMENT_INITIAL_PAYMENT and req.treaty_id:
            treaty = req.treaty
            if treaty.down_payment and req.amount >= treaty.down_payment:
                pass

        req.refresh_from_db()
        return Response(
            BuildingCashRegisterRequestSerializer(req, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class CashRegisterRequestRejectView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Отклонить заявку на кассу."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashRegisterRequestRejectSerializer
    queryset = BuildingCashRegisterRequest.objects.all()

    def get_queryset(self):
        return _cash_register_request_queryset(self.request.user)

    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        req = self.get_object()
        if req.status != BuildingCashRegisterRequest.Status.PENDING:
            raise ValidationError({"status": "Заявка уже обработана."})

        reason = ""
        if request.data and isinstance(request.data, dict):
            reason = (request.data.get("reason") or "").strip()

        req.status = BuildingCashRegisterRequest.Status.REJECTED
        req.reject_reason = reason
        req.save(update_fields=["status", "reject_reason", "updated_at"])

        req.refresh_from_db()
        return Response(
            BuildingCashRegisterRequestSerializer(req, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class CashRegisterRequestFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к заявке на кассу."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashRegisterRequestFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingCashRegisterRequest.objects.all()

    def get_queryset(self):
        return _cash_register_request_queryset(self.request.user)

    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        req = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        BuildingCashRegisterRequestFile.objects.create(
            request=req,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        req.refresh_from_db()
        return Response(
            BuildingCashRegisterRequestSerializer(req, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CashFlowFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    """Загрузить файл к движению по кассе."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingCashFlowFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingCashFlow.objects.prefetch_related("files")

    def get_queryset(self):
        qs = BuildingCashFlow.objects.prefetch_related("files")
        if getattr(self.request.user, "is_superuser", False):
            return qs
        company_id = getattr(self.request.user, "company_id", None)
        return qs.filter(company_id=company_id) if company_id else qs.none()

    def post(self, request, pk=None):
        _require_cash_register_perm(request.user)
        cf = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        BuildingCashFlowFile.objects.create(
            cashflow=cf,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        cf.refresh_from_db()
        files_data = [BuildingCashFlowFileSerializer(f, context={"request": request}).data for f in cf.files.all()]
        return Response({"files": files_data}, status=status.HTTP_201_CREATED)


# -----------------------
# Treaty groups / move
# -----------------------


class BuildingTreatyGroupListCreateView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingTreatyGroup.objects.all()

    def get(self, request):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        if not getattr(user, "company_id", None) and not getattr(user, "is_superuser", False):
            return Response([], status=status.HTTP_200_OK)

        qs = BuildingTreatyGroup.objects.filter(company_id=user.company_id)
        rc = request.query_params.get("residential_complex")
        if rc:
            qs = qs.filter(residential_complex_id=rc)
        tree = (request.query_params.get("tree") or "").lower() in ("1", "true", "yes")
        if tree:
            qs = qs.filter(parent__isnull=True).order_by("order", "title")
            return Response(BuildingTreatyGroupSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)
        qs = qs.order_by("tree_id", "lft")
        return Response(BuildingTreatyGroupSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        ser = BuildingTreatyGroupCreateUpdateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        rc = ser.validated_data.get("residential_complex")
        if rc and rc.company_id != getattr(user, "company_id", None) and not getattr(user, "is_superuser", False):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        obj = ser.save(company_id=user.company_id)
        return Response(BuildingTreatyGroupSerializer(obj, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingTreatyGroupDetailView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingTreatyGroup.objects.all()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not getattr(user, "is_superuser", False) and obj.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Объект другой компании.")
        return obj

    def get(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        obj = self.get_object()
        return Response(BuildingTreatyGroupSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def patch(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        obj = self.get_object()
        ser = BuildingTreatyGroupCreateUpdateSerializer(obj, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        rc = ser.validated_data.get("residential_complex")
        if rc and rc.company_id != getattr(user, "company_id", None) and not getattr(user, "is_superuser", False):
            raise PermissionDenied("ЖК принадлежит другой компании.")
        obj = ser.save()
        return Response(BuildingTreatyGroupSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        obj = self.get_object()
        if obj.get_children().exists():
            raise ValidationError({"detail": "Нельзя удалить папку с дочерними папками."})
        if obj.treaties.exists():
            raise ValidationError({"detail": "Нельзя удалить папку с договорами."})
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BuildingTreatyMoveView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingTreatyMoveSerializer

    @transaction.atomic
    def post(self, request):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_treaty", False)):
            raise PermissionDenied("Нет прав на договора (Building).")
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        treaty_ids = [str(x) for x in ser.validated_data["treaty_ids"]]
        target_group = ser.validated_data.get("target_group")

        qs = BuildingTreaty.objects.filter(id__in=treaty_ids).select_related("residential_complex")
        if not getattr(user, "is_superuser", False) and getattr(user, "company_id", None):
            qs = qs.filter(Q(residential_complex__company_id=user.company_id) | Q(company_id=user.company_id))

        group_obj = None
        if target_group:
            group_obj = BuildingTreatyGroup.objects.filter(id=target_group, company_id=user.company_id).first()
            if not group_obj:
                raise ValidationError({"target_group": "Папка не найдена."})

        updated = qs.update(group=group_obj, updated_at=timezone.now())
        return Response({"moved": updated}, status=status.HTTP_200_OK)


# -----------------------
# WorkEntry: receipts from warehouse + acceptance (АВР)
# -----------------------


class BuildingWorkEntryWarehouseReceiptsView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingWorkEntry.objects.select_related("residential_complex")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        return qs.none()

    def get(self, request, pk=None):
        we = self.get_object()
        movements = (
            BuildingWarehouseMovement.objects.filter(
                movement_type=BuildingWarehouseMovement.MovementType.TRANSFER_TO_WORK_ENTRY,
                work_entry_id=we.id,
            )
            .select_related("warehouse")
            .prefetch_related("items__stock_item", "files")
            .order_by("-created_at")
        )
        results = []
        for m in movements:
            items = []
            for it in m.items.all():
                si = it.stock_item
                items.append(
                    {
                        "nomenclature": str(si.id),
                        "name": getattr(si, "name", ""),
                        "quantity": str(it.quantity),
                        "unit": getattr(si, "unit", None) or "",
                    }
                )
            files = [BuildingWarehouseMovementFileSerializer(f, context={"request": request}).data for f in m.files.all()]
            results.append(
                {
                    "warehouse_movement_id": str(m.id),
                    "warehouse": str(m.warehouse_id),
                    "issued_to": m.issued_to,
                    "issued_at": m.created_at,
                    "items": items,
                    "files": files,
                }
            )
        return Response({"work_entry": str(we.id), "results": results}, status=status.HTTP_200_OK)


class BuildingWorkEntryAcceptanceView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntryAcceptanceUpsertSerializer
    queryset = BuildingWorkEntry.objects.select_related("residential_complex").prefetch_related("acceptance__files")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")
        if user.is_authenticated and getattr(user, "company_id", None):
            qs = qs.filter(residential_complex__company_id=user.company_id)
            allowed_ids = _allowed_residential_complex_ids(user)
            if allowed_ids is not None:
                qs = qs.filter(residential_complex_id__in=allowed_ids)
            return qs
        return qs.none()

    def get(self, request, pk=None):
        we = self.get_object()
        acc = getattr(we, "acceptance", None)
        if not acc:
            return Response(None, status=status.HTTP_200_OK)
        return Response(BuildingWorkEntryAcceptanceSerializer(acc, context={"request": request}).data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk=None):
        we = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        acc, _ = BuildingWorkEntryAcceptance.objects.select_for_update().get_or_create(work_entry=we)
        if "comment" in ser.validated_data:
            acc.comment = ser.validated_data.get("comment") or ""
        if "status" in ser.validated_data:
            acc.status = ser.validated_data["status"]
            if acc.status == BuildingWorkEntryAcceptance.Status.SIGNED and not acc.signed_at:
                acc.signed_at = ser.validated_data.get("signed_at") or timezone.now()
        if "signed_at" in ser.validated_data and ser.validated_data.get("signed_at"):
            acc.signed_at = ser.validated_data["signed_at"]
        acc.save()
        acc.refresh_from_db()
        return Response(BuildingWorkEntryAcceptanceSerializer(acc, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingWorkEntryAcceptanceFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingWorkEntryAcceptanceFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingWorkEntryAcceptance.objects.select_related("work_entry__residential_complex").prefetch_related("files")

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        rc = obj.work_entry.residential_complex
        if not (_is_owner_like(user) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на процесс работы (Building).")
        if not getattr(user, "is_superuser", False) and rc.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Объект другой компании.")
        allowed = _allowed_residential_complex_ids(user)
        if allowed is not None and rc.id not in allowed:
            raise PermissionDenied("Нет доступа к этому ЖК.")
        return obj

    def post(self, request, pk=None):
        acc = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingWorkEntryAcceptanceFile.objects.create(
            acceptance=acc,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        acc.refresh_from_db()
        return Response(BuildingWorkEntryAcceptanceSerializer(acc, context={"request": request}).data, status=status.HTTP_201_CREATED)


# -----------------------
# Debts ledger API
# -----------------------


class BuildingDebtsLedgerListCreateView(CompanyQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingDebtLedgerEntry.objects.all().prefetch_related("files")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["direction", "counterparty_type", "counterparty_id", "status", "residential_complex", "source_type", "source_id"]
    search_fields = ["comment", "source_type"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BuildingDebtLedgerEntryCreateSerializer
        return BuildingDebtLedgerEntrySerializer

    def get_queryset(self):
        user = self.request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_procurement", False) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на долги (Building).")
        qs = super().get_queryset()
        if getattr(user, "is_superuser", False):
            return qs
        company_id = getattr(user, "company_id", None)
        if not company_id:
            return qs.none()
        qs = qs.filter(company_id=company_id)
        allowed = _allowed_residential_complex_ids(user)
        if allowed is not None:
            qs = qs.filter(Q(residential_complex_id__in=allowed) | Q(residential_complex_id__isnull=True))
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        serializer.save(company_id=company_id, created_by=user)


class BuildingDebtsLedgerFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingDebtLedgerFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = BuildingDebtLedgerEntry.objects.all().prefetch_related("files")

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not getattr(user, "is_superuser", False) and obj.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Объект другой компании.")
        return obj

    def post(self, request, pk=None):
        entry = self.get_object()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        BuildingDebtLedgerFile.objects.create(
            entry=entry,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=request.user,
        )
        entry.refresh_from_db()
        return Response(BuildingDebtLedgerEntrySerializer(entry, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingDebtsSummaryView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_procurement", False) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на долги (Building).")
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            return Response([], status=status.HTTP_200_OK)

        qs = BuildingDebtLedgerEntry.objects.filter(company_id=company_id, status=BuildingDebtLedgerEntry.Status.APPROVED)
        allowed = _allowed_residential_complex_ids(user)
        if allowed is not None:
            qs = qs.filter(Q(residential_complex_id__in=allowed) | Q(residential_complex_id__isnull=True))

        # balance = charges - payments - barter - writeoff (+/- adjustments) within direction+counterparty
        agg = qs.values("direction", "counterparty_type", "counterparty_id").annotate(
            charges=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.CHARGE)), Decimal("0.00")),
            payments=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.PAYMENT)), Decimal("0.00")),
            barter=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.BARTER)), Decimal("0.00")),
            writeoff=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.WRITEOFF)), Decimal("0.00")),
            adjustments=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.ADJUSTMENT)), Decimal("0.00")),
        )
        out = []
        for r in agg:
            balance = (r["charges"] - r["payments"] - r["barter"] - r["writeoff"] + r["adjustments"]).quantize(Decimal("0.01"))
            out.append(
                {
                    "direction": r["direction"],
                    "counterparty_type": r["counterparty_type"],
                    "counterparty_id": str(r["counterparty_id"]),
                    "balance": str(balance),
                    "charges": str(r["charges"].quantize(Decimal("0.01"))),
                    "payments": str(r["payments"].quantize(Decimal("0.01"))),
                    "barter": str(r["barter"].quantize(Decimal("0.01"))),
                    "writeoff": str(r["writeoff"].quantize(Decimal("0.01"))),
                    "adjustments": str(r["adjustments"].quantize(Decimal("0.01"))),
                }
            )
        return Response(out, status=status.HTTP_200_OK)


class BuildingDebtsCounterpartySummaryView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, counterparty_type: str, counterparty_id):
        user = request.user
        if not (_is_owner_like(user) or getattr(user, "can_view_building_procurement", False) or getattr(user, "can_view_building_work_process", False)):
            raise PermissionDenied("Нет прав на долги (Building).")
        company_id = getattr(user, "company_id", None)
        qs = BuildingDebtLedgerEntry.objects.filter(
            company_id=company_id,
            status=BuildingDebtLedgerEntry.Status.APPROVED,
            counterparty_type=counterparty_type,
            counterparty_id=counterparty_id,
        )
        agg = qs.values("direction").annotate(
            charges=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.CHARGE)), Decimal("0.00")),
            payments=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.PAYMENT)), Decimal("0.00")),
            barter=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.BARTER)), Decimal("0.00")),
            writeoff=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.WRITEOFF)), Decimal("0.00")),
            adjustments=Coalesce(Sum("amount", filter=Q(entry_type=BuildingDebtLedgerEntry.EntryType.ADJUSTMENT)), Decimal("0.00")),
        )
        out = []
        for r in agg:
            balance = (r["charges"] - r["payments"] - r["barter"] - r["writeoff"] + r["adjustments"]).quantize(Decimal("0.01"))
            out.append({"direction": r["direction"], "balance": str(balance)})
        return Response({"counterparty_type": counterparty_type, "counterparty_id": str(counterparty_id), "results": out}, status=status.HTTP_200_OK)


# -----------------------
# Barter API (generic)
# -----------------------


class BuildingBarterItemsUpsertView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, source_type: str, source_id: str):
        user = request.user
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        items = request.data if isinstance(request.data, list) else request.data.get("items")
        if not isinstance(items, list):
            raise ValidationError({"items": "Ожидается список items."})
        BuildingBarterItem.objects.filter(company_id=company_id, source_type=source_type, source_id=source_id).delete()
        created = []
        for raw in items:
            ser = BuildingBarterItemUpsertSerializer(data=raw)
            ser.is_valid(raise_exception=True)
            v = ser.validated_data
            created.append(
                BuildingBarterItem.objects.create(
                    company_id=company_id,
                    source_type=source_type,
                    source_id=source_id,
                    title=(v["title"] or "").strip(),
                    quantity=v.get("quantity"),
                    unit=(v.get("unit") or "").strip() or None,
                    unit_price=v.get("unit_price"),
                    total_price=v["total_price"],
                    currency=(v.get("currency") or "KGS").strip() or "KGS",
                    comment=(v.get("comment") or "").strip(),
                )
            )
        return Response(BuildingBarterItemSerializer(created, many=True, context={"request": request}).data, status=status.HTTP_201_CREATED)


class BuildingBarterItemDetailView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = BuildingBarterItem.objects.all()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not getattr(user, "is_superuser", False) and obj.company_id != getattr(user, "company_id", None):
            raise PermissionDenied("Объект другой компании.")
        return obj

    def patch(self, request, pk=None):
        obj = self.get_object()
        ser = BuildingBarterItemSerializer(obj, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(BuildingBarterItemSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        obj = self.get_object()
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BuildingBarterFileAddView(CompanyQuerysetMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BuildingBarterFileCreateSerializer
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, source_type: str, source_id: str):
        user = request.user
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise PermissionDenied("У пользователя не указана компания.")
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = BuildingBarterFile.objects.create(
            company_id=company_id,
            source_type=source_type,
            source_id=source_id,
            file=ser.validated_data["file"],
            title=(ser.validated_data.get("title") or "").strip(),
            created_by=user,
        )
        return Response(BuildingBarterFileSerializer(obj, context={"request": request}).data, status=status.HTTP_201_CREATED)
