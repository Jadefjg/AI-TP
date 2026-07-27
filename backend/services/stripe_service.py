from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import BillingInvoice, Organization

logger = logging.getLogger(__name__)


def stripe_enabled() -> bool:
    return bool(get_settings().stripe_secret_key.strip())


def _stripe():
    try:
        import stripe
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="stripe package not installed; pip install stripe") from exc
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key.strip()
    return stripe


def ensure_stripe_customer(db: Session, org: Organization) -> str:
    if org.stripe_customer_id:
        return org.stripe_customer_id
    if not stripe_enabled():
        raise HTTPException(status_code=501, detail="STRIPE_SECRET_KEY not configured")
    stripe = _stripe()
    settings = get_settings()
    customer = stripe.Customer.create(
        name=org.name,
        email=org.billing_email or None,
        metadata={"organization_id": str(org.id), "organization_slug": org.slug},
    )
    org.stripe_customer_id = customer["id"]
    db.commit()
    return org.stripe_customer_id


def create_mock_checkout_session(
    db: Session,
    *,
    org: Organization,
    invoice: BillingInvoice,
    success_url: str,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="invoice already paid")
    session_id = f"mock_cs_{invoice.id}_{int(datetime.now(timezone.utc).timestamp())}"
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.stripe_checkout_session_id = session_id
    invoice.stripe_invoice_id = f"mock_pi_{invoice.id}"
    db.commit()
    logger.info(
        "stripe mock checkout: org=%s invoice=%s marked paid (STRIPE_SECRET_KEY not configured)",
        org.slug,
        invoice.id,
    )
    return {"checkout_url": success_url, "session_id": session_id, "mock": True}


def create_checkout_session(
    db: Session,
    *,
    org: Organization,
    invoice: BillingInvoice,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    if not stripe_enabled():
        return create_mock_checkout_session(
            db,
            org=org,
            invoice=invoice,
            success_url=success_url,
        )
    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="invoice already paid")
    stripe = _stripe()
    customer_id = ensure_stripe_customer(db, org)
    settings = get_settings()
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "price_data": {
                    "currency": invoice.currency,
                    "unit_amount": max(invoice.amount_cents, 0),
                    "product_data": {
                        "name": f"AI usage {invoice.period}",
                        "description": f"{invoice.token_usage} tokens",
                    },
                },
                "quantity": 1,
            }
        ],
        metadata={
            "organization_id": str(org.id),
            "billing_invoice_id": str(invoice.id),
            "period": invoice.period,
        },
    )
    invoice.stripe_checkout_session_id = session["id"]
    db.commit()
    return {"checkout_url": session["url"], "session_id": session["id"]}


def verify_webhook_payload(payload: bytes, signature: str) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.stripe_webhook_secret.strip()
    if not secret:
        raise HTTPException(status_code=501, detail="STRIPE_WEBHOOK_SECRET not configured")
    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid stripe webhook signature") from exc
    return event


def mark_invoice_paid_from_event(db: Session, event: dict[str, Any]) -> BillingInvoice | None:
    from datetime import datetime, timezone

    etype = event.get("type")
    if etype not in {"checkout.session.completed", "invoice.paid"}:
        return None
    data = event.get("data", {}).get("object", {})
    invoice_id = None
    if etype == "checkout.session.completed":
        meta = data.get("metadata") or {}
        invoice_id = meta.get("billing_invoice_id")
        stripe_ref = data.get("payment_intent") or data.get("id")
    else:
        meta = data.get("metadata") or {}
        invoice_id = meta.get("billing_invoice_id")
        stripe_ref = data.get("id")
    if not invoice_id:
        return None
    row = db.query(BillingInvoice).filter(BillingInvoice.id == int(invoice_id)).one_or_none()
    if not row:
        return None
    row.status = "paid"
    row.paid_at = datetime.now(timezone.utc)
    row.stripe_invoice_id = str(stripe_ref) if stripe_ref else row.stripe_invoice_id
    db.commit()
    db.refresh(row)
    return row
