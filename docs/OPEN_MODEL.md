# The AI engine: an open-source model, running on your machine

Hito's default engine is **Qwen2.5 3B Instruct**, an Apache-2.0 licensed
open-source model, run locally through [Ollama](https://ollama.com). No
account, no API key, no per-token bill, and no network call.

This is a product decision before it is a technical one.

## Why a local open-source model

**The document is the sensitive part.** A freelance contract carries the
client's legal name, their billing address, the fee schedule, the payment
terms, and often the collaborators' names and what each of them is paid.
Sending that to a third-party API to extract four numbers is a trade most
freelancers would not make if anyone asked them. Hito does not ask, because it
does not have to: the contract is read on the same machine it was downloaded
to, and nothing about it is transmitted anywhere.

**Cost should not scale with trying.** Reading a contract is not a one-shot
action — you re-read it when the plan looks wrong, when you fix an amount, when
you upload a revised version. On a metered API each of those is a charge, which
quietly teaches you to re-read less. Locally it is free, so the product can
afford to be generous with it.

**It has to work on the hardware freelancers own.** Hito's reference machine is
an Intel Core Ultra 5 laptop with integrated graphics and 16 GB of RAM. A 3B
model quantised to 4 bits is about 2 GB and runs on that CPU; a 7B model
roughly doubles both. The engine is one environment variable, so anyone with
more machine can point it at a bigger model.

## Why Qwen2.5 3B specifically

| | |
| --- | --- |
| **Licence** | Apache-2.0 — genuinely open source, not "open weights" under a bespoke community licence with usage restrictions. It can be used commercially without asking anyone. |
| **Structured extraction** | Reliable under a JSON-schema constraint, which is how every Hito agent is called. |
| **Multilingual** | Hito's users write contracts in Spanish and receive them in English. Qwen2.5 handles both; many small models are English-first. |
| **Size** | ~2 GB quantised. Pulls in a few minutes, runs on a laptop CPU, leaves room for a browser and an IDE. |

Swap it with one line — `HITO_OLLAMA_MODEL=qwen2.5:7b`, or any model Ollama
serves. Nothing in Hito is tied to this particular one.

## How it is wired

Both model backends are called the same way: a system prompt, a user message,
and a **JSON schema the output must satisfy** — Ollama's `format` field and
Claude's `output_config.format` are the same idea. So the backend never parses
prose, never repairs malformed JSON, and the agents' code does not know or care
which engine answered.

The engine is chosen once, in `app/agents/llm.py`, and falls through:

```
local open-source model  (Ollama, if a model is pulled)
        ↓ unavailable, or the call fails
Claude                   (only if ANTHROPIC_API_KEY is set)
        ↓ unavailable, or the call fails
deterministic rule engine  (always there)
```

Pin it with `HITO_LLM_PROVIDER=ollama | claude | rules`. Whatever actually ran
is recorded per call in `agent_runs` and shown in the UI — the header says
`AI: qwen2.5:3b · local`, and the rule engine is never dressed up as a model.

## Setup

```bash
# 1. install Ollama: https://ollama.com/download
#    (winget install Ollama.Ollama  /  brew install ollama)

# 2. pull the model (~2 GB, once)
ollama pull qwen2.5:3b

# 3. nothing else. Hito finds it.
python scripts/check_credentials.py
```

`check_credentials.py` makes a real schema-constrained call and reports the
latency and token counts, so you know it works before you rely on it.

**Judges and anyone who has not installed Ollama** still get a working app:
every agent has a deterministic twin, the flow runs end to end, and the UI
labels the engine honestly as `rule engine`. Nothing dead-ends.

## How well does it actually read a contract?

Not a vibe check — `scripts/eval_parser.py` scores the parser field by field
against three contracts whose correct answers are known:

1. the sample PDF, a tidy list of milestones in `US$3,000` notation
2. a Spanish contract using `US$3.000` and dates written as
   "18 de octubre de 2026", with the fee schedule wrapping across lines
3. an English letter of engagement in **prose**, where the amounts and dates
   are in sentences rather than a list

Eight checks per contract: milestone count, amounts, total, due dates, client
email, collaborator shares, currency, and whether every milestone carries a
verbatim quote from the contract.

```bash
python scripts/eval_parser.py --provider rules
python scripts/eval_parser.py --provider ollama --runs 3
```

### Results

| Engine | Sample PDF | Spanish | Prose | Overall |
| --- | --- | --- | --- | --- |
| Deterministic rule engine | 8/8 | 7/8 | 2/8 | **17/24 (71%)** |
| Qwen2.5 3B (local) | _see below_ | | | |

The rule engine's 8/8 on the sample is flattering and worth being honest
about: those regexes were written against that contract. Its real behaviour is
the other two columns — it survives a different notation and language, and it
collapses on prose, because there is no list to find. That is the gap a model
is for.

<!-- MEASURED -->

## Limitations, stated plainly

A 3B model is not a frontier model, and the places that shows are predictable:

- **Judgment beats extraction.** Pulling a number out of a sentence is easy;
  deciding whether an invoice contradicts a contract clause is not. The
  reviewer agent is the one that benefits most from a larger model — which is
  exactly why its seven blocking checks are deterministic Python, and the model
  can only ever add a HOLD on top. The guardrail does not depend on model
  quality.
- **Arithmetic is never the model's job** here, in any engine. Splits and
  remainders are `Decimal` maths in Python.
- **Latency.** On CPU, reading a contract takes seconds rather than
  milliseconds. The UI shows it working; it is not a hang.
- **Nothing is auto-applied.** Every model output is a proposal a human
  approves — the plan, the invoice, the reminder, the payout. That is the
  design regardless of engine, and it is what makes a small local model a
  reasonable choice rather than a risk.
