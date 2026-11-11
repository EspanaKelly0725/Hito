"""Real PayPal REST client: OAuth2, Invoicing v2, Payouts v1, webhook verification.

Only the calls Hito actually needs, written against the documented request
shapes, with idempotency keys on everything that moves money.
"""
from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import httpx

from ..config import settings


class PayPalError(RuntimeError):
    """A PayPal REST call failed. Carries the status and the parsed body."""

    def __init__(self, message: str, *, status: int = 0, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body

    def as_dict(self) -> dict:
        return {"error": str(self), "status": self.status, "detail": self.body}


class PayPalClient:
    mode = "paypal"

    def __init__(self, *, base_url: str | None = None,
                 client_id: str | None = None, client_secret: str | None = None):
        self.base_url = (base_url or settings.paypal_base_url).rstrip("/")
        self.client_id = client_id or settings.paypal_client_id
        self.client_secret = client_secret or settings.paypal_client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # -- plumbing ----------------------------------------------------------
    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content="grant_type=client_credentials",
            )
        if resp.status_code != 200:
            raise PayPalError(
                "PayPal rejected the credentials (check PAYPAL_CLIENT_ID / SECRET)",
                status=resp.status_code,
                body=_safe_json(resp),
            )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload.get("expires_in", 3000))
        return self._token

    async def _request(self, method: str, path: str, *, json: Any = None,
                       idempotency_key: str | None = None,
                       expect: tuple[int, ...] = (200, 201, 202)) -> dict:
        token = await self._access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        async with httpx.AsyncClient(timeout=45.0) as http:
            resp = await http.request(
                method, f"{self.base_url}{path}", headers=headers, json=json
            )
        if resp.status_code not in expect:
            raise PayPalError(
                f"PayPal {method} {path} returned {resp.status_code}",
                status=resp.status_code,
                body=_safe_json(resp),
            )
        return _safe_json(resp) or {}

    # -- invoicing ---------------------------------------------------------
    async def next_invoice_number(self) -> str:
        data = await self._request("POST", "/v2/invoicing/generate-next-invoice-number")
        return data.get("invoice_number") or f"HITO-{uuid.uuid4().hex[:6].upper()}"

    async def create_invoice(self, *, number: str, currency: str, note: str,
                             terms: str, invoice_date: str, due_date: str,
                             recipient_name: str, recipient_email: str,
                             items: list[dict], reference: str) -> dict:
        given, _, surname = recipient_name.partition(" ")
        payload = {
            "detail": {
                "invoice_number": number,
                "reference": reference,
                "invoice_date": invoice_date,
                "currency_code": currency,
                "note": note,
                "terms_and_conditions": terms,
                "payment_term": {
                    "term_type": "DUE_ON_DATE_SPECIFIED",
                    "due_date": due_date,
                },
            },
            "invoicer": {
                "name": {
                    "given_name": settings.invoicer_given_name,
                    "surname": settings.invoicer_surname,
                },
                "email_address": settings.invoicer_email,
                "business_name": settings.invoicer_business,
            },
            "primary_recipients": [{
                "billing_info": {
                    "name": {"given_name": given or recipient_name,
                             "surname": surname or "-"},
                    "email_address": recipient_email,
                }
            }],
            "items": [
                {
                    "name": item["name"][:200],
                    "description": (item.get("description") or "")[:1000],
                    "quantity": "1",
                    "unit_amount": {
                        "currency_code": currency,
                        "value": f"{float(item['amount']):.2f}",
                    },
                    "unit_of_measure": "AMOUNT",
                }
                for item in items
            ],
            "configuration": {
                "partial_payment": {"allow_partial_payment": False},
                "allow_tip": False,
                "tax_inclusive": False,
            },
        }
        data = await self._request(
            "POST", "/v2/invoicing/invoices", json=payload,
            idempotency_key=f"hito-inv-{reference}",
        )
        return _normalize_invoice(data, number)

    async def send_invoice(self, invoice_id: str, *, subject: str = "",
                           note: str = "") -> dict:
        payload: dict = {"send_to_recipient": True, "send_to_invoicer": True}
        if subject:
            payload["subject"] = subject
        if note:
            payload["note"] = note
        await self._request(
            "POST", f"/v2/invoicing/invoices/{invoice_id}/send", json=payload,
            idempotency_key=f"hito-send-{invoice_id}",
        )
        return await self.get_invoice(invoice_id)

    async def get_invoice(self, invoice_id: str) -> dict:
        data = await self._request("GET", f"/v2/invoicing/invoices/{invoice_id}")
        return _normalize_invoice(data, data.get("detail", {}).get("invoice_number", ""))

    async def send_reminder(self, invoice_id: str, *, subject: str, note: str) -> dict:
        """PayPal's own reminder email - the delivery channel for Hito's dunning copy."""
        await self._request(
            "POST", f"/v2/invoicing/invoices/{invoice_id}/remind",
            json={
                "subject": subject[:998],
                "note": note[:4000],
                "send_to_invoicer": True,
            },
            idempotency_key=f"hito-remind-{invoice_id}-{uuid.uuid4().hex[:8]}",
        )
        return {"ok": True, "channel": "paypal_invoice_reminder"}

    # -- payouts -----------------------------------------------------------
    async def create_payout(self, *, batch_id: str, subject: str, message: str,
                            items: list[dict], currency: str = "USD") -> dict:
        payload = {
            "sender_batch_header": {
                "sender_batch_id": batch_id,
                "email_subject": subject[:255],
                "email_message": message[:1000],
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": item["email"],
                    "amount": {
                        "currency": currency,
                        "value": f"{float(item['amount']):.2f}",
                    },
                    "note": (item.get("note") or "")[:1000],
                    "sender_item_id": item["id"],
                }
                for item in items
            ],
        }
        data = await self._request(
            "POST", "/v1/payments/payouts", json=payload,
            idempotency_key=f"hito-payout-{batch_id}",
        )
        header = data.get("batch_header", {})
        return {
            "batch_id": header.get("payout_batch_id", batch_id),
            "status": header.get("batch_status", "PENDING"),
            "raw": data,
        }

    async def get_payout(self, batch_id: str) -> dict:
        data = await self._request("GET", f"/v1/payments/payouts/{batch_id}")
        header = data.get("batch_header", {})
        return {
            "batch_id": header.get("payout_batch_id", batch_id),
            "status": header.get("batch_status", "UNKNOWN"),
            "items": [
                {
                    "sender_item_id": it.get("payout_item", {}).get("sender_item_id"),
                    "status": it.get("transaction_status"),
                    "amount": it.get("payout_item", {}).get("amount", {}).get("value"),
                }
                for it in data.get("items", [])
            ],
            "raw": data,
        }

    # -- webhooks ----------------------------------------------------------
    async def verify_webhook(self, *, headers: dict, body: dict) -> str:
        """Returns 'SUCCESS', 'FAILURE', or 'UNVERIFIED' when no webhook id is set."""
        if not settings.paypal_webhook_id:
            return "UNVERIFIED"
        lower = {k.lower(): v for k, v in headers.items()}
        payload = {
            "transmission_id": lower.get("paypal-transmission-id"),
            "transmission_time": lower.get("paypal-transmission-time"),
            "cert_url": lower.get("paypal-cert-url"),
            "auth_algo": lower.get("paypal-auth-algo"),
            "transmission_sig": lower.get("paypal-transmission-sig"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": body,
        }
        if not all(payload[k] for k in (
                "transmission_id", "transmission_time", "cert_url",
                "auth_algo", "transmission_sig")):
            return "FAILURE"
        try:
            data = await self._request(
                "POST", "/v1/notifications/verify-webhook-signature", json=payload
            )
        except PayPalError:
            return "FAILURE"
        return data.get("verification_status", "FAILURE")

    async def health(self) -> dict:
        try:
            await self._access_token()
            return {"ok": True, "env": settings.paypal_env, "base_url": self.base_url}
        except PayPalError as exc:
            return {"ok": False, **exc.as_dict()}


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:2000]}


def _normalize_invoice(data: dict, fallback_number: str) -> dict:
    links = {link.get("rel"): link.get("href") for link in data.get("links", [])}
    detail = data.get("detail", {})
    amount = data.get("amount", {})
    return {
        "id": data.get("id"),
        "number": detail.get("invoice_number") or fallback_number,
        "status": data.get("status", "DRAFT"),
        "currency": amount.get("currency_code", detail.get("currency_code", "USD")),
        "amount": float(amount.get("value") or 0) or None,
        "due_date": (detail.get("payment_term") or {}).get("due_date"),
        "view_url": links.get("payer-view") or links.get("self"),
        "self_url": links.get("self"),
        "raw": data,
    }
