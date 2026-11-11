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

**The AI engine — open source, running on the freelancer's own machine.**
Four agents (a contract parser, an invoice reviewer, a collections writer and a
payout writer) run on **Qwen2.5 3B Instruct, Apache-2.0**, served locally by
Ollama. Claude is supported as a drop-in swap but is opt-in, not required.

That choice is about the user, not about cost. A freelance contract carries the
client's legal name, their billing address, the fee schedule, the payment terms
and the collaborators' names and shares. Sending that to a third-party API to
extract four numbers is a trade most freelancers would not make if anyone
actually asked them. Hito does not ask, because it does not have to: the
contract is read on the machine it was downloaded to, and nothing about it is
transmitted. It is also free, which matters more than it sounds — re-reading a
contract is something you do when the plan looks wrong, and a metered API
quietly teaches you to do it less.

Every agent is called with a JSON schema its output must satisfy — Ollama's
`format`, Claude's `output_config.format` — so the backend never parses prose
and the agents do not know which engine answered.

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
- **The guardrails do not depend on model quality.** This is what makes a 3B
  local model a reasonable choice rather than a risk: the seven blocking checks
  are deterministic Python, the arithmetic is `Decimal`, the ceiling is a
  number, and every model output is a proposal a human approves. A better model
  makes the writing better; it cannot make the money safer, because the model
  was never what was keeping it safe.

## How well does a 3B model actually read a contract?

We measured instead of guessing. `scripts/eval_parser.py` scores the parser
field by field — milestone count, amounts, total, due dates, client email,
collaborator shares, currency, and whether each milestone carries a verbatim
quote — against three contracts with known answers: the sample PDF, a Spanish
one using `US$3.000` notation with dates written as "18 de octubre de 2026",
and an English letter of engagement written in prose rather than as a list.

The deterministic baseline scores 17/24. It gets 8/8 on the sample contract,
which flatters it because those regexes were written against that contract, and
2/8 on prose, where there is simply no list to find. That gap is the reason
there is a model at all, and the numbers are in `docs/OPEN_MODEL.md`.

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
can audit.

Also, two things we did not expect. From fitting the risk model: cross-border
barely survives. How a client paid you before beats where they are, by an order
of magnitude. And from swapping the engine: once the guardrails are
deterministic, the model gets to be small, local and free — which turns out to
be the version a freelancer in Medellín can actually afford to run on every
contract that lands in her inbox, rather than the ones she decides are worth
the API call.

## What's next

Reading payment behaviour across every freelancer on Hito instead of one
ledger, so a new client arrives with a prior instead of a shrug. Partial
payments and the payment-plan follow-through as first-class states. And pricing
advice at contract time: given this client's profile, ask for a deposit.

---

## Try it (what judges need)

**Hosted, nothing to install: <https://hito-zz3z.onrender.com>**

Press *Seed history*, then *Use the sample contract*, and walk the five steps.
It is on Render's free tier, so the first request can take ~50 seconds while
the instance wakes up — after that it is instant. The hosted copy runs the
in-process PayPal gateway and the deterministic engine, both labelled in the
header, because a 2 GB open-source model does not fit a free instance and the
whole argument for that model is that it runs on the freelancer's own machine.

To see it with the real engine and real PayPal sandbox invoices, run it
locally:

```bash
git clone <repo> && cd hito
pip install -r requirements.txt
uvicorn app.main:app
```

Open <http://localhost:8000>, press **Seed history**, then **Use the sample
contract**. The whole five-step flow runs with **no accounts of any kind** —
in-process PayPal gateway and deterministic agents, both clearly labelled in
the header.

To see it with the real engine, which needs no key either:

```bash
ollama pull qwen2.5:3b        # ~2 GB, once
```

Add PayPal sandbox credentials to `.env` for real invoices and payouts. Verify
everything with `python scripts/check_credentials.py`, which tests each piece
separately and prints no secrets.

## Built with

`python` · `fastapi` · `sqlite` · `paypal-invoicing-v2` · `paypal-payouts-v1` ·
`paypal-webhooks` · `qwen2.5` · `ollama` · `open-source-llm` · `local-inference` ·
`claude` · `anthropic-api` · `structured-outputs` ·
`model-context-protocol` · `logistic-regression` · `react` · `typescript` ·
`vite` · `tailwindcss` · `shadcn-ui` · `base-ui` · `ag-grid` · `sonner` ·
`cmdk` · `number-flow` · `apimatic` · `render` · `docker`
