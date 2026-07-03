import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { ClassSlice } from '@/api/types'
import { fmtEur, fmtPct } from '@/lib/format'
import { cn } from '@/lib/utils'

// Stable colour per known class; unknown classes fall back by index.
const CLASS_COLORS: Record<string, string> = {
  Acciones: '#6366f1',
  ETF: '#06b6d4',
  'Oro / Materias primas': '#f59e0b',
  Bonos: '#10b981',
  Cripto: '#f7931a',
}
const FALLBACK = ['#8b5cf6', '#ec4899', '#3b82f6', '#14b8a6', '#a855f7', '#64748b']

function colorFor(name: string, i: number): string {
  return CLASS_COLORS[name] ?? FALLBACK[i % FALLBACK.length]
}

export function ClassBreakdown({ classes }: { classes: ClassSlice[] }) {
  const [open, setOpen] = useState<string | null>(null)
  if (!classes.length) return null

  return (
    <div>
      {/* Stacked proportion bar */}
      <div className="mb-4 flex h-3 w-full overflow-hidden rounded-full bg-card2">
        {classes.map((c, i) => (
          <div
            key={c.name}
            className="h-full"
            style={{ width: `${c.pct}%`, background: colorFor(c.name, i) }}
            title={`${c.name} · ${fmtPct(c.pct, 1)}`}
          />
        ))}
      </div>

      {/* Legend / list */}
      <div className="space-y-1">
        {classes.map((c, i) => {
          const isOpen = open === c.name
          return (
            <div key={c.name} className="rounded-[var(--radius-card)]">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : c.name)}
                className="flex w-full items-center gap-3 px-1 py-1.5 text-left hover:bg-card2"
              >
                <span
                  className="size-3 shrink-0 rounded-[3px]"
                  style={{ background: colorFor(c.name, i) }}
                />
                <span className="flex-1 truncate text-sm text-txt">{c.name}</span>
                <span className="text-sm tabular-nums text-txt2">{fmtEur(c.value)}</span>
                <span className="w-14 text-right text-sm font-medium tabular-nums text-txt">
                  {fmtPct(c.pct, 1)}
                </span>
                <ChevronDown
                  className={cn(
                    'size-4 shrink-0 text-txt3 transition-transform',
                    isOpen && 'rotate-180',
                  )}
                />
              </button>

              {isOpen && (
                <div className="mb-1 ml-6 border-l border-border-subtle pl-3">
                  {c.members.map((m) => (
                    <div
                      key={m.symbol}
                      className="flex items-center gap-2 py-0.5 text-xs text-txt2"
                    >
                      <span className="flex-1 truncate">{m.name}</span>
                      <span className="tabular-nums">{fmtEur(m.value)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
