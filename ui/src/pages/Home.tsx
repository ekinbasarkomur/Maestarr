import { ArrowRight, HardDrive, Loader2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { MediaTile } from '@/components/MediaCard'
import { Badge, Button, Panel } from '@/components/ui/primitives'
import { api, type Overview, type Recommendations } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
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

  useEffect(() => {
    api
      .overview()
      .then(setOverview)
      .catch(() => setOverview(null))
    api
      .recommendations('movie')
      .then(setPicks)
      .catch((e) => setPicksError((e as Error).message))
  }, [])

  const ask = (text: string) => {
    if (!text.trim()) return
    navigate('/chat', { state: { prompt: text.trim() } })
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
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
          <section className="grid gap-4 lg:grid-cols-3" aria-busy="true">
            <Panel className="h-44 animate-pulse lg:col-span-2" />
            <Panel className="h-44 animate-pulse" />
          </section>
        )}

        {overview && (
          <section className="grid gap-4 lg:grid-cols-3">
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
          {!picks && !picksError && (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Reading your history…
            </div>
          )}
          {picksError && (
            <p className="py-6 text-sm text-muted-foreground">
              Recommendations need TMDB and a watch history (Jellyfin, Trakt or AniList) — add them
              in{' '}
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
              {picks.recommendations.slice(0, 12).map((r) => (
                <MediaTile
                  key={`${r.kind}-${r.tmdb_id}`}
                  title={r.title}
                  year={r.year}
                  poster={r.poster_url}
                  kind={r.kind}
                  rating={r.imdb_rating ?? r.rating}
                  inLibrary={r.in_library}
                  onClick={() =>
                    ask(
                      `Tell me about ${r.title} (${r.year ?? ''}, tmdb ${r.tmdb_id}) and whether I would like it.`,
                    )
                  }
                />
              ))}
            </div>
          )}
        </section>

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
