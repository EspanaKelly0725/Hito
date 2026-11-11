"""Agent 1 - read the contract, propose the plan.

Laura uploads a PDF. This agent turns it into something a payment system can
act on: who the client is, how many deliverables there are, what each one is
worth, when it is due, and what share each collaborator gets. Every milestone
carries the sentence from the contract it came from, because Laura has to
approve the plan and "trust me" is not an approval.

The output is a *proposal*. Nothing is created, sent, or charged until Laura
approves it in the UI.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {"type": "string"},
        "client_name": {"type": "string"},
        "client_email": {"type": "string"},
        "client_country": {
            "type": "string",
            "description": "ISO 3166-1 alpha-2 country code of the client, e.g. US",
        },
        "client_language": {
            "type": "string",
            "description": "Language the client writes in: 'en' or 'es'",
        },
        "currency": {"type": "string"},
        "total_amount": {"type": "number"},
        "payment_terms": {"type": "string"},
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "due_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD. Derive it from the contract; if the "
                                       "contract only gives a term like 'net 15 after "
                                       "delivery', leave it empty.",
                    },
                    "contract_quote": {
                        "type": "string",
                        "description": "The exact sentence from the contract that sets "
                                       "this deliverable and its amount.",
                    },
                },
                "required": ["title", "description", "amount", "due_date",
                             "contract_quote"],
                "additionalProperties": False,
            },
        },
        "collaborators": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                    "pct": {
                        "type": "number",
                        "description": "Share of each payment, as a percentage (30 = 30%)",
                    },
                },
                "required": ["name", "email", "role", "pct"],
                "additionalProperties": False,
            },
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Anything ambiguous, missing or risky that Laura should "
                           "read before approving: no late-payment clause, amounts "
                           "that do not add up, undefined acceptance criteria.",
        },
        "confidence": {"type": "number", "description": "0 to 1"},
    },
    "required": ["project_name", "client_name", "client_email", "client_country",
                 "client_language", "currency", "total_amount", "payment_terms",
                 "milestones", "collaborators", "warnings", "confidence"],
    "additionalProperties": False,
}

SYSTEM = """You read freelance service contracts and turn them into a payment plan.

You are precise and you never invent numbers. Rules:
- Extract amounts exactly as written. Do not round, convert currency, or redistribute.
- One milestone per deliverable that triggers a payment. If the contract names three
  deliverables with one payment each, return exactly three milestones.
- contract_quote must be a verbatim span from the contract. Never paraphrase it.
- Collaborator percentages are shares of each payment unless the contract says otherwise.
- If the milestone amounts do not sum to the stated total, keep both as written and add
  a warning. Do not silently fix the contract.
- Put anything a freelancer would regret not noticing into warnings: missing late-payment
  terms, vague acceptance criteria, unlimited revisions, IP transferred before payment.
- Dates: resolve relative terms against the contract date when it is stated. If you
  cannot resolve a date, return an empty string rather than guessing."""


def parse(contract_text: str, *, filename: str = "") -> dict:
    user = (
        f"Contract file: {filename or 'contract.pdf'}\n"
        f"Today: {date.today().isoformat()}\n\n"
        "--- CONTRACT TEXT ---\n"
        f"{llm.trim_to_budget(contract_text)}\n"
        "--- END CONTRACT TEXT ---\n\n"
        "Extract the payment plan."
    )
    data = llm.call_json(
        "contract_parser",
        system=SYSTEM,
        user=user,
        schema=SCHEMA,
        fallback=lambda: _fallback(contract_text),
        effort="high",
    )
    return _normalize(data, contract_text)


# ---------------------------------------------------------------------------
# Deterministic fallback: a readable regex pass over the contract. It handles
# the shapes freelance contracts actually use (US$3,000 / $3.000 USD / 30%)
# and is what runs in demo mode with no API key.
# ---------------------------------------------------------------------------

AMOUNT_RE = re.compile(
    # Stop before a trailing separator, so "US$3,000, due on..." yields "3,000".
    r"(?:US\s?\$|USD\s?\$?|\$)\s?(\d(?:[\d.,]*\d)?)", re.IGNORECASE
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PCT_RE = re.compile(r"(\d{1,2}(?:[.,]\d+)?)\s?%")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
MONTH_NAMES = "|".join(MONTHS)
# "October 10, 2026" / "10 October 2026" / "10 de octubre de 2026"
MONTH_DATE_RE = re.compile(
    rf"(?:({MONTH_NAMES})\s+(\d{{1,2}})(?:\s*,)?\s+(\d{{4}})"
    rf"|(\d{{1,2}})\s+(?:de\s+)?({MONTH_NAMES})\s+(?:de\s+)?(\d{{4}}))",
    re.IGNORECASE,
)


def find_date(text: str) -> str:
    """Pull an ISO date out of free text, in the notations contracts actually use."""
    iso = DATE_RE.search(text or "")
    if iso:
        return iso.group(0)
    hit = MONTH_DATE_RE.search(text or "")
    if not hit:
        return ""
    if hit.group(1):
        month, day, year = MONTHS[hit.group(1).lower()], hit.group(2), hit.group(3)
    else:
        day, month, year = hit.group(4), MONTHS[hit.group(5).lower()], hit.group(6)
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""

DELIVERABLE_HINTS = (
    "milestone", "deliverable", "entrega", "hito", "phase", "fase",
    "logo", "website", "web site", "web page", "brand manual", "manual de marca",
)


def _to_float(raw: str) -> float:
    text = raw.strip().strip(".,")
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") \
            else text.replace(".", "").replace(",", ".")
    elif "," in text:
        parts = text.split(",")
        text = text.replace(",", "") if len(parts[-1]) == 3 else text.replace(",", ".")
    elif text.count(".") == 1 and len(text.split(".")[-1]) == 3:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _fallback(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    emails = EMAIL_RE.findall(text)
    amounts = [_to_float(a) for a in AMOUNT_RE.findall(text)]
    amounts = [a for a in amounts if a > 0]
    total = max(amounts) if amounts else 0.0

    milestones = []
    for line in lines:
        low = line.lower()
        if not any(h in low for h in DELIVERABLE_HINTS):
            continue
        found = AMOUNT_RE.search(line)
        if not found:
            continue
        amount = _to_float(found.group(1))
        if amount <= 0 or amount >= total:
            continue
        due = find_date(line)
        title = _milestone_title(line) or f"Deliverable {len(milestones) + 1}"
        milestones.append({
            "title": title,
            "description": line[:240],
            "amount": amount,
            "due_date": due,
            "contract_quote": line[:300],
        })

    collaborators = []
    for line in lines:
        pct_hit = PCT_RE.search(line)
        mail_hit = EMAIL_RE.search(line)
        if not (pct_hit and mail_hit):
            continue
        pct = float(pct_hit.group(1).replace(",", "."))
        if not 0 < pct < 100:
            continue
        name = re.split(r"[—:\-–(]", line)[0].strip(" .*#")
        role = "collaborator"
        for candidate in ("developer", "programmer", "illustrator", "designer",
                          "copywriter", "desarrollador", "programador",
                          "ilustrador", "disenador"):
            if candidate in line.lower():
                role = candidate
                break
        collaborators.append({
            "name": name[:60] or mail_hit.group(0).split("@")[0],
            "email": mail_hit.group(0),
            "role": role,
            "pct": pct,
        })

    client_email = ""
    for email in emails:
        if not any(c["email"] == email for c in collaborators):
            client_email = email
            break

    warnings = ["Parsed by the deterministic fallback (no ANTHROPIC_API_KEY set): "
                "review every amount and date before approving."]
    if milestones and total and abs(sum(m["amount"] for m in milestones) - total) > 0.01:
        warnings.append("Milestone amounts do not add up to the contract total.")
    if "late" not in text.lower() and "mora" not in text.lower():
        warnings.append("No late-payment clause found in the contract.")

    return {
        "project_name": (lines[0][:80] if lines else "Untitled project"),
        "client_name": _guess_client(lines) or "Client",
        "client_email": client_email,
        "client_country": "US" if "texas" in text.lower() or "usa" in text.lower() else "",
        "client_language": "es" if _looks_spanish(text) else "en",
        "currency": "USD",
        "total_amount": total,
        "payment_terms": "See contract",
        "milestones": milestones,
        "collaborators": collaborators,
        "warnings": warnings,
        "confidence": 0.45,
    }


def _milestone_title(line: str) -> str:
    """Pull the deliverable name out of a line like
    "Milestone 2 - Website design and build: US$3,000, due on ...".
    """
    head = re.split(r"(?:US\s?\$|USD|\$)", line)[0]
    head = re.sub(r"[,:;\s]+$", "", head)
    for separator in (" - ", " – ", ": ", " -- "):
        if separator in head:
            head = head.split(separator, 1)[1]
            break
    else:
        head = re.sub(r"^(milestone|deliverable|entrega|hito|phase|fase)\s*\d*[.)]?\s*",
                      "", head, flags=re.IGNORECASE)
    return head.strip(" .*#-–:").rstrip(",")[:70]


def _looks_spanish(text: str) -> bool:
    hits = sum(text.lower().count(w) for w in
               (" el ", " la ", " de ", " entrega", " pago", " cliente"))
    return hits >= 4


def _guess_client(lines: list[str]) -> str:
    for line in lines[:40]:
        low = line.lower()
        if low.startswith(("client:", "cliente:", "customer:")):
            return line.split(":", 1)[1].strip()[:60]
    return ""


# ---------------------------------------------------------------------------


def _normalize(data: dict, contract_text: str) -> dict:
    """Clamp whatever came back into something the rest of the app can trust."""
    meta = data.pop("_meta", {})
    milestones = []
    for idx, raw in enumerate(data.get("milestones") or []):
        amount = round(float(raw.get("amount") or 0), 2)
        if amount <= 0:
            continue
        milestones.append({
            "idx": idx + 1,
            "title": (raw.get("title") or f"Deliverable {idx + 1}")[:120],
            "description": (raw.get("description") or "")[:600],
            "amount": amount,
            "due_date": _clean_date(raw.get("due_date"), idx),
            "contract_quote": (raw.get("contract_quote") or "")[:600],
        })

    collaborators = []
    for raw in data.get("collaborators") or []:
        pct = round(float(raw.get("pct") or 0), 2)
        if not 0 < pct <= 100 or not raw.get("email"):
            continue
        collaborators.append({
            "name": (raw.get("name") or raw["email"].split("@")[0])[:80],
            "email": raw["email"].strip(),
            "role": (raw.get("role") or "collaborator")[:60],
            "pct": pct,
        })

    total = round(float(data.get("total_amount") or 0), 2)
    milestone_sum = round(sum(m["amount"] for m in milestones), 2)
    warnings = list(data.get("warnings") or [])
    if total and milestone_sum and abs(total - milestone_sum) > 0.01:
        warnings.append(
            f"Milestones add up to {llm.money(milestone_sum)} but the contract "
            f"total is {llm.money(total)}."
        )
    if sum(c["pct"] for c in collaborators) > 100:
        warnings.append("Collaborator shares add up to more than 100% of each payment.")
    if not milestones:
        warnings.append("No milestone with an amount was found in this document.")

    return {
        "project_name": (data.get("project_name") or "Untitled project")[:140],
        "client_name": (data.get("client_name") or "Client")[:120],
        "client_email": (data.get("client_email") or "").strip(),
        "client_country": (data.get("client_country") or "").upper()[:2],
        "client_language": "es" if (data.get("client_language") or "en").lower().startswith("es") else "en",
        "currency": _clean_currency(data.get("currency")),
        "total_amount": total or milestone_sum,
        "payment_terms": (data.get("payment_terms") or "")[:400],
        "milestones": milestones,
        "collaborators": collaborators,
        "warnings": warnings[:8],
        "confidence": round(float(data.get("confidence") or 0.5), 2),
        "contract_chars": len(contract_text),
        "_meta": meta,
    }


CURRENCY_WORDS = {
    "us dollar": "USD", "us dollars": "USD", "dollar": "USD", "dollars": "USD",
    "usd": "USD", "u.s. dollars": "USD", "united states dollars": "USD",
    "dolar": "USD", "dolares": "USD", "dólar": "USD", "dólares": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "pound": "GBP", "pounds": "GBP", "gbp": "GBP",
    "peso": "COP", "pesos": "COP", "cop": "COP",
    "mxn": "MXN", "cad": "CAD", "brl": "BRL", "ars": "ARS",
}


def _clean_currency(raw: object) -> str:
    """Models write "US dollars" as happily as "USD"; the rest of the app needs
    an ISO code, and naively upper-casing the first three characters turns
    "US dollars" into "US ", which PayPal rejects."""
    text = str(raw or "").strip()
    if not text:
        return "USD"
    mapped = CURRENCY_WORDS.get(text.lower())
    if mapped:
        return mapped
    if len(text) == 3 and text.isalpha():
        return text.upper()
    for word, code in CURRENCY_WORDS.items():
        if word in text.lower():
            return code
    return "USD"


def _clean_date(raw: object, idx: int) -> str:
    found = find_date(str(raw or "").strip())
    if found:
        try:
            datetime.strptime(found, "%Y-%m-%d")
            return found
        except ValueError:
            pass
    # No usable date in the contract: stage them a fortnight apart so the plan
    # has a timeline Laura can edit, and say so in the UI.
    return (date.today() + timedelta(days=14 * (idx + 1))).isoformat()
