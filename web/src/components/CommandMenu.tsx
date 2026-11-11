import { useEffect } from "react"
import { Command } from "cmdk"
import {
  BanknoteIcon,
  DatabaseZapIcon,
  FileTextIcon,
  HandCoinsIcon,
  MoonIcon,
  PackageCheckIcon,
  RotateCcwIcon,
  SendIcon,
  SunIcon,
} from "lucide-react"

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import type { Milestone } from "@/lib/api"
import { money } from "@/lib/format"

export interface CommandActions {
  deliver: (milestone: Milestone) => void
  pay: (milestone: Milestone) => void
  chase: (milestone: Milestone) => void
  split: (milestone: Milestone) => void
  seed: () => void
  reset: () => void
  toggleTheme: () => void
  isDark: boolean
}

/**
 * ⌘K palette, built on cmdk. Every action an agent can take is reachable from
 * here, which is also the quickest way to drive the demo without hunting for
 * buttons.
 */
export function CommandMenu({
  open,
  onOpenChange,
  milestones,
  actions,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  milestones: Milestone[]
  actions: CommandActions
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onOpenChange])

  function run(action: () => void) {
    onOpenChange(false)
    action()
  }

  const deliverable = milestones.filter(
    (m) => m.status === "pending" || m.status === "delivered"
  )
  const payable = milestones.filter(
    (m) => m.status === "invoiced" || m.status === "overdue"
  )
  const chaseable = milestones.filter((m) => m.status === "overdue")
  const splittable = milestones.filter((m) => m.status === "paid")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="overflow-hidden p-0 sm:max-w-xl"
      >
        <DialogTitle className="sr-only">Command menu</DialogTitle>
        <Command
          loop
          className="[&_[cmdk-input]]:h-11 [&_[cmdk-input]]:w-full [&_[cmdk-input]]:border-b [&_[cmdk-input]]:border-rule [&_[cmdk-input]]:bg-transparent [&_[cmdk-input]]:px-4 [&_[cmdk-input]]:text-[14px] [&_[cmdk-input]]:outline-none"
        >
          <Command.Input placeholder="What should Hito do?" autoFocus />
          <Command.List className="max-h-[360px] overflow-y-auto p-1.5">
            <Command.Empty className="px-4 py-6 text-center text-[13px] text-ink-faint">
              Nothing matches that.
            </Command.Empty>

            {deliverable.length ? (
              <Command.Group heading="Mark as delivered">
                {deliverable.map((milestone) => (
                  <Item
                    key={milestone.id}
                    icon={<PackageCheckIcon className="size-3.5" />}
                    label={milestone.title}
                    hint={money(milestone.amount, milestone.currency)}
                    onSelect={() => run(() => actions.deliver(milestone))}
                  />
                ))}
              </Command.Group>
            ) : null}

            {chaseable.length ? (
              <Command.Group heading="Chase an overdue invoice">
                {chaseable.map((milestone) => (
                  <Item
                    key={milestone.id}
                    icon={<SendIcon className="size-3.5" />}
                    label={milestone.title}
                    hint={`${milestone.days_overdue} days overdue`}
                    onSelect={() => run(() => actions.chase(milestone))}
                  />
                ))}
              </Command.Group>
            ) : null}

            {payable.length ? (
              <Command.Group heading="Simulate the client paying">
                {payable.map((milestone) => (
                  <Item
                    key={milestone.id}
                    icon={<BanknoteIcon className="size-3.5" />}
                    label={milestone.title}
                    hint={money(milestone.amount, milestone.currency)}
                    onSelect={() => run(() => actions.pay(milestone))}
                  />
                ))}
              </Command.Group>
            ) : null}

            {splittable.length ? (
              <Command.Group heading="Split a payment">
                {splittable.map((milestone) => (
                  <Item
                    key={milestone.id}
                    icon={<HandCoinsIcon className="size-3.5" />}
                    label={milestone.title}
                    hint={money(milestone.paid_amount ?? milestone.amount)}
                    onSelect={() => run(() => actions.split(milestone))}
                  />
                ))}
              </Command.Group>
            ) : null}

            <Command.Group heading="Demo">
              <Item
                icon={<DatabaseZapIcon className="size-3.5" />}
                label="Seed this client's payment history"
                hint="3 past invoices"
                onSelect={() => run(actions.seed)}
              />
              <Item
                icon={<FileTextIcon className="size-3.5" />}
                label="Download the sample contract"
                onSelect={() =>
                  run(() => window.open("/api/demo/contract", "_blank"))
                }
              />
              <Item
                icon={<RotateCcwIcon className="size-3.5" />}
                label="Reset everything"
                onSelect={() => run(actions.reset)}
              />
              <Item
                icon={
                  actions.isDark ? (
                    <SunIcon className="size-3.5" />
                  ) : (
                    <MoonIcon className="size-3.5" />
                  )
                }
                label={actions.isDark ? "Switch to light" : "Switch to dark"}
                onSelect={() => run(actions.toggleTheme)}
              />
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  )
}

function Item({
  icon,
  label,
  hint,
  onSelect,
}: {
  icon: React.ReactNode
  label: string
  hint?: string
  onSelect: () => void
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px]"
    >
      <span className="text-ink-faint">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {hint ? (
        <span className="tabular shrink-0 font-mono text-[11.5px] text-ink-faint">
          {hint}
        </span>
      ) : null}
    </Command.Item>
  )
}
