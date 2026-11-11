export function money(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: value % 1 === 0 ? 0 : 2,
  }).format(value)
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  return `${(value * 100).toFixed(digits)}%`
}

export function day(value: string | null | undefined): string {
  if (!value) return "—"
  const parsed = new Date(value.length <= 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

export function clock(value: string | null | undefined): string {
  if (!value) return "—"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function relative(value: string | null | undefined): string {
  if (!value) return ""
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return ""
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 45) return "just now"
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}

export const TONE_LABEL: Record<string, string> = {
  friendly: "Friendly nudge",
  firm: "Firm reminder",
  payment_plan: "Offer a payment plan",
}

export const BAND_LABEL: Record<string, string> = {
  low: "Low risk",
  medium: "Watch",
  high: "High risk",
}

export const STATUS_LABEL: Record<string, string> = {
  pending: "Not delivered",
  delivered: "Delivered",
  invoiced: "Invoiced",
  overdue: "Overdue",
  paid: "Paid",
  blocked: "Blocked by review",
}
