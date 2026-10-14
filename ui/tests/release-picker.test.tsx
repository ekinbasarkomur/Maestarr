import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReleasePicker, type ReleaseList } from '@/components/chat/ToolPart'

const row = (n: number, extra: Partial<ReleaseList['assessed'][number]> = {}) => ({
  guid: `g${n}`,
  title: `Release ${n}`,
  size_gb: n,
  score: 80 - n,
  indexer_seeders: 10,
  live_seeders: 9,
  swarm_source: 'scrape',
  coverage: null,
  bitrate_mbps: null,
  blockers: [],
  ...extra,
})

const data: ReleaseList = {
  subject: 'Se7en (1995)',
  decided_by: 'llm',
  verdict: { chosen_guid: 'g1', runner_up_guid: 'g2', rationale: 'Best bitrate.' },
  assessed: [1, 2, 3, 4, 5, 6].map((n) => row(n, n === 6 ? { blockers: ['likely fake'] } : {})),
  results_id: 'abc123',
  more_available: 40,
  next_offset: 0,
}

describe('ReleasePicker', () => {
  it('lists the top five with a download button each and asks for the right one', async () => {
    const onAsk = vi.fn()
    render(<ReleasePicker data={data} onAsk={onAsk} />)
    expect(screen.getAllByRole('button', { name: /Download/ })).toHaveLength(5)
    expect(screen.getByText('Recommended')).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /Download/ })[1])
    expect(onAsk).toHaveBeenCalledWith('Download "Release 2" (guid g2) for Se7en (1995).')
  })

  it('offers more results from the same search', async () => {
    const onAsk = vi.fn()
    render(<ReleasePicker data={data} onAsk={onAsk} />)
    await userEvent.click(screen.getByRole('button', { name: /Show more results \(40\)/ }))
    expect(onAsk).toHaveBeenCalledWith(
      'Show more results for Se7en (1995) (results abc123, offset 0).',
    )
    await userEvent.click(screen.getByRole('button', { name: /Show all 6/ }))
    expect(screen.getByText('likely fake')).toBeInTheDocument()
  })
})
