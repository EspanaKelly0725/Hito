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
local open-source model     (Ollama, if a model is pulled)
        ↓ unavailable, or the call fails
same open weights, hosted   (any OpenAI-compatible endpoint, if configured)
        ↓ unavailable, or the call fails
Claude                      (only if ANTHROPIC_API_KEY is set)
        ↓ unavailable, or the call fails
deterministic rule engine   (always there)
```

Local is first on purpose: it is the privacy promise, not an accident of
ordering. There is a test that asserts it.

Pin one with `HITO_LLM_PROVIDER=ollama | remote | claude | rules`.

### Why there is a hosted tier at all

A 2 GB model does not fit a free hosting instance, and the demo at
<https://hito-zz3z.onrender.com> would otherwise show a rule engine to anyone
who only clicks the link. So that deployment serves an open-weights model
through an OpenAI-compatible endpoint instead:

```bash
HITO_REMOTE_BASE_URL=https://openrouter.ai/api/v1
HITO_REMOTE_API_KEY=sk-or-...
HITO_REMOTE_MODEL=baidu/ernie-5.5-flash-preview:free
```

Any OpenAI-compatible endpoint works — OpenRouter, Groq, Together, your own
vLLM. If the endpoint rejects a full JSON schema, the backend degrades to plain
JSON mode with the schema in the prompt rather than failing.

### Why the hosted demo is not running Qwen2.5

Plainly: **there is no budget for paid inference.** Qwen2.5 costs nothing to
run on your own hardware, which is the entire point of choosing it — but
having a provider serve it is metered, and this is a hackathon project with no
funding behind it. The cheapest Apache-2.0 Qwen on OpenRouter is about
$0.0003 per full pass through the demo, which is almost nothing and still more
than zero, and paying for it needs a minimum credit top-up.

So the hosted tier runs a **free** open-weights model instead. It is a
different model from the one Hito is built around, and the README and the UI
say so rather than letting the header imply otherwise.

Two things make that an acceptable trade rather than a hole:

1. **The engine is one environment variable.** Nothing in Hito is coupled to a
   particular model — all four agents go through one wrapper and one JSON
   schema. Give the deployment a budget and `HITO_REMOTE_MODEL=qwen/qwen3-32b`
   is the whole change.
2. **The real engine is one command away**, and a judge can check it in
   minutes rather than taking our word for it:

   ```bash
   ollama pull qwen2.5:3b
   uvicorn app.main:app              # header now reads qwen2.5:3b | local
   python scripts/eval_parser.py --provider ollama
   ```

### Which free model, and how it was picked

By measurement, not by reading the catalogue. Nine free models on OpenRouter
advertise JSON-schema support; most of them returned text that would not parse,
and the one chosen first by reputation returned empty content on a real
contract because it is a reasoning model that spent its whole token budget
thinking. (The backend now disables reasoning where the endpoint allows it,
salvages an answer out of the reasoning trace when it does not, and reports the
finish reason when it still comes back empty.)

Two survived a real run:

| Free model | Score | Median latency | Note |
| --- | --- | --- | --- |
| `baidu/ernie-5.5-flash-preview:free` | **22/24** | 16.5 s | all three contracts ran on the model |
| `liquid/lfm-2.5-2.6b:free` | 22/24 | 5.1 s | one call in three failed outright |

ERNIE is the default: for a demo a judge opens, a call that fails is worse than
a call that takes eleven seconds longer. LFM is the faster alternative if you
are willing to accept the misses.

### Hosted vs local, measured the same way

| | Local — Qwen2.5 3B | Hosted — ERNIE 5.5 flash (free) |
| --- | --- | --- |
| Sample PDF | 8/8 | 7/8 |
| Spanish, `US$3.000`, dates in words | 8/8 | 7/8 |
| **Prose, no list** | **8/8** | **8/8** |
| Overall | **24/24** | 22/24 |
| Median latency | 55 s (laptop CPU) | 16.5 s |
| Cost | none | none |
| Contract leaves the machine | no | **yes** |

The local model is more accurate and completely private; the hosted one is
faster because it is not running on a thin laptop. Both clear the bar that
matters — 8/8 on the prose contract, where a regex gets 2/8.

Reproduce either:

```bash
python scripts/eval_parser.py --provider ollama
python scripts/eval_parser.py --provider remote
```

### What the hosted tier gives up

The contract leaves the machine. That is the price of a demo anyone can click,
and it is exactly why the local tier is the default and goes first in the
chain. Run Hito on your own laptop and nothing is transmitted at all. Whatever actually ran
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
| Deterministic rule engine | 8/8 | 7/8 | **2/8** | 17/24 (71%) |
| **Qwen2.5 3B (local)** | 8/8 | 8/8 | **8/8** | **24/24 (100%)** |

Measured on 11 Nov 2026, on the reference machine: Intel Core Ultra 5 125U,
16 GB RAM, integrated graphics, Ollama 0.40.16, `qwen2.5:3b` at Q4_K_M.

The rule engine's 8/8 on the sample is flattering and worth being honest
about: those regexes were written against that contract. Its real behaviour is
the other two columns — it survives a different notation and language, and it
collapses on prose, because there is no list to find and the amounts live in
sentences. **That column is the entire argument for having a model**, and it is
where 2/8 became 8/8.

The Spanish contract is the quieter result. The rule engine missed only the
dates, because the fee schedule wrapped mid-sentence —
`"US$3.000, con fecha 18 de\noctubre de 2026"` — and a line-oriented regex
cannot see across the break. A model reads the sentence.

### What it costs in time

| | Sample PDF | Spanish | Prose |
| --- | --- | --- | --- |
| Wall clock | 74.1 s | 55.5 s | 31.6 s |
| Output tokens | 642 | 589 | 353 |

Roughly a minute to read a contract, on a CPU, scaling with how much JSON it
has to write. That is the honest trade for this hardware: the rule engine is
instant and wrong on prose; the model is right and takes a minute. Reading a
contract happens once per project and the UI shows it working, so a minute is
affordable in a way it would not be on a per-keystroke path.

If a minute is too long for your machine or your demo:

- `HITO_OLLAMA_MODEL=qwen2.5:1.5b` roughly halves it, with a real accuracy cost
  on prose — re-run the benchmark before trusting it.
- Any GPU changes the picture entirely; this measurement is a laptop CPU floor,
  not a ceiling.
- `HITO_LLM_PROVIDER=claude` with a key is the fast path, at the cost of
  sending the contract to a third party.

Reproduce all of it:

```bash
python scripts/eval_parser.py --provider rules
python scripts/eval_parser.py --provider ollama
```

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
