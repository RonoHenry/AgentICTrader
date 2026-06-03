import type { Metadata } from 'next'
import './globals.css'
import { NavSidebar } from '@/components/NavSidebar'

export const metadata: Metadata = {
  title: 'AgentICTrader.AI',
  description: 'Autonomous intelligent trading platform dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="flex min-h-screen bg-slate-50">
        <NavSidebar />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </body>
    </html>
  )
}
