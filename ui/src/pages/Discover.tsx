import { Download, Loader2, MessageCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { MediaTile } from '@/components/MediaCard'
import { Button } from '@/components/ui/primitives'
import { api, type Recommendations } from '@/lib/api'
import { cn } from '@/lib/utils'

const KINDS = [
  { id: 'movie', label: 'Movies' },
  { id: 'series', label: 'Series' },
  { id: 'anime', label: 'Anime' },
]
const MOODS = [
  'melancholic',
  'cozy',
  'mind-bending',
  'tense',
  'funny',
  'romantic',
  'epic',
  'inspiring',
  'scary',
]

export default function DiscoverPage() {
  const navigate = useNavigate()
  const [kind, setKind] = useState('movie')
  const [mood, setMood] = useState<string | null>(null)
  // Results are keyed by the request they answer; "loading" is simply "the
  // latest result is for another request".
  const key = `${kind}|${mood ?? ''}`
  const [result, setResult] = useState<{
    key: string
    data?: Recommendations
    error?: string
  } | null>(null)
  const loading = result?.key !== key
  const data = result?.data ?? null
  const error = result?.key === key ? (result.error ?? null) : null

  useEffect(() => {
    let alive = true
    api
      .recommendations(kind, mood ?? undefined)
      .then((d) => alive && setResult({ key: `${kind}|${mood ?? ''}`, data: d }))
      .catch(
        (e) => alive && setResult({ key: `${kind}|${mood ?? ''}`, error: (e as Error).message }),
      )
    return () => {
      alive = false
    }
  }, [kind, mood])

  const ask = (prompt: string) => navigate('/chat', { state: { prompt } })

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 px-5 py-10 sm:px-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Discover</h1>
          <p className="text-sm text-muted-foreground">
            {data?.based_on.length
              ? `Tuned to ${data.based_on.slice(0, 4).join(', ')}`
              : 'Picks from your own watch history.'}
          </p>
        </header>
        <div className="flex flex-wrap items-center gap-3">
          <div className="glass flex rounded-xl p-1">
            {KINDS.map((k) => (
              <button
                key={k.id}
                onClick={() => setKind(k.id)}
                className={cn(
                  'rounded-lg px-4 py-1.5 text-sm transition',
                  kind === k.id
                    ? 'bg-white/[0.1] text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {k.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {MOODS.map((m) => (
              <button
                key={m}
                onClick={() => setMood(mood === m ? null : m)}
                className={cn(
                  'rounded-full px-3 py-1 text-xs ring-1 transition',
                  mood === m
                    ? 'bg-primary/15 text-primary ring-primary/40'
                    : 'bg-white/[0.03] text-muted-foreground ring-white/[0.08] hover:text-foreground',
                )}
              >
                {m}
              </button>
            ))}
          </div>
          {loading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        </div>

        {error && (
          <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">
            <p>{error}</p>
            <p className="mt-2">
              Recommendations need TMDB and a watch history (Jellyfin, Trakt or AniList).{' '}
              <button
                className="text-primary underline"
                onClick={() => navigate('/settings/discovery')}
              >
                Open settings
              </button>
            </p>
          </div>
        )}

        {data && !error && (
          <div
            className={cn(
              'grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 lg:grid-cols-5',
              loading && 'opacity-60',
            )}
          >
            {data.recommendations.map((r) => (
              <MediaTile
                key={`${r.kind}-${r.tmdb_id}-${r.title}`}
                title={r.title}
                year={r.year}
                poster={r.poster_url}
                kind={r.kind}
                rating={r.imdb_rating ?? r.rating}
                inLibrary={r.in_library}
                onClick={() =>
                  ask(
                    `Tell me about ${r.title} (${r.year ?? ''}, tmdb ${r.tmdb_id}) and why I'd like it.`,
                  )
                }
                footer={
                  <div className="mt-1.5 space-y-2">
                    {r.why?.slice(0, 2).map((w) => (
                      <p
                        key={w}
                        className="line-clamp-2 text-[11px] leading-snug text-muted-foreground"
                      >
                        {w}
                      </p>
                    ))}
                    <div className="flex gap-1.5">
                      {!r.in_library && (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 px-2 text-xs"
                          onClick={() =>
                            ask(
                              `Get ${r.title} (${r.year ?? ''}, tmdb ${r.tmdb_id}) for me — judge the releases first.`,
                            )
                          }
                        >
                          <Download className="size-3.5" />
                          Get
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        onClick={() => ask(`Is ${r.title} (${r.year ?? ''}) right for me tonight?`)}
                      >
                        <MessageCircle className="size-3.5" />
                        Ask
                      </Button>
                    </div>
                  </div>
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
