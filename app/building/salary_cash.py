# Обработка одобрения операций ЗП в кассе.
# Вызывается при переводе BuildingCashFlow в статус APPROVED.

from django.db import transaction

from .models import (
    BuildingPayrollAdjustment,
    BuildingPayrollPayment,
)


def on_cashflow_approved(cashflow):
    """
    Когда движение кассы (ЗП) одобрено: провести выплату и при необходимости аванс.
    cashflow.source_business_operation_id = UUID выплаты (BuildingPayrollPayment).
    """
    op_id = getattr(cashflow, "source_business_operation_id", None) or ""
    op_id = (op_id or "").strip()
    if not op_id:
        return
    try:
        payment = BuildingPayrollPayment.objects.select_related(
            "line",
            "line__payroll",
            "advance_adjustment",
        ).filter(id=op_id, status=BuildingPayrollPayment.Status.PENDING).first()
    except (ValueError, TypeError):
        return
    if not payment:
        return
    with transaction.atomic():
        payment.status = BuildingPayrollPayment.Status.POSTED
        payment.save(update_fields=["status"])
        adj = payment.advance_adjustment
        if adj and adj.status == BuildingPayrollAdjustment.Status.PENDING:
            adj.status = BuildingPayrollAdjustment.Status.COMPLETED
            adj.save(update_fields=["status"])
        line = payment.line
        line.recalculate_totals()
        line.recalculate_paid_total()
        if line.payroll_id:
            line.payroll.try_mark_paid()
