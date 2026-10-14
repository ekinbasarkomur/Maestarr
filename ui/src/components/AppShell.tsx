import { Compass, Home, LogOut, MessageSquare, Settings } from 'lucide-react'
import { Suspense } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'

import { Logo, Spinner, StatusDot } from '@/components/ui/primitives'
import { useStatus } from '@/hooks/useStatus'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/chat', label: 'Chat', icon: MessageSquare, end: false },
  { to: '/discover', label: 'Discover', icon: Compass, end: false },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
]

export function AppShell() {
  const { refresh, state } = useAuth()
  const navigate = useNavigate()
  const status = useStatus()

  const logout = async () => {
    await api.logout()
    await refresh()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-full">
      <aside className="glass-strong hidden w-[72px] shrink-0 flex-col items-center gap-2 border-r border-white/[0.06] py-4 md:flex">
        <NavLink to="/" className="mb-3" title="Maestarr">
          <Logo className="size-9" />
        </NavLink>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={label}
            className={({ isActive }) =>
              cn(
                'group flex w-14 flex-col items-center gap-1 rounded-xl py-2 text-[10px] font-medium transition',
                isActive
                  ? 'bg-white/[0.08] text-foreground'
                  : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
              )
            }
          >
            <Icon className="size-5" />
            {label}
          </NavLink>
        ))}
        <div className="mt-auto flex flex-col items-center gap-3">
          <span
            title={
              status
                ? `${status.model}${status.model_ready ? '' : ' — not configured'}`
                : 'Checking…'
            }
          >
            <StatusDot state={!status ? 'off' : status.model_ready ? 'ok' : 'down'} />
          </span>
          <button
            onClick={logout}
            title={`Sign out ${state?.user?.username ?? ''}`}
            className="rounded-lg p-2 text-muted-foreground transition hover:bg-white/[0.05] hover:text-foreground"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </aside>
      <main className="relative min-w-0 flex-1 pb-16 md:pb-0">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <Spinner />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>
      <nav className="glass-strong fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-white/[0.06] py-2 md:hidden">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex flex-col items-center gap-0.5 px-3 text-[10px]',
                isActive ? 'text-foreground' : 'text-muted-foreground',
              )
            }
          >
            <Icon className="size-5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
