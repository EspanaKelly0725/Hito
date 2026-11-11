import { useCallback, useEffect, useState } from "react"
import { useTheme } from "next-themes"
import { toast } from "sonner"
import {
  BotIcon,
  CommandIcon,
  DatabaseZapIcon,
  MoonIcon,
  RotateCcwIcon,
  SunIcon,
} from "lucide-react"

import { Kpi, ModeBadges, SectionTitle } from "@/components/bits"
import { CommandMenu } from "@/components/CommandMenu"
import { ContractStep } from "@/components/ContractStep"
import { DunningDialog, PayoutDialog, ReviewDialog } from "@/components/dialogs"
import {
  AgentRunsGrid,
  EventsGrid,
  InvoicesGrid,
  MilestonesGrid,
} from "@/components/grids"
import { RiskPanel } from "@/components/RiskPanel"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  api,
  type Dashboard,
  type DeliverResult,
  type DunningDraft,
  type Invoice,
  type Milestone,
  type PayoutProposal,
} from "@/lib/api"
import { money } from "@/lib/format"

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [review, setReview] = useState<DeliverResult | null>(null)
  const [reviewMilestone, setReviewMilestone] = useState<Milestone | null>(null)
  const [dunning, setDunning] = useState<DunningDraft | null>(null)
  const [payout, setPayout] = useState<PayoutProposal | null>(null)
  const [sending, setSending] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const { theme, setTheme } = useTheme()

  const refresh = useCallback(async () => {
    try {
      setData(await api.dashboard())
    } catch (error) {
      toast.error("Could not reach the Hito API", {
        description: error instanceof Error ? error.message : String(error),
      })
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const failed = (error: unknown, title: string) =>
    toast.error(title, {
      description: error instanceof Error ? error.message : String(error),
    })

  /**
   * On a local open-source model an agent takes the better part of a minute.
   * A disabled button is not enough feedback for that, so every long call says
   * what it is doing and on what, and the result replaces the same toast.
   */
  const working = (message: string) =>
    toast.loading(message, {
      description: data?.modes.ai_local
        ? `Running ${data.modes.ai} on this machine — about a minute.`
        : undefined,
      duration: Infinity,
    })

  /* ---- actions -------------------------------------------------------- */

  async function deliver(milestone: Milestone, override = false) {
    setBusyId(milestone.id)
    const toastId = working("The reviewer is checking this against the contract…")
    try {
      const result = await api.deliver(
        milestone.id,
        milestone.evidence || "Delivered and handed over to the client.",
        override
      )
      setReview(result)
      setReviewMilestone(milestone)
      if (result.stage === "invoiced" && result.invoice) {
        toast.success(`Invoice ${result.invoice.number} sent`, {
          id: toastId,
          description: `${money(result.invoice.amount)} to the client through PayPal (${result.invoice.gateway}).`,
        })
      } else if (result.stage === "hold") {
        toast.warning("The reviewer held this invoice", {
          id: toastId,
          description: result.review.headline,
        })
      } else {
        toast.error("The reviewer blocked this invoice", {
          id: toastId,
          description: result.review.headline,
        })
      }
      await refresh()
    } catch (error) {
      toast.dismiss(toastId)
      failed(error, "Could not invoice this milestone")
    } finally {
      setBusyId(null)
    }
  }

  async function pay(milestone: Milestone) {
    setBusyId(milestone.id)
    try {
      await api.simulatePayment(milestone.id)
      toast.success("Payment received", {
        description: `${money(milestone.amount, milestone.currency)} for ${milestone.title}.`,
      })
      await refresh()
    } catch (error) {
      failed(error, "Could not record the payment")
    } finally {
      setBusyId(null)
    }
  }

  async function chase(milestoneId: string) {
    setBusyId(milestoneId)
    const toastId = working("Scoring the risk and writing the reminder…")
    try {
      const draft = await api.draftDunning(milestoneId)
      setDunning(draft)
      toast.success(`Drafted a ${draft.risk.tone.replace("_", " ")} reminder`, {
        id: toastId,
        description: `The risk model put this at ${Math.round(draft.risk.pd * 100)}% — ${draft.risk.band} risk.`,
      })
    } catch (error) {
      toast.dismiss(toastId)
      failed(error, "Could not draft the reminder")
    } finally {
      setBusyId(null)
    }
  }

  async function sendDunning(subject: string, body: string) {
    if (!dunning) return
    setSending(true)
    try {
      const result = await api.sendDunning(dunning.dunning_id, subject, body)
      toast.success("Reminder sent", { description: `Delivered via ${result.channel}.` })
      setDunning(null)
      await refresh()
    } catch (error) {
      failed(error, "Could not send the reminder")
    } finally {
      setSending(false)
    }
  }

  async function split(milestone: Milestone) {
    setBusyId(milestone.id)
    const toastId = working("Working out everyone's share…")
    try {
      const proposal = await api.proposePayout(milestone.id)
      setPayout(proposal)
      toast.success(`Split into ${proposal.items.length} payouts`, {
        id: toastId,
        description: proposal.needs_approval
          ? "One item is above your ceiling and needs your tick."
          : "All under your approval ceiling.",
      })
    } catch (error) {
      toast.dismiss(toastId)
      failed(error, "Could not propose the split")
    } finally {
      setBusyId(null)
    }
  }

  async function approvePayout(approvedItemIds: string[]) {
    if (!payout) return
    setSending(true)
    try {
      const result = await api.approvePayout(payout.payout_id, approvedItemIds)
      toast.success(`Payout ${result.batch_status}`, {
        description:
          `${result.sent.length} item(s) sent via PayPal Payouts` +
          (result.held.length ? `, ${result.held.length} held for approval.` : "."),
      })
      setPayout(null)
      await refresh()
    } catch (error) {
      failed(error, "Could not send the payout")
    } finally {
      setSending(false)
    }
  }

  async function seed(clientEmail?: string) {
    try {
      const result = await api.seedDemo(clientEmail)
      toast.success("Client history seeded", {
        description: `${result.history.invoices_settled} past invoices for ${result.client_email}, ${Math.round(result.history.late_ratio * 100)}% paid late. The risk model reads this.`,
      })
      await refresh()
    } catch (error) {
      failed(error, "Could not seed the demo")
    }
  }

  async function refreshPayout(payoutId: string) {
    try {
      const result = await api.refreshPayout(payoutId)
      toast.success(`PayPal reports the batch as ${result.batch_status}`)
      await refresh()
    } catch (error) {
      failed(error, "Could not refresh the payout")
    }
  }

  async function reset() {
    try {
      await api.resetDemo()
      toast.success("Everything cleared")
      await refresh()
    } catch (error) {
      failed(error, "Could not reset")
    }
  }

  /* ---- derived -------------------------------------------------------- */

  const milestones = (data?.milestones ?? []).filter((m) => !m.historical)
  const activeProject = (data?.projects ?? []).find((p) => p.status !== "closed")
  const splitDone = new Set((data?.payouts ?? []).map((p) => p.milestone_id))
  const isDark = theme === "dark"

  return (
    <div className="relative z-10 min-h-screen">
      <header className="sticky top-0 z-30 border-b border-rule bg-paper/85 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-3 px-5 py-2.5">
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-[17px] font-semibold tracking-tight">
              Hito
            </span>
            <span className="hidden text-[12.5px] text-ink-soft sm:inline">
              contract to cash, without the chasing
            </span>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            {data ? <ModeBadges modes={data.modes} /> : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCommandOpen(true)}
              className="gap-1.5 font-mono text-[11.5px]"
            >
              <CommandIcon className="size-3" />K
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Toggle theme"
              onClick={() => setTheme(isDark ? "light" : "dark")}
            >
              {isDark ? <SunIcon /> : <MoonIcon />}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1240px] space-y-7 px-5 py-6">
        {data && milestones.length > 0 ? (
          <section>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <Kpi label="Contracted" value={data.totals.contracted} />
              <Kpi label="Invoiced" value={data.totals.invoiced} tone="accent" />
              <Kpi
                label="Collected"
                value={data.totals.collected}
                tone="in"
                footnote={activeProject ? `from ${activeProject.client_name}` : undefined}
              />
              <Kpi
                label="Outstanding"
                value={data.totals.outstanding}
                footnote={
                  data.totals.overdue > 0
                    ? `${money(data.totals.overdue)} of it overdue`
                    : "nothing overdue"
                }
              />
              <Kpi
                label="Expected loss"
                value={data.totals.at_risk}
                tone="risk"
                footnote="probability-weighted, by the risk model"
              />
            </div>
          </section>
        ) : null}

        {!data || milestones.length === 0 ? (
          <>
            <ContractStep onApproved={refresh} />
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-rule bg-card px-3.5 py-3 shadow-card">
              <BotIcon className="size-4 text-teal" />
              <span className="text-[12.5px] text-ink-soft">
                First run? Seed this client's payment history so the risk model
                has something to read.
              </span>
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={() => void seed(activeProject?.client_email)}
              >
                <DatabaseZapIcon /> Seed history
              </Button>
            </div>
          </>
        ) : (
          <Tabs defaultValue="flow" className="gap-4">
            <TabsList variant="line">
              <TabsTrigger value="flow">The flow</TabsTrigger>
              <TabsTrigger value="risk">Invoices &amp; risk</TabsTrigger>
              <TabsTrigger value="model">The model</TabsTrigger>
              <TabsTrigger value="trail">Audit trail</TabsTrigger>
            </TabsList>

            <TabsContent value="flow" className="space-y-6">
              <section>
                <SectionTitle
                  step="02"
                  title="Deliver, and Hito invoices"
                  hint="every invoice clears the reviewer before PayPal is called"
                >
                  <Button variant="ghost" size="sm" onClick={reset}>
                    <RotateCcwIcon /> Reset demo
                  </Button>
                </SectionTitle>
                <MilestonesGrid
                  rows={milestones}
                  busyId={busyId}
                  splitDone={splitDone}
                  onDeliver={(row) => void deliver(row)}
                  onPay={(row) => void pay(row)}
                  onSplit={(row) => void split(row)}
                />
              </section>

              {data.payouts.length ? (
                <section>
                  <SectionTitle
                    step="05"
                    title="What went out to the team"
                    hint={`items above ${money(data.modes.payout_threshold)} need your tick`}
                  />
                  <div className="space-y-2">
                    {data.payouts.map((row) => (
                      <div
                        key={row.id}
                        className="rounded-lg border border-rule bg-card px-3.5 py-3 shadow-card"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="font-medium">
                            {row.milestone_title}
                            <span className="ml-2 font-mono text-[11.5px] text-ink-faint">
                              {row.batch_id ?? row.id}
                            </span>
                          </span>
                          <span className="flex items-center gap-2">
                            <span className="tabular font-heading text-[15px]">
                              {money(row.total, row.currency)}
                            </span>
                            <span className="text-[11.5px] text-ink-faint">
                              {row.status}
                            </span>
                            {row.batch_id ? (
                              <Button
                                variant="ghost"
                                size="icon-xs"
                                aria-label="Ask PayPal for the batch status"
                                title="Ask PayPal where this batch got to"
                                onClick={() => void refreshPayout(row.id)}
                              >
                                <RotateCcwIcon />
                              </Button>
                            ) : null}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {row.items.map((item) => (
                            <span
                              key={item.id}
                              className={`rounded-md border px-2 py-1 text-[12px] ${
                                item.status === "sent"
                                  ? "border-green/30 bg-green-soft/50 text-green"
                                  : item.status === "held"
                                    ? "border-amber/40 bg-amber-soft/40 text-amber"
                                    : "border-rule text-ink-soft"
                              }`}
                            >
                              {item.name} · {item.pct}% ·{" "}
                              <span className="tabular font-medium">
                                {money(item.amount, row.currency)}
                              </span>
                              {item.status === "held" ? " · held" : ""}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </TabsContent>

            <TabsContent value="risk" className="space-y-6">
              <section>
                <SectionTitle
                  step="04"
                  title="Collect, with the tone the risk deserves"
                  hint="sorted by what each invoice could cost you"
                />
                <InvoicesGrid
                  rows={data.invoices}
                  busyId={busyId}
                  onChase={(row: Invoice) => void chase(row.milestone_id)}
                />
              </section>

              {data.dunning.length ? (
                <section>
                  <SectionTitle title="Reminders" hint="what was drafted and what went out" />
                  <div className="space-y-2">
                    {data.dunning.map((row) => (
                      <div
                        key={row.id}
                        className="rounded-lg border border-rule bg-card px-3.5 py-2.5 shadow-card"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="text-[13px] font-medium">{row.subject}</span>
                          <span className="font-mono text-[11.5px] text-ink-faint">
                            {row.tone} · {Math.round(row.pd * 100)}% · {row.status}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[12.5px] whitespace-pre-line text-ink-soft">
                          {row.body}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </TabsContent>

            <TabsContent value="model">
              <RiskPanel card={data.risk_model} />
            </TabsContent>

            <TabsContent value="trail" className="space-y-6">
              <section>
                <SectionTitle
                  title="Every decision, and who made it"
                  hint="agent decisions and your decisions, in one ledger"
                />
                <EventsGrid rows={data.events} />
              </section>
              <section>
                <SectionTitle
                  title="Agent log"
                  hint={`${data.agent_spend.runs} runs · ${data.agent_spend.input_tokens} in / ${data.agent_spend.output_tokens} out · $${data.agent_spend.cost_usd.toFixed(5)} spent`}
                />
                <AgentRunsGrid rows={data.agent_runs} />
              </section>
            </TabsContent>
          </Tabs>
        )}

        <footer className="pt-2 pb-8 text-[11.5px] text-ink-faint">
          Hito · PayPal Invoicing v2, Payouts v1 and Webhooks ·{" "}
          {data?.modes.ai_local
            ? `four agents on ${data.modes.ai}, open source, on this machine`
            : data?.modes.ai_live
              ? `four agents on ${data.modes.ai}`
              : "four agents on the deterministic engine"}{" "}
          · risk model fitted in-process. Press{" "}
          <kbd className="rounded border border-rule px-1 font-mono">⌘K</kbd> for
          everything.
        </footer>
      </main>

      <ReviewDialog
        result={review}
        overriding={busyId !== null}
        onClose={() => {
          setReview(null)
          setReviewMilestone(null)
        }}
        onOverride={() => {
          if (reviewMilestone) {
            setReview(null)
            void deliver(reviewMilestone, true)
          }
        }}
      />
      <DunningDialog
        draft={dunning}
        sending={sending}
        onClose={() => setDunning(null)}
        onSend={(subject, body) => void sendDunning(subject, body)}
      />
      <PayoutDialog
        proposal={payout}
        sending={sending}
        onClose={() => setPayout(null)}
        onApprove={(ids) => void approvePayout(ids)}
      />
      <CommandMenu
        open={commandOpen}
        onOpenChange={setCommandOpen}
        milestones={milestones}
        actions={{
          deliver: (m) => void deliver(m),
          pay: (m) => void pay(m),
          chase: (m) => void chase(m.id),
          split: (m) => void split(m),
          seed: () => void seed(activeProject?.client_email),
          reset: () => void reset(),
          toggleTheme: () => setTheme(isDark ? "light" : "dark"),
          isDark,
        }}
      />
    </div>
  )
}
