import { useRef, useState } from "react"
import {
  FileTextIcon,
  LoaderCircleIcon,
  SparklesIcon,
  TriangleAlertIcon,
  UploadIcon,
} from "lucide-react"
import { toast } from "sonner"

import { EngineBadge, SectionTitle } from "@/components/bits"
import { PlanGrid } from "@/components/grids"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, type Plan, type PlanMilestone } from "@/lib/api"
import { money, pct } from "@/lib/format"

export function ContractStep({ onApproved }: { onApproved: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [reading, setReading] = useState(false)
  const [approving, setApproving] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  async function read(file: File) {
    setReading(true)
    const toastId = toast.loading(`Reading ${file.name}…`, {
      description:
        "Pulling out every deliverable, its amount, its date and the line of "
        + "the contract that sets it. On a local model this takes about a minute.",
      duration: Infinity,
    })
    try {
      const result = await api.parseContract(file)
      setPlan(result)
      const meta = result._meta
      const engine =
        meta?.engine === "rules" ? "the rule engine" : (meta?.model ?? "the model")
      toast.success(
        `Read ${result.milestones.length} milestones out of ${file.name}`,
        {
          id: toastId,
          description:
            `Extracted by ${engine}`
            + (meta?.latency_ms ? ` in ${(meta.latency_ms / 1000).toFixed(0)}s` : "")
            + ". Nothing is created until you approve.",
        }
      )
    } catch (error) {
      toast.error("Could not read that contract", {
        id: toastId,
        description: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setReading(false)
    }
  }

  async function useSample() {
    setReading(true)
    try {
      const response = await fetch("/api/demo/contract")
      if (!response.ok) throw new Error("Sample contract is not generated yet")
      const blob = await response.blob()
      await read(new File([blob], "contract_laura_bluebonnet.pdf", {
        type: "application/pdf",
      }))
    } catch (error) {
      toast.error("Sample contract unavailable", {
        description: error instanceof Error ? error.message : String(error),
      })
      setReading(false)
    }
  }

  async function approve() {
    if (!plan) return
    setApproving(true)
    try {
      await api.approvePlan({
        project_name: plan.project_name,
        client_name: plan.client_name,
        client_email: plan.client_email,
        client_country: plan.client_country,
        client_language: plan.client_language,
        currency: plan.currency,
        total_amount: plan.milestones.reduce((sum, m) => sum + Number(m.amount), 0),
        payment_terms: plan.payment_terms,
        contract_text: plan.contract_text,
        contract_filename: plan.contract_filename,
        milestones: plan.milestones,
        collaborators: plan.collaborators,
      })
      toast.success("Plan approved", {
        description: "Hito will invoice each milestone as you deliver it.",
      })
      setPlan(null)
      onApproved()
    } catch (error) {
      toast.error("Could not save the plan", {
        description: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setApproving(false)
    }
  }

  if (!plan) {
    return (
      <section>
        <SectionTitle
          step="01"
          title="Read the contract"
          hint="PDF, text or markdown — nothing is created until you approve the plan"
        />
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            const file = event.dataTransfer.files?.[0]
            if (file) void read(file)
          }}
          className={`flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center transition-colors ${
            dragging ? "border-teal bg-teal-soft/50" : "border-rule-strong bg-card"
          }`}
        >
          <FileTextIcon className="size-7 text-ink-faint" />
          <p className="mt-3 font-heading text-[15px] font-semibold">
            Drop the signed contract here
          </p>
          <p className="mt-1 max-w-md text-[12.5px] text-ink-soft">
            Hito pulls out every deliverable, what it is worth, when it is due and
            which sentence in the contract says so — plus the collaborator shares.
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            <Button disabled={reading} onClick={() => fileInput.current?.click()}>
              {reading ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <UploadIcon />
              )}
              Choose a file
            </Button>
            <Button variant="outline" disabled={reading} onClick={useSample}>
              Use the sample contract
            </Button>
          </div>
          <Input
            ref={fileInput}
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void read(file)
              event.target.value = ""
            }}
          />
        </div>
      </section>
    )
  }

  const total = plan.milestones.reduce((sum, m) => sum + Number(m.amount), 0)
  const mismatch = Math.abs(total - plan.total_amount) > 0.01

  return (
    <section>
      <SectionTitle
        step="01"
        title="Approve the plan"
        hint={`${plan.contract_filename} · ${plan.contract_chars ?? 0} characters read`}
      >
        <EngineBadge
          engine={plan._meta?.engine}
          model={plan._meta?.model}
          note={plan._meta?.note}
        />
        <Button variant="ghost" size="sm" onClick={() => setPlan(null)}>
          Start over
        </Button>
      </SectionTitle>

      <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-rule bg-card px-3 py-2.5 shadow-card">
          <div className="text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
            Client — invoices go here
          </div>
          <div className="mt-1 truncate font-heading text-[15px]">
            {plan.client_name}
          </div>
          <Input
            value={plan.client_email}
            onChange={(event) =>
              setPlan({ ...plan, client_email: event.target.value })
            }
            placeholder="client@example.com"
            spellCheck={false}
            aria-label="Client email"
            className="mt-1 h-6 border-0 border-b border-dashed border-rule-strong bg-transparent px-0 text-[11.5px] text-ink-faint shadow-none focus-visible:ring-0"
          />
        </div>
        <Field
          label="Contract total"
          value={money(plan.total_amount, plan.currency)}
          sub={mismatch ? `milestones add up to ${money(total)}` : "matches the milestones"}
          warn={mismatch}
        />
        <Field
          label="Payment terms"
          value={plan.payment_terms || "not stated"}
          sub={plan.client_country ? `client in ${plan.client_country}` : ""}
        />
        <Field
          label="Extraction confidence"
          value={pct(plan.confidence)}
          sub={
            plan._meta?.engine === "claude"
              ? `${plan._meta.latency_ms} ms · $${(plan._meta.cost_usd ?? 0).toFixed(4)}`
              : "deterministic fallback"
          }
        />
      </div>

      {plan.warnings.length ? (
        <div className="mb-3 rounded-md border border-amber/40 bg-amber-soft/40 px-3 py-2.5">
          <div className="mb-1 inline-flex items-center gap-1.5 text-[12px] font-semibold text-amber">
            <TriangleAlertIcon className="size-3.5" />
            Read these before approving
          </div>
          <ul className="list-inside list-disc space-y-0.5 text-[12.5px] text-ink">
            {plan.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <PlanGrid
        rows={plan.milestones}
        currency={plan.currency}
        onChange={(rows: PlanMilestone[]) => setPlan({ ...plan, milestones: rows })}
      />

      {plan.collaborators.length ? (
        <div className="mt-3 rounded-lg border border-rule bg-card px-3 py-2.5 shadow-card">
          <div className="mb-2 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
            Who gets a share of every payment
          </div>
          <div className="flex flex-wrap gap-2">
            {plan.collaborators.map((collaborator) => (
              <div
                key={collaborator.email}
                className="rounded-md border border-rule bg-background px-2.5 py-1.5 text-[12.5px]"
              >
                <span className="font-medium">{collaborator.name}</span>
                <span className="text-ink-faint"> · {collaborator.role} · </span>
                <span className="tabular font-medium text-teal">
                  {collaborator.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-lg text-[12.5px] text-ink-soft">
          Approving records the plan. From then on Hito only acts when you say a
          milestone is delivered, and every invoice still has to clear the reviewer.
          {plan.client_email.endsWith(".example") ? (
            <span className="mt-1 block text-amber">
              That address is a placeholder from the contract. Running against
              the real PayPal sandbox? Put your sandbox buyer address above, or
              the invoice goes nowhere.
            </span>
          ) : null}
        </p>
        <Button size="lg" disabled={approving} onClick={approve}>
          {approving ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : (
            <SparklesIcon />
          )}
          Approve this plan
        </Button>
      </div>
    </section>
  )
}

function Field({
  label,
  value,
  sub,
  warn,
}: {
  label: string
  value: string
  sub?: string
  warn?: boolean
}) {
  return (
    <div className="rounded-lg border border-rule bg-card px-3 py-2.5 shadow-card">
      <div className="text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
        {label}
      </div>
      <div className="mt-1 truncate font-heading text-[15px]">{value}</div>
      {sub ? (
        <div
          className={`mt-0.5 truncate text-[11.5px] ${
            warn ? "text-amber" : "text-ink-faint"
          }`}
        >
          {sub}
        </div>
      ) : null}
    </div>
  )
}
