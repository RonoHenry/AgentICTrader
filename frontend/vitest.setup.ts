import '@testing-library/jest-dom'
import { vi } from 'vitest'
import React from 'react'

// Mock ResizeObserver since jsdom doesn't support it
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Mock next/navigation (used by NavSidebar and other components)
vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}))

// Mock next/link to render a plain anchor tag in tests
vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    className,
    ...props
  }: {
    href: string
    children: React.ReactNode
    className?: string
    [key: string]: unknown
  }) =>
    React.createElement('a', { href, className, ...props }, children),
}))

// Recharts uses SVGElement.getTotalLength — stub it for jsdom
if (typeof window !== 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).SVGElement = class SVGElement extends HTMLElement {}
}
