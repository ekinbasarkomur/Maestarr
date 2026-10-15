import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useRef } from 'react'

import { MediaTile } from '@/components/MediaCard'
import type { DiscoverRow, MediaRef } from '@/lib/api'
import { cn } from '@/lib/utils'

/** One horizontally scrolling row of titles, like a streaming app's shelf. */
export function Shelf({
  row,
  onOpen,
  onDismiss,
}: {
  row: DiscoverRow
  onOpen: (item: MediaRef) => void
  onDismiss?: (item: MediaRef) => void
}) {
  const track = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) =>
    track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.85, behavior: 'smooth' })
  return (
    <section className="group/shelf min-w-0">
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold tracking-tight">{row.title}</h2>
        {row.subtitle && <p className="text-sm text-muted-foreground">{row.subtitle}</p>}
      </div>
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

export function ShelfSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-5 w-48 animate-pulse rounded bg-white/[0.06]" />
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 7 }, (_, i) => (
          <div
            key={i}
            className="aspect-[2/3] w-36 shrink-0 animate-pulse rounded-xl bg-white/[0.05] sm:w-40"
          />
        ))}
      </div>
    </div>
  )
}
