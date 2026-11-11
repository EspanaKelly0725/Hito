/** Typed client for the Hito API. One place that knows about HTTP. */

export interface Modes {
  paypal: "sandbox" | "live" | "mock"
  paypal_live: boolean
  ai: string
  ai_live: boolean
  payout_threshold: number
  webhook_verification: boolean
}

export interface AgentMeta {
  agent?: string
  engine?: "claude" | "rules"
  model?: string
  latency_ms?: number
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
  note?: string
}

export interface PlanMilestone {
  idx?: number
  title: string
  description: string
  amount: number
  due_date: string
  contract_quote: string
}

export interface PlanCollaborator {
  name: string
  email: string
  role: string
  pct: number
}

export interface Plan {
  project_name: string
  client_name: string
  client_email: string
  client_country: string
  client_language: string
  currency: string
  total_amount: number
  payment_terms: string
  milestones: PlanMilestone[]
  collaborators: PlanCollaborator[]
  warnings: string[]
  confidence: number
  contract_text: string
  contract_filename: string
  contract_chars?: number
  _meta: AgentMeta
}

export interface RiskFactor {
  feature: string
  label: string
  value: number
  weight: number
  logit_contribution: number
  direction: "raises" | "lowers"
}

export interface RiskScore {
  pd: number
  band: "low" | "medium" | "high"
  tone: string
  intent: string
  offer: string | null
  expected_loss: number
  factors: RiskFactor[]
  top_factors: string[]
  cutoffs?: { low_below: number; high_above: number }
  days_overdue?: number
  history?: ClientHistory
}

export interface ClientHistory {
  invoices_settled: number
  late_ratio: number
  avg_days_late: number
  reminder_count?: number
}

export interface Milestone {
  id: string
  project_id: string
  idx: number
  title: string
  description: string
  amount: number
  currency: string
  due_date: string
  status: string
  evidence?: string
  contract_quote?: string
  delivered_at?: string
  invoice_id?: string
  invoice_number?: string
  invoice_url?: string
  paid_at?: string
  paid_amount?: number
  days_overdue: number
  project_name: string
  client_name: string
  client_email: string
  historical?: boolean
  pd?: number
  risk_band?: string
  suggested_tone?: string
  expected_loss?: number
  top_factors?: string[]
}

export interface Invoice {
  invoice_id: string
  number: string
  milestone_id: string
  milestone_title: string
  project_name: string
  client_name: string
  amount: number
  currency: string
  status: string
  due_date: string
  days_overdue: number
  paid_at?: string
  view_url?: string
  pd?: number
  risk_band?: string
  expected_loss?: number
  suggested_tone?: string
}

export interface PayoutItem {
  id: string
  payout_id: string
  name: string
  email: string
  role: string
  pct: number
  amount: number
  needs_approval: number
  approved: number
  status: string
  note: string
}

export interface Payout {
  id: string
  project_id: string
  milestone_id: string
  milestone_title?: string
  project_name?: string
  created_at: string
  status: string
  total: number
  currency: string
  batch_id?: string
  rationale?: string
  items: PayoutItem[]
}

export interface DunningRow {
  id: string
  milestone_id: string
  milestone_title: string
  invoice_number: string
  client_name: string
  created_at: string
  days_overdue: number
  pd: number
  band: string
  tone: string
  expected_loss: number
  subject: string
  body: string
  status: string
  sent_at?: string
}

export interface EventRow {
  id: string
  ts: string
  project_id: string | null
  actor: "agent" | "human" | "paypal" | "system"
  kind: string
  summary: string
  payload: string
}

export interface AgentRun {
  id: string
  ts: string
  agent: string
  model: string
  engine: string
  latency_ms: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  verdict: string
}

export interface Project {
  id: string
  name: string
  client_name: string
  client_email: string
  client_country: string
  client_language?: string
  currency: string
  total_amount: number
  contract_filename?: string
  contract_text?: string
  status: string
  created_at: string
  collaborators: (PlanCollaborator & { id: string })[]
}

export interface ModelCard {
  kind: string
  target: string
  trained: boolean
  n_train: number
  n_test: number
  dataset: string
  bias: number
  metrics: Record<string, number>
  cutoffs: { low_below: number; high_above: number; derived_from: string }
  coefficients: {
    feature: string
    label: string
    standardized_weight: number
    mean: number
    std: number
  }[]
  tone_policy: { band: string; tone: string; intent: string; offer: string | null }[]
}

export interface Dashboard {
  modes: Modes
  totals: {
    contracted: number
    invoiced: number
    collected: number
    outstanding: number
    at_risk: number
    overdue: number
  }
  projects: Project[]
  milestones: Milestone[]
  invoices: Invoice[]
  payouts: Payout[]
  dunning: DunningRow[]
  events: EventRow[]
  agent_runs: AgentRun[]
  agent_spend: {
    runs: number
    cost_usd: number
    input_tokens: number
    output_tokens: number
  }
  risk_model: ModelCard
}

export interface ReviewCheck {
  name: string
  pass: boolean
  detail: string
  blocking: boolean
}

export interface ReviewFinding {
  severity: "info" | "warning" | "critical"
  check: string
  detail: string
}

export interface Review {
  verdict: "approve" | "hold" | "block"
  headline: string
  amount: number
  currency: string
  checks: ReviewCheck[]
  hard_failures: string[]
  soft_failures: string[]
  model_verdict: string
  model_confidence: number
  contract_evidence: string
  findings: ReviewFinding[]
  _meta: AgentMeta
}

export interface DeliverResult {
  stage: "invoiced" | "hold" | "blocked"
  review: Review
  invoice: {
    id: string
    number: string
    status: string
    view_url?: string
    amount: number
    gateway: string
  } | null
}

export interface DunningDraft {
  dunning_id: string
  risk: RiskScore
  history: ClientHistory
  engine?: string
  message: {
    subject: string
    body: string
    tone_used: string
    rationale: string
    escalation_suggestion: string
    offer_terms: {
      first: number
      second: number
      first_date: string
      second_date: string
    } | null
    _meta: AgentMeta
  }
}

export interface PayoutProposal {
  payout_id: string
  items: PayoutItem[]
  retained: number
  paid_amount: number
  currency: string
  rationale: string
  threshold: number
  needs_approval: boolean
  already_exists?: boolean
  _meta?: AgentMeta
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!response.ok) {
    const detail = (body as { detail?: unknown })?.detail ?? body
    const message =
      typeof detail === "string"
        ? detail
        : ((detail as { error?: string })?.error ??
          `Request failed (${response.status})`)
    throw new ApiError(message, response.status, detail)
  }
  return body as T
}

function post<T>(path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  })
}

export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  status: () => request<Record<string, unknown>>("/api/status"),
  modelCard: () => request<ModelCard>("/api/risk/model"),

  parseContract(file: File | null, text?: string) {
    const form = new FormData()
    if (file) form.append("file", file)
    if (text) form.append("text", text)
    return request<Plan>("/api/contracts/parse", { method: "POST", body: form })
  },

  approvePlan(plan: {
    project_name: string
    client_name: string
    client_email: string
    client_country: string
    client_language: string
    currency: string
    total_amount: number
    payment_terms: string
    contract_text: string
    contract_filename: string
    milestones: PlanMilestone[]
    collaborators: PlanCollaborator[]
  }) {
    return post<{ project_id: string; ok: boolean }>("/api/projects", plan)
  },

  deliver: (milestoneId: string, evidence: string, override = false) =>
    post<DeliverResult>(`/api/milestones/${milestoneId}/deliver`, {
      evidence,
      override,
    }),

  simulatePayment: (milestoneId: string) =>
    post<{ ok: boolean }>(`/api/milestones/${milestoneId}/simulate-payment`),

  risk: (milestoneId: string) =>
    request<RiskScore>(`/api/milestones/${milestoneId}/risk`),

  draftDunning: (milestoneId: string) =>
    post<DunningDraft>(`/api/milestones/${milestoneId}/dunning`),

  sendDunning: (dunningId: string, subject: string, body: string) =>
    post<{ ok: boolean; channel: string }>(`/api/dunning/${dunningId}/send`, {
      subject,
      body,
    }),

  proposePayout: (milestoneId: string) =>
    post<PayoutProposal>(`/api/milestones/${milestoneId}/payout/propose`),

  approvePayout: (payoutId: string, approvedItemIds: string[]) =>
    post<{
      ok: boolean
      batch_id: string
      batch_status: string
      sent: string[]
      held: string[]
      gateway: string
    }>(`/api/payouts/${payoutId}/approve`, { approved_item_ids: approvedItemIds }),

  whatIf: (payload: Record<string, number | boolean>) =>
    post<RiskScore>("/api/risk/score", payload),

  seedDemo: () => post<{ ok: boolean; history: ClientHistory }>("/api/demo/seed"),
  resetDemo: () => post<{ ok: boolean }>("/api/demo/reset"),
}
