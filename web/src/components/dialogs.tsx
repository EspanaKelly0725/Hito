import { useEffect, useState } from "react"
import {
  AlertTriangleIcon,
  CheckIcon,
  ExternalLinkIcon,
  SendIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  ShieldXIcon,
  XIcon,
} from "lucide-react"
import { cn } from "cn"

import { BandBadge, EngineBadge, RiskMeter } from "@/components/bits"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import type { DeliverResult, DunningDraft, PayoutProposal } from "@/lib/api"
import { TONE_LABEL, day, money, pct } from "@/lib/format"

/* -------------------------------------------------------------------------- */
/*  The reviewer's verdict                                                     */
/* -------------------------------------------------------------------------- */

export function ReviewDialog({
  result,
  onClose,
  onOverride,
  overriding,
}: {
  result: DeliverResult | null
  onClose: () => void
  onOverride: () => void
  overriding: boolean
}) {
  if (!result) return null
  const { review, invoice, stage } = result

  const tone = {
    approve: {
      icon: <ShieldCheckIcon className="size-4" />,
      label: "Approved",
      className: "bg-green-soft text-green",
    },
    hold: {
      icon: <ShieldAlertIcon className="size-4" />,
      label: "Held for your call",
      className: "bg-amber-soft text-amber",
    },
    block: {
      icon: <ShieldXIcon className="size-4" />,
      label: "Blocked",
      className: "bg-red-soft text-red",
    },
  }[review.verdict]

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-[12px] font-semibold",
                tone.className
              )}
            >
              {tone.icon} {tone.label}
            </span>
            <EngineBadge
              engine={review._meta?.engine}
              model={review._meta?.model}
              note={review._meta?.note}
            />
          </div>
          <DialogTitle className="mt-2 font-heading">
            Second reviewer on {money(review.amount, review.currency)}
          </DialogTitle>
          <DialogDescription>{review.headline}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[52vh] space-y-4 overflow-y-auto pr-1">
          <div>
            <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
              Deterministic checks
            </div>
            <ul className="divide-y divide-rule rounded-md border border-rule">
              {review.checks.map((check) => (
                <li
                  key={check.name}
                  className="flex items-start gap-2 px-3 py-2 text-[12.5px]"
                >
                  {check.pass ? (
                    <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-green" />
                  ) : (
                    <XIcon
                      className={cn(
                        "mt-0.5 size-3.5 shrink-0",
                        check.blocking ? "text-red" : "text-amber"
                      )}
                    />
                  )}
                  <div className="min-w-0">
                    <span className="font-mono text-[11.5px] text-ink-soft">
                      {check.name}
                    </span>
                    <div className="text-ink">{check.detail}</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {review.contract_evidence ? (
            <div>
              <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
                What the contract says
              </div>
              <blockquote className="border-l-2 border-teal bg-teal-soft/40 px-3 py-2 text-[12.5px] italic">
                “{review.contract_evidence}”
              </blockquote>
            </div>
          ) : null}

          {review.findings.length ? (
            <div>
              <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
                Reviewer notes
              </div>
              <ul className="space-y-1.5">
                {review.findings.map((finding, index) => (
                  <li
                    key={`${finding.check}-${index}`}
                    className="flex items-start gap-2 text-[12.5px]"
                  >
                    <Badge
                      className={cn(
                        "mt-0.5 shrink-0 rounded-sm border-transparent",
                        finding.severity === "critical"
                          ? "bg-red-soft text-red"
                          : finding.severity === "warning"
                            ? "bg-amber-soft text-amber"
                            : "bg-secondary text-ink-soft"
                      )}
                    >
                      {finding.severity}
                    </Badge>
                    <span>{finding.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {invoice ? (
            <div className="rounded-md border border-rule bg-background px-3 py-2.5">
              <div className="text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
                Sent through PayPal
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[13px]">
                  {invoice.number} · {money(invoice.amount, review.currency)} ·{" "}
                  {invoice.status}
                </span>
                {invoice.view_url ? (
                  <a
                    className="inline-flex items-center gap-1 text-[12.5px] text-teal hover:underline"
                    href={invoice.view_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open the invoice <ExternalLinkIcon className="size-3" />
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          {stage === "hold" ? (
            <>
              <Button variant="ghost" onClick={onClose}>
                Leave it held
              </Button>
              <Button
                variant="outline"
                disabled={overriding}
                onClick={onOverride}
              >
                <AlertTriangleIcon /> Override and invoice anyway
              </Button>
            </>
          ) : (
            <Button onClick={onClose}>Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* -------------------------------------------------------------------------- */
/*  The collection message                                                     */
/* -------------------------------------------------------------------------- */

export function DunningDialog({
  draft,
  onClose,
  onSend,
  sending,
}: {
  draft: DunningDraft | null
  onClose: () => void
  onSend: (subject: string, body: string) => void
  sending: boolean
}) {
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")

  useEffect(() => {
    if (draft) {
      setSubject(draft.message.subject)
      setBody(draft.message.body)
    }
  }, [draft])

  if (!draft) return null
  const { risk, message, history } = draft

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <BandBadge band={risk.band} />
            <Badge variant="outline" className="rounded-sm border-rule">
              {TONE_LABEL[risk.tone] ?? risk.tone}
            </Badge>
            <EngineBadge
              engine={message._meta?.engine}
              model={message._meta?.model}
              note={message._meta?.note}
            />
          </div>
          <DialogTitle className="mt-2 font-heading">
            The risk model picked the tone. You pick whether it goes.
          </DialogTitle>
          <DialogDescription>{message.rationale}</DialogDescription>
        </DialogHeader>

        <div className="grid max-h-[56vh] gap-4 overflow-y-auto pr-1 md:grid-cols-[260px_1fr]">
          <div className="space-y-3">
            <div className="rounded-md border border-rule bg-background p-3">
              <RiskMeter pd={risk.pd} band={risk.band} cutoffs={risk.cutoffs} />
              <Separator className="my-2.5" />
              <dl className="space-y-1 text-[12px]">
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Expected loss</dt>
                  <dd className="tabular font-medium">
                    {money(risk.expected_loss)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Days overdue</dt>
                  <dd className="tabular">{risk.days_overdue ?? 0}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Invoices settled</dt>
                  <dd className="tabular">{history.invoices_settled}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Paid late</dt>
                  <dd className="tabular">{pct(history.late_ratio)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Avg days late</dt>
                  <dd className="tabular">{history.avg_days_late}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-md border border-rule bg-background p-3">
              <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
                What moved the score
              </div>
              <ul className="space-y-1.5">
                {risk.factors.slice(0, 4).map((factor) => (
                  <li key={factor.feature} className="text-[11.5px]">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-ink-soft">{factor.label}</span>
                      <span
                        className={cn(
                          "tabular shrink-0 font-mono",
                          factor.direction === "raises" ? "text-red" : "text-green"
                        )}
                      >
                        {factor.logit_contribution > 0 ? "+" : ""}
                        {factor.logit_contribution.toFixed(2)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {message.offer_terms ? (
              <div className="rounded-md border border-amber/40 bg-amber-soft/40 p-3 text-[12px]">
                <div className="mb-1 font-semibold text-amber">
                  Payment plan offered
                </div>
                {money(message.offer_terms.first)} by{" "}
                {day(message.offer_terms.first_date)}, then{" "}
                {money(message.offer_terms.second)} by{" "}
                {day(message.offer_terms.second_date)}.
              </div>
            ) : null}
          </div>

          <div className="space-y-3">
            <div>
              <Label htmlFor="dunning-subject" className="text-[12px]">
                Subject
              </Label>
              <Input
                id="dunning-subject"
                className="mt-1 border-rule"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="dunning-body" className="text-[12px]">
                Message — edit anything before it goes
              </Label>
              <Textarea
                id="dunning-body"
                className="mt-1 min-h-[260px] border-rule font-sans text-[13px] leading-relaxed"
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
            </div>
            <p className="text-[11.5px] text-ink-faint">
              Goes out as a PayPal invoice reminder, so the payment link is
              attached to the message. Next step if there is no reply:{" "}
              {message.escalation_suggestion}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Not yet
          </Button>
          <Button disabled={sending} onClick={() => onSend(subject, body)}>
            <SendIcon /> Send it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* -------------------------------------------------------------------------- */
/*  The split                                                                  */
/* -------------------------------------------------------------------------- */

export function PayoutDialog({
  proposal,
  onClose,
  onApprove,
  sending,
}: {
  proposal: PayoutProposal | null
  onClose: () => void
  onApprove: (approvedItemIds: string[]) => void
  sending: boolean
}) {
  const [approved, setApproved] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setApproved({})
  }, [proposal?.payout_id])

  if (!proposal) return null

  const toSend = proposal.items.filter(
    (item) => !item.needs_approval || approved[item.id]
  )
  const total = toSend.reduce((sum, item) => sum + item.amount, 0)

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-heading">
            Split {money(proposal.paid_amount, proposal.currency)}
          </DialogTitle>
          <DialogDescription>{proposal.rationale}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          {proposal.items.map((item) => {
            const needs = Boolean(item.needs_approval)
            const ticked = !needs || approved[item.id]
            return (
              <div
                key={item.id}
                className={cn(
                  "flex items-start gap-3 rounded-md border px-3 py-2.5",
                  needs && !ticked
                    ? "border-amber/50 bg-amber-soft/30"
                    : "border-rule bg-background"
                )}
              >
                <Checkbox
                  className="mt-0.5"
                  checked={ticked}
                  disabled={!needs}
                  onCheckedChange={(value: boolean) =>
                    setApproved((prev) => ({ ...prev, [item.id]: Boolean(value) }))
                  }
                  aria-label={`Approve the payout to ${item.name}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium">
                      {item.name}{" "}
                      <span className="text-[12px] font-normal text-ink-faint">
                        {item.role} · {item.pct}%
                      </span>
                    </span>
                    <span className="tabular font-heading text-[15px]">
                      {money(item.amount, proposal.currency)}
                    </span>
                  </div>
                  <div className="truncate text-[11.5px] text-ink-faint">
                    {item.email}
                  </div>
                  {item.note ? (
                    <div className="mt-1 text-[12px] text-ink-soft italic">
                      “{item.note}”
                    </div>
                  ) : null}
                  {needs ? (
                    <div className="mt-1 inline-flex items-center gap-1 text-[11.5px] font-medium text-amber">
                      <AlertTriangleIcon className="size-3" />
                      Above the {money(proposal.threshold)} ceiling — needs your tick
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>

        <div className="flex items-center justify-between rounded-md bg-secondary px-3 py-2 text-[12.5px]">
          <span className="text-ink-soft">
            You keep {money(proposal.retained, proposal.currency)}
          </span>
          <span className="tabular font-medium">
            Sending {money(total, proposal.currency)} to {toSend.length} of{" "}
            {proposal.items.length}
          </span>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={sending || toSend.length === 0}
            onClick={() =>
              onApprove(
                proposal.items
                  .filter((item) => approved[item.id])
                  .map((item) => item.id)
              )
            }
          >
            <SendIcon /> Approve and send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
