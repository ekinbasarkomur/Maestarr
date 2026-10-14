import { Input, Toggle } from '@/components/ui/primitives'
import type { UrlParts } from '@/lib/url'

export function UrlInput({
  id,
  parts,
  onChange,
  hostPlaceholder,
}: {
  id: string
  parts: UrlParts
  onChange: (p: UrlParts) => void
  hostPlaceholder?: string
}) {
  const set = (patch: Partial<UrlParts>) => onChange({ ...parts, ...patch })
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[1fr_96px] gap-3">
        <div className="space-y-1.5">
          <label
            htmlFor={`${id}-host`}
            className="block text-[13px] font-medium text-foreground/90"
          >
            Hostname or IP address
          </label>
          <div className="flex items-center rounded-lg bg-black/25 ring-1 ring-white/10 focus-within:ring-2 focus-within:ring-ring/50">
            <span className="pl-3.5 font-mono text-xs text-muted-foreground select-none">
              {parts.ssl ? 'https://' : 'http://'}
            </span>
            <input
              id={`${id}-host`}
              value={parts.host}
              onChange={(e) => set({ host: e.target.value })}
              placeholder={hostPlaceholder}
              spellCheck={false}
              autoComplete="off"
              className="h-10 min-w-0 flex-1 bg-transparent pr-3.5 pl-1 text-sm outline-none placeholder:text-muted-foreground/60"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor={`${id}-port`}
            className="block text-[13px] font-medium text-foreground/90"
          >
            Port
          </label>
          <Input
            id={`${id}-port`}
            inputMode="numeric"
            value={parts.port}
            onChange={(e) => set({ port: e.target.value.replace(/[^0-9]/g, '') })}
          />
        </div>
      </div>
      <div className="grid grid-cols-[1fr_1fr] items-end gap-3">
        <Toggle
          checked={parts.ssl}
          onChange={(ssl) => set({ ssl })}
          label="Use SSL"
          description="https"
        />
        <div className="space-y-1.5">
          <label
            htmlFor={`${id}-base`}
            className="block text-[13px] font-medium text-foreground/90"
          >
            URL base
          </label>
          <Input
            id={`${id}-base`}
            value={parts.base}
            onChange={(e) => set({ base: e.target.value })}
            placeholder="optional, e.g. /sonarr"
            spellCheck={false}
          />
        </div>
      </div>
    </div>
  )
}
