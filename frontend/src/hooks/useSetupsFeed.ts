'use client'

import { useEffect, useRef, useState } from 'react'
import type { Setup } from '@/types'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'
const POLL_INTERVAL_MS = 10_000

// Use a loose type for the socket ref to avoid dynamic import type issues
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SocketRef = any

export function useSetupsFeed() {
  const [setups, setSetups] = useState<Setup[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const socketRef = useRef<SocketRef>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const addSetup = (setup: Setup) => {
    setSetups((prev: Setup[]) => {
      // Deduplicate by id, newest first
      const filtered = prev.filter((s: Setup) => s.id !== setup.id)
      return [setup, ...filtered].slice(0, 100)
    })
  }

  const startPolling = () => {
    if (pollTimerRef.current) return
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(
          `${WS_URL.replace('ws://', 'http://').replace('wss://', 'https://')}/setups`,
          { cache: 'no-store' }
        )
        if (res.ok) {
          const data: Setup[] = await res.json()
          setSetups(data.slice(0, 100))
        }
      } catch {
        // silently ignore polling errors
      }
    }, POLL_INTERVAL_MS)
  }

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  useEffect(() => {
    let mounted = true

    const connect = async () => {
      try {
        const { io } = await import('socket.io-client')
        const socket = io(WS_URL, {
          transports: ['websocket'],
          reconnectionAttempts: 5,
          reconnectionDelay: 2000,
        })

        socketRef.current = socket

        socket.on('connect', () => {
          if (!mounted) return
          setConnected(true)
          setError(null)
          stopPolling()
        })

        socket.on('setup', (data: Setup) => {
          if (!mounted) return
          addSetup(data)
        })

        socket.on('disconnect', () => {
          if (!mounted) return
          setConnected(false)
          startPolling()
        })

        socket.on('connect_error', (err: Error) => {
          if (!mounted) return
          setError(err.message)
          setConnected(false)
          startPolling()
        })
      } catch (err) {
        if (!mounted) return
        setError(err instanceof Error ? err.message : 'WebSocket unavailable')
        startPolling()
      }
    }

    connect()

    return () => {
      mounted = false
      socketRef.current?.disconnect()
      stopPolling()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { setups, connected, error }
}
