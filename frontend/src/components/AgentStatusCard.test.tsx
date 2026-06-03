import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentStatusCard } from './AgentStatusCard'
import type { AgentStatus } from '@/types'

const healthyStatus: AgentStatus = {
  healthy: true,
  kill_switch_active: false,
}

const unhealthyStatus: AgentStatus = {
  healthy: false,
  kill_switch_active: true,
}

describe('AgentStatusCard', () => {
  it('shows "Healthy" when healthy=true', () => {
    render(
      <AgentStatusCard
        status={healthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('health-badge')).toHaveTextContent('Healthy')
  })

  it('shows "Unhealthy" when healthy=false', () => {
    render(
      <AgentStatusCard
        status={unhealthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('health-badge')).toHaveTextContent('Unhealthy')
  })

  it('shows kill switch as Inactive when kill_switch_active=false', () => {
    render(
      <AgentStatusCard
        status={healthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('kill-switch-badge')).toHaveTextContent('Inactive')
  })

  it('shows kill switch as ACTIVE when kill_switch_active=true', () => {
    render(
      <AgentStatusCard
        status={unhealthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('kill-switch-badge')).toHaveTextContent('ACTIVE')
  })

  it('calls onPause when Pause button is clicked', async () => {
    const onPause = vi.fn()
    render(
      <AgentStatusCard
        status={healthyStatus}
        onPause={onPause}
        onResume={vi.fn()}
      />
    )
    await userEvent.click(screen.getByTestId('pause-button'))
    expect(onPause).toHaveBeenCalledOnce()
  })

  it('calls onResume when Resume button is clicked', async () => {
    const onResume = vi.fn()
    render(
      <AgentStatusCard
        status={unhealthyStatus}
        onPause={vi.fn()}
        onResume={onResume}
      />
    )
    await userEvent.click(screen.getByTestId('resume-button'))
    expect(onResume).toHaveBeenCalledOnce()
  })

  it('disables Pause button when kill switch is active', () => {
    render(
      <AgentStatusCard
        status={unhealthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('pause-button')).toBeDisabled()
  })

  it('disables Resume button when kill switch is not active', () => {
    render(
      <AgentStatusCard
        status={healthyStatus}
        onPause={vi.fn()}
        onResume={vi.fn()}
      />
    )
    expect(screen.getByTestId('resume-button')).toBeDisabled()
  })
})
