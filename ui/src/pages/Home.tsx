import { ArrowRight, HardDrive, Loader2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { type DetailsTarget } from '@/components/DetailsModal'
import { MediaTile } from '@/components/MediaCard'
import { Shelf } from '@/components/Shelf'
import { Badge, Button, Panel } from '@/components/ui/primitives'
import {
  api,
  type DiscoverRows,
  type MediaRef,
  type Overview,
  type Recommendations,
} from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { sendFeedback, targetFrom, useDetails } from '@/lib/useDetails'
import { cn } from '@/lib/utils'

const SUGGESTIONS = [
  'Recommend me a melancholic film for tonight',
  'What is downloading right now?',
  'How much disk space is left?',
  'Find the best release of a series I name',
]

function greeting() {
  const h = new Date().getHours()
  if (h < 5) return 'Good night'
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function HomePage() {
  const { state } = useAuth()
  const navigate = useNavigate()
  // undefined while loading, null when the stack could not be read
  const [overview, setOverview] = useState<Overview | null | undefined>(undefined)
  const [picks, setPicks] = useState<Recommendations | null>(null)
  const [picksError, setPicksError] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [taste, setTaste] = useState<string[]>([])
  const [shelves, setShelves] = useState<DiscoverRows | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () =>
      api
        .overview()
        .then((o) => {
          if (!alive) return
          if (o.loading) timer = setTimeout(load, 5000)
          else setOverview(o)
        })
        .catch(() => alive && setOverview(null))
    void load()
    api
      .taste()
      .then((t) => alive && setTaste(t.tags))
      .catch(() => undefined)
    api
      .rows()
      .then((r) => alive && setShelves(r))
      .catch(() => undefined)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])

  // Picks for tonight, filtered by the chosen tags.
  const tagKey = tags.join(',')
  useEffect(() => {
    let alive = true
    api
      .recommendations('movie', undefined, tagKey ? tagKey.split(',') : undefined)
      .then((p) => {
        if (!alive) return
        setPicks(p)
        setPicksError(null)
      })
      .catch((e) => alive && setPicksError((e as Error).message))
    return () => {
      alive = false
    }
  }, [tagKey])

  const ask = (text: string) => {
    if (!text.trim()) return
    navigate('/chat', { state: { prompt: text.trim() } })
  }
  const details = useDetails(ask)
  const dismiss = (r: MediaRef) => {
    sendFeedback(r.kind, r.tmdb_id, 'dismiss', r.title)
    setHidden((h) => new Set(h).add(`${r.kind}-${r.tmdb_id}`))
  }
  const visible = (r: MediaRef) => !hidden.has(`${r.kind}-${r.tmdb_id}`)

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      {details.modal}
      <div className="mx-auto max-w-6xl space-y-10 px-5 py-10 sm:px-8">
        <section className="space-y-5">
          <div>
            <p className="text-sm text-muted-foreground">
              {greeting()}, {state?.user?.username}
            </p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">
              What shall we play?
            </h1>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              ask(prompt)
            }}
            className="glass flex items-center gap-2 rounded-2xl p-2 pl-4"
          >
            <Sparkles className="size-5 shrink-0 text-primary" />
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask for a film, a series, a release, or anything about your library…"
              className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground/70"
            />
            <Button type="submit" variant="primary" disabled={!prompt.trim()}>
              Ask
              <ArrowRight className="size-4" />
            </Button>
          </form>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => ask(s)}
                className="rounded-full bg-white/[0.04] px-3 py-1.5 text-xs text-muted-foreground ring-1 ring-white/[0.08] transition hover:bg-white/[0.08] hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        </section>

        {overview === undefined && (
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-busy="true">
            <Panel className="h-44 animate-pulse lg:col-span-2" />
            <Panel className="h-44 animate-pulse" />
          </section>
        )}

        {overview && (
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel className="p-5 lg:col-span-2">
              <SectionTitle
                title="Downloading"
                subtitle={`${overview.queue.length} in the queue`}
              />
              {overview.queue.length === 0 ? (
                <p className="py-6 text-sm text-muted-foreground">Nothing is downloading.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {overview.queue.map((q) => (
                    <li key={`${q.app}-${q.queue_id}`} className="space-y-1.5">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="min-w-0 flex-1 truncate">{q.title}</span>
                        <Badge>{q.app}</Badge>
                        {q.problems.length > 0 && <Badge tone="warning">needs attention</Badge>}
                        <span className="w-12 text-right text-xs text-muted-foreground tabular-nums">
                          {q.progress_pct != null ? `${Math.round(q.progress_pct)}%` : ''}
                        </span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <div
                          className="h-full rounded-full bg-primary/80"
                          style={{ width: `${q.progress_pct ?? 0}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel className="p-5">
              <SectionTitle
                title="Library"
                subtitle={`${overview.counts.series} series · ${overview.counts.movies} movies`}
              />
              <div className="mt-4 space-y-4">
                {overview.disks.slice(0, 3).map((d) => {
                  const used = d.total_gb ? 100 - (d.free_gb / d.total_gb) * 100 : 0
                  return (
                    <div key={d.path} className="space-y-1.5">
                      <div className="flex items-center gap-2 text-xs">
                        <HardDrive className="size-3.5 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate font-mono text-muted-foreground">
                          {d.path}
                        </span>
                        <span className="tabular-nums">{Math.round(d.free_gb)} GB free</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                        <div
                          className={cn(
                            'h-full rounded-full',
                            used > 90 ? 'bg-danger' : used > 75 ? 'bg-primary' : 'bg-success/80',
                          )}
                          style={{ width: `${used}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
                {overview.disks.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    Connect Sonarr or Radarr to see disks.
                  </p>
                )}
              </div>
            </Panel>
          </section>
        )}

        <section>
          <SectionTitle
            title="Picks for tonight"
            subtitle={
              picks?.based_on.length
                ? `Because you watched ${picks.based_on.slice(0, 3).join(', ')}`
                : 'From your watch history'
            }
            action={
              <Button variant="ghost" size="sm" onClick={() => navigate('/discover')}>
                Discover
                <ArrowRight className="size-3.5" />
              </Button>
            }
          />
          {taste.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {taste.slice(0, 14).map((t) => {
                const on = tags.includes(t)
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTags((v) => (on ? v.filter((x) => x !== t) : [...v, t]))}
                    className={cn(
                      'rounded-full px-3 py-1 text-xs ring-1 transition',
                      on
                        ? 'bg-primary/15 text-primary ring-primary/40'
                        : 'bg-white/[0.03] text-muted-foreground ring-white/[0.08] hover:text-foreground',
                    )}
                  >
                    {t}
                  </button>
                )
              })}
            </div>
          )}
          {!picks && !picksError && (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Reading your history…
            </div>
          )}
          {picksError && (
            <p className="py-6 text-sm text-muted-foreground">
              Recommendations need Seerr or a TMDB key, plus some history (Jellyfin, Trakt, AniList
              or just your library) — set them up in{' '}
              <button
                className="text-primary underline"
                onClick={() => navigate('/settings/discovery')}
              >
                Settings
              </button>
              .
            </p>
          )}
          {picks && (
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
              {picks.recommendations
                .filter(visible)
                .slice(0, 12)
                .map((r) => (
                  <MediaTile
                    onDismiss={() => dismiss(r)}
                    key={`${r.kind}-${r.tmdb_id}`}
                    title={r.title}
                    year={r.year}
                    poster={r.poster_url}
                    kind={r.kind}
                    rating={r.imdb_rating ?? r.rating}
                    inLibrary={r.in_library}
                    onClick={() => details.open(targetFrom(r))}
                  />
                ))}
            </div>
          )}
        </section>

        {shelves && shelves.rows.length > 0 && (
          <div className="space-y-10">
            {shelves.rows
              .filter((row) => row.id !== 'picks-movie')
              .slice(0, 4)
              .map((row) => (
                <Shelf
                  key={row.id}
                  row={{ ...row, items: row.items.filter(visible) }}
                  onOpen={(r) => details.open(targetFrom(r))}
                  onDismiss={row.id === 'waiting' ? undefined : dismiss}
                />
              ))}
          </div>
        )}

        {overview && overview.recently_added.length > 0 && (
          <section>
            <SectionTitle title="Recently added" />
            <div className="mt-4 grid grid-cols-3 gap-4 sm:grid-cols-6 lg:grid-cols-8">
              {overview.recently_added.slice(0, 16).map((m) => (
                <MediaTile
                  key={`${m.kind}-${m.id}`}
                  title={m.title}
                  year={m.year}
                  poster={m.poster}
                  kind={m.kind}
                  inLibrary
                  onClick={() =>
                    details.open({
                      kind: m.kind as DetailsTarget['kind'],
                      tmdb_id: m.tmdb_id,
                      tvdb_id: m.tvdb_id,
                      title: m.title,
                      year: m.year,
                      poster: m.poster,
                    })
                  }
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export function SectionTitle({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
