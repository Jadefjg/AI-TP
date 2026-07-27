from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from fpdf import FPDF
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import AiCallLog, BillingInvoice, Organization
from backend.services.tenant_service import month_start_utc, organization_token_usage


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    try:
        year_s, month_s = period.split("-", 1)
        year, month = int(year_s), int(month_s)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="period must be YYYY-MM") from exc
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def token_usage_for_period(db: Session, org_id: int, period: str) -> int:
    start, end = _period_bounds(period)
    prompt = (
        db.query(func.coalesce(func.sum(AiCallLog.prompt_tokens), 0))
        .filter(
            AiCallLog.organization_id == org_id,
            AiCallLog.created_at >= start,
            AiCallLog.created_at < end,
        )
        .scalar()
        or 0
    )
    completion = (
        db.query(func.coalesce(func.sum(AiCallLog.completion_tokens), 0))
        .filter(
            AiCallLog.organization_id == org_id,
            AiCallLog.created_at >= start,
            AiCallLog.created_at < end,
        )
        .scalar()
        or 0
    )
    return int(prompt) + int(completion)


def calculate_amount_cents(token_usage: int) -> int:
    settings = get_settings()
    unit = max(settings.stripe_price_per_1k_tokens_cents, 0)
    return int((token_usage / 1000.0) * unit)


def generate_invoice(
    db: Session,
    *,
    org: Organization,
    period: str | None = None,
) -> BillingInvoice:
    if not period:
        now = datetime.now(timezone.utc)
        period = now.strftime("%Y-%m")
    existing = (
        db.query(BillingInvoice)
        .filter(BillingInvoice.organization_id == org.id, BillingInvoice.period == period)
        .one_or_none()
    )
    if existing and existing.status not in {"draft"}:
        return existing

    usage = token_usage_for_period(db, org.id, period)
    amount = calculate_amount_cents(usage)
    settings = get_settings()
    if existing:
        row = existing
        row.token_usage = usage
        row.amount_cents = amount
        row.status = "issued"
        row.detail = {"generated_at": datetime.now(timezone.utc).isoformat()}
    else:
        row = BillingInvoice(
            organization_id=org.id,
            period=period,
            token_usage=usage,
            amount_cents=amount,
            currency=settings.billing_currency,
            status="issued",
            detail={"generated_at": datetime.now(timezone.utc).isoformat()},
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _pdf_text(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")


def build_invoice_pdf(invoice: BillingInvoice, org: Organization) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, "AI-TP Usage Invoice", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, f"Organization: {_pdf_text(org.name)} ({org.slug})", ln=True)
    pdf.cell(0, 8, f"Period: {invoice.period}", ln=True)
    pdf.cell(0, 8, f"Invoice ID: {invoice.id}", ln=True)
    pdf.cell(0, 8, f"Status: {invoice.status}", ln=True)
    pdf.cell(0, 8, f"Token usage: {invoice.token_usage:,}", ln=True)
    pdf.cell(0, 8, f"Amount: {invoice.amount_cents / 100:.2f} {invoice.currency.upper()}", ln=True)
    if invoice.paid_at:
        pdf.cell(0, 8, f"Paid at: {invoice.paid_at.isoformat()}", ln=True)
    if invoice.stripe_invoice_id:
        pdf.cell(0, 8, f"Stripe Invoice: {invoice.stripe_invoice_id}", ln=True)
    raw = pdf.output()
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, bytes):
        return raw
    return str(raw).encode("latin-1")


def current_billing_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")
