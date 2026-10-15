import {
  Download,
  Loader2,
  MessageCircle,
  RotateCcw,
  Search as SearchIcon,
  SlidersHorizontal,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { ChipInput } from '@/components/ChipInput'
import { PickCardView } from '@/components/chat/PickCarousel'
import { MediaTile } from '@/components/MediaCard'
import { Button, Input, Select } from '@/components/ui/primitives'
import { type AdultPicks, api, type MediaRef, type SearchParams } from '@/lib/api'
import { type PickCard, searchPrompt } from '@/lib/picks'
import { sendFeedback, targetFrom, useDetails } from '@/lib/useDetails'
import { cn } from '@/lib/utils'

const TABS = [
  { id: 'movie', label: 'Movies' },
  { id: 'series', label: 'Series' },
  { id: 'anime', label: 'Anime' },
]
const ADULT = { id: 'adult', label: 'Adult' }
const LANGUAGES: [string, string][] = [
  ['', 'Any language'],
  ['en', 'English'],
  ['ja', 'Japanese'],
  ['ko', 'Korean'],
  ['tr', 'Turkish'],
  ['fr', 'French'],
  ['es', 'Spanish'],
  ['de', 'German'],
  ['it', 'Italian'],
  ['zh', 'Chinese'],
  ['hi', 'Hindi'],
]

type Filters = Omit<SearchParams, 'kind'>
const EMPTY: Filters = { sort: 'relevance' }

export default function DiscoverPage() {
  const navigate = useNavigate()
  const ask = (prompt: string) => navigate('/chat', { state: { prompt } })
  const details = useDetails(ask)
  const [tab, setTab] = useState('movie')
  const [adultOn, setAdultOn] = useState(false)
  const [taste, setTaste] = useState<{ tags: string[]; genres: string[]; people: string[] } | null>(
    null,
  )

  useEffect(() => {
    // Settings answer at once; /api/status pings every service and can be slow.
    api
      .settings()
      .then((st) => setAdultOn(Boolean(st.sections.adult?.MAESTARR_ADULT_CONTENT)))
      .catch(() => undefined)
    api
      .taste()
      .then(setTaste)
      .catch(() => undefined)
  }, [])

  const tabs = adultOn ? [...TABS, ADULT] : TABS
  return (
    <div className="scroll-thin h-full overflow-x-hidden overflow-y-auto">
      {details.modal}
      <div className="mx-auto max-w-7xl space-y-6 px-5 py-10 sm:px-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Discover</h1>
          <p className="text-sm text-muted-foreground">
            {tab === 'adult'
              ? 'New scenes from the studios and performers in your Whisparr library.'
              : 'Search by anything: text, tags, people, genres, years, rating, language. Your picks live on the home page.'}
          </p>
        </header>
        <div className="glass inline-flex flex-wrap rounded-xl p-1">
          {tabs.map((k) => (
            <button
              key={k.id}
              onClick={() => setTab(k.id)}
              className={cn(
                'rounded-lg px-4 py-1.5 text-sm transition',
                tab === k.id
                  ? 'bg-white/[0.1] text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {k.label}
              {k.id === 'adult' && <span className="ml-1.5 text-[10px] text-primary">18+</span>}
            </button>
          ))}
        </div>

        {(tab === 'movie' || tab === 'series' || tab === 'anime') && (
          <SearchTab
            key={tab}
            kind={tab}
            taste={taste}
            onOpen={(r) => details.open(targetFrom(r))}
            onGet={(r) => {
              sendFeedback(r.kind, r.tmdb_id, 'search', r.title)
              ask(searchPrompt({ ...targetFrom(r), why: '' } as unknown as PickCard))
            }}
            onAsk={(r) => ask(`Is ${r.title} (${r.year ?? ''}) right for me tonight?`)}
          />
        )}
        {tab === 'adult' && (
          <AdultPanel
            onSearch={(c) => ask(searchPrompt(c))}
            onOpen={(c) =>
              details.open({
                kind: 'scene',
                stash_id: c.stash_id,
                title: c.title,
                poster: c.image,
                why: c.why,
              })
            }
          />
        )}
      </div>
    </div>
  )
}

/** Detailed search for one kind; with only tags (or nothing) set, the picks are personal. */
function SearchTab({
  kind,
  taste,
  onOpen,
  onGet,
  onAsk,
}: {
  kind: string
  taste: { tags: string[]; genres: string[]; people: string[] } | null
  onOpen: (r: MediaRef) => void
  onGet: (r: MediaRef) => void
  onAsk: (r: MediaRef) => void
}) {
  const [draft, setDraft] = useState('')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [showFilters, setShowFilters] = useState(false)
  const [genres, setGenres] = useState<string[]>([])
  const [result, setResult] = useState<{
    key: string
    items?: MediaRef[]
    note?: string
    error?: string
  } | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  useEffect(() => {
    api
      .genres(kind)
      .then(setGenres)
      .catch(() => undefined)
  }, [kind])

  // Only tags (or nothing) → personal picks filtered by those tags; anything else → search.
  const personal =
    !filters.query &&
    !filters.genres?.length &&
    !filters.people?.length &&
    !filters.year_from &&
    !filters.year_to &&
    !filters.min_rating &&
    !filters.language &&
    !filters.max_runtime &&
    (filters.sort ?? 'relevance') === 'relevance'
  const key = JSON.stringify([kind, filters])
  const loading = result?.key !== key
  const active = Object.entries(filters).filter(
    ([k, v]) => k !== 'sort' && (Array.isArray(v) ? v.length : v),
  ).length

  useEffect(() => {
    let alive = true
    const done = (r: { items?: MediaRef[]; note?: string; error?: string }) =>
      alive && setResult({ key, ...r })
    if (personal)
      api
        .recommendations(kind, undefined, filters.tags)
        .then((d) =>
          done({
            items: d.recommendations,
            note: d.based_on.length ? `Tuned to ${d.based_on.slice(0, 4).join(', ')}` : undefined,
          }),
        )
        .catch((e) => done({ error: (e as Error).message }))
    else
      api
        .search({ kind, ...filters, limit: 30 })
        .then((d) =>
          done({
            items: d.results,
            note: [
              d.applied.people?.length ? `with ${d.applied.people.join(', ')}` : '',
              d.applied.tags?.length ? `tagged ${d.applied.tags.join(', ')}` : '',
            ]
              .filter(Boolean)
              .join(' · '),
          }),
        )
        .catch((e) => done({ error: (e as Error).message }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const set = <K extends keyof Filters>(name: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [name]: value }))
  const items = useMemo(
    () => (result?.items ?? []).filter((i) => !hidden.has(`${i.kind}-${i.tmdb_id}`)),
    [result, hidden],
  )

  return (
    <div className="space-y-5">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          set('query', draft.trim() || undefined)
        }}
      >
        <div className="relative min-w-60 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Search ${kind === 'movie' ? 'movies' : kind}…`}
            className="pl-9"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        <Button
          type="button"
          variant={showFilters ? 'secondary' : 'ghost'}
          onClick={() => setShowFilters((v) => !v)}
        >
          <SlidersHorizontal className="size-4" />
          Filters{active ? ` (${active})` : ''}
        </Button>
        {(active > 0 || filters.query) && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setFilters(EMPTY)
              setDraft('')
            }}
          >
            <RotateCcw className="size-4" />
            Reset
          </Button>
        )}
      </form>

      <div>
        <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Tags
        </p>
        <ChipInput
          type="tag"
          values={filters.tags ?? []}
          onChange={(v) => set('tags', v)}
          placeholder="Add a tag: heist, time loop, found family…"
          quick={taste?.tags ?? []}
        />
      </div>

      {showFilters && (
        <div className="glass grid gap-5 rounded-2xl p-5 md:grid-cols-2">
          <div className="md:col-span-2">
            <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Genres
            </p>
            <div className="flex flex-wrap gap-1.5">
              {genres.map((g) => {
                const on = filters.genres?.includes(g)
                return (
                  <button
                    key={g}
                    type="button"
                    onClick={() =>
                      set(
                        'genres',
                        on
                          ? filters.genres?.filter((x) => x !== g)
                          : [...(filters.genres ?? []), g],
                      )
                    }
                    className={cn(
                      'rounded-full px-3 py-1 text-xs ring-1 transition',
                      on
                        ? 'bg-primary/15 text-primary ring-primary/40'
                        : 'bg-white/[0.03] text-muted-foreground ring-white/[0.08] hover:text-foreground',
                    )}
                  >
                    {g}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="md:col-span-2">
            <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              People (actors, directors)
            </p>
            <ChipInput
              type="person"
              values={filters.people ?? []}
              onChange={(v) => set('people', v)}
              placeholder="Add a person…"
              quick={taste?.people ?? []}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-xs text-muted-foreground">
              From year
              <Input
                type="number"
                inputMode="numeric"
                value={filters.year_from ?? ''}
                onChange={(e) =>
                  set('year_from', e.target.value ? Number(e.target.value) : undefined)
                }
                placeholder="1990"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              To year
              <Input
                type="number"
                inputMode="numeric"
                value={filters.year_to ?? ''}
                onChange={(e) =>
                  set('year_to', e.target.value ? Number(e.target.value) : undefined)
                }
                placeholder="2026"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-xs text-muted-foreground">
              Minimum rating
              <Select
                value={String(filters.min_rating ?? '')}
                onChange={(e) =>
                  set('min_rating', e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">Any</option>
                {[6, 6.5, 7, 7.5, 8, 8.5].map((r) => (
                  <option key={r} value={r}>
                    {r}+
                  </option>
                ))}
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Max runtime
              <Select
                value={String(filters.max_runtime ?? '')}
                onChange={(e) =>
                  set('max_runtime', e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">Any</option>
                {[30, 60, 90, 120, 150].map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-xs text-muted-foreground">
              Original language
              <Select
                value={filters.language ?? ''}
                onChange={(e) => set('language', e.target.value || undefined)}
              >
                {LANGUAGES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Sort
              <Select
                value={filters.sort ?? 'relevance'}
                onChange={(e) => set('sort', e.target.value as Filters['sort'])}
              >
                <option value="relevance">Most popular</option>
                <option value="rating">Best rated</option>
                <option value="newest">Newest</option>
                <option value="oldest">Oldest</option>
              </Select>
            </label>
          </div>
        </div>
      )}

      <div className="flex min-h-5 items-center gap-2 text-sm text-muted-foreground">
        {loading && <Loader2 className="size-4 animate-spin" />}
        {!loading && result?.note && <span>{result.note}</span>}
        {!loading && personal && !result?.error && (
          <span className="text-xs">
            · your picks{filters.tags?.length ? ', filtered by tags' : ''}
          </span>
        )}
      </div>

      {result?.error && !loading && (
        <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">
            {result.error.includes('tmdb') || result.error.includes('metadata')
              ? 'Picks need a metadata source.'
              : 'Nothing to show.'}
          </p>
          <p className="mt-1">{result.error}</p>
        </div>
      )}

      {!result?.error && (
        <div
          className={cn(
            'grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6',
            loading && 'opacity-60',
          )}
        >
          {items.map((r) => (
            <MediaTile
              key={`${r.kind}-${r.tmdb_id}-${r.title}`}
              title={r.title}
              year={r.year}
              poster={r.poster_url}
              kind={r.kind}
              rating={r.imdb_rating ?? r.rating}
              inLibrary={r.in_library}
              onClick={() => onOpen(r)}
              onDismiss={() => {
                sendFeedback(r.kind, r.tmdb_id, 'dismiss', r.title)
                setHidden((h) => new Set(h).add(`${r.kind}-${r.tmdb_id}`))
              }}
              footer={
                <div className="mt-1.5 space-y-2">
                  {r.watched && <p className="text-[11px] text-success">Watched</p>}
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
                        onClick={() => onGet(r)}
                      >
                        <Download className="size-3.5" />
                        Get
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      onClick={() => onAsk(r)}
                    >
                      <MessageCircle className="size-3.5" />
                      Ask
                    </Button>
                  </div>
                </div>
              }
            />
          ))}
          {!loading && items.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">
              Nothing matches — loosen a filter.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function AdultPanel({
  onSearch,
  onOpen,
}: {
  onSearch: (c: PickCard) => void
  onOpen: (c: PickCard) => void
}) {
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
              onOpen={onOpen}
              className="w-full"
              label="Get"
            />
          ))}
        </div>
      )}
    </div>
  )
}
