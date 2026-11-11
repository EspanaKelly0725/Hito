/**
 * Every table in Hito is an AG Grid Community grid.
 *
 * They are not decorative: the milestone grid is where Laura approves the plan
 * (editable amount and due-date cells, validated against the contract), and the
 * invoice grid is where she acts on risk - sorted by expected loss, with the
 * action buttons living in the row they belong to.
 *
 * Community-only features used here: custom cell renderers, value formatters
 * and getters, editable cells with validation, quick filter, column filters,
 * sorting, row classes, pinned bottom totals, auto-height rows and CSV export.
 */
import { useCallback, useMemo, useRef, useState } from "react"
import { AgGridReact } from "ag-grid-react"
import {
  AllCommunityModule,
  ModuleRegistry,
  type CellClassParams,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type ICellRendererParams,
  type ValueFormatterParams,
  type RowClassParams,
} from "ag-grid-community"
import "ag-grid-community/styles/ag-grid.css"
import "ag-grid-community/styles/ag-theme-quartz.css"
import {
  BanknoteIcon,
  DownloadIcon,
  ExternalLinkIcon,
  HandCoinsIcon,
  PackageCheckIcon,
  SearchIcon,
} from "lucide-react"

import { BandBadge, RiskMeter, StatusBadge, ActorMark } from "@/components/bits"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type {
  AgentRun,
  EventRow,
  Invoice,
  Milestone,
  PlanMilestone,
} from "@/lib/api"
import { clock, day, money, relative } from "@/lib/format"

ModuleRegistry.registerModules([AllCommunityModule])

const BASE_COL: ColDef = {
  sortable: true,
  resizable: true,
  suppressMovable: true,
  filter: false,
  flex: 1,
  minWidth: 90,
}

function usdFormatter(params: ValueFormatterParams) {
  return money(params.value, params.data?.currency ?? "USD")
}

/* -------------------------------------------------------------------------- */
/*  Shell: toolbar with quick filter + CSV export                              */
/* -------------------------------------------------------------------------- */

function GridShell({
  children,
  api,
  filename,
  placeholder = "Filter…",
  onFilter,
  rightSlot,
}: {
  children: React.ReactNode
  api: GridApi | null
  filename: string
  placeholder?: string
  onFilter: (value: string) => void
  rightSlot?: React.ReactNode
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-card shadow-card">
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-3 py-2">
        <div className="relative min-w-[180px] flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-faint" />
          <Input
            className="h-7 border-rule bg-background pl-7 text-[13px]"
            placeholder={placeholder}
            onChange={(event) => onFilter(event.target.value)}
          />
        </div>
        {rightSlot}
        <Button
          variant="ghost"
          size="xs"
          onClick={() => api?.exportDataAsCsv({ fileName: filename })}
          title="Export this view as CSV"
        >
          <DownloadIcon /> CSV
        </Button>
      </div>
      {children}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/*  1. Plan review - the editable grid where Laura approves the contract       */
/* -------------------------------------------------------------------------- */

export function PlanGrid({
  rows,
  currency,
  onChange,
}: {
  rows: PlanMilestone[]
  currency: string
  onChange: (rows: PlanMilestone[]) => void
}) {
  const [api, setApi] = useState<GridApi | null>(null)

  const columns = useMemo<ColDef[]>(
    () => [
      {
        headerName: "#",
        valueGetter: (p) => (p.node?.rowPinned ? "" : (p.node?.rowIndex ?? 0) + 1),
        width: 44,
        maxWidth: 44,
        flex: 0,
        sortable: false,
        cellClass: "text-ink-faint font-mono text-[11px]",
      },
      {
        field: "title",
        headerName: "Deliverable",
        editable: true,
        flex: 2.2,
        minWidth: 170,
        cellClass: "font-medium",
      },
      {
        field: "amount",
        headerName: `Amount (${currency})`,
        editable: true,
        flex: 1,
        minWidth: 120,
        type: "numericColumn",
        cellClass: "tabular justify-end",
        headerClass: "ag-right-aligned-header",
        valueFormatter: (p) => money(p.value, currency),
        valueParser: (p) => {
          const parsed = Number(String(p.newValue).replace(/[^0-9.-]/g, ""))
          return Number.isFinite(parsed) && parsed > 0 ? parsed : p.oldValue
        },
      },
      {
        field: "due_date",
        headerName: "Due",
        editable: true,
        flex: 1,
        minWidth: 110,
        valueFormatter: (p) => day(p.value),
      },
      {
        field: "contract_quote",
        headerName: "Where it says so",
        flex: 3,
        minWidth: 220,
        tooltipField: "contract_quote",
        cellRenderer: (p: ICellRendererParams) => {
          if (p.node?.rowPinned) return null
          return p.value ? (
            <span className="truncate text-[12px] text-ink-soft italic">
              “{p.value}”
            </span>
          ) : (
            <span className="text-[12px] text-amber">
              not quoted from the contract
            </span>
          )
        },
      },
    ],
    [currency]
  )

  const total = rows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0)

  return (
    <GridShell
      api={api}
      filename="hito-plan.csv"
      placeholder="Filter milestones…"
      onFilter={(value) => api?.setGridOption("quickFilterText", value)}
      rightSlot={
        <span className="px-1 text-[12px] text-ink-soft">
          Click a cell to correct it before approving
        </span>
      }
    >
      <div
        className="ag-theme-quartz hito-grid"
        style={{ height: 36 + rows.length * 42 + 46 }}
      >
        <AgGridReact
          theme="legacy"
          rowData={rows}
          columnDefs={columns}
          defaultColDef={BASE_COL}
          headerHeight={32}
          rowHeight={42}
          animateRows
          stopEditingWhenCellsLoseFocus
          singleClickEdit
          onGridReady={(event: GridReadyEvent) => setApi(event.api)}
          onCellValueChanged={(event) => {
            const next: PlanMilestone[] = []
            event.api.forEachNode((node) => next.push(node.data))
            onChange(next)
          }}
          pinnedBottomRowData={[
            {
              title: "Total",
              amount: total,
              due_date: "",
              contract_quote: "",
              description: "",
            },
          ]}
        />
      </div>
    </GridShell>
  )
}

/* -------------------------------------------------------------------------- */
/*  2. Milestones                                                              */
/* -------------------------------------------------------------------------- */

export function MilestonesGrid({
  rows,
  onDeliver,
  onPay,
  onSplit,
  busyId,
  splitDone,
}: {
  rows: Milestone[]
  onDeliver: (row: Milestone) => void
  onPay: (row: Milestone) => void
  onSplit: (row: Milestone) => void
  busyId: string | null
  splitDone: Set<string>
}) {
  const [api, setApi] = useState<GridApi | null>(null)

  const columns = useMemo<ColDef[]>(
    () => [
      {
        field: "title",
        headerName: "Deliverable",
        flex: 2.2,
        minWidth: 180,
        cellRenderer: (p: ICellRendererParams<Milestone>) => (
          <div className="flex min-w-0 flex-col justify-center leading-tight">
            <span className="truncate font-medium">{p.value}</span>
            <span className="truncate text-[11.5px] text-ink-faint">
              {p.data?.project_name}
            </span>
          </div>
        ),
        autoHeight: true,
      },
      {
        field: "amount",
        headerName: "Amount",
        flex: 0.9,
        minWidth: 105,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: usdFormatter,
      },
      {
        field: "due_date",
        headerName: "Due",
        flex: 0.9,
        minWidth: 105,
        valueFormatter: (p) => day(p.value),
        cellClass: (p: CellClassParams<Milestone>) =>
          p.data?.status === "overdue" ? "text-amber font-medium" : "",
      },
      {
        field: "status",
        headerName: "State",
        flex: 1,
        minWidth: 125,
        cellRenderer: (p: ICellRendererParams<Milestone>) => (
          <div className="flex items-center gap-1.5">
            <StatusBadge status={p.value} />
            {p.data?.status === "overdue" ? (
              <span className="text-[11px] text-amber tabular">
                +{p.data.days_overdue}d
              </span>
            ) : null}
          </div>
        ),
      },
      {
        field: "invoice_number",
        headerName: "Invoice",
        flex: 0.9,
        minWidth: 120,
        cellRenderer: (p: ICellRendererParams<Milestone>) =>
          p.value ? (
            <a
              className="inline-flex items-center gap-1 font-mono text-[11.5px] text-teal hover:underline"
              href={p.data?.invoice_url || "#"}
              target="_blank"
              rel="noreferrer"
            >
              {p.value} <ExternalLinkIcon className="size-3" />
            </a>
          ) : (
            <span className="text-ink-faint">—</span>
          ),
      },
      {
        headerName: "",
        flex: 1.3,
        minWidth: 190,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<Milestone>) => {
          const row = p.data
          if (!row) return null
          const busy = busyId === row.id
          if (row.status === "pending" || row.status === "delivered") {
            return (
              <Button
                size="xs"
                variant="default"
                disabled={busy}
                onClick={() => onDeliver(row)}
              >
                <PackageCheckIcon /> I delivered this
              </Button>
            )
          }
          if (row.status === "invoiced" || row.status === "overdue") {
            return (
              <Button
                size="xs"
                variant="outline"
                disabled={busy}
                onClick={() => onPay(row)}
                title="Stand in for the client paying the invoice"
              >
                <BanknoteIcon /> Simulate payment
              </Button>
            )
          }
          if (row.status === "paid") {
            const done = splitDone.has(row.id)
            return (
              <Button
                size="xs"
                variant={done ? "ghost" : "secondary"}
                disabled={busy}
                onClick={() => onSplit(row)}
                title={done ? "Review the split that went out" : undefined}
              >
                <HandCoinsIcon /> {done ? "Split sent" : "Split it"}
              </Button>
            )
          }
          return <span className="text-[12px] text-red">Blocked by review</span>
        },
      },
    ],
    [busyId, onDeliver, onPay, onSplit, splitDone]
  )

  return (
    <GridShell
      api={api}
      filename="hito-milestones.csv"
      placeholder="Filter milestones…"
      onFilter={(value) => api?.setGridOption("quickFilterText", value)}
    >
      <div
        className="ag-theme-quartz hito-grid"
        style={{ height: Math.max(140, 44 + rows.length * 50) }}
      >
        <AgGridReact
          theme="legacy"
          rowData={rows}
          columnDefs={columns}
          defaultColDef={BASE_COL}
          headerHeight={32}
          rowHeight={50}
          animateRows
          getRowId={(p) => p.data.id}
          getRowClass={(p: RowClassParams<Milestone>) =>
            p.data?.status === "overdue"
              ? "ag-row-overdue"
              : p.data?.status === "paid"
                ? "ag-row-paid"
                : ""
          }
          overlayNoRowsTemplate="No milestones yet — read a contract first."
          onGridReady={(event: GridReadyEvent) => setApi(event.api)}
        />
      </div>
    </GridShell>
  )
}

/* -------------------------------------------------------------------------- */
/*  3. Invoices, sorted by what they could cost                                */
/* -------------------------------------------------------------------------- */

export function InvoicesGrid({
  rows,
  onChase,
  busyId,
}: {
  rows: Invoice[]
  onChase: (row: Invoice) => void
  busyId: string | null
}) {
  const [api, setApi] = useState<GridApi | null>(null)

  const columns = useMemo<ColDef[]>(
    () => [
      {
        field: "number",
        headerName: "Invoice",
        flex: 1,
        minWidth: 130,
        cellRenderer: (p: ICellRendererParams<Invoice>) => (
          <div className="flex min-w-0 flex-col justify-center leading-tight">
            <span className="font-mono text-[12px]">{p.value}</span>
            <span className="truncate text-[11.5px] text-ink-faint">
              {p.data?.milestone_title}
            </span>
          </div>
        ),
        autoHeight: true,
      },
      {
        field: "client_name",
        headerName: "Client",
        flex: 1.2,
        minWidth: 140,
      },
      {
        field: "amount",
        headerName: "Amount",
        flex: 0.9,
        minWidth: 105,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: usdFormatter,
      },
      {
        field: "days_overdue",
        headerName: "Overdue",
        flex: 0.7,
        minWidth: 90,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: (p) =>
          p.data?.status === "paid" ? "—" : p.value > 0 ? `${p.value} d` : "on time",
      },
      {
        field: "pd",
        headerName: "Risk of non-payment",
        flex: 2,
        minWidth: 210,
        cellRenderer: (p: ICellRendererParams<Invoice>) => {
          if (p.node?.rowPinned) return null
          if (p.data?.status === "paid") return <StatusBadge status="paid" />
          if (p.value == null)
            return <span className="text-[12px] text-ink-faint">—</span>
          return (
            <div className="flex w-full items-center gap-2.5">
              <div className="min-w-0 flex-1">
                <RiskMeter pd={p.value} band={p.data?.risk_band ?? "low"} compact />
              </div>
              <BandBadge band={p.data?.risk_band} />
            </div>
          )
        },
      },
      {
        field: "expected_loss",
        headerName: "Expected loss",
        flex: 1,
        minWidth: 120,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: (p) =>
          p.data?.status === "paid" ? "—" : money(p.value, p.data?.currency),
        sort: "desc",
      },
      {
        headerName: "",
        flex: 1.1,
        minWidth: 160,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<Invoice>) => {
          const row = p.data
          if (!row || row.status === "paid" || p.node?.rowPinned) return null
          return (
            <Button
              size="xs"
              variant={row.days_overdue > 0 ? "default" : "ghost"}
              disabled={busyId === row.milestone_id || row.days_overdue === 0}
              onClick={() => onChase(row)}
              title={
                row.days_overdue === 0
                  ? "Not due yet"
                  : "Score the risk and draft the message"
              }
            >
              Chase with tact
            </Button>
          )
        },
      },
    ],
    [busyId, onChase]
  )

  const outstanding = rows
    .filter((row) => row.status !== "paid")
    .reduce((sum, row) => sum + row.amount, 0)
  const exposure = rows
    .filter((row) => row.status !== "paid")
    .reduce((sum, row) => sum + (row.expected_loss ?? 0), 0)

  return (
    <GridShell
      api={api}
      filename="hito-invoices.csv"
      placeholder="Filter invoices…"
      onFilter={(value) => api?.setGridOption("quickFilterText", value)}
    >
      <div
        className="ag-theme-quartz hito-grid"
        style={{ height: Math.max(150, 36 + rows.length * 52 + 56) }}
      >
        <AgGridReact
          theme="legacy"
          rowData={rows}
          columnDefs={columns}
          defaultColDef={BASE_COL}
          headerHeight={32}
          rowHeight={52}
          animateRows
          getRowId={(p) => p.data.invoice_id}
          getRowClass={(p: RowClassParams<Invoice>) =>
            p.data?.status === "overdue" ? "ag-row-overdue" : ""
          }
          overlayNoRowsTemplate="No invoices yet."
          onGridReady={(event: GridReadyEvent) => setApi(event.api)}
          pinnedBottomRowData={[
            {
              number: "Outstanding",
              client_name: "",
              amount: outstanding,
              expected_loss: exposure,
              status: "total",
              days_overdue: null,
              pd: null,
            },
          ]}
        />
      </div>
    </GridShell>
  )
}

/* -------------------------------------------------------------------------- */
/*  4. Audit trail and agent log                                               */
/* -------------------------------------------------------------------------- */

export function EventsGrid({ rows }: { rows: EventRow[] }) {
  const [api, setApi] = useState<GridApi | null>(null)
  const columns = useMemo<ColDef[]>(
    () => [
      {
        field: "ts",
        headerName: "When",
        flex: 0.8,
        minWidth: 120,
        cellRenderer: (p: ICellRendererParams<EventRow>) => (
          <div className="flex flex-col justify-center leading-tight">
            <span className="font-mono text-[11.5px]">{clock(p.value)}</span>
            <span className="text-[10.5px] text-ink-faint">{relative(p.value)}</span>
          </div>
        ),
        autoHeight: true,
      },
      {
        field: "actor",
        headerName: "Decided by",
        flex: 0.7,
        minWidth: 110,
        cellRenderer: (p: ICellRendererParams<EventRow>) => (
          <ActorMark actor={p.value} />
        ),
      },
      {
        field: "kind",
        headerName: "Event",
        flex: 0.9,
        minWidth: 140,
        cellClass: "font-mono text-[11.5px] text-ink-soft",
      },
      {
        field: "summary",
        headerName: "What happened",
        flex: 3,
        minWidth: 260,
        tooltipField: "summary",
      },
    ],
    []
  )

  return (
    <GridShell
      api={api}
      filename="hito-audit-trail.csv"
      placeholder="Filter the audit trail…"
      onFilter={(value) => api?.setGridOption("quickFilterText", value)}
    >
      <div className="ag-theme-quartz hito-grid" style={{ height: 420 }}>
        <AgGridReact
          theme="legacy"
          rowData={rows}
          columnDefs={columns}
          defaultColDef={BASE_COL}
          headerHeight={32}
          rowHeight={46}
          getRowId={(p) => p.data.id}
          overlayNoRowsTemplate="Nothing has happened yet."
          onGridReady={(event: GridReadyEvent) => setApi(event.api)}
        />
      </div>
    </GridShell>
  )
}

export function AgentRunsGrid({ rows }: { rows: AgentRun[] }) {
  const [api, setApi] = useState<GridApi | null>(null)
  const gridRef = useRef<AgGridReact>(null)

  const columns = useMemo<ColDef[]>(
    () => [
      { field: "agent", headerName: "Agent", flex: 1.1, minWidth: 130,
        cellClass: "font-medium" },
      {
        field: "engine",
        headerName: "Engine",
        flex: 0.8,
        minWidth: 100,
        cellRenderer: (p: ICellRendererParams<AgentRun>) => (
          <span
            className={
              p.value === "claude"
                ? "font-mono text-[11.5px] text-teal"
                : "font-mono text-[11.5px] text-ink-faint"
            }
          >
            {p.value}
          </span>
        ),
      },
      { field: "model", headerName: "Model", flex: 1.2, minWidth: 140,
        cellClass: "font-mono text-[11.5px] text-ink-soft" },
      { field: "verdict", headerName: "Result", flex: 1, minWidth: 110 },
      {
        field: "latency_ms",
        headerName: "Latency",
        flex: 0.7,
        minWidth: 90,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: (p) => (p.value ? `${p.value} ms` : "—"),
      },
      {
        headerName: "Tokens",
        flex: 0.8,
        minWidth: 110,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end font-mono text-[11.5px]",
        valueGetter: (p) =>
          p.data?.input_tokens
            ? `${p.data.input_tokens} → ${p.data.output_tokens}`
            : "—",
      },
      {
        field: "cost_usd",
        headerName: "Cost",
        flex: 0.7,
        minWidth: 90,
        type: "numericColumn",
        headerClass: "ag-right-aligned-header",
        cellClass: "tabular justify-end",
        valueFormatter: (p) => (p.value ? `$${Number(p.value).toFixed(5)}` : "$0"),
      },
    ],
    []
  )

  const onFilter = useCallback(
    (value: string) => api?.setGridOption("quickFilterText", value),
    [api]
  )

  return (
    <GridShell
      api={api}
      filename="hito-agent-runs.csv"
      placeholder="Filter agent runs…"
      onFilter={onFilter}
    >
      <div className="ag-theme-quartz hito-grid" style={{ height: 320 }}>
        <AgGridReact
          ref={gridRef}
          theme="legacy"
          rowData={rows}
          columnDefs={columns}
          defaultColDef={BASE_COL}
          headerHeight={32}
          rowHeight={40}
          getRowId={(p) => p.data.id}
          overlayNoRowsTemplate="No agent has run yet."
          onGridReady={(event: GridReadyEvent) => setApi(event.api)}
        />
      </div>
    </GridShell>
  )
}
