# Devpost submission text

Paste-ready. Deadline: **12 Nov 2026, 3:00 pm GMT-5**.

---

## Tagline (one line)

Hito reads a freelancer's contract, invoices each milestone through PayPal, and
decides how hard to chase a late client based on how likely they are to never
pay.

---

## Inspiration

Laura is a designer in Medellín. A client in Texas pays her US$9,000 for a
brand identity, in three parts, and she shares each payment with a developer
and an illustrator.

She does all of it by hand: reads the contract, creates each PayPal invoice,
sends it when she finishes that piece, checks whether the money arrived, writes
the awkward "hi, just a reminder…" when it didn't, and transfers her friends
their share at the end.

The invoicing is tedious. The chasing is the expensive part. Collection is an
emotional task performed by the person who is owed, so the uncomfortable email
gets delayed, then softened, then sent to a client who has already learned that
being late with Laura costs nothing. Freelancers do not lose money because they
cannot invoice. They lose it because asking is hard.

## What it does

Hito runs the whole thing, in five moments:

1. **Reads the contract.** Drop in the PDF; Hito extracts every deliverable,
   its amount, its due date, the sentence in the contract that sets it, and the
   collaborator revenue shares — and flags what is vague before Laura agrees to
   it. Nothing is created until she approves the plan.
2. **Invoices when she delivers.** She marks a milestone delivered. Before
   PayPal is called, a second, independent reviewer checks the invoice against
   the contract. Only then does Hito create and send the real PayPal invoice.
3. **Notices the money.** The PayPal webhook arrives, the signature is
   verified, the milestone flips to paid, the dashboard updates.
4. **Collects, with tact.** When an invoice goes past due, a risk model
   estimates the probability it is never paid, and *that* picks the register: a
   friendly nudge, a firm reminder with a date and the contract clause, or an
   offer to split the balance in two. Claude writes inside that decision. Laura
   edits and sends.
5. **Splits it.** 30% to the developer, 20% to the illustrator, through PayPal
   Payouts — with a visible approval ceiling above which Hito will not send
   anything on its own.

## How we built it

**Backend** — FastAPI + SQLite, no ORM. `pip install -r requirements.txt` and
`uvicorn app.main:app` is the entire setup.

**PayPal** — Invoicing v2 (generate invoice number, create, send, read back,
remind), Payouts v1 (batch, status), and webhook signature verification, with
idempotency keys on everything that moves money.

**Claude** — four agents, each with a JSON schema through
`output_config.format` so the backend never parses prose: a contract parser, an
invoice reviewer, a collections writer and a payout writer. Server-side refusal
fallback is requested on every call.

**The risk model** — a logistic regression fitted in pure Python at boot on
~900 historical invoices and scored out of sample (AUC ≈ 0.70, Brier ≈ 0.18
against a 29% base rate). Features are behaviour Hito observed in its own
ledger: invoices this client has settled, how often late, how late, invoice
size, days past due. The band cut-offs are the 50th and 85th percentile of the
model's own predictions, not round numbers, so the policy travels with the
data. The dashboard shows the fitted weights, the metrics and a what-if panel.

**Frontend** — Vite + React + Tailwind + shadcn/ui on Base UI, AG Grid
Community for every table, Sonner, cmdk and NumberFlow. Compiled to
`app/static` and committed, so judges need no Node.

**Also an MCP server** — the same flow as 11 Model Context Protocol tools over
stdio, so any agent can drive a freelancer's billing, with identical
guardrails.

## What makes it defensible rather than just automated

An agent that can send invoices and move money needs more than good intentions:

- **The agent that writes the invoice never approves it.** Seven deterministic
  Python checks (amount matches the approved plan, not already invoiced, within
  the contract total, recipient is the client of record, currency matches, the
  amount actually appears in the contract) *plus* an independent Claude pass
  that reads the contract. A deterministic failure **blocks**; a model objection
  **holds** for a human; only agreement sends.
- **The model never does arithmetic.** Splits, remainders and instalments are
  `Decimal` maths in Python, reconciled so payouts can never exceed the
  payment. Claude is given finished numbers and writes the copy.
- **A visible ceiling on money movement.** Payout items above the threshold are
  flagged and not sent until a human ticks that specific line — in the UI, the
  API and over MCP.
- **One audit ledger.** Every decision recorded as `agent` or `human`, with
  every model call's tokens, latency and cost beside it.

## Challenges we ran into

Calibrating the tone policy. The first version used hand-picked thresholds
(0.18 / 0.45) and put *every* realistic client in the "high risk, offer a
payment plan" band, because a 29% base rate makes 0.30 an ordinary client
rather than a worrying one. The fix was to derive the cut-offs from the model's
own predicted distribution, which made the policy portable to any portfolio.

Making the demo runnable by people with no accounts. The answer was a second
PayPal gateway with the same interface, in-process, including a payer page with
a working Pay button — plus a deterministic twin for all four agents, so the
product degrades honestly instead of breaking when a key is missing. The UI
always says which mode is live.

## What we learned

That the interesting problem was never the invoicing. It was deciding, with
evidence, how to talk to someone who owes you money — and that this is exactly
the kind of judgment call that should be split between a model and a number you
can audit. Also, from fitting the model: cross-border barely survives. How a
client paid you before beats where they are, by an order of magnitude.

## What's next

Reading payment behaviour across every freelancer on Hito instead of one
ledger, so a new client arrives with a prior instead of a shrug. Partial
payments and the payment-plan follow-through as first-class states. And pricing
advice at contract time: given this client's profile, ask for a deposit.

---

## Try it (what judges need)

```bash
git clone <repo> && cd hito
pip install -r requirements.txt
uvicorn app.main:app
```

Open <http://localhost:8000>, press **Seed history**, then **Use the sample
contract**. The whole five-step flow runs with no PayPal account and no API key
— mock gateway and deterministic agents, clearly labelled. Add credentials to
`.env` and the same screens drive the real PayPal sandbox and Claude; verify
with `python scripts/check_credentials.py`.

## Built with

`python` · `fastapi` · `sqlite` · `paypal-invoicing-v2` · `paypal-payouts-v1` ·
`paypal-webhooks` · `claude` · `anthropic-api` · `structured-outputs` ·
`model-context-protocol` · `logistic-regression` · `react` · `typescript` ·
`vite` · `tailwindcss` · `shadcn-ui` · `base-ui` · `ag-grid` · `sonner` ·
`cmdk` · `number-flow` · `apimatic` · `render` · `docker`
