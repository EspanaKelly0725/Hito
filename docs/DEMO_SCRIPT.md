# Demo video script — 2:45

Judging weighs **Presentation** on whether the video shows the project working
end to end, and whether the pitch says what problem is solved, for whom, and
why it matters. So: no slides, no logo animation, no talking head. Screen
recording with voice-over, the product doing the thing.

**Before you record**

```bash
cp .env.example .env            # fill in PayPal sandbox + ANTHROPIC_API_KEY
python scripts/check_credentials.py   # must print OK for PayPal and Claude
uvicorn app.main:app
```

Then, in this order — it matters:

1. **⌘K → Reset everything.**
2. **Use the sample contract.**
3. On the approval screen, set **Client — invoices go here** to your sandbox
   **buyer** address. The contract's own address is a placeholder and PayPal
   will deliver the invoice nowhere; the UI warns you about this in amber.
4. **Approve this plan.**
5. **⌘K → Seed this client's payment history.** Do it *after* approving, so the
   history is seeded against the sandbox buyer's address — the risk model looks
   history up by email, and against a client it has never seen it will
   correctly report low risk and pick a friendly tone, which is not the story
   you want to tell.

Browser at ~1440px wide, zoom 110%, light mode. Have a second tab open on the
PayPal sandbox inbox of the *buyer* account — showing the real invoice land
there is the single most convincing second of the video.

> Verified against the real sandbox on 11 Nov 2026: OAuth2, invoice-number
> generation, invoice create, invoice send, the payer-view link, the reminder
> call and a Payouts batch all work end to end. The only path that needs extra
> setup is webhook signature verification, which needs a public tunnel and
> `PAYPAL_WEBHOOK_ID`; without it the demo uses **Simulate payment**, which
> goes through exactly the same code path as the webhook.

---

### 0:00 – 0:22 · The problem, in her words

> *"This is Laura. She is a designer in Medellín, and a client in Texas is
> paying her nine thousand dollars for a brand, in three parts. She works with
> two friends who get a cut of each payment."*
>
> *"Today she reads the contract, makes each PayPal invoice by hand, checks
> whether the money came in, writes the awkward 'hi, just a reminder' when it
> doesn't, and transfers her friends their share at the end. The invoicing is
> tedious. The chasing is worse — it's an emotional task, done by the person
> who is owed, so it gets delayed, softened, and ignored."*

On screen: the empty Hito dashboard, then drag the contract PDF in.

### 0:22 – 0:52 · It reads the contract

> *"Hito reads the contract. Three deliverables, three thousand dollars each,
> with the due dates — and behind every line, the sentence in the contract it
> came from, because Laura has to approve this and 'trust me' isn't an
> approval. It also flags what's vague: there's no real late-payment clause and
> revisions are unlimited."*

On screen: the plan grid filling in, the quoted clauses column, the warnings
box. Click one amount cell to show it is editable. Click **Approve this plan**.

### 0:52 – 1:25 · It invoices — but not alone

> *"She delivers the logo. Before anything is sent, a second reviewer checks
> the invoice against the contract — seven deterministic checks in code, plus a
> separate Claude pass that reads the contract and asks a different question:
> does this invoice match what the client agreed to pay for?"*

Click **I delivered this**. The review dialog opens.

> *"Both agree, so the invoice goes out."*

Switch to the PayPal sandbox buyer inbox. **Show the real invoice.**

> *"That's a real PayPal invoice, in the sandbox."*

*(If you have 10 spare seconds: before approving the plan, change one milestone
to $4,500, deliver it, and show the reviewer blocking it and quoting the line
that says three thousand. It is the strongest 10 seconds in the video.)*

### 1:25 – 1:55 · The client is late

> *"The second invoice goes past due. Here's the part Laura hates."*

Open **Invoices & risk**.

> *"Hito scores how likely it is that this one never gets paid. Forty-four
> percent — and that number isn't a vibe, it's a logistic regression fitted on
> this client's actual payment history: three invoices settled, one of them two
> weeks late. That score picks the tone. Not Laura's mood on a Tuesday."*

Click **Chase with tact**.

> *"Forty-four percent lands in the middle band, so it writes a firm reminder —
> names the amount, names a date, cites the clause. Under twenty-four percent
> it would be a friendly nudge. Over fifty-two, it would offer to split the
> balance in two rather than keep sending reminders."*

Scrub the **Days past due** slider on the **Model** tab for two seconds and let
the tone flip. Then **Send it**.

### 1:55 – 2:20 · It splits the money

> *"The first payment arrived, so Hito proposes the split: thirty percent to
> the developer, twenty to the illustrator. The amounts are computed in code,
> not by the model — the model only writes the note."*
>
> *"And the developer's nine hundred dollars is above Laura's approval ceiling,
> so Hito will not send it on its own. She ticks that one line. Then it goes
> through PayPal Payouts."*

On screen: the payout dialog with one item amber and unticked. Tick it. Send.

### 2:20 – 2:45 · Why it holds up

Open the **Audit trail** tab.

> *"Every decision is in one ledger, and it says who made it — the agent, or
> Laura. Beside it, every model call with its tokens and its cost."*
>
> *"The same flow runs as an MCP server, so any agent can drive it — with the
> same guardrails, because they live in the service, not in the screen."*
>
> *"Hito doesn't make Laura braver about asking for her money. It makes the
> asking a consequence of the risk."*

---

### Checklist before uploading

- [ ] Under 3:00 (judges are not required to watch past that)
- [ ] The PayPal sandbox invoice is visible on screen at least once
- [ ] The reviewer dialog is visible at least once
- [ ] The risk number and the tone it chose are on screen together
- [ ] The approval ceiling blocking a payout is visible
- [ ] No third-party trademarks or copyrighted music
- [ ] Uploaded to YouTube, **public**, link on the submission form
