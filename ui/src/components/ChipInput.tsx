import { Loader2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Input } from '@/components/ui/primitives'
import { api, type Suggestion } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Chips with autocomplete for tags (TMDB keywords) or people, or any `suggest` source. */
export function ChipInput({
  type,
  suggest,
  values,
  onChange,
  placeholder,
  quick = [],
}: {
  type: 'tag' | 'person'
  /** Where suggestions come from instead of TMDB (e.g. StashDB). */
  suggest?: (q: string) => Promise<Suggestion[]>
  values: string[]
  onChange: (values: string[]) => void
  placeholder: string
  /** One-tap suggestions (e.g. the user's own strongest tags). */
  quick?: string[]
}) {
  const [text, setText] = useState('')
  const [hits, setHits] = useState<Suggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = text.trim()
    if (q.length < 2) return
    let alive = true
    const t = setTimeout(() => {
      setLoading(true)
      const source = suggest ? suggest(q) : api.suggest(type, q)
      source
        .then((h) => alive && setHits(h))
        .catch(() => alive && setHits([]))
        .finally(() => alive && setLoading(false))
    }, 300)
    return () => {
      alive = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `suggest` is a new function each render
  }, [text, type])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const add = (name: string) => {
    const v = name.trim()
    if (v && !values.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...values, v])
    setText('')
    setHits([])
  }
  const remove = (name: string) => onChange(values.filter((v) => v !== name))
  const quickLeft = quick.filter((q) => !values.some((v) => v.toLowerCase() === q.toLowerCase()))

  return (
    <div ref={box} className="relative space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2.5 py-1 text-xs text-primary ring-1 ring-primary/40"
          >
            {v}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => remove(v)}>
              <X className="size-3" />
            </button>
          </span>
        ))}
        <div className="relative min-w-40 flex-1">
          <Input
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                add(hits[0]?.name ?? text)
              }
              if (e.key === 'Backspace' && !text && values.length) remove(values[values.length - 1])
            }}
            placeholder={placeholder}
            className="h-8 text-sm"
          />
          {loading && (
            <Loader2 className="absolute top-1/2 right-2 size-3.5 -translate-y-1/2 animate-spin text-muted-foreground" />
          )}
        </div>
      </div>
      {open && text.trim().length >= 2 && hits.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-64 w-full max-w-sm overflow-y-auto rounded-xl bg-[#14161d] p-1 shadow-2xl shadow-black/60 ring-1 ring-white/15">
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                onClick={() => {
                  add(h.name)
                  setOpen(false)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-white/[0.06]"
              >
                {type === 'person' && (
                  <span className="size-7 shrink-0 overflow-hidden rounded-full bg-white/[0.06]">
                    {h.image && <img src={h.image} alt="" className="h-full w-full object-cover" />}
                  </span>
                )}
                <span className="min-w-0">
                  <span className="block truncate">{h.name}</span>
                  {h.known_for?.length ? (
                    <span className="block truncate text-xs text-muted-foreground">
                      {h.known_for.join(', ')}
                    </span>
                  ) : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {quickLeft.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {quickLeft.slice(0, 12).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => add(q)}
              className={cn(
                'rounded-full px-2.5 py-1 text-xs ring-1 transition',
                'bg-white/[0.03] text-muted-foreground ring-white/[0.08] hover:text-foreground',
              )}
            >
              + {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
