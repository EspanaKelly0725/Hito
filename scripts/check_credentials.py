"""Verify the credentials in .env, one at a time, and say exactly what works.

    python scripts/check_credentials.py

Checks, in order:
  1. PayPal OAuth2 against the sandbox (or live) token endpoint
  2. A real PayPal invoice-number generation call
  3. The Claude API with the same structured-output call the agents make
  4. The risk model

Prints no secrets. Exit code 0 when everything a project needs is working, 1
otherwise - so it is usable as a pre-demo smoke test.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents import llm  # noqa: E402
from app.config import settings  # noqa: E402
from app.paypal import PayPalClient, PayPalError  # noqa: E402
from app.risk import risk_model  # noqa: E402

OK, BAD, SKIP = "  OK  ", " FAIL ", " SKIP "


def line(tag: str, label: str, detail: str = "") -> None:
    print(f"[{tag}] {label}" + (f"\n         {detail}" if detail else ""))


async def check_paypal() -> bool:
    if not (settings.paypal_client_id and settings.paypal_client_secret):
        line(SKIP, "PayPal credentials",
             "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are empty in .env - "
             "the app will run with the in-process mock gateway.")
        return True
    client = PayPalClient()
    try:
        await client._access_token()
        line(OK, f"PayPal OAuth2 ({settings.paypal_env})", client.base_url)
    except PayPalError as exc:
        line(BAD, "PayPal OAuth2", f"{exc} / {exc.body}")
        return False

    try:
        number = await client.next_invoice_number()
        line(OK, "PayPal Invoicing v2 reachable", f"next invoice number: {number}")
    except PayPalError as exc:
        line(BAD, "PayPal Invoicing v2", f"{exc} / {exc.body}")
        return False

    if not settings.invoicer_email:
        line(SKIP, "Invoicer email",
             "PAYPAL_INVOICER_EMAIL is empty. Set it to your sandbox BUSINESS "
             "account email, or PayPal will reject the invoice.")
    else:
        line(OK, "Invoicer email set", settings.invoicer_email)

    if not settings.paypal_webhook_id:
        line(SKIP, "Webhook verification",
             "PAYPAL_WEBHOOK_ID is empty: incoming webhooks are accepted "
             "without signature verification. Fine for a local demo, not for live.")
    else:
        line(OK, "Webhook id set", "signatures will be verified")
    return True


def check_local_model() -> bool:
    """The default engine: an open-source model running on this machine."""
    local = llm.ollama_status(force=True)
    if not local["ok"]:
        line(SKIP, "Local open-source model", local["detail"])
        return True

    schema = {
        "type": "object",
        "properties": {
            "milestones_found": {"type": "integer"},
            "currency": {"type": "string"},
        },
        "required": ["milestones_found", "currency"],
        "additionalProperties": False,
    }
    result = llm.call_json(
        "credential_check",
        system="You extract payment plans from contracts. Answer only from the text.",
        user="Contract: two deliverables, US$1,500 each, payable in US dollars. "
             "How many milestones and which currency?",
        schema=schema,
        fallback=lambda: {"milestones_found": -1, "currency": "?"},
        max_tokens=256,
    )
    meta = result.get("_meta", {})
    if meta.get("engine") != "ollama":
        line(BAD, "Local open-source model",
             meta.get("note", "the call did not reach the local model"))
        return False
    line(OK, f"Local open-source model ({meta.get('model')})",
         f"structured output returned milestones_found="
         f"{result.get('milestones_found')}, currency={result.get('currency')} "
         f"in {meta.get('latency_ms')} ms "
         f"({meta.get('input_tokens')} in / {meta.get('output_tokens')} out, "
         f"no cost, nothing left this machine)")
    return result.get("milestones_found") == 2


def check_remote_model() -> bool:
    """The engine a deployment without a GPU uses: same open weights, hosted."""
    if not llm.remote_configured():
        line(SKIP, "Hosted open-weights model (optional)",
             "HITO_REMOTE_BASE_URL / HITO_REMOTE_API_KEY are empty. Only needed "
             "where there is no GPU to run the local model - the Render demo "
             "uses this so a visitor still sees a model working.")
        return True

    original = settings.llm_provider
    settings.llm_provider = "remote"
    result = llm.call_json(
        "credential_check",
        system="You extract payment plans from contracts. Answer only from the text.",
        user="Contract: two deliverables, US$1,500 each, payable in US dollars. "
             "How many milestones and which currency?",
        schema={
            "type": "object",
            "properties": {
                "milestones_found": {"type": "integer"},
                "currency": {"type": "string"},
            },
            "required": ["milestones_found", "currency"],
            "additionalProperties": False,
        },
        fallback=lambda: {"milestones_found": -1, "currency": "?"},
        max_tokens=256,
    )
    settings.llm_provider = original
    meta = result.get("_meta", {})
    if meta.get("engine") != "remote":
        line(BAD, "Hosted open-weights model",
             meta.get("note", "the call did not reach the endpoint"))
        return False
    line(OK, f"Hosted open-weights model ({meta.get('model')})",
         f"structured output returned milestones_found="
         f"{result.get('milestones_found')} in {meta.get('latency_ms')} ms "
         f"({meta.get('input_tokens')} in / {meta.get('output_tokens')} out) "
         f"via {settings.remote_base_url}")
    return result.get("milestones_found") == 2


def check_claude() -> bool:
    if not settings.anthropic_api_key:
        line(SKIP, "Claude API key (optional)",
             "ANTHROPIC_API_KEY is empty. Hito runs on the local open-source "
             "model; set a key only if you want Claude as the engine instead.")
        return True

    schema = {
        "type": "object",
        "properties": {
            "milestones_found": {"type": "integer"},
            "currency": {"type": "string"},
        },
        "required": ["milestones_found", "currency"],
        "additionalProperties": False,
    }
    import os
    os.environ["HITO_LLM_PROVIDER"] = "claude"
    settings.llm_provider = "claude"
    result = llm.call_json(
        "credential_check",
        system="You extract payment plans from contracts. Answer only from the text.",
        user="Contract: two deliverables, US$1,500 each, payable in US dollars. "
             "How many milestones and which currency?",
        schema=schema,
        fallback=lambda: {"milestones_found": -1, "currency": "?"},
        effort="low",
        max_tokens=1000,
    )
    settings.llm_provider = "auto"
    meta = result.get("_meta", {})
    if meta.get("engine") != "claude":
        line(BAD, "Claude API call", meta.get("note", "fell back to the rule engine"))
        return False
    line(OK, f"Claude API ({meta.get('model')})",
         f"structured output returned milestones_found="
         f"{result.get('milestones_found')}, currency={result.get('currency')} "
         f"in {meta.get('latency_ms')} ms "
         f"({meta.get('input_tokens')} in / {meta.get('output_tokens')} out, "
         f"${meta.get('cost_usd'):.5f})")
    return result.get("milestones_found") == 2


def check_risk() -> bool:
    if not risk_model.trained:
        line(BAD, "Risk model", "not fitted - is data/historial_pagos.csv present? "
                                "Regenerate it with python scripts/make_dataset.py")
        return False
    metrics = risk_model.metrics
    line(OK, "Risk model fitted",
         f"{risk_model.n_train} train / {risk_model.n_test} test rows, "
         f"AUC {metrics.get('auc')}, Brier {metrics.get('brier')}, "
         f"bands split at {risk_model.cutoffs[0]} / {risk_model.cutoffs[1]}")
    return True


def main() -> int:
    print("Hito - credential and model check\n" + "-" * 58)
    results = [
        asyncio.run(check_paypal()),
        check_local_model(),
        check_remote_model(),
        check_claude(),
        check_risk(),
    ]
    print("-" * 58)
    modes = settings.modes()
    print(f"PayPal gateway : {modes['paypal']}")
    print(f"AI engine      : {modes['ai']} ({modes['ai_provider']})")
    print(f"Payout ceiling : USD {modes['payout_threshold']:,.2f}")
    if all(results):
        print("\nEverything checked out. Start the app with:\n"
              "  uvicorn app.main:app --reload")
        return 0
    print("\nSomething above needs attention before the demo.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
