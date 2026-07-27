from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_permission
from backend.core.config import get_settings
from backend.db.session import get_db
from backend.models.entities import BillingInvoice, User
from backend.schemas.dto import BillingCheckoutIn, BillingCheckoutOut, BillingInvoiceOut
from backend.services.audit_service import log_action
from backend.services.billing_service import build_invoice_pdf, current_billing_period, generate_invoice
from backend.services.stripe_service import create_checkout_session, mark_invoice_paid_from_event, verify_webhook_payload
from backend.services.tenant_service import assert_can_access_organization, get_organization

router = APIRouter(tags=["billing"])
org_router = APIRouter(prefix="/organizations", tags=["billing"])


@org_router.get(
    "/{org_id}/billing/invoices",
    response_model=list[BillingInvoiceOut],
    dependencies=[Depends(require_permission("billing.read"))],
)
def list_invoices(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BillingInvoice]:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    return (
        db.query(BillingInvoice)
        .filter(BillingInvoice.organization_id == org.id)
        .order_by(BillingInvoice.id.desc())
        .limit(24)
        .all()
    )


@org_router.post(
    "/{org_id}/billing/invoices/generate",
    response_model=BillingInvoiceOut,
    dependencies=[Depends(require_permission("billing.manage"))],
)
def generate_org_invoice(
    org_id: int,
    period: str | None = Query(default=None, description="YYYY-MM"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingInvoice:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    invoice = generate_invoice(db, org=org, period=period or current_billing_period())
    log_action(
        db,
        module="billing",
        action="billing.invoice_generated",
        message=f"invoice #{invoice.id} for {org.slug} {invoice.period}",
        organization_id=org.id,
        detail={"invoice_id": invoice.id, "amount_cents": invoice.amount_cents},
    )
    return invoice


@org_router.get(
    "/{org_id}/billing/invoices/{invoice_id}/pdf",
    dependencies=[Depends(require_permission("billing.read"))],
)
def download_invoice_pdf(
    org_id: int,
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    invoice = (
        db.query(BillingInvoice)
        .filter(BillingInvoice.id == invoice_id, BillingInvoice.organization_id == org.id)
        .one_or_none()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="invoice not found")
    pdf_bytes = build_invoice_pdf(invoice, org)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{invoice.period}.pdf"'},
    )


@org_router.post(
    "/{org_id}/billing/checkout",
    response_model=BillingCheckoutOut,
    dependencies=[Depends(require_permission("billing.manage"))],
)
def stripe_checkout(
    org_id: int,
    body: BillingCheckoutIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingCheckoutOut:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    invoice = (
        db.query(BillingInvoice)
        .filter(BillingInvoice.id == body.invoice_id, BillingInvoice.organization_id == org.id)
        .one_or_none()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="invoice not found")
    settings = get_settings()
    result = create_checkout_session(
        db,
        org=org,
        invoice=invoice,
        success_url=body.success_url or settings.billing_checkout_success_url,
        cancel_url=body.cancel_url or settings.billing_checkout_cancel_url,
    )
    log_action(
        db,
        module="billing",
        action="billing.checkout_created" if not result.get("mock") else "billing.checkout_mock_paid",
        message=(
            f"stripe checkout for invoice #{invoice.id}"
            if not result.get("mock")
            else f"mock checkout paid invoice #{invoice.id}"
        ),
        organization_id=org.id,
        detail={"session_id": result["session_id"], "mock": bool(result.get("mock"))},
    )
    return BillingCheckoutOut(**result)


@router.post("/billing/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Stripe-Signature header required")
    event = verify_webhook_payload(payload, stripe_signature)
    invoice = mark_invoice_paid_from_event(db, event)
    if invoice:
        log_action(
            db,
            module="billing",
            action="billing.invoice_paid",
            message=f"invoice #{invoice.id} marked paid via stripe",
            organization_id=invoice.organization_id,
            detail={"event_type": event.get("type")},
        )
    return {"ok": True, "handled": invoice is not None}
