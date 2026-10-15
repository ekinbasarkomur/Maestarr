import { Check, Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button, Field, Select, Toggle } from '@/components/ui/primitives'
import { api, type CacheStatus, type Sections } from '@/lib/api'

const DATA_HOURS: [number, string][] = [
  [12, 'Every 12 hours'],
  [24, 'Every day'],
  [168, 'Every week'],
]
const PICK_HOURS: [number, string][] = [
  [6, 'Every 6 hours'],
  [12, 'Every 12 hours'],
  [24, 'Every day'],
  [168, 'Every week'],
]

function ago(ts: number | null): string {
  if (!ts) return 'never'
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 90) return 'just now'
  if (s < 5400) return `${Math.round(s / 60)} min ago`
  if (s < 129600) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} days ago`
}

/** Settings → General → Caching: what is kept, how often it is rebuilt, and a refresh button. */
export function CachingSettings({
  sections,
  onSaved,
}: {
  sections: Sections
  onSaved: (s: Sections) => void
}) {
  const c = sections.caching ?? {}
  const [status, setStatus] = useState<CacheStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .cacheStatus()
      .then(setStatus)
      .catch(() => undefined)
  }, [])
  useEffect(() => load(), [load])
  // While a refresh runs, look again every few seconds.
  useEffect(() => {
    if (!status?.running) return
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [status?.running, load])

  const save = async (fields: Record<string, unknown>) => {
    setError(null)
    try {
      onSaved((await api.saveSettings(fields)).sections)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const refresh = async () => {
    await api.cacheRefresh().catch((e) => setError((e as Error).message))
    setStatus((s) => (s ? { ...s, running: true } : s))
    setTimeout(load, 1500)
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Watch history, libraries, favourites and your taste profile are kept between visits, so
        pages open at once. When they get older than the interval they are refreshed the next time
        you open Maestarr — or on a schedule, if you switch background refresh on.
      </p>
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-3">
          <Toggle
            checked={Boolean(c.MAESTARR_BACKGROUND_REFRESH)}
            onChange={(v) => save({ MAESTARR_BACKGROUND_REFRESH: v })}
            label="Refresh in the background"
            description="Keeps the data warm even when nobody opens Maestarr."
          />
          <Field label="History and libraries" htmlFor="data-hours">
            <Select
              id="data-hours"
              value={String(c.MAESTARR_DATA_REFRESH_HOURS ?? 24)}
              onChange={(e) => save({ MAESTARR_DATA_REFRESH_HOURS: Number(e.target.value) })}
            >
              {DATA_HOURS.map(([h, label]) => (
                <option key={h} value={h}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="space-y-3">
          <Toggle
            checked={c.MAESTARR_PICKS_REFRESH !== false}
            onChange={(v) => save({ MAESTARR_PICKS_REFRESH: v })}
            label="Refresh picks automatically"
            description="New shelves when you visit after the interval; off: only by hand."
          />
          <Field label="Picks and shelves" htmlFor="pick-hours">
            <Select
              id="pick-hours"
              value={String(c.MAESTARR_PICKS_REFRESH_HOURS ?? 24)}
              onChange={(e) => save({ MAESTARR_PICKS_REFRESH_HOURS: Number(e.target.value) })}
              disabled={c.MAESTARR_PICKS_REFRESH === false}
            >
              {PICK_HOURS.map(([h, label]) => (
                <option key={h} value={h}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.06] pt-4">
        <Button variant="secondary" onClick={() => void refresh()} disabled={status?.running}>
          {status?.running ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          {status?.running ? 'Refreshing…' : 'Refresh now'}
        </Button>
        <p className="text-xs text-muted-foreground">
          Data {ago(status?.data_refreshed_at ?? null)} · Picks{' '}
          {ago(status?.picks_refreshed_at ?? null)}
        </p>
        {status && !status.running && !status.last_error && status.data_refreshed_at && (
          <Check className="size-4 text-success" />
        )}
      </div>
      {(error || status?.last_error) && (
        <p className="text-xs text-danger">{error ?? status?.last_error}</p>
      )}
    </div>
  )
}
