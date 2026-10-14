import { Check, Clock, Download, MessageCircle, Play, Sparkles, Star, Tv, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Badge, Button, Spinner } from '@/components/ui/primitives'
import { api, type DetailsQuery, type TitleDetails } from '@/lib/api'
import { cn } from '@/lib/utils'

/** What the caller already knows, shown at once while the details load. */
export interface DetailsTarget extends DetailsQuery {
  poster?: string | null
  why?: string | null
}

const KIND_LABEL = { movie: 'Movie', series: 'Series', anime: 'Anime', scene: 'Scene' }

function runtime(minutes?: number | null): string | null {
  if (!minutes) return null
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h ${m ? `${m}m` : ''}`.trim() : `${m}m`
}

/** A full-bleed details popup: backdrop or trailer behind, facts in front. */
export function DetailsModal({
  target,
  onClose,
  onGet,
  onAsk,
}: {
  target: DetailsTarget
  onClose: () => void
  onGet: (d: TitleDetails) => void
  onAsk: (d: TitleDetails) => void
}) {
  const [data, setData] = useState<TitleDetails | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    api
      .details(target)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError((e as Error).message))
    return () => {
      alive = false
    }
  }, [target])

  // Like Netflix: the trailer starts on its own, muted, a moment after opening.
  useEffect(() => {
    if (!data?.trailer) return
    const t = setTimeout(() => setPlaying(true), 1500)
    return () => clearTimeout(t)
  }, [data?.trailer])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  const title = data?.title ?? target.title ?? ''
  const backdrop = data?.backdrop ?? data?.poster ?? target.poster ?? null
  const scene = target.kind === 'scene'
  const facts = [
    data?.year ?? target.year,
    runtime(data?.runtime),
    data?.seasons ? `${data.seasons} season${data.seasons === 1 ? '' : 's'}` : null,
    scene ? data?.studio : (data?.network ?? data?.studio),
  ].filter(Boolean)

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 px-3 py-6 backdrop-blur-sm sm:py-10"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        ref={panel}
        tabIndex={-1}
        className="relative w-full max-w-5xl overflow-hidden rounded-2xl bg-[#0c0e13] shadow-2xl ring-1 ring-white/10 outline-none"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3 z-20 flex size-9 items-center justify-center rounded-full bg-black/60 text-foreground ring-1 ring-white/15 backdrop-blur transition hover:bg-black/80"
        >
          <X className="size-5" />
        </button>

        {/* Hero: backdrop, or the trailer once it starts */}
        <div className={cn('relative w-full bg-black', scene ? 'aspect-video' : 'aspect-[16/8]')}>
          {playing && data?.trailer ? (
            <iframe
              title={`${title} trailer`}
              src={`https://www.youtube-nocookie.com/embed/${data.trailer}?autoplay=1&mute=1&rel=0&playsinline=1&modestbranding=1`}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          ) : backdrop ? (
            <img
              src={backdrop}
              alt=""
              referrerPolicy="no-referrer"
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
              <Tv className="size-10 opacity-40" />
            </div>
          )}
          {!playing && (
            <>
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#0c0e13] via-[#0c0e13]/30 to-transparent" />
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[#0c0e13]/85 via-[#0c0e13]/20 to-transparent" />
            </>
          )}
          <div
            className={cn(
              'absolute inset-x-0 bottom-0 z-10 p-5 sm:p-8',
              playing && 'pointer-events-none opacity-0',
            )}
          >
            {data?.logo ? (
              <img
                src={data.logo}
                alt={title}
                referrerPolicy="no-referrer"
                className="mb-4 max-h-24 max-w-[60%] object-contain object-left drop-shadow-2xl sm:max-h-28"
              />
            ) : (
              <h2 className="mb-3 max-w-2xl text-2xl font-bold tracking-tight drop-shadow-lg sm:text-4xl">
                {title}
              </h2>
            )}
            {data?.tagline && (
              <p className="mb-4 max-w-xl text-sm text-foreground/80 italic">{data.tagline}</p>
            )}
            <Actions
              data={data}
              playing={playing}
              onPlay={() => setPlaying(true)}
              onGet={onGet}
              onAsk={onAsk}
            />
          </div>
        </div>
        {playing && (
          <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.06] px-5 py-3 sm:px-8">
            <p className="mr-auto text-sm font-semibold">{title}</p>
            <Actions
              data={data}
              playing={playing}
              onPlay={() => setPlaying(false)}
              onGet={onGet}
              onAsk={onAsk}
            />
          </div>
        )}

        {/* Facts */}
        <div className="grid gap-8 px-5 pt-5 pb-8 sm:px-8 md:grid-cols-[1fr_280px]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              {data?.ratings.slice(0, 3).map((r) => (
                <span key={r.source} className="inline-flex items-center gap-1 font-medium">
                  <Star className="size-3.5 fill-primary text-primary" />
                  {r.value}
                  <span className="text-xs font-normal text-muted-foreground">{r.source}</span>
                </span>
              ))}
              {facts.map((f) => (
                <span key={String(f)} className="text-muted-foreground">
                  {f}
                </span>
              ))}
              {data?.certification && (
                <span className="rounded border border-white/25 px-1.5 py-px text-[11px] text-muted-foreground">
                  {data.certification}
                </span>
              )}
              <Badge>{KIND_LABEL[target.kind]}</Badge>
              {data?.in_library && (
                <Badge tone="success">
                  <Check className="size-3" /> In library
                </Badge>
              )}
            </div>

            {target.why && (
              <p className="flex gap-2 rounded-xl bg-primary/[0.08] px-3.5 py-2.5 text-sm leading-relaxed ring-1 ring-primary/20">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                <span>{target.why}</span>
              </p>
            )}

            {data?.overview ? (
              <p className="text-[15px] leading-relaxed text-foreground/90">{data.overview}</p>
            ) : !data && !error ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner className="size-4" /> Loading details…
              </div>
            ) : null}
            {error && <p className="text-sm text-danger">{error}</p>}

            {data && data.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {data.tags.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-white/[0.05] px-2.5 py-1 text-xs text-muted-foreground ring-1 ring-white/[0.08]"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}

            {data && data.cast.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  {scene ? 'Performers' : 'Cast'}
                </p>
                <div className="scroll-thin -mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
                  {data.cast.map((c) => (
                    <div key={`${c.name}-${c.role ?? ''}`} className="w-20 shrink-0 text-center">
                      <div className="mx-auto size-16 overflow-hidden rounded-full bg-white/[0.06] ring-1 ring-white/10">
                        {c.image && (
                          <img
                            src={c.image}
                            alt={c.name}
                            loading="lazy"
                            referrerPolicy="no-referrer"
                            className="h-full w-full object-cover"
                          />
                        )}
                      </div>
                      <p className="mt-1.5 line-clamp-2 text-[11px] leading-tight font-medium">
                        {c.name}
                      </p>
                      {c.role && (
                        <p className="line-clamp-1 text-[10px] text-muted-foreground">{c.role}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <dl className="space-y-3 text-sm">
            <Fact label="Genres" value={data?.genres.join(', ')} />
            <Fact
              label={scene ? 'Studio' : 'Network'}
              value={scene ? data?.studio : data?.network}
            />
            {!scene && <Fact label="Studio" value={data?.studio} />}
            <Fact label="Director" value={data?.director} />
            <Fact label="Released" value={data?.date} />
            <Fact
              label="Status"
              value={data?.status ? data.status[0].toUpperCase() + data.status.slice(1) : null}
            />
            <Fact
              label="Ratings"
              value={data?.ratings.map((r) => `${r.source} ${r.value}`).join(' · ')}
            />
            {data?.links?.map((l) => (
              <a
                key={l.url}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-xs text-primary underline-offset-2 hover:underline"
              >
                {l.site ?? 'Link'} ↗
              </a>
            ))}
            {!data && !error && (
              <div className="space-y-2">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-4 animate-pulse rounded bg-white/[0.05]" />
                ))}
              </div>
            )}
          </dl>
        </div>
      </div>
    </div>
  )
}

function Actions({
  data,
  playing,
  onPlay,
  onGet,
  onAsk,
}: {
  data: TitleDetails | null
  playing: boolean
  onPlay: () => void
  onGet: (d: TitleDetails) => void
  onAsk: (d: TitleDetails) => void
}) {
  return (
    <div className="pointer-events-auto flex flex-wrap gap-2">
      <Button variant="primary" disabled={!data} onClick={() => data && onGet(data)}>
        {data?.in_library ? <Clock className="size-4" /> : <Download className="size-4" />}
        {data?.in_library ? 'Find a better release' : 'Search & download'}
      </Button>
      {data?.trailer && (
        <Button variant="secondary" onClick={onPlay}>
          <Play className="size-4" />
          {playing ? 'Back to poster' : 'Play trailer'}
        </Button>
      )}
      <Button variant="ghost" disabled={!data} onClick={() => data && onAsk(data)}>
        <MessageCircle className="size-4" />
        Ask Maestarr
      </Button>
    </div>
  )
}

function Fact({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 leading-snug">{value}</dd>
    </div>
  )
}
