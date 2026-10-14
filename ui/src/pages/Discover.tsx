import { Download, Loader2, MessageCircle, Search as SearchIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { PickCardView } from '@/components/chat/PickCarousel'
import { MediaTile } from '@/components/MediaCard'
import { Button, Input } from '@/components/ui/primitives'
import { type AdultPicks, api, type Recommendations } from '@/lib/api'
import { type PickCard, searchPrompt } from '@/lib/picks'
import { cn } from '@/lib/utils'

const KINDS = [
  { id: 'movie', label: 'Movies' },
  { id: 'series', label: 'Series' },
  { id: 'anime', label: 'Anime' },
]
const ADULT = { id: 'adult', label: 'Adult' }
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
  const [adultOn, setAdultOn] = useState(false)
  useEffect(() => {
    // Settings answer at once; /api/status pings every service and can be slow.
    api
      .settings()
      .then((st) => setAdultOn(Boolean(st.sections.adult?.MAESTARR_ADULT_CONTENT)))
      .catch(() => undefined)
  }, [])
  const kinds = adultOn ? [...KINDS, ADULT] : KINDS
  const adult = kind === 'adult'
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
    if (kind === 'adult') return
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
            {adult
              ? 'New scenes from the studios and performers in your Whisparr library.'
              : data?.based_on.length
                ? `Tuned to ${data.based_on.slice(0, 4).join(', ')}`
                : 'Picks from your own watch history.'}
          </p>
        </header>
        <div className="flex flex-wrap items-center gap-3">
          <div className="glass flex rounded-xl p-1">
            {kinds.map((k) => (
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
                {k.id === 'adult' && <span className="ml-1.5 text-[10px] text-primary">18+</span>}
              </button>
            ))}
          </div>
          {!adult && (
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
          )}
          {loading && !adult && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        </div>

        {adult && <AdultPanel onSearch={(c) => ask(searchPrompt(c))} />}

        {!adult && error && (
          <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">
              {error.includes('tmdb') ? 'Picks need a TMDB key.' : 'No picks yet.'}
            </p>
            <p className="mt-1">
              {error.includes('tmdb')
                ? 'TMDB is free (themoviedb.org → Settings → API). Your watch history comes from Jellyfin, Trakt or AniList, or from your library until you have one.'
                : error}{' '}
              <button
                className="text-primary underline"
                onClick={() => navigate('/settings/discovery')}
              >
                Open settings
              </button>
            </p>
          </div>
        )}

        {!adult && data && !error && (
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

function AdultPanel({ onSearch }: { onSearch: (c: PickCard) => void }) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<{ key: string; data?: AdultPicks; error?: string } | null>(
    null,
  )
  const loading = result?.key !== query

  useEffect(() => {
    let alive = true
    api
      .adult(query || undefined)
      .then((d) => alive && setResult({ key: query, data: d }))
      .catch((e) => alive && setResult({ key: query, error: (e as Error).message }))
    return () => {
      alive = false
    }
  }, [query])

  const data = result?.data
  return (
    <div className="space-y-5">
      <form
        className="flex max-w-xl gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(draft.trim())
        }}
      >
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Search StashDB: a studio, performer or theme"
            className="pl-9"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        {query && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setDraft('')
              setQuery('')
            }}
          >
            For you
          </Button>
        )}
      </form>
      {!query && data?.based_on.length ? (
        <p className="text-xs text-muted-foreground">Tuned to {data.based_on.join(', ')}</p>
      ) : null}
      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {query ? 'Searching StashDB…' : 'Reading your Whisparr library and StashDB…'}
        </div>
      )}
      {!loading && result?.error && (
        <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">{result.error}</div>
      )}
      {!loading && data && data.scenes.length === 0 && (
        <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">Nothing found.</div>
      )}
      {data && !result?.error && (
        <div
          className={cn(
            'grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
            loading && 'opacity-60',
          )}
        >
          {data.scenes.map((c) => (
            <PickCardView
              key={c.stash_id ?? c.title}
              card={{ ...c, why: c.why?.[0] ?? '' } as PickCard}
              onSearch={onSearch}
              className="w-full"
              label="Get"
            />
          ))}
        </div>
      )}
    </div>
  )
}
