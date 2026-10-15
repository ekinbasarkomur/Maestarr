import { useCallback, useState } from 'react'

import { DetailsModal, type DetailsTarget } from '@/components/DetailsModal'
import { api, type MediaRef } from '@/lib/api'
import { detailsToCard, searchPrompt } from '@/lib/picks'

/** Opening a title counts as interest; searching it counts more. Never blocks the UI. */
export function sendFeedback(
  kind: string,
  tmdbId: number | null | undefined,
  action: 'open' | 'search' | 'add' | 'dismiss',
  title?: string,
) {
  if (!tmdbId || kind === 'scene') return
  api.feedback({ kind, tmdb_id: tmdbId, action, title }).catch(() => undefined)
}

export function targetFrom(r: MediaRef): DetailsTarget {
  return {
    kind: (r.kind === 'tv' ? 'series' : r.kind) as DetailsTarget['kind'],
    tmdb_id: r.tmdb_id,
    tvdb_id: r.tvdb_id,
    title: r.title,
    year: r.year,
    poster: r.poster_url,
    why: r.why?.[0],
  }
}

/** The details popup plus the feedback it sends, for any page that lists titles. */
export function useDetails(ask: (prompt: string) => void) {
  const [target, setTarget] = useState<DetailsTarget | null>(null)
  const open = useCallback((t: DetailsTarget) => {
    setTarget(t)
    sendFeedback(t.kind, t.tmdb_id, 'open', t.title ?? undefined)
  }, [])
  const modal = target ? (
    <DetailsModal
      target={target}
      onClose={() => setTarget(null)}
      onGet={(d) => {
        sendFeedback(d.kind, d.tmdb_id ?? target.tmdb_id, 'search', d.title)
        setTarget(null)
        ask(searchPrompt(detailsToCard(d)))
      }}
      onAsk={(d) => {
        setTarget(null)
        ask(`Tell me more about ${d.title}${d.year ? ` (${d.year})` : ''} — is it right for me?`)
      }}
    />
  ) : null
  return { open, modal }
}
