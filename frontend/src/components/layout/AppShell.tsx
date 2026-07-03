import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard,
  ListOrdered,
  Bitcoin,
  Receipt,
  Upload,
  Settings,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/operaciones', label: 'Operaciones', icon: ListOrdered },
  { to: '/crypto', label: 'Crypto', icon: Bitcoin },
  { to: '/fiscalidad', label: 'Fiscalidad', icon: Receipt },
  { to: '/importar', label: 'Importar', icon: Upload },
  { to: '/ajustes', label: 'Ajustes', icon: Settings },
]

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-[220px] flex-shrink-0 flex-col border-r border-border-subtle bg-bg2">
        <div className="flex h-14 items-center gap-2 px-5">
          <img src="/app-icon.png" alt="" className="size-7 shrink-0" />
          <span className="text-sm font-semibold text-txt">Global Position</span>
        </div>
        <nav className="flex flex-col gap-0.5 px-3 py-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-[var(--radius-card)] px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-accent/15 text-accent2'
                    : 'text-txt2 hover:bg-card2 hover:text-txt',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 text-[11px] text-txt3">
          Cartera personal · EUR
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
