import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search as SearchIcon,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { ChipInput } from '@/components/ChipInput'
import { PickCardView } from '@/components/chat/PickCarousel'
import { ShelvesLoading } from '@/components/Shelf'
import { Button, Input, Select } from '@/components/ui/primitives'
import {
  type AdultRow,
  type AdultRows,
  type AdultScene,
  type AdultSearchParams,
  type AdultSearchResult,
  api,
} from '@/lib/api'
import type { PickCard } from '@/lib/picks'
import { cn } from '@/lib/utils'

type Filters = Omit<AdultSearchParams, 'text'>
const EMPTY: Filters = { sort: 'relevance' }
const SORTS: [string, string][] = [
  ['relevance', 'Most popular'],
  ['newest', 'Newest'],
  ['oldest', 'Oldest'],
  ['trending', 'Trending'],
  ['longest', 'Longest'],
  ['shortest', 'Shortest'],
]
const LENGTHS = [10, 20, 30, 45, 60, 90]
const STEPS = [
  'Reading your Whisparr library',
  'Checking your StashDB favourites',
  'Working out your taste',
  'Curating your shelves',
]

const toCard = (s: AdultScene): PickCard => ({ ...s, why: s.why?.[0] ?? '' })

function filterCount(f: Filters): number {
  return (
    (f.tags?.length ?? 0) +
    (f.exclude_tags?.length ?? 0) +
    (f.performers?.length ?? 0) +
    (f.studios?.length ?? 0) +
    (f.date_from ? 1 : 0) +
    (f.date_to ? 1 : 0) +
    (f.min_minutes ? 1 : 0) +
    (f.max_minutes ? 1 : 0) +
    (f.sort && f.sort !== 'relevance' ? 1 : 0)
  )
}

/**
 * Discover → Adult: streaming-style shelves built from Whisparr and StashDB
 * favourites. Typing or setting a filter swaps the shelves for search results;
 * clearing them brings the shelves back.
 */
export function AdultDiscover({
  onGet,
  onOpen,
}: {
  onGet: (c: PickCard) => void
  onOpen: (c: PickCard) => void
}) {
  const [text, setText] = useState('')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [showFilters, setShowFilters] = useState(false)
  const [rows, setRows] = useState<AdultRows | null>(null)
  const [rowsError, setRowsError] = useState<string | null>(null)
  const [result, setResult] = useState<{
    key: string
    data?: AdultSearchResult
    error?: string
  } | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const count = filterCount(filters)
  const active = text.trim() !== '' || count > 0
  const key = JSON.stringify({ text: text.trim(), ...filters })
  const searching = active && result?.key !== key

  useEffect(() => {
    api
      .adultRows()
      .then(setRows)
      .catch((e) => setRowsError((e as Error).message))
  }, [])

  useEffect(() => {
    if (!active) return
    let alive = true
    const params: AdultSearchParams = { ...filters, text: text.trim() || undefined }
    const t = setTimeout(() => {
      api
        .adultSearch(params)
        .then((d) => alive && setResult({ key, data: d }))
        .catch((e) => alive && setResult({ key, error: (e as Error).message }))
    }, 450)
    return () => {
      alive = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` covers text and filters
  }, [key, active])

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  const clearAll = () => {
    setText('')
    setFilters(EMPTY)
  }
  const dismiss = (c: PickCard) => {
    if (!c.stash_id) return
    api.adultFeedback(c.stash_id, 'dismiss').catch(() => undefined)
    setHidden((h) => new Set(h).add(c.stash_id as string))
  }
  const open = (c: PickCard) => {
    if (c.stash_id) api.adultFeedback(c.stash_id, 'open').catch(() => undefined)
    onOpen(c)
  }
  const get = (c: PickCard) => {
    if (c.stash_id) api.adultFeedback(c.stash_id, 'search').catch(() => undefined)
    onGet(c)
  }
  const visible = (s: AdultScene) => !hidden.has(s.stash_id ?? '')
  const addTag = (t: string) => {
    if (!(filters.tags ?? []).includes(t)) set({ tags: [...(filters.tags ?? []), t] })
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-0 flex-1 basis-64">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Search scenes: a title, performer, studio or theme"
              className="pr-9 pl-9"
              aria-label="Search scenes"
            />
            {text && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setText('')}
                className="absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <Button
            type="button"
            variant={showFilters ? 'secondary' : 'ghost'}
            onClick={() => setShowFilters((v) => !v)}
            aria-expanded={showFilters}
          >
            <SlidersHorizontal className="size-4" />
            Filters
            {count > 0 && (
              <span className="rounded-full bg-primary/20 px-1.5 text-[11px] text-primary">
                {count}
              </span>
            )}
          </Button>
          {active && (
            <Button type="button" variant="ghost" onClick={clearAll}>
              Clear
            </Button>
          )}
        </div>

        {showFilters && (
          <div className="glass grid gap-4 rounded-2xl p-4 sm:grid-cols-2">
            <Field label="Tags (all of them)">
              <ChipInput
                type="tag"
                suggest={(q) => api.adultSuggest('tag', q)}
                values={filters.tags ?? []}
                onChange={(v) => set({ tags: v })}
                placeholder="e.g. massage"
                quick={rows?.tags ?? []}
              />
            </Field>
            <Field label="Without tags">
              <ChipInput
                type="tag"
                suggest={(q) => api.adultSuggest('tag', q)}
                values={filters.exclude_tags ?? []}
                onChange={(v) => set({ exclude_tags: v })}
                placeholder="Leave out scenes tagged…"
              />
            </Field>
            <Field label="Performers (any of them)">
              <ChipInput
                type="tag"
                suggest={(q) => api.adultSuggest('performer', q)}
                values={filters.performers ?? []}
                onChange={(v) => set({ performers: v })}
                placeholder="A performer's name"
              />
            </Field>
            <Field label="Studios (any of them)">
              <ChipInput
                type="tag"
                suggest={(q) => api.adultSuggest('studio', q)}
                values={filters.studios ?? []}
                onChange={(v) => set({ studios: v })}
                placeholder="A studio's name"
              />
            </Field>
            <Field label="Released">
              <div className="flex items-center gap-2">
                <Input
                  type="date"
                  value={filters.date_from ?? ''}
                  onChange={(e) => set({ date_from: e.target.value || undefined })}
                  aria-label="Released after"
                  className="h-9 min-w-0 text-sm"
                />
                <span className="text-xs text-muted-foreground">to</span>
                <Input
                  type="date"
                  value={filters.date_to ?? ''}
                  onChange={(e) => set({ date_to: e.target.value || undefined })}
                  aria-label="Released before"
                  className="h-9 min-w-0 text-sm"
                />
              </div>
            </Field>
            <Field label="Length and order">
              <div className="grid grid-cols-3 gap-2">
                <Select
                  value={filters.min_minutes ?? ''}
                  onChange={(e) => set({ min_minutes: Number(e.target.value) || undefined })}
                  aria-label="At least"
                  className="h-9 text-sm"
                >
                  <option value="">Any length</option>
                  {LENGTHS.map((m) => (
                    <option key={m} value={m}>
                      ≥ {m} min
                    </option>
                  ))}
                </Select>
                <Select
                  value={filters.max_minutes ?? ''}
                  onChange={(e) => set({ max_minutes: Number(e.target.value) || undefined })}
                  aria-label="At most"
                  className="h-9 text-sm"
                >
                  <option value="">No limit</option>
                  {LENGTHS.map((m) => (
                    <option key={m} value={m}>
                      ≤ {m} min
                    </option>
                  ))}
                </Select>
                <Select
                  value={filters.sort ?? 'relevance'}
                  onChange={(e) => set({ sort: e.target.value })}
                  aria-label="Sort by"
                  className="h-9 text-sm"
                >
                  {SORTS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </div>
            </Field>
          </div>
        )}

        {!active && !showFilters && rows && rows.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {rows.tags.slice(0, 12).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => addTag(t)}
                className="rounded-full bg-white/[0.03] px-3 py-1 text-xs text-muted-foreground ring-1 ring-white/[0.08] transition hover:text-foreground"
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      {active ? (
        <Results
          result={result}
          searching={searching}
          visible={visible}
          onGet={get}
          onOpen={open}
          onDismiss={dismiss}
        />
      ) : (
        <>
          {!rows && !rowsError && <ShelvesLoading rows={3} steps={STEPS} wide />}
          {rowsError && (
            <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">{rowsError}</div>
          )}
          {rows && rows.based_on.length > 0 && (
            <p className="text-xs text-muted-foreground">Tuned to {rows.based_on.join(', ')}</p>
          )}
          {rows && rows.rows.length === 0 && (
            <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">
              Nothing to suggest yet: add scenes to Whisparr or favourite performers and studios on
              StashDB.
            </div>
          )}
          {rows && (
            <div className="space-y-10">
              {rows.rows.map((row) => {
                const items = row.items.filter(visible)
                return items.length >= 3 ? (
                  <SceneShelf
                    key={row.id}
                    row={{ ...row, items }}
                    onGet={get}
                    onOpen={open}
                    onDismiss={dismiss}
                  />
                ) : null
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {children}
    </div>
  )
}

function Results({
  result,
  searching,
  visible,
  onGet,
  onOpen,
  onDismiss,
}: {
  result: { data?: AdultSearchResult; error?: string } | null
  searching: boolean
  visible: (s: AdultScene) => boolean
  onGet: (c: PickCard) => void
  onOpen: (c: PickCard) => void
  onDismiss: (c: PickCard) => void
}) {
  const data = result?.data
  return (
    <div className="space-y-4">
      {searching && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Searching StashDB…
        </div>
      )}
      {!searching && result?.error && (
        <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">{result.error}</div>
      )}
      {!searching && data?.not_found.length ? (
        <p className="text-xs text-muted-foreground">
          Not found on StashDB: {data.not_found.join(', ')}
        </p>
      ) : null}
      {!searching && data && data.scenes.length === 0 && (
        <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">Nothing found.</div>
      )}
      {data && !result?.error && (
        <div
          className={cn(
            'grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
            searching && 'opacity-60',
          )}
        >
          {data.scenes.filter(visible).map((s) => (
            <PickCardView
              key={s.stash_id ?? s.title}
              card={toCard(s)}
              onSearch={onGet}
              onOpen={onOpen}
              onDismiss={onDismiss}
              className="w-full"
              label="Get"
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SceneShelf({
  row,
  onGet,
  onOpen,
  onDismiss,
}: {
  row: AdultRow
  onGet: (c: PickCard) => void
  onOpen: (c: PickCard) => void
  onDismiss: (c: PickCard) => void
}) {
  const track = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) =>
    track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.85, behavior: 'smooth' })
  return (
    <section className="group/shelf min-w-0">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-lg font-semibold tracking-tight">{row.title}</h2>
        {row.subtitle && <p className="text-sm text-muted-foreground">{row.subtitle}</p>}
      </div>
      <div className="relative">
        <div
          ref={track}
          className="scroll-thin flex snap-x gap-4 overflow-x-auto scroll-smooth pb-3"
        >
          {row.items.map((s) => (
            <PickCardView
              key={s.stash_id ?? s.title}
              card={toCard(s)}
              onSearch={onGet}
              onOpen={onOpen}
              onDismiss={onDismiss}
              className="w-[260px] sm:w-[300px]"
              label="Get"
            />
          ))}
        </div>
        {row.items.length > 3 &&
          (['left', 'right'] as const).map((side) => {
            const Icon = side === 'left' ? ChevronLeft : ChevronRight
            return (
              <button
                key={side}
                type="button"
                aria-label={`Scroll ${row.title} ${side}`}
                onClick={() => scroll(side === 'left' ? -1 : 1)}
                className={cn(
                  'absolute top-[22%] hidden size-9 items-center justify-center rounded-full bg-black/70 opacity-0 ring-1 ring-white/15 backdrop-blur transition group-hover/shelf:opacity-100 hover:bg-black/90 sm:flex',
                  side === 'left' ? 'left-1' : 'right-1',
                )}
              >
                <Icon className="size-5" />
              </button>
            )
          })}
      </div>
    </section>
  )
}
