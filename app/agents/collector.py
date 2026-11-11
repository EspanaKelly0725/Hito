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

import re
from datetime import date, timedelta

from . import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "Email subject, under 80 chars."},
        "body": {
            "type": "string",
            "description": "The message, as plain text. Separate paragraphs with "
                           "a blank line - never one solid block of text. No "
                           "markdown, no placeholders like [name]: use the real "
                           "names given.",
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

# The tone instructions are injected one at a time, not all three at once.
# A small model reads the other two as available options: given the whole menu
# while writing a "firm" reminder, qwen2.5:3b offered the client a payment plan
# that was never on the table. It cannot leak an instruction it was never given.
TONE_INSTRUCTIONS = {
    "friendly": (
        "TONE: friendly. Assume the invoice slipped through the cracks. Two short "
        "paragraphs. Do NOT give a deadline, do NOT mention consequences, do NOT "
        "offer any payment plan or instalments. Make it easy to pay and easy to reply."
    ),
    "firm": (
        "TONE: firm. Name the invoice, the amount, how many days overdue it is, and "
        "ONE specific future date to pay by. Reference the contract clause you are "
        "given. One sentence on what happens after that date. Stay courteous: no "
        "threats, no legal language. Do NOT offer a payment plan, instalments, or a "
        "split - none is on the table."
    ),
    "payment_plan": (
        "TONE: payment plan. Acknowledge that cash flow gets tight, and offer the "
        "exact split you are given below, with both amounts and both dates and "
        "nothing else. Make accepting it the easiest option. Keep the door open."
    ),
}

SYSTEM = """You write payment reminders on behalf of an independent designer to her
clients. You are her voice: warm, brief, professional, never passive-aggressive,
never grovelling. She is a professional asking for money she has earned, not a
supplicant.

Hard rules:
- Write in the client's language (given below).
- Use ONLY the facts you are given. Never invent an amount, a date, a deadline, an
  attachment, a link, or a term of any kind. If you were not told it, it does not exist.
- Never claim this is a final notice, a last reminder, or that the matter will be
  escalated, unless you are explicitly told so below.
- Never mention risk scores, probabilities, models or automation. The client must read
  a message from Laura, not from a system.
- No markdown, no bullet characters, no placeholders, no postscript. Sign as the
  designer's name.
- Break the message into short paragraphs separated by a blank line. A single solid
  block of text reads like a form letter.
- Never open with filler. No "I hope this message finds you well", no "I trust you are
  doing well", no "I am writing to inform you". Start with the point.
- Never say "please do not hesitate to contact me" or "thank you for your prompt
  attention to this matter". Write the way a person writes to someone she knows."""


def draft(*, project: dict, milestone: dict, risk: dict, days_overdue: int,
          history: dict, invoice_url: str = "") -> dict:
    amount = round(float(milestone.get("amount") or 0), 2)
    currency = project.get("currency") or "USD"
    language = "Spanish" if project.get("client_language") == "es" else "English"
    offer = _offer_terms(amount, risk) if risk.get("offer") == "split_in_two" else None

    tone = risk.get("tone", "friendly")
    user = (
        f"{TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS['friendly'])}\n"
        f"The tone was decided by a risk model and is not yours to change.\n\n"
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
    result["warnings"] = review_draft(
        result.get("body", ""),
        offer=offer,
        reminder_count=int(history.get("reminder_count", 0)),
    )
    return result


FABRICATION_CHECKS = [
    (
        "offers_unoffered_plan",
        r"\b(payment plan|instal?ments?|in two parts|split the balance|"
        r"plan de pago|cuotas?)\b",
        "Offers a payment plan, which this tone does not include. Remove it or "
        "you are committing to terms you did not choose.",
    ),
    (
        "claims_finality",
        r"\b(final (reminder|notice|warning)|last (reminder|notice)|"
        r"�ltimo (aviso|recordatorio)|ultimo (aviso|recordatorio))\b",
        "Calls itself a final notice. Nothing told it that, and saying it when "
        "it is not true costs you the next reminder.",
    ),
    (
        "invents_attachment",
        r"\b(attached|attachment|enclosed|adjunto|adjunta|see the link below)\b",
        "Mentions an attachment or a link that is not being sent.",
    ),
    (
        "threatens_escalation",
        r"\b(legal action|collections? agency|lawyer|attorney|court|"
        r"acciones legales|abogad[oa]|cobro jur�dico)\b",
        "Threatens legal escalation. Hito never authorises that.",
    ),
    (
        "opens_with_filler",
        r"(i hope this (message|email) finds you well|i trust you are doing well|"
        r"i am writing to (inform|remind) you|espero que (este|se encuentre))",
        "Opens with form-letter filler instead of the point.",
    ),
    (
        "closes_with_filler",
        r"(do not hesitate to contact me|prompt attention to this matter|"
        r"no dude en contactarme)",
        "Closes with form-letter filler.",
    ),
]


def review_draft(body: str, *, offer: dict | None, reminder_count: int) -> list[dict]:
    """Check the draft for things the model made up.

    The collection message is the only model output in Hito that a *client*
    reads, so it gets the same treatment as the invoice: something independent
    checks it before a human is asked to approve it. These are the fabrications
    a small model actually produced - offering a payment plan that was never on
    the table, calling itself a final notice on the first try, inventing an
    attachment.

    Findings are shown to Laura, never auto-applied. She is the one sending it.
    """
    findings: list[dict] = []
    text = (body or "").lower()

    for name, pattern, explanation in FABRICATION_CHECKS:
        if not re.search(pattern, text, re.IGNORECASE):
            continue
        if name == "offers_unoffered_plan" and offer:
            continue  # a payment plan is exactly what this tone offers
        if name == "claims_finality" and reminder_count >= 2:
            continue  # by the third try, it is fair to say so
        findings.append({"check": name, "detail": explanation})

    if body and len(body.split()) > 230:
        findings.append({
            "check": "too_long",
            "detail": "Longer than a reminder needs to be; long reminders read "
                      "as anxious.",
        })
    return findings


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
