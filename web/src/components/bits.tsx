import NumberFlow from "@number-flow/react"
import {
  BotIcon,
  CircleDollarSignIcon,
  CloudIcon,
  CpuIcon,
  ServerCogIcon,
  UserRoundIcon,
} from "lucide-react"
import { cn } from "cn"

import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Modes } from "@/lib/api"
import { BAND_LABEL, STATUS_LABEL, money, pct } from "@/lib/format"

/* -------------------------------------------------------------------------- */
/*  Section heading                                                            */
/* -------------------------------------------------------------------------- */

export function SectionTitle({
  step,
  title,
  hint,
  children,
}: {
  step?: string
  title: string
  hint?: string
  children?: React.ReactNode
}) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
      <div className="flex items-baseline gap-2.5">
        {step ? (
          <span className="font-mono text-[11px] font-medium text-ink-faint tabular">
            {step}
          </span>
        ) : null}
        <h2 className="font-heading text-[15px] font-semibold">{title}</h2>
        {hint ? (
          <span className="text-[12.5px] text-ink-soft">{hint}</span>
        ) : null}
      </div>
      {children ? <div className="flex items-center gap-2">{children}</div> : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  KPI tiles - NumberFlow does the counting                                   */
/* -------------------------------------------------------------------------- */

export function Kpi({
  label,
  value,
  currency = "USD",
  tone = "neutral",
  footnote,
}: {
  label: string
  value: number
  currency?: string
  tone?: "neutral" | "in" | "risk" | "accent"
  footnote?: string
}) {
  const toneClass = {
    neutral: "text-ink",
    in: "text-green",
    risk: "text-amber",
    accent: "text-teal",
  }[tone]

  return (
    <div className="relative rounded-lg border border-rule bg-card px-4 py-3 shadow-card">
      <div className="text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint uppercase">
        {label}
      </div>
      <div className={cn("mt-1.5 font-heading text-[26px] leading-none tabular", toneClass)}>
        <NumberFlow
          value={value}
          locales="en-US"
          format={{
            style: "currency",
            currency,
            currencyDisplay: "narrowSymbol",
            maximumFractionDigits: 0,
          }}
          transformTiming={{ duration: 650, easing: "cubic-bezier(0.22,1,0.36,1)" }}
        />
      </div>
      {footnote ? (
        <div className="mt-1.5 text-[11.5px] text-ink-soft">{footnote}</div>
      ) : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Risk meter - the one visual flourish in the product                        */
/* -------------------------------------------------------------------------- */

/**
 * The risk meter: this screen's single visual flourish. Built on shadcn's
 * Progress (Base UI, so the ARIA progressbar semantics come for free); the only
 * additions are the band colour and the scale underneath, which exist because a
 * bare percentage means nothing until you can see which band it falls in.
 */
export function RiskMeter({
  pd,
  band,
  cutoffs,
  compact = false,
}: {
  pd: number
  band: string
  cutoffs?: { low_below: number; high_above: number }
  compact?: boolean
}) {
  const colour =
    band === "high" ? "var(--red)" : band === "medium" ? "var(--amber)" : "var(--green)"
  const indicator = {
    low: "[&_[data-slot=progress-indicator]]:bg-green",
    medium: "[&_[data-slot=progress-indicator]]:bg-amber",
    high: "[&_[data-slot=progress-indicator]]:bg-red",
  }[band] ?? "[&_[data-slot=progress-indicator]]:bg-ink-faint"

  return (
    <div className="w-full">
      <div className="flex items-baseline justify-between gap-2">
        <span className="tabular text-[13px] font-semibold" style={{ color: colour }}>
          {pct(pd, 1)}
        </span>
        {!compact ? (
          <span className="text-[11px] text-ink-faint">chance of not being paid</span>
        ) : null}
      </div>
      <Progress
        value={Math.min(Math.max(pd * 100, 1), 100)}
        className={cn(
          "mt-1 block",
          "[&_[data-slot=progress-indicator]]:duration-700",
          indicator
        )}
        aria-label="Probability of default"
      />
      {!compact && cutoffs ? (
        <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-faint tabular">
          <span>friendly &lt; {pct(cutoffs.low_below)}</span>
          <span>firm</span>
          <span>{pct(cutoffs.high_above)} &gt; payment plan</span>
        </div>
      ) : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  Badges                                                                     */
/* -------------------------------------------------------------------------- */

export function BandBadge({ band }: { band?: string }) {
  if (!band) return <span className="text-ink-faint">—</span>
  const style = {
    low: "bg-green-soft text-green border-transparent",
    medium: "bg-amber-soft text-amber border-transparent",
    high: "bg-red-soft text-red border-transparent",
  }[band]
  return (
    <Badge className={cn("rounded-sm font-medium", style)}>
      {BAND_LABEL[band] ?? band}
    </Badge>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const style =
    {
      paid: "bg-green-soft text-green",
      overdue: "bg-amber-soft text-amber",
      blocked: "bg-red-soft text-red",
      invoiced: "bg-teal-soft text-teal-ink",
      delivered: "bg-secondary text-ink-soft",
      pending: "bg-secondary text-ink-faint",
    }[status] ?? "bg-secondary text-ink-soft"
  return (
    <Badge className={cn("rounded-sm border-transparent font-medium", style)}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  )
}

export function EngineBadge({
  engine,
  model,
  note,
}: {
  engine?: string
  model?: string
  note?: string
}) {
  const local = engine === "ollama"
  const claude = engine === "claude"
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="outline"
            className={cn(
              "gap-1 rounded-sm border-rule font-mono text-[10.5px]",
              local && "text-teal"
            )}
          >
            {local ? <CpuIcon /> : claude ? <CloudIcon /> : <ServerCogIcon />}
            {local || claude ? (model ?? engine) : "rule engine"}
          </Badge>
        }
      />
      <TooltipContent>
        {local
          ? `Written by ${model}, an open-source model running on this machine. No API key, no network call, no cost — the contract never leaves the laptop. Tokens and latency are in the Agent log.`
          : claude
            ? `Written by ${model}. Token counts and cost are in the Agent log.`
            : `Deterministic fallback: ${note ?? "no model engine available"}.`}
      </TooltipContent>
    </Tooltip>
  )
}

export function ActorMark({ actor }: { actor: string }) {
  if (actor === "human") {
    return (
      <span className="inline-flex items-center gap-1 text-ink-soft">
        <UserRoundIcon className="size-3" /> Laura
      </span>
    )
  }
  if (actor === "paypal") {
    return (
      <span className="inline-flex items-center gap-1 text-green">
        <CircleDollarSignIcon className="size-3" /> PayPal
      </span>
    )
  }
  if (actor === "system") {
    return (
      <span className="inline-flex items-center gap-1 text-ink-faint">
        <ServerCogIcon className="size-3" /> system
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-teal">
      <BotIcon className="size-3" /> agent
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/*  Mode banner                                                                */
/* -------------------------------------------------------------------------- */

export function ModeBadges({ modes }: { modes: Modes }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Tooltip>
        <TooltipTrigger
          render={
            <Badge
              variant="outline"
              className={cn(
                "rounded-sm border-rule font-mono text-[10.5px]",
                modes.paypal === "mock" ? "text-ink-faint" : "text-green"
              )}
            >
              PayPal: {modes.paypal}
            </Badge>
          }
        />
        <TooltipContent>
          {modes.paypal === "mock"
            ? "No PayPal credentials found, so invoices and payouts run through the in-process gateway. Add PAYPAL_CLIENT_ID to .env for the real sandbox."
            : `Real PayPal REST calls against the ${modes.paypal} environment: Invoicing v2, Payouts v1, Webhooks.`}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger
          render={
            <Badge
              variant="outline"
              className={cn(
                "gap-1 rounded-sm border-rule font-mono text-[10.5px]",
                modes.ai_live ? "text-teal" : "text-ink-faint"
              )}
            >
              {modes.ai_local ? <CpuIcon /> : null}
              AI: {modes.ai_live ? modes.ai : "rule engine"}
              {modes.ai_local ? " · local" : ""}
            </Badge>
          }
        />
        <TooltipContent>
          {modes.ai_local
            ? `All four agents run on ${modes.ai}, an open-source model on this machine, constrained by a JSON schema. No API key, no cost, and the contract never leaves the laptop.`
            : modes.ai_live
              ? `All four agents call ${modes.ai} with structured outputs.`
              : `Every agent is using its deterministic fallback, so the flow works but the writing is templated. ${modes.ai_detail} To turn the real engine on: install Ollama, then run "ollama pull qwen2.5:3b".`}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger
          render={
            <Badge
              variant="outline"
              className="rounded-sm border-rule font-mono text-[10.5px] text-ink-soft"
            >
              ceiling: {money(modes.payout_threshold)}
            </Badge>
          }
        />
        <TooltipContent>
          Payout items above this amount are never sent without Laura ticking
          that specific line.
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
