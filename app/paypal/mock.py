"""In-process stand-in for PayPal, with the same surface as PayPalClient.

Why it exists: the hackathon asks judges to be able to *run* the project. Not
every judge will create a sandbox app before clicking through a demo, and a
broken credential should never look like a broken product. So Hito ships a
gateway that behaves like PayPal Invoicing and Payouts - invoice ids, statuses,
a payer view, a payout batch that settles item by item - and the UI says loudly
which one is live.

Everything here is fake money. The real client in client.py is the one that
matters for judging; this is the fallback that keeps the demo runnable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MockPayPal:
    mode = "mock"

    def __init__(self) -> None:
        self.invoices: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}
        self.reminders: list[dict] = []
        self._seq = 1000

    # -- invoicing ---------------------------------------------------------
    async def next_invoice_number(self) -> str:
        self._seq += 1
        return f"HITO-{self._seq:05d}"

    async def create_invoice(self, *, number: str, currency: str, note: str,
                             terms: str, invoice_date: str, due_date: str,
                             recipient_name: str, recipient_email: str,
                             items: list[dict], reference: str) -> dict:
        invoice_id = f"INV2-MOCK-{uuid.uuid4().hex[:10].upper()}"
        total = round(sum(float(i["amount"]) for i in items), 2)
        record = {
            "id": invoice_id,
            "number": number,
            "status": "DRAFT",
            "currency": currency,
            "amount": total,
            "due_date": due_date,
            "invoice_date": invoice_date,
            "note": note,
            "terms": terms,
            "reference": reference,
            "recipient_name": recipient_name,
            "recipient_email": recipient_email,
            "items": items,
            "view_url": f"/mock/invoice/{invoice_id}",
            "self_url": f"/mock/invoice/{invoice_id}",
            "created_at": _now(),
            "history": [{"ts": _now(), "event": "created"}],
        }
        self.invoices[invoice_id] = record
        return dict(record, raw={"mock": True})

    async def send_invoice(self, invoice_id: str, *, subject: str = "",
                           note: str = "") -> dict:
        record = self.invoices[invoice_id]
        record["status"] = "SENT"
        record["sent_at"] = _now()
        record["history"].append({"ts": _now(), "event": "sent", "subject": subject})
        return dict(record, raw={"mock": True})

    async def get_invoice(self, invoice_id: str) -> dict:
        record = self.invoices.get(invoice_id)
        if record is None:
            return {"id": invoice_id, "status": "NOT_FOUND", "raw": {"mock": True}}
        return dict(record, raw={"mock": True})

    async def send_reminder(self, invoice_id: str, *, subject: str, note: str) -> dict:
        self.reminders.append({
            "invoice_id": invoice_id, "subject": subject,
            "note": note, "ts": _now(),
        })
        record = self.invoices.get(invoice_id)
        if record:
            record["history"].append({"ts": _now(), "event": "reminder", "subject": subject})
        return {"ok": True, "channel": "mock_invoice_reminder"}

    def mark_paid(self, invoice_id: str) -> dict | None:
        """Called by the mock payer page - the trigger the real webhook replaces."""
        record = self.invoices.get(invoice_id)
        if record is None:
            return None
        record["status"] = "PAID"
        record["paid_at"] = _now()
        record["history"].append({"ts": _now(), "event": "paid"})
        return record

    # -- payouts -----------------------------------------------------------
    async def create_payout(self, *, batch_id: str, subject: str, message: str,
                            items: list[dict], currency: str = "USD") -> dict:
        record = {
            "batch_id": batch_id,
            "status": "SUCCESS",
            "created_at": _now(),
            "subject": subject,
            "message": message,
            "items": [
                {
                    "sender_item_id": item["id"],
                    "receiver": item["email"],
                    "amount": round(float(item["amount"]), 2),
                    "status": "SUCCESS",
                }
                for item in items
            ],
        }
        self.payouts[batch_id] = record
        return {"batch_id": batch_id, "status": "SUCCESS", "raw": record}

    async def get_payout(self, batch_id: str) -> dict:
        record = self.payouts.get(batch_id, {})
        return {
            "batch_id": batch_id,
            "status": record.get("status", "UNKNOWN"),
            "items": record.get("items", []),
            "raw": record,
        }

    # -- webhooks ----------------------------------------------------------
    async def verify_webhook(self, *, headers: dict, body: dict) -> str:
        return "MOCK"

    async def health(self) -> dict:
        return {
            "ok": True,
            "env": "mock",
            "note": "No PayPal credentials configured - running the in-process gateway.",
        }
