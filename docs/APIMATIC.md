# APIMatic: SDKs and a docs portal for the Hito API

Hito's API is the product; the web UI and the MCP server are two clients of it.
So the spec is generated from the running app rather than hand-written, and
APIMatic turns that spec into SDKs and a portal.

## 1. Generate the spec

```bash
python scripts/export_openapi.py
# wrote docs/openapi.json (20 paths, 20 operations)
```

`scripts/export_openapi.py` takes FastAPI's own `app.openapi()` — so the schemas
come from the real Pydantic models and cannot drift from the code — then adds
the things a generated spec does not know: the product description, the two
guardrails that are part of the API contract, servers, and tags grouping the
operations the way the product thinks about them (Contracts, Invoicing,
Payments, Collections, Payouts, Risk, Dashboard, Demo).

The result is OpenAPI 3.1, `docs/openapi.json`, committed.

## 2. Import it into APIMatic

1. Sign in at <https://www.apimatic.io/> and create an API entity.
2. **Import** → upload `docs/openapi.json`.
3. Run **API Validation**. The spec validates clean; the tags above become the
   sections of the portal.
4. **Code Generation** → pick the SDKs you want (Python, TypeScript, Java, C#,
   Go, PHP…). Each one wraps the same five moments:
   `parseContract` → `approvePlan` → `deliverMilestone` → `draftDunning` →
   `proposePayout` / `approvePayout`.
5. **Portal** → publish. The hosted portal gives every endpoint a try-it
   console and code samples in every generated language.

## 3. Regenerate after any API change

```bash
python scripts/export_openapi.py && git add docs/openapi.json
```

Re-upload and APIMatic re-generates the SDKs and the portal.

## Why the spec is worth reading

Two rules that usually live in a UI are in the API contract here, and the
description says so, so a generated SDK carries them:

- `POST /api/milestones/{milestone_id}/deliver` returns `stage` — `"blocked"`
  (nothing created), `"hold"` (needs a human to re-send with `override: true`),
  or `"invoiced"`. The full reviewer verdict, every check and the quoted
  contract clause come back in the same response.
- `POST /api/payouts/{payout_id}/approve` only sends items above
  `PAYOUT_APPROVAL_THRESHOLD_USD` when their ids are listed in
  `approved_item_ids`; the response reports `sent` and `held` separately.

`GET /api/status` always reports which PayPal gateway and which AI engine are
live, so a client never has to guess whether it is talking to the sandbox or
the in-process mock.
