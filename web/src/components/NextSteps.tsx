import {
  BanknoteIcon,
  HandCoinsIcon,
  PackageCheckIcon,
  SendIcon,
  ShieldXIcon,
} from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import type { Milestone, Modes } from "@/lib/api"
import { day, money, pct } from "@/lib/format"

/**
 * What needs Laura, in priority order.
 *
 * The dashboard used to be organised by data type - milestones here, invoices
 * there, the model on a third tab - which meant the single most urgent thing
 * (an invoice 14 days late with a 44% chance of never arriving) sat behind a
 * tab, while the most prominent button on its row was a demo shortcut.
 *
 * A product whose promise is "it does the chasing for you" has to open with
 * the decision, not with the ledger. So: the pending decisions, worst first,
 * each with the one action that resolves it, and a plain sentence saying why
 * it matters. Everything else is still there, one tab away, for when she wants
 * to look rather than act.
 */

type Action = {
  key: string
  tone: "urgent" | "money" | "normal"
  icon: React.ReactNode
  headline: React.ReactNode
  detail: string
  cta: string
  onClick: () => void
}

export function NextSteps({
  milestones,
  splitDone,
  modes,
  busyId,
  onDeliver,
  onChase,
  onSplit,
  onPay,
}: {
  milestones: Milestone[]
  splitDone: Set<string>
  modes: Modes
  busyId: string | null
  onDeliver: (m: Milestone) => void
  onChase: (m: Milestone) => void
  onSplit: (m: Milestone) => void
  onPay: (m: Milestone) => void
}) {
  const actions: Action[] = []

  // 1. money that is late - ordered by what it could cost
  const overdue = milestones
    .filter((m) => m.status === "overdue")
    .sort((a, b) => (b.expected_loss ?? 0) - (a.expected_loss ?? 0))
  for (const milestone of overdue) {
    actions.push({
      key: `chase-${milestone.id}`,
      tone: "urgent",
      icon: <SendIcon />,
      headline: (
        <>
          {milestone.client_name} is{" "}
          <strong className="font-semibold">
            {milestone.days_overdue} days late
          </strong>{" "}
          on {money(milestone.amount, milestone.currency)}
        </>
      ),
      detail:
        milestone.pd != null
          ? `${pct(milestone.pd)} chance it never arrives — ${money(
              milestone.expected_loss ?? 0
            )} at risk. Hito will pick the tone and draft the message.`
          : "Hito will score the risk and draft the message.",
      cta: "Chase with tact",
      onClick: () => onChase(milestone),
    })
  }

  // 2. money that arrived and is owed onward
  for (const milestone of milestones.filter(
    (m) => m.status === "paid" && !splitDone.has(m.id)
  )) {
    actions.push({
      key: `split-${milestone.id}`,
      tone: "money",
      icon: <HandCoinsIcon />,
      headline: (
        <>
          {money(milestone.paid_amount ?? milestone.amount, milestone.currency)}{" "}
          arrived for {milestone.title}
        </>
      ),
      detail:
        "Your collaborators are owed their share. Hito works out the amounts; "
        + `anything over ${money(modes.payout_threshold)} waits for your tick.`,
      cta: "Split it",
      onClick: () => onSplit(milestone),
    })
  }

  // 3. work the reviewer stopped
  for (const milestone of milestones.filter((m) => m.status === "blocked")) {
    actions.push({
      key: `blocked-${milestone.id}`,
      tone: "urgent",
      icon: <ShieldXIcon />,
      headline: <>The reviewer blocked the invoice for {milestone.title}</>,
      detail: "Nothing was sent. Open it to see which check failed.",
      cta: "See why",
      onClick: () => onDeliver(milestone),
    })
  }

  // 4. work that is ready to bill
  const billable = milestones.filter(
    (m) => m.status === "pending" || m.status === "delivered"
  )
  for (const milestone of billable.slice(0, 1)) {
    actions.push({
      key: `deliver-${milestone.id}`,
      tone: "normal",
      icon: <PackageCheckIcon />,
      headline: <>{milestone.title} is next to deliver</>,
      detail:
        `${money(milestone.amount, milestone.currency)}, due ${day(
          milestone.due_date
        )}. Say the word and Hito reviews it against the contract, then invoices.`,
      cta: "I delivered this",
      onClick: () => onDeliver(milestone),
    })
  }

  // 5. demo affordance, last and visibly separate
  const awaiting = milestones.filter(
    (m) => m.status === "invoiced" || m.status === "overdue"
  )

  if (actions.length === 0 && awaiting.length === 0) {
    return null
  }

  const shown = actions.slice(0, 3)

  return (
    <section>
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-[15px] font-semibold">
          {shown.length ? "What needs you" : "Nothing needs you right now"}
        </h2>
        <span className="text-[12.5px] text-ink-soft">
          {shown.length
            ? "worst first — everything else is in the tabs below"
            : "Hito is watching for the payment"}
        </span>
      </div>

      {shown.length ? (
        <div className="grid gap-2.5 lg:grid-cols-3">
          {shown.map((action) => (
            <div
              key={action.key}
              className={cn(
                "flex flex-col justify-between rounded-lg border bg-card p-3.5 shadow-card",
                action.tone === "urgent"
                  ? "border-amber/45 bg-amber-soft/30"
                  : action.tone === "money"
                    ? "border-green/35 bg-green-soft/30"
                    : "border-rule"
              )}
            >
              <div>
                <div
                  className={cn(
                    "mb-1 flex items-center gap-1.5 text-[10.5px] font-semibold tracking-[0.08em] uppercase",
                    action.tone === "urgent"
                      ? "text-amber"
                      : action.tone === "money"
                        ? "text-green"
                        : "text-ink-faint"
                  )}
                >
                  {action.icon}
                  {action.tone === "urgent"
                    ? "Needs a decision"
                    : action.tone === "money"
                      ? "Money to pass on"
                      : "Ready when you are"}
                </div>
                <p className="text-[13.5px] leading-snug">{action.headline}</p>
                <p className="mt-1 text-[12px] leading-snug text-ink-soft">
                  {action.detail}
                </p>
              </div>
              <Button
                className="mt-3 w-full"
                size="sm"
                variant={action.tone === "normal" ? "outline" : "default"}
                disabled={busyId !== null}
                onClick={action.onClick}
              >
                {action.cta}
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {awaiting.length ? (
        <p className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-faint">
          <span>
            Waiting on {awaiting.length} invoice
            {awaiting.length > 1 ? "s" : ""}. In the real world the PayPal
            webhook tells Hito the moment a client pays.
          </span>
          <Button
            variant="ghost"
            size="xs"
            disabled={busyId !== null}
            onClick={() => onPay(awaiting[0])}
            className="text-ink-soft"
          >
            <BanknoteIcon />
            Demo: pretend {awaiting[0].client_name} just paid
          </Button>
        </p>
      ) : null}
    </section>
  )
}
