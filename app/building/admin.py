from django.contrib import admin
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
    BuildingTransferRequestFile,
    BuildingWarehouseRequest,
    BuildingWarehouseRequestItem,
    BuildingReconciliationAct,
    BuildingReconciliationActItem,
    BuildingWarehouseMovement,
    BuildingWarehouseMovementItem,
    BuildingWarehouseMovementFile,
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
    BuildingClient,
    BuildingClientFile,
    BuildingTaskFile,
    BuildingTreatyNumberSequence,
    BuildingTreaty,
    BuildingTreatyInstallment,
    BuildingTreatyFile,
    BuildingWorkEntry,
    BuildingWorkEntryPhoto,
    BuildingWorkEntryFile,
    BuildingTask,
    BuildingTaskAssignee,
    BuildingTaskChecklistItem,
    BuildingEmployeeCompensation,
    BuildingPayrollPeriod,
    BuildingPayrollLine,
    BuildingPayrollAdjustment,
    BuildingPayrollPayment,
)


@admin.register(BuildingCashbox)
class BuildingCashboxAdmin(admin.ModelAdmin):
    list_display = ("name", "company_id", "branch_id", "created_at")
    list_filter = ("company_id", "branch_id")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(BuildingCashFlow)
class BuildingCashFlowAdmin(admin.ModelAdmin):
    list_display = ("cashbox", "type", "name", "amount", "status", "created_at", "cashier")
    list_filter = ("type", "status", "cashbox__company_id")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at")


@admin.register(BuildingCashRegisterRequest)
class BuildingCashRegisterRequestAdmin(admin.ModelAdmin):
    list_display = ("request_type", "status", "amount", "cashbox", "created_at", "approved_by")
    list_filter = ("request_type", "status", "cashbox__company_id")
    search_fields = ("comment",)
    readonly_fields = ("id", "created_at", "updated_at", "approved_at")


@admin.register(BuildingCashRegisterRequestFile)
class BuildingCashRegisterRequestFileAdmin(admin.ModelAdmin):
    list_display = ("request", "title", "created_at")
    list_filter = ("request__request_type",)


@admin.register(BuildingCashFlowFile)
class BuildingCashFlowFileAdmin(admin.ModelAdmin):
    list_display = ("cashflow", "title", "created_at")


@admin.register(ResidentialComplex)
class ResidentialComplexAdmin(admin.ModelAdmin):
    list_display = ("name", "company_id", "address", "is_active", "created_at")
    list_filter = ("company_id", "is_active")
    search_fields = ("name", "address")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ResidentialComplexMember)
class ResidentialComplexMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "residential_complex", "user", "is_active", "added_by", "created_at")
    list_filter = ("is_active", "created_at", "residential_complex__company_id")
    search_fields = ("residential_complex__name", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("id", "created_at")


@admin.register(ResidentialComplexDrawing)
class ResidentialComplexDrawingAdmin(admin.ModelAdmin):
    list_display = ("title", "residential_complex", "is_active", "created_at")
    list_filter = ("residential_complex__company_id", "is_active")
    search_fields = ("title", "residential_complex__name", "description")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ResidentialComplexWarehouse)
class ResidentialComplexWarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "residential_complex", "is_active", "created_at")
    list_filter = ("residential_complex__company_id", "is_active")
    search_fields = ("name", "residential_complex__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ResidentialComplexApartment)
class ResidentialComplexApartmentAdmin(admin.ModelAdmin):
    list_display = ("number", "floor", "residential_complex", "status", "price", "area", "rooms", "updated_at")
    list_filter = ("residential_complex__company_id", "residential_complex", "status", "floor")
    search_fields = ("number", "notes", "residential_complex__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(BuildingProduct)
class BuildingProductAdmin(admin.ModelAdmin):
    list_display = ("name", "company_id", "article", "barcode", "unit", "is_active", "created_at")
    list_filter = ("company_id", "is_active")
    search_fields = ("name", "article", "barcode")
    readonly_fields = ("id", "created_at", "updated_at")


class BuildingContractorFileInline(admin.TabularInline):
    model = BuildingContractorFile
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(BuildingContractor)
class BuildingContractorAdmin(admin.ModelAdmin):
    list_display = ("company_name", "company_id", "contractor_type", "status", "contact_person", "phone", "created_at")
    list_filter = ("company_id", "contractor_type", "status")
    search_fields = ("company_name", "contact_person", "phone", "email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [BuildingContractorFileInline]


class BuildingSupplierFileInline(admin.TabularInline):
    model = BuildingSupplierFile
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(BuildingSupplier)
class BuildingSupplierAdmin(admin.ModelAdmin):
    list_display = ("company_name", "company_id", "supplier_type", "status", "contact_person", "phone", "created_at")
    list_filter = ("company_id", "supplier_type", "status")
    search_fields = ("company_name", "contact_person", "phone", "email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [BuildingSupplierFileInline]


class BuildingProcurementItemInline(admin.TabularInline):
    model = BuildingProcurementItem
    extra = 0
    readonly_fields = ("id", "line_total", "created_at", "updated_at")


class BuildingProcurementFileInline(admin.TabularInline):
    model = BuildingProcurementFile
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(BuildingProcurementRequest)
class BuildingProcurementRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "residential_complex", "status", "total_amount", "initiator", "created_at")
    list_filter = ("status", "residential_complex__company_id")
    search_fields = ("title", "comment", "residential_complex__name")
    readonly_fields = ("id", "total_amount", "submitted_to_cash_at", "cash_decided_at", "created_at", "updated_at")
    inlines = [BuildingProcurementItemInline, BuildingProcurementFileInline]


@admin.register(BuildingProcurementCashDecision)
class BuildingProcurementCashDecisionAdmin(admin.ModelAdmin):
    list_display = ("procurement", "decision", "decided_by", "decided_at")
    list_filter = ("decision", "procurement__residential_complex__company_id")
    search_fields = ("procurement__title", "reason")
    readonly_fields = ("id", "decided_at")


class BuildingTransferItemInline(admin.TabularInline):
    model = BuildingTransferItem
    extra = 0
    readonly_fields = ("id", "line_total", "created_at", "updated_at")


@admin.register(BuildingTransferRequest)
class BuildingTransferRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "procurement", "warehouse", "status", "total_amount", "created_by", "created_at")
    list_filter = ("status", "warehouse__residential_complex__company_id")
    search_fields = ("procurement__title", "warehouse__name", "note", "rejection_reason")
    readonly_fields = ("id", "total_amount", "accepted_at", "rejected_at", "created_at", "updated_at")
    inlines = [BuildingTransferItemInline]


@admin.register(BuildingWarehouseStockItem)
class BuildingWarehouseStockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "warehouse", "quantity", "last_price", "updated_at")
    list_filter = ("warehouse__residential_complex__company_id", "warehouse")
    search_fields = ("name", "warehouse__name", "warehouse__residential_complex__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(BuildingWarehouseStockMove)
class BuildingWarehouseStockMoveAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "stock_item", "move_type", "quantity_delta", "price", "created_by", "created_at")
    list_filter = ("move_type", "warehouse__residential_complex__company_id", "warehouse")
    search_fields = ("stock_item__name", "warehouse__name")
    readonly_fields = ("id", "created_at")


@admin.register(BuildingWorkflowEvent)
class BuildingWorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "procurement", "transfer", "warehouse", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("action", "message", "procurement__title", "warehouse__name")
    readonly_fields = ("id", "created_at", "payload")


class BuildingTreatyFileInline(admin.TabularInline):
    model = BuildingTreatyFile
    extra = 0
    readonly_fields = ("id", "created_at")


class BuildingTreatyInstallmentInline(admin.TabularInline):
    model = BuildingTreatyInstallment
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(BuildingTreatyNumberSequence)
class BuildingTreatyNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("company_id", "next_value", "updated_at")
    list_filter = ("company_id",)
    readonly_fields = ("id", "updated_at")


@admin.register(BuildingTreaty)
class BuildingTreatyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "number",
        "title",
        "residential_complex",
        "apartment",
        "client",
        "operation_type",
        "payment_type",
        "status",
        "amount",
        "erp_sync_status",
        "created_at",
    )
    list_filter = ("status", "operation_type", "payment_type", "erp_sync_status", "residential_complex__company_id")
    search_fields = ("number", "title", "description", "residential_complex__name", "apartment__number")
    readonly_fields = ("id", "created_at", "updated_at", "erp_requested_at", "erp_synced_at")
    inlines = [BuildingTreatyFileInline, BuildingTreatyInstallmentInline]


@admin.register(BuildingTreatyFile)
class BuildingTreatyFileAdmin(admin.ModelAdmin):
    list_display = ("id", "treaty", "title", "created_by", "created_at")
    list_filter = ("treaty__residential_complex__company_id", "created_at")
    search_fields = ("title", "file", "treaty__number", "treaty__title")
    readonly_fields = ("id", "created_at")


@admin.register(BuildingClient)
class BuildingClientAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company_id", "phone", "email", "is_active", "created_at")
    list_filter = ("company_id", "is_active")
    search_fields = ("name", "phone", "email", "inn")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(BuildingClientFile)
class BuildingClientFileAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "title", "created_at")
    list_filter = ("client__company_id",)


@admin.register(BuildingTaskFile)
class BuildingTaskFileAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "title", "created_at")
    list_filter = ("task__company_id",)


class BuildingWorkEntryPhotoInline(admin.TabularInline):
    model = BuildingWorkEntryPhoto
    extra = 0
    readonly_fields = ("id", "created_at")


class BuildingWorkEntryFileInline(admin.TabularInline):
    model = BuildingWorkEntryFile
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(BuildingWorkEntry)
class BuildingWorkEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "residential_complex", "category", "title", "created_by", "occurred_at", "created_at")
    list_filter = ("category", "residential_complex__company_id")
    search_fields = ("title", "description", "residential_complex__name")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [BuildingWorkEntryPhotoInline, BuildingWorkEntryFileInline]


@admin.register(BuildingWorkEntryPhoto)
class BuildingWorkEntryPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "entry", "caption", "created_by", "created_at")
    list_filter = ("entry__residential_complex__company_id", "created_at")
    search_fields = ("caption", "image", "entry__title")
    readonly_fields = ("id", "created_at")


@admin.register(BuildingWorkEntryFile)
class BuildingWorkEntryFileAdmin(admin.ModelAdmin):
    list_display = ("id", "entry", "title", "created_by", "created_at")
    list_filter = ("entry__residential_complex__company_id", "created_at")
    search_fields = ("title", "entry__title")
    readonly_fields = ("id", "created_at")


class BuildingTaskAssigneeInline(admin.TabularInline):
    model = BuildingTaskAssignee
    extra = 0
    readonly_fields = ("id", "created_at")


class BuildingTaskChecklistInline(admin.TabularInline):
    model = BuildingTaskChecklistItem
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at", "done_at")


@admin.register(BuildingTask)
class BuildingTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "company_id", "status", "due_at", "created_by", "created_at")
    list_filter = ("company_id", "status")
    search_fields = ("title", "description")
    readonly_fields = ("id", "created_at", "updated_at", "completed_at")
    inlines = [BuildingTaskAssigneeInline, BuildingTaskChecklistInline]


@admin.register(BuildingTaskAssignee)
class BuildingTaskAssigneeAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "user", "added_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("task__title",)
    readonly_fields = ("id", "created_at")


@admin.register(BuildingTaskChecklistItem)
class BuildingTaskChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "text", "is_done", "order", "done_by", "done_at", "updated_at")
    list_filter = ("is_done", "created_at")
    search_fields = ("text", "task__title")
    readonly_fields = ("id", "created_at", "updated_at", "done_at")


@admin.register(BuildingEmployeeCompensation)
class BuildingEmployeeCompensationAdmin(admin.ModelAdmin):
    list_display = ("id", "company_id", "user", "salary_type", "base_salary", "sale_commission_type", "sale_commission_value", "is_active", "updated_at")
    list_filter = ("company_id", "salary_type", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("id", "created_at", "updated_at")


class BuildingPayrollLineInline(admin.TabularInline):
    model = BuildingPayrollLine
    extra = 0
    readonly_fields = ("id", "bonus_total", "deduction_total", "advance_total", "net_to_pay", "paid_total", "created_at", "updated_at")


@admin.register(BuildingPayrollPeriod)
class BuildingPayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ("id", "company_id", "title", "period_start", "period_end", "status", "created_by", "approved_by", "approved_at")
    list_filter = ("company_id", "status")
    search_fields = ("title",)
    readonly_fields = ("id", "created_at", "updated_at", "approved_at")
    inlines = [BuildingPayrollLineInline]


class BuildingPayrollAdjustmentInline(admin.TabularInline):
    model = BuildingPayrollAdjustment
    extra = 0
    readonly_fields = ("id", "created_at")


class BuildingPayrollPaymentInline(admin.TabularInline):
    model = BuildingPayrollPayment
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(BuildingPayrollLine)
class BuildingPayrollLineAdmin(admin.ModelAdmin):
    list_display = ("id", "payroll", "employee", "base_amount", "net_to_pay", "paid_total", "updated_at")
    list_filter = ("payroll__company_id", "payroll__status")
    search_fields = ("employee__email", "employee__first_name", "employee__last_name")
    readonly_fields = ("id", "bonus_total", "deduction_total", "advance_total", "net_to_pay", "paid_total", "created_at", "updated_at")
    inlines = [BuildingPayrollAdjustmentInline, BuildingPayrollPaymentInline]


@admin.register(BuildingPayrollAdjustment)
class BuildingPayrollAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("id", "line", "type", "amount", "title", "created_by", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("title", "line__employee__email")
    readonly_fields = ("id", "created_at")


@admin.register(BuildingPayrollPayment)
class BuildingPayrollPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "line", "amount", "paid_at", "cashbox", "status", "paid_by", "created_at")
    list_filter = ("status", "paid_at")
    search_fields = ("line__employee__email",)
    readonly_fields = ("id", "created_at")
