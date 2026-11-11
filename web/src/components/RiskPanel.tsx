import { useEffect, useMemo, useState } from "react"

import { BandBadge, RiskMeter, SectionTitle } from "@/components/bits"
import { Slider } from "@/components/ui/slider"
import { Separator } from "@/components/ui/separator"
import { api, type ModelCard, type RiskScore } from "@/lib/api"
import { TONE_LABEL, money, pct } from "@/lib/format"

/**
 * The model card and a what-if panel.
 *
 * A score that decides how you talk to a client should be inspectable, so this
 * shows the fitted weights, the out-of-sample metrics and the band cut-offs,
 * and lets anyone move the inputs and watch the tone decision change.
 */
export function RiskPanel({ card }: { card: ModelCard }) {
  const [amount, setAmount] = useState(3000)
  const [overdue, setOverdue] = useState(14)
  const [lateRatio, setLateRatio] = useState(0.33)
  const [relationship, setRelationship] = useState(3)
  const [avgDaysLate, setAvgDaysLate] = useState(14)
  const [score, setScore] = useState<RiskScore | null>(null)

  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .whatIf({
          amount,
          days_overdue: overdue,
          prior_late_ratio: lateRatio,
          prior_avg_days_late: avgDaysLate,
          relationship_invoices: relationship,
          cross_border: true,
        })
        .then((result) => {
          if (!cancelled) setScore(result)
        })
        .catch(() => undefined)
    }, 120)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [amount, overdue, lateRatio, relationship, avgDaysLate])

  const maxWeight = useMemo(
    () =>
      Math.max(
        ...card.coefficients.map((c) => Math.abs(c.standardized_weight)),
        0.001
      ),
    [card.coefficients]
  )

  return (
    <section>
      <SectionTitle
        step="—"
        title="The risk model"
        hint="logistic regression, fitted on boot, scored out of sample"
      />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="rounded-lg border border-rule bg-card p-4 shadow-card">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-heading text-[14px] font-semibold">
              What it learned
            </h3>
            <span className="font-mono text-[11px] text-ink-faint">
              {card.n_train} train / {card.n_test} test · {card.dataset}
            </span>
          </div>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            Target: {card.target}.
          </p>

          <div className="mt-3 grid grid-cols-4 gap-2">
            <Metric label="AUC" value={card.metrics.auc?.toFixed(3) ?? "—"} />
            <Metric label="Brier" value={card.metrics.brier?.toFixed(3) ?? "—"} />
            <Metric label="Log loss" value={card.metrics.log_loss?.toFixed(3) ?? "—"} />
            <Metric
              label="Base rate"
              value={card.metrics.base_rate ? pct(card.metrics.base_rate) : "—"}
            />
          </div>

          <Separator className="my-3" />

          <div className="space-y-2">
            {card.coefficients.map((coefficient) => {
              const width = (Math.abs(coefficient.standardized_weight) / maxWeight) * 100
              const positive = coefficient.standardized_weight > 0
              return (
                <div key={coefficient.feature}>
                  <div className="flex items-baseline justify-between gap-2 text-[12px]">
                    <span className="truncate text-ink">{coefficient.label}</span>
                    <span
                      className={`tabular shrink-0 font-mono text-[11.5px] ${
                        positive ? "text-red" : "text-green"
                      }`}
                    >
                      {positive ? "+" : ""}
                      {coefficient.standardized_weight.toFixed(3)}
                    </span>
                  </div>
                  <div className="mt-1 flex h-[5px] w-full overflow-hidden rounded-full bg-secondary">
                    <div className="flex w-1/2 justify-end">
                      {!positive ? (
                        <div
                          className="h-full rounded-l-full bg-green"
                          style={{ width: `${width}%` }}
                        />
                      ) : null}
                    </div>
                    <div className="w-1/2">
                      {positive ? (
                        <div
                          className="h-full rounded-r-full bg-red"
                          style={{ width: `${width}%` }}
                        />
                      ) : null}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <p className="mt-3 text-[11.5px] text-ink-faint">
            Standardized weights, so they are comparable. Behaviour beats
            geography here: how a client paid in the past moves the score far
            more than where they are.
          </p>
        </div>

        <div className="rounded-lg border border-rule bg-card p-4 shadow-card">
          <h3 className="font-heading text-[14px] font-semibold">
            Move the inputs, watch the tone change
          </h3>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            The band cut-offs are the 50th and 85th percentile of the model's own
            predictions ({pct(card.cutoffs.low_below)} and{" "}
            {pct(card.cutoffs.high_above)}), not round numbers someone liked.
          </p>

          <div className="mt-4 space-y-3.5">
            <Control
              label="Invoice amount"
              display={money(amount)}
              value={amount}
              min={200}
              max={12000}
              step={100}
              onChange={setAmount}
            />
            <Control
              label="Days past due"
              display={`${overdue} d`}
              value={overdue}
              min={0}
              max={90}
              step={1}
              onChange={setOverdue}
            />
            <Control
              label="Share of past invoices paid late"
              display={pct(lateRatio)}
              value={lateRatio * 100}
              min={0}
              max={100}
              step={1}
              onChange={(value) => setLateRatio(value / 100)}
            />
            <Control
              label="Average days late in the past"
              display={`${avgDaysLate} d`}
              value={avgDaysLate}
              min={0}
              max={60}
              step={1}
              onChange={setAvgDaysLate}
            />
            <Control
              label="Invoices already settled with this client"
              display={String(relationship)}
              value={relationship}
              min={0}
              max={10}
              step={1}
              onChange={setRelationship}
            />
          </div>

          <Separator className="my-4" />

          {score ? (
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <BandBadge band={score.band} />
                <span className="text-[13px] font-medium">
                  {TONE_LABEL[score.tone] ?? score.tone}
                </span>
                <span className="ml-auto tabular text-[12.5px] text-ink-soft">
                  expected loss {money(score.expected_loss)}
                </span>
              </div>
              <RiskMeter pd={score.pd} band={score.band} cutoffs={score.cutoffs} />
              <p className="mt-2 text-[12px] text-ink-soft">{score.intent}</p>
            </div>
          ) : (
            <div className="h-[86px] animate-pulse rounded-md bg-secondary" />
          )}
        </div>
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-rule bg-background px-2 py-1.5 text-center">
      <div className="text-[10px] font-semibold tracking-[0.07em] text-ink-faint uppercase">
        {label}
      </div>
      <div className="tabular mt-0.5 font-heading text-[14px]">{value}</div>
    </div>
  )
}

function Control({
  label,
  display,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  display: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-ink-soft">{label}</span>
        <span className="tabular font-mono text-[12px] font-medium">{display}</span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(next) =>
          onChange(Array.isArray(next) ? next[0] : (next as number))
        }
      />
    </div>
  )
}
