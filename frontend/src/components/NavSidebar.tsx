'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Bot,
  BookOpen,
  BarChart2,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  {
    href: '/dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
  },
  {
    href: '/agent',
    label: 'Agent',
    icon: Bot,
  },
  {
    href: '/journal',
    label: 'Journal',
    icon: BookOpen,
  },
  {
    href: '/analytics',
    label: 'Analytics',
    icon: BarChart2,
  },
]

export function NavSidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex flex-col w-56 min-h-screen bg-slate-900 text-white shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-slate-700">
        <Zap className="h-5 w-5 text-yellow-400" aria-hidden="true" />
        <span className="font-bold text-sm tracking-wide">
          AgentICTrader
        </span>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-2 py-4 space-y-1" aria-label="Main navigation">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                active
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              )}
              aria-current={active ? 'page' : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-700">
        <p className="text-xs text-slate-500">v0.1.0</p>
      </div>
    </aside>
  )
}
