# Hito as an MCP server

Hito's whole flow is exposed over the Model Context Protocol, so any
MCP-speaking agent — Claude Desktop, Claude Code, your own — can run a
freelancer's billing: read the contract, invoice a milestone through PayPal,
score the risk, draft the reminder, propose the split.

The server is `app/mcp_server.py`. It has **no dependencies**: MCP stdio
transport is newline-delimited JSON-RPC 2.0, which is what the file implements.

```bash
python -m app.mcp_server
# hito mcp server ready | paypal=mock | ai=rule-based fallback | 11 tools
```

## Claude Desktop

Add this to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "hito": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/hito"
    }
  }
}
```

Restart Claude Desktop. The tools appear under the connector icon. Credentials
come from the same `.env` the web app uses, so with PayPal configured the agent
sends real sandbox invoices.

## Claude Code

```bash
claude mcp add hito -- python -m app.mcp_server
```

## The tools

| Tool | What it does |
| --- | --- |
| `read_contract` | Contract text in, payment plan out. Creates nothing. |
| `approve_plan` | Records an approved plan as a project. The only way a project comes into being. |
| `list_milestones` | Every milestone with state, invoice, and current risk. |
| `invoice_milestone` | Delivers and invoices through PayPal — **after** the reviewer clears it. |
| `score_risk` | Probability of non-payment, the factors behind it, the tone band. |
| `draft_reminder` | Drafts the collection message in the register the risk picked. |
| `send_reminder` | Sends it. Contacts the client, so it needs human approval first. |
| `propose_split` | Exact-cent split, with items above the ceiling flagged. |
| `send_payout` | Sends the payout through PayPal Payouts. |
| `explain_risk_model` | The model card: weights, metrics, cut-offs, tone policy. |
| `audit_trail` | Who decided what, agent vs human. |

## The guardrails hold over MCP too

This is the point of exposing it this way. The rules are enforced in the
service, not in the web UI, so an agent driving Hito gets exactly the same
treatment a human does:

- **`invoice_milestone`** runs the independent reviewer before PayPal is
  called. A deterministic failure returns `stage: "blocked"` and creates
  nothing. A model objection returns `stage: "hold"`, and only a call with
  `override: true` proceeds — which the server instructions tell the agent must
  come from the human, not from its own judgment.
- **`send_payout`** will not send an item flagged `needs_approval` unless its
  id appears in `approved_item_ids`. Calling it with an empty list when every
  item is flagged returns an error rather than quietly sending nothing — or,
  worse, quietly sending everything.

Both are covered by tests:

```bash
python -m pytest tests/test_mcp.py -q
```

`test_the_full_loop_over_mcp_keeps_the_payout_ceiling` drives the entire flow
through the protocol and asserts the payout is refused until the flagged item
is explicitly approved.

## Talking to it by hand

```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python -m app.mcp_server
```
