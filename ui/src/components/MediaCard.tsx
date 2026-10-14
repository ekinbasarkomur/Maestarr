import { Check, Film, Star, Tv } from 'lucide-react'

import { cn } from '@/lib/utils'

export function Poster({
  src,
  title,
  className,
}: {
  src?: string | null
  title: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'relative aspect-[2/3] overflow-hidden rounded-xl bg-white/[0.04] ring-1 ring-white/[0.08]',
        className,
      )}
    >
      {src ? (
        <img src={src} alt={title} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full items-center justify-center p-3 text-center text-xs text-muted-foreground">
          {title}
        </div>
      )}
    </div>
  )
}

export function MediaTile({
  title,
  year,
  poster,
  kind,
  rating,
  inLibrary,
  footer,
  onClick,
}: {
  title: string
  year?: number
  poster?: string | null
  kind?: string
  rating?: number | null
  inLibrary?: boolean
  footer?: React.ReactNode
  onClick?: () => void
}) {
  const Icon = kind === 'movie' ? Film : Tv
  return (
    <div className="group w-full">
      <button
        type="button"
        onClick={onClick}
        className="block w-full text-left"
        disabled={!onClick}
      >
        <div className="relative">
          <Poster
            src={poster}
            title={title}
            className="transition duration-300 group-hover:ring-white/25 group-hover:brightness-110"
          />
          {inLibrary && (
            <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-success backdrop-blur">
              <Check className="size-3" />
              In library
            </span>
          )}
          {rating ? (
            <span className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium backdrop-blur">
              <Star className="size-3 fill-primary text-primary" />
              {rating.toFixed(1)}
            </span>
          ) : null}
        </div>
        <div className="mt-2 flex items-start gap-1.5">
          <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{title}</p>
            {year && <p className="text-xs text-muted-foreground">{year}</p>}
          </div>
        </div>
      </button>
      {footer}
    </div>
  )
}
