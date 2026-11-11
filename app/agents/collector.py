"""Agent 3 - ask for the money, in the register the risk says it deserves.

This is the part Laura hates doing. It is also the part where tone is a
business decision rather than a style choice: leaning on a client who simply
forgot costs you the relationship, and sending a third "just a gentle
reminder" to a client who is 45 days late costs you the invoice.

So the tone is not chosen by the model. It is chosen by the risk model in
app/risk/model.py, which estimates the probability this invoice is never paid
and maps it to a band:

    PD < 0.18   friendly       a nudge
    PD < 0.45   firm           a date, the contract clause, consequences
    PD >= 0.45  payment_plan   offer to split the balance in two

Claude writes the message *inside* that decision - never chooses it - and the
message is a draft until Laura presses send.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "Email subject, under 80 chars."},
        "body": {
            "type": "string",
            "description": "The message. Plain text, no markdown, no placeholders "
                           "like [name] - use the real names given.",
        },
        "tone_used": {"type": "string"},
        "rationale": {
            "type": "string",
            "description": "One sentence to Laura explaining why the message reads the "
                           "way it does.",
        },
        "escalation_suggestion": {
            "type": "string",
            "description": "What to do if this message gets no reply. One short sentence.",
        },
    },
    "required": ["subject", "body", "tone_used", "rationale", "escalation_suggestion"],
    "additionalProperties": False,
}

SYSTEM = """You write payment reminders on behalf of an independent designer to her
clients. You are her voice: warm, brief, professional, never passive-aggressive,
never grovelling. She is a professional asking for money she has earned, not a
supplicant.

The TONE is given to you and is not yours to change:

- friendly: assume it slipped. Two short paragraphs. No deadline, no consequences.
  Make it easy to pay and easy to reply.
- firm: name the invoice, the amount, the days overdue and a specific date. Reference
  the contract clause if one is given. One sentence on what happens after that date.
  Stay courteous. No threats, no legal language.
- payment_plan: acknowledge that cash flow happens, and offer the concrete split you
  are given, with both amounts and both dates. Make accepting it the easiest option.
  Keep the door open.

Hard rules:
- Write in the client's language (given below).
- Never invent amounts, dates or facts. Use only what you are given.
- Never mention risk scores, probabilities, models or automation. The client must read
  a message from Laura, not from a system.
- No markdown, no bullet characters, no placeholders. Sign as the designer's name."""


def draft(*, project: dict, milestone: dict, risk: dict, days_overdue: int,
          history: dict, invoice_url: str = "") -> dict:
    amount = round(float(milestone.get("amount") or 0), 2)
    currency = project.get("currency") or "USD"
    language = "Spanish" if project.get("client_language") == "es" else "English"
    offer = _offer_terms(amount, risk) if risk.get("offer") == "split_in_two" else None

    user = (
        f"TONE (decided by the risk model, do not change): {risk.get('tone')}\n"
        f"INTENT: {risk.get('intent')}\n"
        f"CLIENT LANGUAGE: {language}\n\n"
        f"From: {project.get('invoicer_name', 'Laura Restrepo')}, "
        f"independent brand designer\n"
        f"To: {project.get('client_name')} <{project.get('client_email')}>\n"
        f"Project: {project.get('name')}\n"
        f"Deliverable billed: {milestone.get('title')} "
        f"({milestone.get('description', '')[:160]})\n"
        f"Invoice: {milestone.get('invoice_number') or '-'} for "
        f"{currency} {llm.money(amount)}\n"
        f"Due date: {milestone.get('due_date')} - {days_overdue} days overdue\n"
        f"Payment link: {invoice_url or '(the PayPal invoice already in their inbox)'}\n"
        f"Contract clause for this deliverable: "
        f"{milestone.get('contract_quote') or '(none recorded)'}\n"
        f"Payment terms in the contract: {project.get('payment_terms') or '(none)'}\n\n"
        f"HISTORY WITH THIS CLIENT: {history.get('invoices_settled', 0)} invoices "
        f"settled, {int(history.get('late_ratio', 0) * 100)}% of them late, "
        f"{history.get('avg_days_late', 0):.0f} days late on average. "
        f"This is reminder number {history.get('reminder_count', 0) + 1} for this invoice.\n"
    )
    if offer:
        user += (
            f"\nPAYMENT SPLIT TO OFFER: {currency} {llm.money(offer['first'])} "
            f"by {offer['first_date']}, then {currency} {llm.money(offer['second'])} "
            f"by {offer['second_date']}.\n"
        )
    user += "\nWrite the message."

    result = llm.call_json(
        "collector",
        system=SYSTEM,
        user=user,
        schema=SCHEMA,
        fallback=lambda: _fallback(project, milestone, risk, days_overdue, offer),
        effort="medium",
        max_tokens=3000,
    )
    result["offer_terms"] = offer
    return result


def _offer_terms(amount: float, risk: dict) -> dict:
    half = round(amount / 2, 2)
    return {
        "kind": "split_in_two",
        "first": half,
        "second": round(amount - half, 2),
        "first_date": (date.today() + timedelta(days=7)).isoformat(),
        "second_date": (date.today() + timedelta(days=37)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Deterministic templates. Same three registers, written by hand, used when
# there is no API key. The UI labels them as templates.
# ---------------------------------------------------------------------------

TEMPLATES = {
    "friendly": {
        "en": ("Quick note about invoice {number}",
               "Hi {client},\n\nHope the {project} work is landing well. Just a quick "
               "note that invoice {number} for {currency} {amount} (for the {title}) "
               "came due on {due} - I think it may have slipped through.\n\nYou can pay "
               "it straight from the PayPal invoice in your inbox. If anything about it "
               "needs changing, tell me and I will fix it today.\n\nThanks!\n{sender}"),
        "es": ("Nota rapida sobre la factura {number}",
               "Hola {client}:\n\nEspero que el trabajo de {project} vaya bien. Solo "
               "para contarte que la factura {number} por {currency} {amount} (del "
               "{title}) vencio el {due}; creo que se paso por alto.\n\nPuedes pagarla "
               "directamente desde la factura de PayPal que tienes en el correo. Si hay "
               "algo que haya que ajustar, me dices y lo corrijo hoy.\n\nGracias!\n{sender}"),
    },
    "firm": {
        "en": ("Invoice {number} - {days} days overdue",
               "Hi {client},\n\nInvoice {number} for {currency} {amount}, covering the "
               "{title}, was due on {due} and is now {days} days overdue.\n\nCould you "
               "settle it by {deadline}? The work is delivered and in use, and our "
               "agreement sets payment on delivery of each milestone. If it is not "
               "settled by then I will pause work on the remaining milestones until it "
               "is.\n\nIf something is blocking payment on your side, tell me what it is "
               "and we will sort it out.\n\nBest,\n{sender}"),
        "es": ("Factura {number} - {days} dias de vencida",
               "Hola {client}:\n\nLa factura {number} por {currency} {amount}, "
               "correspondiente al {title}, vencio el {due} y lleva {days} dias de "
               "mora.\n\nTe pido que la pagues antes del {deadline}. El trabajo esta "
               "entregado y en uso, y nuestro acuerdo establece el pago contra entrega "
               "de cada hito. Si no esta pagada en esa fecha, pausare los hitos "
               "pendientes hasta que lo este.\n\nSi hay algo que este frenando el pago "
               "de tu lado, dime que es y lo resolvemos.\n\nSaludos,\n{sender}"),
    },
    "payment_plan": {
        "en": ("A way to close out invoice {number}",
               "Hi {client},\n\nInvoice {number} for {currency} {amount} (the {title}) "
               "is {days} days past its {due} due date. Cash flow gets tight - it "
               "happens on my side too - so rather than keep sending reminders, let me "
               "offer a split.\n\n{currency} {first} by {first_date}, and the remaining "
               "{currency} {second} by {second_date}. Say the word and I will send both "
               "invoices today, and we keep the rest of the project moving.\n\nIf the "
               "full amount is easier, that works too.\n\nBest,\n{sender}"),
        "es": ("Una forma de cerrar la factura {number}",
               "Hola {client}:\n\nLa factura {number} por {currency} {amount} (el "
               "{title}) lleva {days} dias desde su vencimiento del {due}. El flujo de "
               "caja se aprieta, me pasa tambien, asi que en vez de seguir mandando "
               "recordatorios te propongo dividirla.\n\n{currency} {first} antes del "
               "{first_date} y los {currency} {second} restantes antes del "
               "{second_date}. Me confirmas y hoy mismo te envio las dos facturas, y "
               "seguimos moviendo el resto del proyecto.\n\nSi te resulta mas facil el "
               "monto completo, tambien funciona.\n\nSaludos,\n{sender}"),
    },
}


MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _pretty_date(value: str, lang: str) -> str:
    """Templates should read like a person wrote them, not like a database."""
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return str(value or "")
    if lang == "es":
        return f"{parsed.day} de {MONTHS_ES[parsed.month - 1]}"
    return f"{MONTHS_EN[parsed.month - 1]} {parsed.day}"


def _fallback(project: dict, milestone: dict, risk: dict, days_overdue: int,
              offer: dict | None) -> dict:
    tone = risk.get("tone", "friendly")
    lang = "es" if project.get("client_language") == "es" else "en"
    subject_tpl, body_tpl = TEMPLATES.get(tone, TEMPLATES["friendly"])[lang]
    fields = {
        "client": project.get("client_name", "there"),
        "project": project.get("name", "the project"),
        "number": milestone.get("invoice_number") or "-",
        "currency": project.get("currency", "USD"),
        "amount": llm.money(milestone.get("amount") or 0),
        "title": milestone.get("title", "deliverable"),
        "due": _pretty_date(milestone.get("due_date", ""), lang),
        "days": days_overdue,
        "deadline": _pretty_date(
            (date.today() + timedelta(days=5)).isoformat(), lang
        ),
        "sender": project.get("invoicer_name", "Laura Restrepo"),
        "first": llm.money(offer["first"]) if offer else "",
        "second": llm.money(offer["second"]) if offer else "",
        "first_date": _pretty_date(offer["first_date"], lang) if offer else "",
        "second_date": _pretty_date(offer["second_date"], lang) if offer else "",
    }
    return {
        "subject": subject_tpl.format(**fields),
        "body": body_tpl.format(**fields),
        "tone_used": tone,
        "rationale": (
            f"Template for the {tone} band (PD {risk.get('pd')}), "
            "rendered without a model call."
        ),
        "escalation_suggestion": (
            "If there is no reply in 5 days, move to the next band."
            if tone != "payment_plan"
            else "If there is no reply in 5 days, pause the remaining milestones."
        ),
    }
