import uuid
from decimal import Decimal

from rest_framework import serializers
from django.db import transaction
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

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
    BuildingSupplierBarterPurchaseItem,
    BuildingSupplierBarterCounterDelivery,
    BuildingTransferRequestFile,
    BuildingWarehouseRequest,
    BuildingWarehouseRequestItem,
    BuildingReconciliationAct,
    BuildingReconciliationActItem,
    BuildingWarehouseMovement,
    BuildingWarehouseMovementItem,
    BuildingWarehouseMovementFile,
    BuildingClient,
    BuildingClientFile,
    BuildingTaskFile,
    ResidentialComplex,
    ResidentialComplexMember,
    ResidentialComplexDrawing,
    ResidentialComplexWarehouse,
    ResidentialComplexApartment,
    BuildingProduct,
    BuildingProcurementRequest,
    BuildingProcurementItem,
    BuildingProcurementFile,
    BuildingProcurementCashDecision,
    BuildingTransferRequest,
    BuildingTransferItem,
    BuildingWarehouseStockItem,
    BuildingWarehouseStockMove,
    BuildingWorkflowEvent,
    BuildingTreatyNumberSequence,
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
    BuildingTaskAssignee,
    BuildingTaskChecklistItem,
    BuildingEmployeeCompensation,
    BuildingPayrollPeriod,
    BuildingPayrollLine,
    BuildingPayrollAdjustment,
    BuildingPayrollPayment,
)

User = get_user_model()


class ResidentialComplexSerializer(serializers.ModelSerializer):
    """Сериализатор для ЖК: список и детали."""

    class Meta:
        model = ResidentialComplex
        fields = [
            "id",
            "company",
            "name",
            "address",
            "description",
            "salary_cashbox",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]


class ResidentialComplexCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания ЖК. company подставляется из request.user."""

    class Meta:
        model = ResidentialComplex
        fields = [
            "id",
            "name",
            "address",
            "description",
            "is_active",
            "salary_cashbox",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        company = self.context["request"].user.company
        if not company:
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})
        validated_data["company_id"] = company.id
        return super().create(validated_data)


class ResidentialComplexMemberSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField(read_only=True)
    added_by_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ResidentialComplexMember
        fields = [
            "id",
            "residential_complex",
            "user",
            "user_display",
            "is_active",
            "added_by",
            "added_by_display",
            "created_at",
        ]
        read_only_fields = ["id", "user_display", "added_by", "added_by_display", "created_at"]

    def _display_user(self, u):
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))

    def get_user_display(self, obj):
        return self._display_user(getattr(obj, "user", None))

    def get_added_by_display(self, obj):
        return self._display_user(getattr(obj, "added_by", None))


class ResidentialComplexMemberCreateSerializer(serializers.Serializer):
    user = serializers.UUIDField(required=True)
    is_active = serializers.BooleanField(required=False, default=True)


class ResidentialComplexDrawingSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ResidentialComplexDrawing
        fields = [
            "id",
            "residential_complex",
            "title",
            "file",
            "file_url",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "file_url", "created_at", "updated_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate_residential_complex(self, value):
        user = self.context["request"].user
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            user_company_id = getattr(user, "company_id", None)
            if not user_company_id:
                raise serializers.ValidationError("У пользователя не указана компания.")
            if value.company_id != user_company_id:
                raise serializers.ValidationError("ЖК принадлежит другой компании.")
        return value


class ResidentialComplexWarehouseSerializer(serializers.ModelSerializer):
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)

    class Meta:
        model = ResidentialComplexWarehouse
        fields = [
            "id",
            "residential_complex",
            "residential_complex_name",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ResidentialComplexApartmentSerializer(serializers.ModelSerializer):
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)
    client_id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ResidentialComplexApartment
        fields = [
            "id",
            "residential_complex",
            "residential_complex_name",
            "floor",
            "number",
            "block",
            "rooms",
            "area",
            "price",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "client_id",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "residential_complex_name", "client_id"]

    def get_client_id(self, obj):
        # Определяем клиента по последнему договору по этой квартире (если есть).
        treaty = None

        # Если prefetch_related уже подтянул treaties, используем их, чтобы избежать доп. запросов.
        rel = getattr(obj, "treaties", None)
        if hasattr(rel, "all"):
            treaty = rel.order_by("-created_at").first()
        else:
            treaty = BuildingTreaty.objects.filter(apartment_id=obj.id).order_by("-created_at").first()

        client = getattr(treaty, "client", None) if treaty else None
        if not client:
            return None
        return str(getattr(client, "id", None)) or None


# -----------------------
# Contractors
# -----------------------


class BuildingContractorFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingContractorFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingContractorSerializer(serializers.ModelSerializer):
    files = BuildingContractorFileSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingContractor
        fields = [
            "id", "company", "company_name", "contractor_type", "tax_id", "registration_number",
            "year_founded", "contact_person", "phone", "email", "city", "address",
            "specializations", "employees", "equipment", "status",
            "created_at", "updated_at", "files",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at", "files"]


class BuildingContractorCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingContractor
        fields = [
            "company_name", "contractor_type", "tax_id", "registration_number", "year_founded",
            "contact_person", "phone", "email", "city", "address",
            "specializations", "employees", "equipment", "status",
        ]

    def create(self, validated_data):
        company = self.context["request"].user.company
        if not company:
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})
        validated_data["company_id"] = company.id
        return super().create(validated_data)


# -----------------------
# Suppliers
# -----------------------


class BuildingSupplierFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingSupplierFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingSupplierSerializer(serializers.ModelSerializer):
    files = BuildingSupplierFileSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingSupplier
        fields = [
            "id", "company", "company_name", "supplier_type", "tax_id", "registration_number",
            "year_founded", "contact_person", "position", "phone", "email", "website",
            "city", "address", "postal_code", "bank_details", "supplied_materials",
            "delivery", "warehouse", "rating", "completed_orders", "status",
            "created_at", "updated_at", "files",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at", "files"]


class BuildingSupplierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingSupplier
        fields = [
            "company_name", "supplier_type", "tax_id", "registration_number", "year_founded",
            "contact_person", "position", "phone", "email", "website",
            "city", "address", "postal_code", "bank_details", "supplied_materials",
            "delivery", "warehouse", "rating", "completed_orders", "status",
        ]

    def create(self, validated_data):
        company = self.context["request"].user.company
        if not company:
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})
        validated_data["company_id"] = company.id
        return super().create(validated_data)


class BuildingSupplierBarterPurchaseItemSerializer(serializers.ModelSerializer):
    procurement_id = serializers.UUIDField(source="procurement_item.procurement_id", read_only=True)

    class Meta:
        model = BuildingSupplierBarterPurchaseItem
        fields = ["id", "procurement_item", "procurement_id", "amount"]
        read_only_fields = ["id", "procurement_id"]


class BuildingSupplierBarterCounterDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingSupplierBarterCounterDelivery
        fields = ["id", "description", "amount"]
        read_only_fields = ["id"]


class BuildingSupplierBarterSettlementSerializer(serializers.ModelSerializer):
    supplier_name = serializers.SerializerMethodField(read_only=True)
    contractor_name = serializers.SerializerMethodField(read_only=True)
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)
    created_by_display = serializers.SerializerMethodField(read_only=True)
    purchase_items = BuildingSupplierBarterPurchaseItemSerializer(many=True, read_only=True)
    counter_deliveries = BuildingSupplierBarterCounterDeliverySerializer(many=True, read_only=True)

    class Meta:
        model = BuildingSupplierBarterSettlement
        fields = [
            "id",
            "company",
            "supplier",
            "supplier_name",
            "contractor",
            "contractor_name",
            "residential_complex",
            "residential_complex_name",
            "date",
            "status",
            "amount_total",
            "currency",
            "comment",
            "created_by",
            "created_by_display",
            "created_at",
            "updated_at",
            "purchase_items",
            "counter_deliveries",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_by",
            "created_by_display",
            "created_at",
            "updated_at",
            "supplier_name",
            "contractor_name",
            "residential_complex_name",
            "purchase_items",
            "counter_deliveries",
        ]

    def get_supplier_name(self, obj):
        s = getattr(obj, "supplier", None)
        return s.company_name if s else None

    def get_contractor_name(self, obj):
        c = getattr(obj, "contractor", None)
        return c.company_name if c else None

    def get_created_by_display(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))


class BuildingSupplierBarterSettlementCreateUpdateSerializer(serializers.ModelSerializer):
    purchase_items = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )
    counter_deliveries = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = BuildingSupplierBarterSettlement
        fields = [
            "id",
            "supplier",
            "contractor",
            "residential_complex",
            "date",
            "amount_total",
            "currency",
            "comment",
            "purchase_items",
            "counter_deliveries",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        inst = self.instance
        if "supplier" in attrs:
            supplier = attrs["supplier"]
        elif inst:
            supplier = inst.supplier
        else:
            supplier = None
        if "contractor" in attrs:
            contractor = attrs["contractor"]
        elif inst:
            contractor = inst.contractor
        else:
            contractor = None

        rc = attrs.get("residential_complex") or getattr(inst, "residential_complex", None)

        if bool(supplier) == bool(contractor):
            raise serializers.ValidationError(
                {"non_field_errors": "Укажите ровно одного контрагента: supplier или contractor."}
            )

        if supplier and rc and supplier.company_id != rc.company_id:
            raise serializers.ValidationError({"residential_complex": "ЖК принадлежит другой компании, чем поставщик."})
        if contractor and rc and contractor.company_id != rc.company_id:
            raise serializers.ValidationError({"residential_complex": "ЖК принадлежит другой компании, чем подрядчик."})

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        company_id = getattr(user, "company_id", None)
        if company_id and supplier and supplier.company_id != company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"supplier": "Поставщик принадлежит другой компании."})
        if company_id and contractor and contractor.company_id != company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"contractor": "Подрядчик принадлежит другой компании."})

        if supplier and not contractor:
            attrs["contractor"] = None
        elif contractor and not supplier:
            attrs["supplier"] = None

        return attrs

    def _sync_nested(self, settlement, purchase_items, counter_deliveries):
        is_contractor = bool(settlement.contractor_id)
        if purchase_items is not None:
            if is_contractor and purchase_items:
                raise serializers.ValidationError(
                    {"purchase_items": "Для зачёта с подрядчиком строки закупок не задаются."}
                )
            BuildingSupplierBarterPurchaseItem.objects.filter(settlement=settlement).delete()
            if not is_contractor:
                for i, raw in enumerate(purchase_items, start=1):
                    procurement_item = raw.get("procurement_item")
                    amount = raw.get("amount")
                    if not procurement_item or amount in (None, ""):
                        raise serializers.ValidationError(
                            {"purchase_items": f"Строка #{i}: укажите procurement_item и amount."}
                        )
                    BuildingSupplierBarterPurchaseItem.objects.create(
                        settlement=settlement,
                        procurement_item=procurement_item,
                        amount=amount,
                    )

        if counter_deliveries is not None:
            BuildingSupplierBarterCounterDelivery.objects.filter(settlement=settlement).delete()
            for i, raw in enumerate(counter_deliveries, start=1):
                description = (raw.get("description") or "").strip()
                amount = raw.get("amount")
                if not description or amount in (None, ""):
                    raise serializers.ValidationError(
                        {"counter_deliveries": f"Строка #{i}: укажите description и amount."}
                    )
                BuildingSupplierBarterCounterDelivery.objects.create(
                    settlement=settlement,
                    description=description,
                    amount=amount,
                )

    @transaction.atomic
    def create(self, validated_data):
        purchase_items = validated_data.pop("purchase_items", [])
        counter_deliveries = validated_data.pop("counter_deliveries", [])

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})

        settlement = BuildingSupplierBarterSettlement.objects.create(
            company_id=company_id,
            created_by=user,
            **validated_data,
        )
        self._sync_nested(settlement, purchase_items, counter_deliveries)
        return settlement

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != BuildingSupplierBarterSettlement.Status.DRAFT:
            raise serializers.ValidationError({"status": "Менять можно только черновик бартерного зачёта."})

        purchase_items = validated_data.pop("purchase_items", None)
        counter_deliveries = validated_data.pop("counter_deliveries", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._sync_nested(instance, purchase_items, counter_deliveries)
        return instance


# -----------------------
# Warehouse requests, reconciliation, movements
# -----------------------


class BuildingWarehouseRequestItemSerializer(serializers.ModelSerializer):
    stock_item_name = serializers.CharField(source="stock_item.name", read_only=True)

    class Meta:
        model = BuildingWarehouseRequestItem
        fields = ["id", "stock_item", "stock_item_name", "quantity", "unit", "approved_quantity", "created_at"]
        read_only_fields = ["id", "created_at"]


class BuildingWarehouseRequestSerializer(serializers.ModelSerializer):
    items = BuildingWarehouseRequestItemSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    work_entry_title = serializers.CharField(source="work_entry.title", read_only=True)

    class Meta:
        model = BuildingWarehouseRequest
        fields = [
            "id",
            "work_entry",
            "work_entry_title",
            "warehouse",
            "warehouse_name",
            "comment",
            "status",
            "items",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "work_entry_title", "warehouse_name"]


class BuildingWarehouseRequestCreateSerializer(serializers.Serializer):
    warehouse = serializers.UUIDField()
    items = serializers.ListField(child=serializers.DictField())
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate_items(self, value):
        for i, item in enumerate(value):
            # Поддерживаем как старое поле `stock_item`, так и новое `nomenclature`.
            stock_item = item.get("stock_item") or item.get("nomenclature")
            if not stock_item or "quantity" not in item:
                raise serializers.ValidationError(f"Позиция {i}: укажите nomenclature/stock_item и quantity.")
            item["stock_item"] = stock_item
            if "unit" not in item:
                item["unit"] = "шт"
        return value


class BuildingReconciliationActItemSerializer(serializers.ModelSerializer):
    stock_item_name = serializers.CharField(source="stock_item.name", read_only=True)

    class Meta:
        model = BuildingReconciliationActItem
        fields = ["id", "stock_item", "stock_item_name", "quantity", "unit", "created_at"]
        read_only_fields = ["id", "created_at"]


class BuildingReconciliationActSerializer(serializers.ModelSerializer):
    returned_items = BuildingReconciliationActItemSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingReconciliationAct
        fields = ["id", "work_entry", "comment", "status", "returned_items", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class BuildingReconciliationActCreateSerializer(serializers.Serializer):
    returned_items = serializers.ListField(
        child=serializers.DictField()
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate_returned_items(self, value):
        for i, item in enumerate(value):
            if "stock_item" not in item or "quantity" not in item:
                raise serializers.ValidationError(f"Позиция {i}: укажите stock_item и quantity.")
            if "unit" not in item:
                item["unit"] = "шт"
        return value


class BuildingWarehouseMovementItemSerializer(serializers.ModelSerializer):
    stock_item_name = serializers.CharField(source="stock_item.name", read_only=True)

    class Meta:
        model = BuildingWarehouseMovementItem
        fields = ["id", "stock_item", "stock_item_name", "quantity", "created_at"]
        read_only_fields = ["id", "created_at"]


class BuildingWarehouseMovementFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingWarehouseMovementFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingWarehouseMovementSerializer(serializers.ModelSerializer):
    items = BuildingWarehouseMovementItemSerializer(many=True, read_only=True)
    files = BuildingWarehouseMovementFileSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = BuildingWarehouseMovement
        fields = [
            "id", "company", "warehouse", "warehouse_name", "movement_type",
            "contractor", "work_entry", "warehouse_request", "issued_to", "reason", "items", "files",
            "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BuildingWarehouseMovementWriteOffSerializer(serializers.Serializer):
    warehouse = serializers.UUIDField()
    items = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField())
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class BuildingWarehouseMovementTransferSerializer(serializers.Serializer):
    warehouse = serializers.UUIDField()
    warehouse_request = serializers.UUIDField(required=False, allow_null=True)
    issued_to = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = serializers.ListField(child=serializers.DictField())
    comment = serializers.CharField(required=False, allow_blank=True)
    # contractor or work_entry / warehouse_request - one of them required for transfer

    def validate_items(self, value):
        for i, item in enumerate(value):
            stock_item = item.get("stock_item") or item.get("nomenclature")
            if not stock_item or "quantity" not in item:
                raise serializers.ValidationError(f"Позиция {i}: укажите nomenclature/stock_item и quantity.")
            item["stock_item"] = stock_item
        return value


class BuildingTransferRequestFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingTransferRequestFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingProduct
        fields = [
            "id",
            "company",
            "name",
            "article",
            "barcode",
            "unit",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]


class BuildingProcurementItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_article = serializers.CharField(source="product.article", read_only=True)

    class Meta:
        model = BuildingProcurementItem
        fields = [
            "id",
            "procurement",
            "product",
            "product_name",
            "product_article",
            "name",
            "unit",
            "quantity",
            "price",
            "line_total",
            "order",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "line_total", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        procurement = attrs.get("procurement") or getattr(self.instance, "procurement", None)
        product = attrs.get("product")
        if product and procurement and product.company_id != procurement.residential_complex.company_id:
            raise serializers.ValidationError({"product": "Товар принадлежит другой компании."})
        if product:
            attrs.setdefault("name", product.name)
            attrs.setdefault("unit", product.unit)
        return attrs


class BuildingProcurementCashDecisionSerializer(serializers.ModelSerializer):
    decided_by_display = serializers.SerializerMethodField()

    class Meta:
        model = BuildingProcurementCashDecision
        fields = ["id", "procurement", "decision", "reason", "decided_by", "decided_by_display", "decided_at"]
        read_only_fields = ["id", "decided_at", "decided_by_display"]

    def get_decided_by_display(self, obj):
        user = getattr(obj, "decided_by", None)
        if not user:
            return None
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return full_name or getattr(user, "email", None) or str(getattr(user, "id", ""))


class BuildingTransferItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingTransferItem
        fields = [
            "id",
            "transfer",
            "procurement_item",
            "name",
            "unit",
            "quantity",
            "price",
            "line_total",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "line_total", "created_at", "updated_at"]


class BuildingTransferSerializer(serializers.ModelSerializer):
    items = BuildingTransferItemSerializer(many=True, read_only=True)
    files = BuildingTransferRequestFileSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    procurement_title = serializers.CharField(source="procurement.title", read_only=True)

    class Meta:
        model = BuildingTransferRequest
        fields = [
            "id",
            "procurement",
            "procurement_title",
            "warehouse",
            "warehouse_name",
            "created_by",
            "decided_by",
            "status",
            "note",
            "rejection_reason",
            "total_amount",
            "accepted_at",
            "rejected_at",
            "created_at",
            "updated_at",
            "items",
            "files",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "decided_by",
            "status",
            "rejection_reason",
            "total_amount",
            "accepted_at",
            "rejected_at",
            "created_at",
            "updated_at",
            "items",
        ]


class BuildingProcurementFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingProcurementFile
        fields = ["id", "file_url", "title", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingProcurementSerializer(serializers.ModelSerializer):
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.company_name", read_only=True)
    initiator_display = serializers.SerializerMethodField()
    cash_decision = BuildingProcurementCashDecisionSerializer(read_only=True)
    transfers = BuildingTransferSerializer(many=True, read_only=True)
    items = BuildingProcurementItemSerializer(many=True, read_only=True)
    files = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingProcurementRequest
        fields = [
            "id",
            "residential_complex",
            "residential_complex_name",
            "supplier",
            "supplier_name",
            "initiator",
            "initiator_display",
            "title",
            "comment",
            "payment_mode",
            "treaty",
            "treaty_auto_create",
            "treaty_type",
            "treaty_title",
            "status",
            "total_amount",
            "submitted_to_cash_at",
            "cash_decided_at",
            "cash_decided_by",
            "created_at",
            "updated_at",
            "cash_decision",
            "items",
            "transfers",
            "files",
        ]
        read_only_fields = [
            "id",
            "initiator",
            "status",
            "total_amount",
            "submitted_to_cash_at",
            "cash_decided_at",
            "cash_decided_by",
            "created_at",
            "updated_at",
            "cash_decision",
            "items",
            "transfers",
            "files",
        ]

    def get_files(self, obj):
        files_qs = getattr(obj, "files", None)
        if files_qs is None:
            return []
        return BuildingProcurementFileSerializer(files_qs.all(), many=True, context=self.context).data

    def get_initiator_display(self, obj):
        user = getattr(obj, "initiator", None)
        if not user:
            return None
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return full_name or getattr(user, "email", None) or str(getattr(user, "id", ""))


class BuildingWorkflowEventSerializer(serializers.ModelSerializer):
    actor_display = serializers.SerializerMethodField()

    class Meta:
        model = BuildingWorkflowEvent
        fields = [
            "id",
            "procurement",
            "procurement_item",
            "transfer",
            "transfer_item",
            "warehouse",
            "stock_item",
            "actor",
            "actor_display",
            "action",
            "from_status",
            "to_status",
            "message",
            "payload",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_display(self, obj):
        user = getattr(obj, "actor", None)
        if not user:
            return None
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return full_name or getattr(user, "email", None) or str(getattr(user, "id", ""))


class BuildingWarehouseStockItemSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = BuildingWarehouseStockItem
        fields = ["id", "warehouse", "warehouse_name", "name", "unit", "quantity", "last_price", "created_at", "updated_at"]
        read_only_fields = fields


class BuildingWarehouseStockMoveSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    stock_item_name = serializers.CharField(source="stock_item.name", read_only=True)

    class Meta:
        model = BuildingWarehouseStockMove
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "stock_item",
            "stock_item_name",
            "transfer",
            "move_type",
            "quantity_delta",
            "price",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class BuildingReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)


class BuildingTransferCreateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class BuildingTransferAcceptSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class BuildingClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingClient
        fields = [
            "id",
            "company",
            "name",
            "phone",
            "email",
            "inn",
            "address",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]

class BuildingClientFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingClientFile
        fields = ["id", "file_url", "title", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingClientDetailSerializer(BuildingClientSerializer):
    treaties = serializers.SerializerMethodField(read_only=True)
    files = serializers.SerializerMethodField(read_only=True)

    class Meta(BuildingClientSerializer.Meta):
        fields = BuildingClientSerializer.Meta.fields + ["treaties", "files"]

    def get_files(self, obj):
        files_qs = getattr(obj, "files", None)
        if files_qs is None:
            return []
        return BuildingClientFileSerializer(files_qs.all(), many=True, context=self.context).data

    def get_treaties(self, obj):
        # В карточке клиента возвращаем договора/сделки по квартирам вместе с файлами и рассрочкой.
        treaties = getattr(obj, "treaties", None)
        if treaties is None:
            return []
        qs = treaties.select_related("residential_complex", "apartment", "created_by").prefetch_related("files", "installments")

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and getattr(user, "is_authenticated", False) and not getattr(user, "is_superuser", False):
            # сотрудник (не owner/admin): только договора по назначенным ЖК; без назначений — ничего
            if getattr(user, "role", None) not in ("owner", "admin") and not getattr(user, "owned_company_id", None):
                allowed = ResidentialComplexMember.objects.filter(
                    user_id=getattr(user, "id", None),
                    is_active=True,
                    residential_complex__company_id=getattr(user, "company_id", None),
                ).values_list("residential_complex_id", flat=True)
                allowed_ids = list(allowed)
                qs = qs.filter(residential_complex_id__in=allowed_ids)

        return BuildingTreatySerializer(qs, many=True, context=self.context).data


class BuildingTreatyFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingTreatyFile
        fields = ["id", "treaty", "title", "file", "file_url", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at", "file_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class BuildingTreatyFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, allow_blank=True)


class BuildingTreatySerializer(serializers.ModelSerializer):
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True, allow_null=True)
    client_name = serializers.SerializerMethodField(read_only=True)
    apartment_number = serializers.CharField(source="apartment.number", read_only=True, allow_null=True)
    apartment_floor = serializers.IntegerField(source="apartment.floor", read_only=True, allow_null=True)
    files = BuildingTreatyFileSerializer(many=True, read_only=True)
    created_by_display = serializers.SerializerMethodField()
    installments = serializers.SerializerMethodField(read_only=True)

    def _installments_qs(self, obj):
        rel = getattr(obj, "installments", None)
        if rel is None:
            return []
        return rel.all().order_by("order", "due_date", "created_at")

    def get_installments(self, obj):
        return BuildingTreatyInstallmentSerializer(self._installments_qs(obj), many=True).data

    class Meta:
        model = BuildingTreaty
        fields = [
            "id",
            "company",
            "residential_complex",
            "residential_complex_name",
            "client",
            "client_name",
            "created_by",
            "created_by_display",
            "number",
            "title",
            "description",
            "amount",
            "treaty_type",
            "apartment",
            "apartment_number",
            "apartment_floor",
            "operation_type",
            "payment_type",
            "payment_mode",
            "group",
            "down_payment",
            "payment_terms",
            "status",
            "signed_at",
            "auto_create_in_erp",
            "erp_sync_status",
            "erp_external_id",
            "erp_last_error",
            "erp_requested_at",
            "erp_synced_at",
            "created_at",
            "updated_at",
            "files",
            "installments",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_by",
            "created_by_display",
            "erp_sync_status",
            "erp_external_id",
            "erp_last_error",
            "erp_requested_at",
            "erp_synced_at",
            "created_at",
            "updated_at",
            "files",
            "residential_complex_name",
            "apartment_number",
            "apartment_floor",
            "installments",
        ]

    def get_client_name(self, obj):
        """Возвращает имя клиента: из карточки client или из поля client_name."""
        client = getattr(obj, "client", None)
        if client:
            return getattr(client, "name", None) or ""
        return getattr(obj, "client_name", None) or ""

    def get_created_by_display(self, obj):
        user = getattr(obj, "created_by", None)
        if not user:
            return None
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return full_name or getattr(user, "email", None) or str(getattr(user, "id", ""))

    def validate(self, attrs):
        attrs = super().validate(attrs)

        operation_type = attrs.get("operation_type") or getattr(self.instance, "operation_type", None)
        payment_type = attrs.get("payment_type") or getattr(self.instance, "payment_type", None)
        installments_data = self.initial_data.get("installments", None)

        # Обязательность полей по типу договора (booking/sale vs other)
        is_booking_or_sale = operation_type in (
            BuildingTreaty.OperationType.BOOKING,
            BuildingTreaty.OperationType.SALE,
        )
        if is_booking_or_sale:
            rc = attrs.get("residential_complex") or getattr(self.instance, "residential_complex", None)
            if not rc:
                raise serializers.ValidationError({"residential_complex": "Для брони и продажи обязателен ЖК."})
            if not attrs.get("client") and not getattr(self.instance, "client", None):
                raise serializers.ValidationError({"client": "Для брони и продажи обязателен клиент."})
            apt = attrs.get("apartment") or getattr(self.instance, "apartment", None)
            if not apt:
                raise serializers.ValidationError({"apartment": "Для брони и продажи обязательна квартира."})
            amt = attrs.get("amount")
            if amt is None:
                amt = getattr(self.instance, "amount", None)
            if amt is None or (hasattr(amt, "__float__") and float(amt) <= 0):
                raise serializers.ValidationError({"amount": "Для брони и продажи обязательна сумма."})
            if not operation_type:
                raise serializers.ValidationError({"operation_type": "Обязателен тип договора."})
            if not payment_type:
                raise serializers.ValidationError({"payment_type": "Обязателен тип оплаты."})
        else:
            # other: residential_complex и amount опциональны; apartment, client — опциональны
            pass

        # На чтение installments идёт отдельным полем; на запись принимаем как list[...]
        if installments_data is not None:
            if payment_type != BuildingTreaty.PaymentType.INSTALLMENT:
                raise serializers.ValidationError({"installments": "График рассрочки можно задавать только при payment_type=installment."})
            if not isinstance(installments_data, list) or not installments_data:
                raise serializers.ValidationError({"installments": "Передайте непустой список платежей рассрочки."})

        apartment = attrs.get("apartment") or getattr(self.instance, "apartment", None)
        rc = attrs.get("residential_complex") or getattr(self.instance, "residential_complex", None)
        if apartment and rc and apartment.residential_complex_id != rc.id:
            raise serializers.ValidationError({"apartment": "Квартира относится к другому ЖК."})

        # не даём менять квартиру у не-черновика (чтобы не ломать историю)
        if self.instance and "apartment" in attrs:
            if getattr(self.instance, "status", None) != BuildingTreaty.Status.DRAFT and attrs["apartment"] != getattr(self.instance, "apartment", None):
                raise serializers.ValidationError({"apartment": "Квартиру можно менять только в статусе draft."})

        return attrs

    def _next_number(self, company_id):
        seq, _ = BuildingTreatyNumberSequence.objects.select_for_update().get_or_create(company_id=company_id)
        v = int(seq.next_value or 1)
        seq.next_value = v + 1
        seq.save(update_fields=["next_value", "updated_at"])
        return f"ДГ-{v:06d}"

    def _parse_installments(self):
        raw = self.initial_data.get("installments", None)
        if raw is None:
            return None
        if not isinstance(raw, list):
            raise serializers.ValidationError({"installments": "Ожидается список платежей."})
        date_f = serializers.DateField()
        dec_f = serializers.DecimalField(max_digits=16, decimal_places=2)
        out = []
        for i, it in enumerate(raw, start=1):
            if not isinstance(it, dict):
                raise serializers.ValidationError({"installments": f"Платёж #{i}: ожидается объект."})
            due_date = it.get("due_date")
            amount = it.get("amount")
            if not due_date or amount in (None, ""):
                raise serializers.ValidationError({"installments": f"Платёж #{i}: нужны due_date и amount."})
            try:
                due_date_v = date_f.to_internal_value(due_date)
            except Exception:
                raise serializers.ValidationError({"installments": f"Платёж #{i}: некорректный due_date."})
            try:
                amount_v = dec_f.to_internal_value(amount)
            except Exception:
                raise serializers.ValidationError({"installments": f"Платёж #{i}: некорректная amount."})
            out.append(
                {
                    "order": int(it.get("order") or i),
                    "due_date": due_date_v,
                    "amount": amount_v,
                }
            )
        return out

    @transaction.atomic
    def create(self, validated_data):
        installments_data = self._parse_installments()

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        user_company_id = getattr(user, "company_id", None) if user else None

        rc = validated_data.get("residential_complex")
        operation_type = validated_data.get("operation_type") or BuildingTreaty.OperationType.SALE

        # company_id: из ЖК или из пользователя (для other без ЖК)
        if rc:
            validated_data["company_id"] = rc.company_id
        elif user_company_id:
            validated_data["company_id"] = user_company_id
        elif not getattr(user, "is_superuser", False):
            raise serializers.ValidationError(
                {"residential_complex": "Укажите ЖК или убедитесь, что у пользователя указана компания (для прочих договоров)."}
            )

        company_id = validated_data.get("company_id")
        if not (validated_data.get("number") or "").strip() and company_id:
            validated_data["number"] = self._next_number(company_id)

        apartment = validated_data.get("apartment")
        if apartment and rc:
            apartment = ResidentialComplexApartment.objects.select_for_update().get(pk=apartment.pk)
            if apartment.residential_complex_id != rc.id:
                raise serializers.ValidationError({"apartment": "Квартира относится к другому ЖК."})
            if operation_type in (BuildingTreaty.OperationType.BOOKING, BuildingTreaty.OperationType.SALE):
                if apartment.status != ResidentialComplexApartment.Status.AVAILABLE:
                    raise serializers.ValidationError({"apartment": "Квартира недоступна для продажи/брони (статус не available)."})
            validated_data["apartment"] = apartment

        payment_type = validated_data.get("payment_type") or BuildingTreaty.PaymentType.FULL
        if payment_type == BuildingTreaty.PaymentType.INSTALLMENT and not installments_data:
            raise serializers.ValidationError({"installments": "Для рассрочки нужно передать график платежей."})

        treaty = BuildingTreaty.objects.create(**validated_data)

        if installments_data:
            total_installments = Decimal("0.00")
            for it in installments_data:
                BuildingTreatyInstallment.objects.create(
                    treaty=treaty,
                    order=it["order"],
                    due_date=it["due_date"],
                    amount=it["amount"],
                )
                total_installments += Decimal(it["amount"] or 0)

            down = Decimal(treaty.down_payment or 0).quantize(Decimal("0.01"))
            amt = Decimal(treaty.amount or 0).quantize(Decimal("0.01"))
            total = (down + total_installments).quantize(Decimal("0.01"))
            if total != amt:
                # допускаем, что на фронте могут не хотеть строгую проверку;
                # но базово контролируем целостность условий оплаты
                raise serializers.ValidationError(
                    {"installments": "Сумма (down_payment + installments) должна быть равна amount."}
                )

        if apartment and treaty.operation_type in (BuildingTreaty.OperationType.BOOKING, BuildingTreaty.OperationType.SALE):
            new_status = (
                ResidentialComplexApartment.Status.SOLD
                if treaty.operation_type == BuildingTreaty.OperationType.SALE
                else ResidentialComplexApartment.Status.RESERVED
            )
            apartment.status = new_status
            apartment.save(update_fields=["status", "updated_at"])

        # created_by обычно проставляет view; но если нет — попробуем проставить из request
        if treaty.created_by_id is None and user and getattr(user, "id", None):
            BuildingTreaty.objects.filter(pk=treaty.pk).update(created_by=user)
            treaty.created_by = user

        return treaty

    @transaction.atomic
    def update(self, instance, validated_data):
        installments_data = self._parse_installments()

        payment_type = validated_data.get("payment_type") or instance.payment_type
        operation_type = validated_data.get("operation_type") or instance.operation_type

        # При смене с other на booking/sale — валидация в validate() потребует заполнения apartment/client/amount

        if payment_type == BuildingTreaty.PaymentType.INSTALLMENT and installments_data is None:
            # не передали installments — не трогаем существующие
            pass

        # если переключили на full — очищаем рассрочку
        if "payment_type" in validated_data and payment_type != BuildingTreaty.PaymentType.INSTALLMENT:
            instance.installments.all().delete()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if installments_data is not None:
            if payment_type != BuildingTreaty.PaymentType.INSTALLMENT:
                raise serializers.ValidationError({"installments": "График рассрочки можно задавать только при payment_type=installment."})
            instance.installments.all().delete()
            total_installments = Decimal("0.00")
            for it in installments_data:
                BuildingTreatyInstallment.objects.create(
                    treaty=instance,
                    order=it["order"],
                    due_date=it["due_date"],
                    amount=it["amount"],
                )
                total_installments += Decimal(it["amount"] or 0)

            down = Decimal(instance.down_payment or 0).quantize(Decimal("0.01"))
            amt = Decimal(instance.amount or 0).quantize(Decimal("0.01"))
            total = (down + total_installments).quantize(Decimal("0.01"))
            if total != amt:
                raise serializers.ValidationError(
                    {"installments": "Сумма (down_payment + installments) должна быть равна amount."}
                )

        return instance


class BuildingTreatyInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingTreatyInstallment
        fields = ["id", "treaty", "order", "due_date", "amount", "status", "paid_amount", "paid_at", "created_at", "updated_at"]
        read_only_fields = ["id", "treaty", "status", "paid_amount", "paid_at", "created_at", "updated_at"]


class BuildingTreatyInstallmentPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    cashbox = serializers.UUIDField(required=True)
    paid_at = serializers.DateTimeField(required=False)
    external_payment_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BuildingTreatyGroupSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingTreatyGroup
        fields = ["id", "company", "residential_complex", "parent", "title", "order", "is_active", "children", "created_at", "updated_at"]
        read_only_fields = ["id", "company", "children", "created_at", "updated_at"]

    def get_children(self, obj):
        rel = getattr(obj, "children", None)
        if rel is None:
            return []
        qs = rel.all().order_by("order", "title")
        return BuildingTreatyGroupSerializer(qs, many=True, context=self.context).data


class BuildingTreatyGroupCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingTreatyGroup
        fields = ["id", "residential_complex", "parent", "title", "order", "is_active"]
        read_only_fields = ["id"]


class BuildingTreatyMoveSerializer(serializers.Serializer):
    treaty_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    target_group = serializers.UUIDField(allow_null=True, required=False)


class BuildingDebtLedgerFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingDebtLedgerFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at", "file_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class BuildingDebtLedgerEntrySerializer(serializers.ModelSerializer):
    files = BuildingDebtLedgerFileSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingDebtLedgerEntry
        fields = [
            "id",
            "company",
            "direction",
            "counterparty_type",
            "counterparty_id",
            "entry_type",
            "amount",
            "currency",
            "status",
            "residential_complex",
            "source_type",
            "source_id",
            "comment",
            "occurred_at",
            "created_by",
            "created_at",
            "updated_at",
            "files",
        ]
        read_only_fields = ["id", "company", "created_by", "created_at", "updated_at", "files"]


class BuildingDebtLedgerEntryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingDebtLedgerEntry
        fields = [
            "direction",
            "counterparty_type",
            "counterparty_id",
            "entry_type",
            "amount",
            "currency",
            "status",
            "residential_complex",
            "source_type",
            "source_id",
            "comment",
            "occurred_at",
        ]


class BuildingDebtLedgerFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, allow_blank=True)


class BuildingBarterItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingBarterItem
        fields = [
            "id",
            "company",
            "title",
            "quantity",
            "unit",
            "unit_price",
            "total_price",
            "currency",
            "comment",
            "source_type",
            "source_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]


class BuildingBarterItemUpsertSerializer(serializers.Serializer):
    title = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=16, decimal_places=3, required=False, allow_null=True)
    unit = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unit_price = serializers.DecimalField(max_digits=16, decimal_places=2, required=False, allow_null=True)
    total_price = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BuildingBarterFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingBarterFile
        fields = ["id", "file", "file_url", "title", "created_at", "source_type", "source_id"]
        read_only_fields = ["id", "created_at", "file_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class BuildingBarterFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, allow_blank=True)


class BuildingWorkEntryAcceptanceFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingWorkEntryAcceptanceFile
        fields = ["id", "file", "file_url", "title", "created_at"]
        read_only_fields = ["id", "created_at", "file_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class BuildingWorkEntryAcceptanceSerializer(serializers.ModelSerializer):
    files = BuildingWorkEntryAcceptanceFileSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingWorkEntryAcceptance
        fields = ["id", "work_entry", "status", "comment", "created_at", "signed_at", "files"]
        read_only_fields = ["id", "work_entry", "created_at", "files"]


class BuildingWorkEntryAcceptanceUpsertSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=BuildingWorkEntryAcceptance.Status.choices, required=False)
    comment = serializers.CharField(required=False, allow_blank=True)
    signed_at = serializers.DateTimeField(required=False, allow_null=True)


class BuildingWorkEntryAcceptanceFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, allow_blank=True)


class BuildingTaskChecklistItemSerializer(serializers.ModelSerializer):
    done_by_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingTaskChecklistItem
        fields = [
            "id",
            "task",
            "text",
            "is_done",
            "order",
            "done_by",
            "done_by_display",
            "done_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "task", "done_by", "done_by_display", "done_at", "created_at", "updated_at"]

    def get_done_by_display(self, obj):
        u = getattr(obj, "done_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))


class BuildingTaskFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingTaskFile
        fields = ["id", "file_url", "title", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingTaskSerializer(serializers.ModelSerializer):
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True,
        help_text="Список пользователей, которым назначена задача",
    )
    assignees = serializers.SerializerMethodField(read_only=True)
    checklist_items = BuildingTaskChecklistItemSerializer(many=True, read_only=True)
    files = serializers.SerializerMethodField(read_only=True)

    created_by_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingTask
        fields = [
            "id",
            "company",
            "created_by",
            "created_by_display",
            "residential_complex",
            "client",
            "treaty",
            "title",
            "description",
            "status",
            "due_at",
            "completed_at",
            "created_at",
            "updated_at",
            "assignee_ids",
            "assignees",
            "checklist_items",
            "files",
        ]
        read_only_fields = ["id", "company", "created_by", "created_by_display", "completed_at", "created_at", "updated_at", "assignees", "checklist_items", "files"]

    def get_files(self, obj):
        files_qs = getattr(obj, "files", None)
        if files_qs is None:
            return []
        return BuildingTaskFileSerializer(files_qs.all(), many=True, context=self.context).data

    def get_created_by_display(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))

    def get_assignees(self, obj):
        items = getattr(obj, "assignees", None)
        if items is None:
            return []
        out = []
        for a in items.select_related("user").all():
            u = a.user
            if not u:
                continue
            full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
            out.append(
                {
                    "id": str(getattr(u, "id", "")),
                    "display": full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", "")),
                }
            )
        return out

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        company_id = getattr(user, "company_id", None)
        if not company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})

        # Проверяем привязанные сущности на компанию (если указаны)
        rc = attrs.get("residential_complex") or getattr(self.instance, "residential_complex", None)
        if rc and company_id and rc.company_id != company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"residential_complex": "ЖК принадлежит другой компании."})

        client = attrs.get("client") or getattr(self.instance, "client", None)
        if client and company_id and client.company_id != company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"client": "Клиент принадлежит другой компании."})

        treaty = attrs.get("treaty") or getattr(self.instance, "treaty", None)
        if treaty and company_id and treaty.residential_complex.company_id != company_id and not getattr(user, "is_superuser", False):
            raise serializers.ValidationError({"treaty": "Договор принадлежит другой компании."})

        return attrs

    def _sync_assignees(self, task: BuildingTask, assignee_ids: list[uuid.UUID] | None, actor):
        if assignee_ids is None:
            return

        ids = [str(x) for x in assignee_ids]
        qs = User.objects.filter(id__in=ids)
        if not getattr(actor, "is_superuser", False):
            company_id = getattr(actor, "company_id", None)
            qs = qs.filter(company_id=company_id)

        valid_ids = set(str(x) for x in qs.values_list("id", flat=True))
        if len(valid_ids) != len(set(ids)):
            raise serializers.ValidationError({"assignee_ids": "Один или несколько пользователей не найдены (или другой компании)."})

        existing = set(str(x) for x in task.assignees.values_list("user_id", flat=True))
        desired = set(ids)

        to_add = desired - existing
        to_del = existing - desired

        if to_del:
            task.assignees.filter(user_id__in=list(to_del)).delete()
        for uid in to_add:
            BuildingTaskAssignee.objects.create(task=task, user_id=uid, added_by=actor)

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None

        assignee_ids = validated_data.pop("assignee_ids", None)

        company_id = getattr(actor, "company_id", None)
        if not company_id and not getattr(actor, "is_superuser", False):
            raise serializers.ValidationError({"company": "У пользователя не указана компания."})

        task = BuildingTask.objects.create(
            company_id=company_id,
            created_by=actor,
            **validated_data,
        )

        self._sync_assignees(task, assignee_ids, actor)
        return task

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None

        assignee_ids = validated_data.pop("assignee_ids", None)

        # completed_at ставим автоматически по статусу
        if "status" in validated_data:
            new_status = validated_data.get("status")
            if new_status == BuildingTask.Status.DONE and instance.completed_at is None:
                instance.completed_at = timezone.now()
            if new_status != BuildingTask.Status.DONE:
                instance.completed_at = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._sync_assignees(instance, assignee_ids, actor)
        return instance


class BuildingTaskChecklistItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingTaskChecklistItem
        fields = ["text", "is_done", "order"]



class BuildingSalaryEmployeeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display = serializers.CharField()
    compensation_id = serializers.UUIDField(allow_null=True)
    salary_type = serializers.CharField(allow_blank=True, allow_null=True)
    base_salary = serializers.DecimalField(max_digits=16, decimal_places=2, allow_null=True)
    is_active = serializers.BooleanField(allow_null=True)
    sale_commission_type = serializers.CharField(allow_blank=True, allow_null=True)
    sale_commission_value = serializers.DecimalField(max_digits=16, decimal_places=2, allow_null=True)


class BuildingEmployeeCompensationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingEmployeeCompensation
        fields = [
            "id",
            "company",
            "user",
            "salary_type",
            "base_salary",
            "is_active",
            "notes",
            "sale_commission_type",
            "sale_commission_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "user", "created_at", "updated_at"]


class BuildingPayrollAdjustmentSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingPayrollAdjustment
        fields = [
            "id",
            "line",
            "type",
            "status",
            "title",
            "amount",
            "source_treaty",
            "created_by",
            "created_by_display",
            "created_at",
        ]
        read_only_fields = ["id", "line", "status", "source_treaty", "created_by", "created_by_display", "created_at"]

    def get_created_by_display(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))


class AdvanceRequestSerializer(serializers.Serializer):
    """Заявка на аванс для оператора кассы."""

    id = serializers.UUIDField()
    payroll_line_id = serializers.UUIDField(source="line_id")
    employee = serializers.UUIDField(source="line.employee_id")
    employee_display = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    cashbox = serializers.SerializerMethodField()
    cashbox_display = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    requested_at = serializers.DateTimeField(source="created_at")
    status = serializers.CharField()
    residential_complex = serializers.UUIDField(source="line.payroll.residential_complex_id", allow_null=True)
    payroll = serializers.UUIDField(source="line.payroll_id")
    period_start = serializers.DateField(source="line.payroll.period_start")
    period_end = serializers.DateField(source="line.payroll.period_end")

    def _get_payment(self, obj):
        payments = obj.payment.all() if hasattr(obj, "payment") else []
        return payments[0] if payments else None

    def get_employee_display(self, obj):
        emp = getattr(obj.line, "employee", None) if obj.line_id else None
        if not emp:
            return None
        full_name = f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip()
        return full_name or getattr(emp, "email", None) or getattr(emp, "username", None) or str(getattr(emp, "id", ""))

    def get_cashbox(self, obj):
        payment = self._get_payment(obj)
        return payment.cashbox_id if payment and payment.cashbox_id else None

    def get_cashbox_display(self, obj):
        payment = self._get_payment(obj)
        if not payment or not payment.cashbox_id:
            return None
        cashbox = getattr(payment, "cashbox", None)
        if not cashbox:
            return None
        return getattr(cashbox, "name", None) or str(cashbox.id)


class AdvanceRequestApproveSerializer(serializers.Serializer):
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class BuildingPayrollPaymentSerializer(serializers.ModelSerializer):
    paid_by_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingPayrollPayment
        fields = [
            "id",
            "line",
            "amount",
            "paid_at",
            "paid_by",
            "paid_by_display",
            "cashbox",
            "cashflow",
            "advance_adjustment",
            "status",
            "void_reason",
            "voided_by",
            "voided_at",
            "created_at",
        ]
        read_only_fields = ["id", "line", "paid_by", "paid_by_display", "cashflow", "advance_adjustment", "status", "voided_by", "voided_at", "created_at"]

    def get_paid_by_display(self, obj):
        u = getattr(obj, "paid_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))


class BuildingPayrollLineSerializer(serializers.ModelSerializer):
    employee_display = serializers.SerializerMethodField(read_only=True)
    adjustments = BuildingPayrollAdjustmentSerializer(many=True, read_only=True)
    payments = BuildingPayrollPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingPayrollLine
        fields = [
            "id",
            "payroll",
            "employee",
            "employee_display",
            "base_amount",
            "bonus_total",
            "deduction_total",
            "advance_total",
            "net_to_pay",
            "paid_total",
            "comment",
            "created_at",
            "updated_at",
            "adjustments",
            "payments",
        ]
        read_only_fields = [
            "id",
            "bonus_total",
            "deduction_total",
            "advance_total",
            "net_to_pay",
            "paid_total",
            "created_at",
            "updated_at",
            "employee_display",
            "adjustments",
            "payments",
        ]

    def get_employee_display(self, obj):
        u = getattr(obj, "employee", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))


class BuildingPayrollPeriodSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField(read_only=True)
    approved_by_display = serializers.SerializerMethodField(read_only=True)
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True, allow_null=True)
    totals = serializers.SerializerMethodField(read_only=True)
    lines = BuildingPayrollLineSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingPayrollPeriod
        fields = [
            "id",
            "company",
            "residential_complex",
            "residential_complex_name",
            "title",
            "period_start",
            "period_end",
            "status",
            "created_by",
            "created_by_display",
            "approved_by",
            "approved_by_display",
            "approved_at",
            "created_at",
            "updated_at",
            "totals",
            "lines",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_by",
            "created_by_display",
            "approved_by",
            "approved_by_display",
            "approved_at",
            "created_at",
            "updated_at",
            "totals",
            "lines",
            "residential_complex_name",
        ]

    def get_created_by_display(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))

    def get_approved_by_display(self, obj):
        u = getattr(obj, "approved_by", None)
        if not u:
            return None
        full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
        return full_name or getattr(u, "email", None) or getattr(u, "username", None) or str(getattr(u, "id", ""))

    def get_totals(self, obj):
        z = Decimal("0.00")
        a = obj.lines.aggregate(
            net=models.Sum("net_to_pay"),
            paid=models.Sum("paid_total"),
        )
        net = a.get("net") or z
        paid = a.get("paid") or z
        return {
            "net_to_pay_total": str(net),
            "paid_total": str(paid),
            "remaining_total": str((Decimal(net) - Decimal(paid)).quantize(Decimal("0.01"))),
        }


class BuildingPayrollPeriodApproveSerializer(serializers.Serializer):
    approve = serializers.BooleanField(default=True)


class BuildingPayrollLineCreateSerializer(serializers.Serializer):
    employee = serializers.UUIDField(required=True)
    base_amount = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    comment = serializers.CharField(required=False, allow_blank=True)


class BuildingPayrollAdjustmentCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=BuildingPayrollAdjustment.Type.choices)
    title = serializers.CharField(required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    cashbox = serializers.UUIDField(required=False, allow_null=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class BuildingPayrollPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    cashbox = serializers.UUIDField(required=True)
    paid_at = serializers.DateTimeField(required=False)
    status = serializers.ChoiceField(
        choices=[("draft", "Черновик"), ("approved", "Одобрено")],
        required=False,
        help_text="Статус выплаты: draft (без движения кассы) или approved (сразу провести). По умолчанию approved.",
    )


class BuildingPayrollPaymentApproveSerializer(serializers.Serializer):
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class BuildingPayrollMyLineSerializer(serializers.ModelSerializer):
    payroll_title = serializers.CharField(source="payroll.title", read_only=True)
    payroll_period_start = serializers.DateField(source="payroll.period_start", read_only=True)
    payroll_period_end = serializers.DateField(source="payroll.period_end", read_only=True)
    payroll_status = serializers.CharField(source="payroll.status", read_only=True)
    payments = BuildingPayrollPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingPayrollLine
        fields = [
            "id",
            "payroll",
            "payroll_title",
            "payroll_period_start",
            "payroll_period_end",
            "payroll_status",
            "base_amount",
            "bonus_total",
            "deduction_total",
            "advance_total",
            "net_to_pay",
            "paid_total",
            "comment",
            "payments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BuildingWorkEntryPhotoSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingWorkEntryPhoto
        fields = ["id", "entry", "image", "image_url", "caption", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at", "image_url"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "image", None):
            return None
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class BuildingWorkEntryFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuildingWorkEntryFile
        fields = ["id", "entry", "title", "file", "file_url", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at", "file_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not getattr(obj, "file", None):
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class BuildingWorkEntrySerializer(serializers.ModelSerializer):
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    treaty_number = serializers.CharField(source="treaty.number", read_only=True)
    contractor_name = serializers.CharField(source="contractor.company_name", read_only=True)
    created_by_display = serializers.SerializerMethodField()
    photos = BuildingWorkEntryPhotoSerializer(many=True, read_only=True)
    files = BuildingWorkEntryFileSerializer(many=True, read_only=True)

    class Meta:
        model = BuildingWorkEntry
        fields = [
            "id",
            "residential_complex",
            "residential_complex_name",
            "contractor",
            "contractor_name",
            "contract_amount",
            "contract_term_start",
            "contract_term_end",
            "work_status",
            "client",
            "client_name",
            "treaty",
            "treaty_number",
            "payment_mode",
            "treaty_auto_create",
            "treaty_type",
            "treaty_title",
            "created_by",
            "created_by_display",
            "category",
            "title",
            "description",
            "occurred_at",
            "created_at",
            "updated_at",
            "photos",
            "files",
        ]
        read_only_fields = ["id", "created_by", "created_by_display", "created_at", "updated_at", "photos", "files"]

    def get_created_by_display(self, obj):
        user = getattr(obj, "created_by", None)
        if not user:
            return None
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        return full_name or getattr(user, "email", None) or str(getattr(user, "id", ""))


class BuildingWorkEntryPhotoCreateSerializer(serializers.Serializer):
    image = serializers.ImageField(required=True)
    caption = serializers.CharField(required=False, allow_blank=True)


class BuildingWorkEntryFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, allow_blank=True)


class BuildingPurchaseDocumentItemSerializer(serializers.ModelSerializer):
    qty = serializers.DecimalField(source="quantity", max_digits=16, decimal_places=3)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_article = serializers.CharField(source="product.article", read_only=True)

    class Meta:
        model = BuildingProcurementItem
        fields = ["id", "product", "product_name", "product_article", "name", "unit", "qty", "price", "line_total", "order", "note"]
        read_only_fields = ["id", "line_total"]


class BuildingPurchaseDocumentSerializer(serializers.ModelSerializer):
    doc_type = serializers.CharField(read_only=True, default="PURCHASE")
    date = serializers.DateTimeField(source="created_at", read_only=True)
    total = serializers.DecimalField(source="total_amount", max_digits=16, decimal_places=2, read_only=True)
    number = serializers.CharField(read_only=True, allow_blank=True, default="")
    residential_complex_name = serializers.CharField(source="residential_complex.name", read_only=True)
    items = BuildingPurchaseDocumentItemSerializer(many=True)

    class Meta:
        model = BuildingProcurementRequest
        fields = [
            "id",
            "doc_type",
            "status",
            "number",
            "date",
            "residential_complex",
            "residential_complex_name",
            "comment",
            "total",
            "items",
        ]
        read_only_fields = ["id", "doc_type", "status", "number", "date", "total", "residential_complex_name"]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        if not items_data:
            raise serializers.ValidationError({"items": "Нельзя создать закупку без позиций."})

        request = self.context.get("request")
        initiator = getattr(request, "user", None) if request else None
        with transaction.atomic():
            procurement = BuildingProcurementRequest.objects.create(initiator=initiator, **validated_data)
            for idx, item in enumerate(items_data, start=1):
                quantity = item.pop("quantity")
                product = item.get("product")
                if product and product.company_id != procurement.residential_complex.company_id:
                    raise serializers.ValidationError({"items": "Один из товаров принадлежит другой компании."})
                if product:
                    item.setdefault("name", product.name)
                    item.setdefault("unit", product.unit)
                BuildingProcurementItem.objects.create(
                    procurement=procurement,
                    quantity=quantity,
                    order=item.get("order", idx),
                    **item,
                )
            procurement.recalculate_totals()
        return procurement

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        if instance.status != BuildingProcurementRequest.Status.DRAFT:
            raise serializers.ValidationError({"status": "Можно изменять только закупку в статусе draft."})

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if items_data is not None:
                if not items_data:
                    raise serializers.ValidationError({"items": "Нельзя оставить закупку без позиций."})
                instance.items.all().delete()
                for idx, item in enumerate(items_data, start=1):
                    quantity = item.pop("quantity")
                    product = item.get("product")
                    if product and product.company_id != instance.residential_complex.company_id:
                        raise serializers.ValidationError({"items": "Один из товаров принадлежит другой компании."})
                    if product:
                        item.setdefault("name", product.name)
                        item.setdefault("unit", product.unit)
                    BuildingProcurementItem.objects.create(
                        procurement=instance,
                        quantity=quantity,
                        order=item.get("order", idx),
                        **item,
                    )
                instance.recalculate_totals()
        return instance


# -----------------------
# Building Cash (касса Building)
# -----------------------


class BuildingCashboxSerializer(serializers.ModelSerializer):
    """Сериализатор кассы Building."""

    class Meta:
        model = BuildingCashbox
        fields = ["id", "company", "branch", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "company", "created_at", "updated_at"]


class BuildingCashFlowSerializer(serializers.ModelSerializer):
    """Движение по кассе Building."""

    cashbox = serializers.PrimaryKeyRelatedField(queryset=BuildingCashbox.objects.none(), required=True)
    cashbox_name = serializers.SerializerMethodField()
    cashier_display = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()

    class Meta:
        model = BuildingCashFlow
        fields = [
            "id",
            "company",
            "branch",
            "cashbox",
            "cashbox_name",
            "type",
            "name",
            "amount",
            "created_at",
            "status",
            "source_business_operation_id",
            "cashier",
            "cashier_display",
            "files",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "cashbox_name",
            "company",
            "branch",
            "cashier",
            "cashier_display",
            "files",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request:
            return
        user = getattr(request, "user", None)
        company_id = getattr(user, "company_id", None)
        if not company_id:
            return
        self.fields["cashbox"].queryset = BuildingCashbox.objects.filter(company_id=company_id)

    def create(self, validated_data):
        cashbox = validated_data.get("cashbox")
        if cashbox:
            validated_data["company"] = cashbox.company
            validated_data["branch"] = cashbox.branch
        return super().create(validated_data)

    def get_cashbox_name(self, obj):
        if obj.cashbox and obj.cashbox.branch:
            return f"Касса Building филиала {obj.cashbox.branch.name}"
        return getattr(obj.cashbox, "name", None) or "Касса Building"

    def get_cashier_display(self, obj):
        u = getattr(obj, "cashier", None)
        if not u:
            return None
        return (
            getattr(u, "get_full_name", lambda: "")()
            or getattr(u, "email", None)
            or getattr(u, "username", None)
        )

    def get_files(self, obj):
        files_qs = getattr(obj, "files", None)
        if files_qs is None:
            return []
        return BuildingCashFlowFileSerializer(files_qs.all(), many=True, context=self.context).data


class BuildingCashFlowBulkStatusItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=BuildingCashFlow.Status.choices)


class BuildingCashFlowBulkStatusSerializer(serializers.Serializer):
    items = BuildingCashFlowBulkStatusItemSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Пустой список.")
        if len(items) > 50000:
            raise serializers.ValidationError("Слишком много. Максимум 50 000 за раз.")
        return items


# -----------------------
# Cash Register Requests
# -----------------------


class BuildingCashRegisterRequestFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingCashRegisterRequestFile
        fields = ["id", "file_url", "title", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingCashFlowFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BuildingCashFlowFile
        fields = ["id", "file_url", "title", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class BuildingCashRegisterRequestCreateSerializer(serializers.Serializer):
    request_type = serializers.ChoiceField(choices=BuildingCashRegisterRequest.RequestType.choices)
    treaty = serializers.PrimaryKeyRelatedField(
        queryset=BuildingTreaty.objects.none(), required=False, allow_null=True
    )
    apartment = serializers.PrimaryKeyRelatedField(
        queryset=ResidentialComplexApartment.objects.none(), required=False, allow_null=True
    )
    client = serializers.PrimaryKeyRelatedField(
        queryset=BuildingClient.objects.none(), required=False, allow_null=True
    )
    installment = serializers.PrimaryKeyRelatedField(
        queryset=BuildingTreatyInstallment.objects.none(), required=False, allow_null=True
    )
    work_entry = serializers.PrimaryKeyRelatedField(
        queryset=BuildingWorkEntry.objects.none(), required=False, allow_null=True
    )
    cashbox = serializers.PrimaryKeyRelatedField(queryset=BuildingCashbox.objects.none(), required=True)
    shift = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request:
            return
        user = getattr(request, "user", None)
        company_id = getattr(user, "company_id", None)
        if not company_id:
            return
        self.fields["treaty"].queryset = BuildingTreaty.objects.filter(
            residential_complex__company_id=company_id
        )
        self.fields["apartment"].queryset = ResidentialComplexApartment.objects.filter(
            residential_complex__company_id=company_id
        )
        self.fields["client"].queryset = BuildingClient.objects.filter(company_id=company_id)
        self.fields["installment"].queryset = BuildingTreatyInstallment.objects.filter(
            treaty__residential_complex__company_id=company_id
        )
        self.fields["work_entry"].queryset = BuildingWorkEntry.objects.filter(
            residential_complex__company_id=company_id
        )
        self.fields["cashbox"].queryset = BuildingCashbox.objects.filter(company_id=company_id)


class BuildingCashRegisterRequestSerializer(serializers.ModelSerializer):
    files = BuildingCashRegisterRequestFileSerializer(many=True, read_only=True)
    source = serializers.SerializerMethodField()
    cashbox_name = serializers.SerializerMethodField()

    class Meta:
        model = BuildingCashRegisterRequest
        fields = [
            "id",
            "request_type",
            "status",
            "amount",
            "comment",
            "cashbox",
            "cashbox_name",
            "shift",
            "residential_complex",
            "treaty",
            "apartment",
            "client",
            "installment",
            "work_entry",
            "cashflow",
            "reject_reason",
            "approved_at",
            "approved_by",
            "created_by",
            "created_at",
            "updated_at",
            "files",
            "source",
        ]
        read_only_fields = [
            "id",
            "status",
            "cashflow",
            "approved_at",
            "approved_by",
            "created_at",
            "updated_at",
        ]

    def get_source(self, obj):
        d = {}
        if obj.treaty_id:
            d["treaty"] = str(obj.treaty_id)
        if obj.apartment_id:
            d["apartment"] = str(obj.apartment_id)
        if obj.client_id:
            d["client"] = str(obj.client_id)
        if obj.installment_id:
            d["installment"] = str(obj.installment_id)
        if obj.work_entry_id:
            d["work_entry"] = str(obj.work_entry_id)
        return d

    def get_cashbox_name(self, obj):
        return getattr(obj.cashbox, "name", None) or "Касса"


class BuildingCashRegisterRequestApproveSerializer(serializers.Serializer):
    cashbox = serializers.PrimaryKeyRelatedField(
        queryset=BuildingCashbox.objects.none(), required=False, allow_null=True
    )
    shift = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and getattr(request.user, "company_id", None):
            self.fields["cashbox"].queryset = BuildingCashbox.objects.filter(
                company_id=request.user.company_id
            )


class BuildingCashRegisterRequestRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class BuildingCashRegisterRequestFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(required=False, allow_blank=True, default="")


class BuildingCashFlowFileCreateSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(required=False, allow_blank=True, default="")
