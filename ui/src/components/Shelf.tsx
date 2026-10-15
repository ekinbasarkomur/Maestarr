import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { MediaTile } from '@/components/MediaCard'
import type { DiscoverRow, MediaRef } from '@/lib/api'
import { cn } from '@/lib/utils'

/** One horizontally scrolling row of titles, like a streaming app's shelf. */
export function Shelf({
  row,
  onOpen,
  onDismiss,
  bare = false,
}: {
  row: DiscoverRow
  onOpen: (item: MediaRef) => void
  onDismiss?: (item: MediaRef) => void
  /** Without its own heading (when the page already titles it). */
  bare?: boolean
}) {
  const track = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) =>
    track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.85, behavior: 'smooth' })
  return (
    <section className="group/shelf min-w-0">
      {!bare && (
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-lg font-semibold tracking-tight">{row.title}</h2>
          {row.subtitle && <p className="text-sm text-muted-foreground">{row.subtitle}</p>}
        </div>
      )}
      <div className="relative">
        <div
          ref={track}
          className="scroll-thin flex snap-x gap-4 overflow-x-auto scroll-smooth pb-3"
        >
          {row.items.map((item) => (
            <div
              key={`${item.kind}-${item.tmdb_id ?? item.title}`}
              className="w-36 shrink-0 snap-start sm:w-40"
            >
              <MediaTile
                title={item.title}
                year={item.year}
                poster={item.poster_url}
                kind={item.kind}
                rating={item.imdb_rating ?? item.rating}
                inLibrary={item.in_library}
                onClick={() => onOpen(item)}
                onDismiss={onDismiss ? () => onDismiss(item) : undefined}
                footer={
                  item.why?.[0] ? (
                    <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                      {item.why[0]}
                    </p>
                  ) : null
                }
              />
            </div>
          ))}
        </div>
        {row.items.length > 4 &&
          (['left', 'right'] as const).map((side) => {
            const Icon = side === 'left' ? ChevronLeft : ChevronRight
            return (
              <button
                key={side}
                type="button"
                aria-label={`Scroll ${row.title} ${side}`}
                onClick={() => scroll(side === 'left' ? -1 : 1)}
                className={cn(
                  'absolute top-[30%] hidden size-9 items-center justify-center rounded-full bg-black/70 opacity-0 ring-1 ring-white/15 backdrop-blur transition group-hover/shelf:opacity-100 hover:bg-black/90 sm:flex',
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

export function ShelfSkeleton({ bare = false, wide = false }: { bare?: boolean; wide?: boolean }) {
  return (
    <div className="space-y-3">
      {!bare && <div className="shimmer h-5 w-48 rounded" />}
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className={cn('shrink-0 space-y-2', wide ? 'w-[260px]' : 'w-36 sm:w-40')}>
            <div
              className={cn('shimmer rounded-xl', wide ? 'aspect-video' : 'aspect-[2/3]')}
              style={{ animationDelay: `${i * 90}ms` }}
            />
            <div className="shimmer h-3 w-3/4 rounded" style={{ animationDelay: `${i * 90}ms` }} />
          </div>
        ))}
      </div>
    </div>
  )
}

const STEPS = [
  'Reading what you watched',
  'Looking through your library',
  'Checking your favourites and requests',
  'Working out your taste',
  'Picking titles for tonight',
]

/**
 * Shown while shelves are being built for the first time (or after a cache
 * refresh): the steps Maestarr goes through, over shimmering placeholders.
 */
export function ShelvesLoading({
  rows = 3,
  steps = STEPS,
  wide = false,
}: {
  rows?: number
  /** What Maestarr is doing, shown one after another. */
  steps?: string[]
  /** Landscape placeholders (scenes) instead of posters. */
  wide?: boolean
}) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % steps.length), 2600)
    return () => clearInterval(t)
  }, [steps.length])
  return (
    <div className="space-y-8" aria-busy="true" aria-live="polite">
      <div className="glass flex items-center gap-4 rounded-2xl px-5 py-4">
        <span className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/30">
          <span className="absolute inset-0 animate-ping rounded-full bg-primary/10" />
          <Sparkles className="size-5 text-primary" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium">Curating your shelves…</p>
          <p
            key={step}
            className="animate-[fadein_0.4s_ease] truncate text-xs text-muted-foreground"
          >
            {steps[step]}
          </p>
        </div>
        <div className="ml-auto hidden gap-1.5 sm:flex">
          {steps.map((_, i) => (
            <span
              key={i}
              className={cn(
                'h-1.5 w-6 rounded-full transition-colors duration-500',
                i <= step ? 'bg-primary/80' : 'bg-white/10',
              )}
            />
          ))}
        </div>
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <ShelfSkeleton key={i} wide={wide} />
      ))}
    </div>
  )
}
