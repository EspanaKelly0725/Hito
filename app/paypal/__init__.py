"""PayPal gateways. Two implementations behind one interface.

`PayPalClient` talks to the real PayPal REST API (sandbox or live):
Invoicing v2 to bill the client, Payouts v1 to pay the collaborators, and
Webhooks v1 to learn that the money landed.

`MockPayPal` implements the same surface in-process, so a judge can clone the
repo and run the entire contract-to-cash loop without creating any account.
Which one is active is decided once, here, and shown in the UI header.
"""
from __future__ import annotations

from ..config import settings
from .client import PayPalClient, PayPalError
from .mock import MockPayPal

_gateway = None


def gateway():
    """Return the process-wide gateway (real when credentials exist, else mock)."""
    global _gateway
    if _gateway is None:
        _gateway = PayPalClient() if settings.paypal_live else MockPayPal()
    return _gateway


__all__ = ["gateway", "PayPalClient", "MockPayPal", "PayPalError"]
