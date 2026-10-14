import { Check, ChevronLeft, ChevronRight, Film, Search, Sparkles, Star, Tv } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button } from '@/components/ui/primitives'
import { KIND_LABEL, type PickCard } from '@/lib/picks'
import { cn } from '@/lib/utils'

export function PickCarousel({
  cards,
  onSearch,
  onOpen,
}: {
  cards: PickCard[]
  onSearch: (card: PickCard) => void
  onOpen?: (card: PickCard) => void
}) {
  const row = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) =>
    row.current?.scrollBy({ left: dir * row.current.clientWidth * 0.8, behavior: 'smooth' })
  if (!cards.length) return null
  return (
    <div className="group/row relative min-w-0">
      <div
        ref={row}
        className="scroll-thin flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pt-1 pb-3"
      >
        {cards.map((c, i) => (
          <PickCardView
            key={`${c.kind}-${c.tmdb_id ?? c.tvdb_id ?? c.stash_id ?? c.title}-${i}`}
            card={c}
            onSearch={onSearch}
            onOpen={onOpen}
          />
        ))}
      </div>
      {cards.length > 2 && (
        <>
          <Arrow side="left" onClick={() => scroll(-1)} />
          <Arrow side="right" onClick={() => scroll(1)} />
        </>
      )}
    </div>
  )
}

function Arrow({ side, onClick }: { side: 'left' | 'right'; onClick: () => void }) {
  const Icon = side === 'left' ? ChevronLeft : ChevronRight
  return (
    <button
      type="button"
      aria-label={side === 'left' ? 'Scroll left' : 'Scroll right'}
      onClick={onClick}
      className={cn(
        'absolute top-[38%] hidden size-9 items-center justify-center rounded-full bg-black/70 text-foreground opacity-0 ring-1 ring-white/15 backdrop-blur transition group-hover/row:opacity-100 hover:bg-black/90 sm:flex',
        side === 'left' ? 'left-1' : 'right-1',
      )}
    >
      <Icon className="size-5" />
    </button>
  )
}

export function PickCardView({
  card: c,
  onSearch,
  onOpen,
  className,
  label = 'Search',
}: {
  card: PickCard
  onSearch: (c: PickCard) => void
  onOpen?: (c: PickCard) => void
  className?: string
  label?: string
}) {
  const [asked, setAsked] = useState(false)
  const [broken, setBroken] = useState(false)
  const scene = c.kind === 'scene'
  const Icon = c.kind === 'movie' ? Film : Tv
  const meta = scene
    ? [c.studio, c.date, c.minutes ? `${c.minutes} min` : null]
    : [KIND_LABEL[c.kind], c.year]
  return (
    <article
      className={cn(
        'glass flex shrink-0 snap-start flex-col overflow-hidden rounded-2xl ring-1 ring-white/[0.08]',
        className ?? (scene ? 'w-[300px]' : 'w-[220px]'),
      )}
    >
      <div
        className={cn(
          'relative overflow-hidden bg-white/[0.04]',
          scene ? 'aspect-video' : 'aspect-[2/3]',
          onOpen && 'cursor-pointer transition hover:brightness-110',
        )}
        onClick={onOpen ? () => onOpen(c) : undefined}
        role={onOpen ? 'button' : undefined}
        aria-label={onOpen ? `Details for ${c.title}` : undefined}
      >
        {c.image && !broken ? (
          <img
            src={c.image}
            alt={c.title}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setBroken(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-xs text-muted-foreground">
            <Icon className="size-6 opacity-50" />
            {c.title}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent" />
        {c.in_library && (
          <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/65 px-2 py-0.5 text-[10px] font-medium text-success backdrop-blur">
            <Check className="size-3" />
            In library
          </span>
        )}
        {c.rating ? (
          <span className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-full bg-black/65 px-2 py-0.5 text-[10px] font-medium backdrop-blur">
            <Star className="size-3 fill-primary text-primary" />
            {c.rating.toFixed(1)}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3.5">
        <div>
          <h3
            className={cn(
              'line-clamp-2 text-sm leading-snug font-semibold',
              onOpen && 'cursor-pointer hover:underline',
            )}
            onClick={onOpen ? () => onOpen(c) : undefined}
          >
            {c.title}
          </h3>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {meta.filter(Boolean).join(' · ')}
          </p>
          {scene && c.performers?.length ? (
            <p className="truncate text-[11px] text-muted-foreground">{c.performers.join(', ')}</p>
          ) : null}
        </div>
        <p className="flex gap-1.5 rounded-lg bg-primary/[0.08] px-2.5 py-2 text-[12px] leading-snug text-foreground/90 ring-1 ring-primary/20">
          <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />
          <span>{c.why}</span>
        </p>
        {c.overview && (
          <p className="line-clamp-4 text-[12px] leading-relaxed text-muted-foreground">
            {c.overview}
          </p>
        )}
        <div className="mt-auto pt-1">
          <Button
            size="sm"
            variant={asked ? 'ghost' : 'secondary'}
            className="w-full"
            disabled={asked}
            onClick={() => {
              setAsked(true)
              onSearch(c)
            }}
          >
            {asked ? <Check className="size-3.5" /> : <Search className="size-3.5" />}
            {asked ? 'Searching…' : label}
          </Button>
        </div>
      </div>
    </article>
  )
}
