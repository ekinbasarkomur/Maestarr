import { AlertCircle, ChevronDown, Plug } from 'lucide-react'
import { useMemo, useState } from 'react'

import {
  Badge,
  Button,
  Field,
  Input,
  Panel,
  SecretInput,
  Select,
  SuccessLine,
  Toggle,
} from '@/components/ui/primitives'
import { UrlInput } from '@/components/UrlInput'
import { api, isSecret, type Sections, type SettingValue, type TestResult } from '@/lib/api'
import type { FieldDef, ServiceDef } from '@/lib/services'
import { isConfigured } from '@/lib/settings-utils'
import { joinUrl, parseUrl, type UrlParts } from '@/lib/url'
import { cn } from '@/lib/utils'

type Values = Record<string, string | boolean>

function defaultPort(field: FieldDef): string {
  const m = field.placeholder?.match(/:(\d+)/)
  return m ? m[1] : ''
}

function placeholderHost(field: FieldDef): string {
  try {
    return field.placeholder ? new URL(field.placeholder).hostname : ''
  } catch {
    return ''
  }
}

function initialParts(
  def: ServiceDef,
  saved: Record<string, SettingValue>,
): Record<string, UrlParts> {
  const out: Record<string, UrlParts> = {}
  for (const f of def.fields)
    if (f.kind === 'url')
      out[f.name] = parseUrl(
        typeof saved?.[f.name] === 'string' ? (saved[f.name] as string) : '',
        defaultPort(f),
      )
  return out
}

function initialValues(def: ServiceDef, saved: Record<string, SettingValue>): Values {
  const out: Values = {}
  for (const f of def.fields) {
    const v = saved?.[f.name]
    if (f.kind === 'toggle') out[f.name] = Boolean(v)
    else if (f.kind === 'secret') out[f.name] = ''
    else if (Array.isArray(v)) out[f.name] = v.join(', ')
    else out[f.name] = v === null || v === undefined || isSecret(v) ? '' : String(v)
  }
  return out
}

function toPayload(
  def: ServiceDef,
  values: Values,
  saved: Record<string, SettingValue>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of def.fields) {
    const v = values[f.name]
    if (f.kind === 'secret') {
      if (typeof v === 'string' && v.trim()) out[f.name] = v.trim()
      continue
    }
    if (f.kind === 'toggle') out[f.name] = Boolean(v)
    else if (f.kind === 'ids')
      out[f.name] = String(v)
        .split(/[\s,]+/)
        .filter(Boolean)
        .map(Number)
        .filter((n) => Number.isFinite(n))
    else if (f.kind === 'number') out[f.name] = v === '' ? null : Number(v)
    else out[f.name] = String(v).trim() === '' ? null : String(v).trim()
    // Unchanged plain values need not be resent, but resending is harmless.
    void saved
  }
  return out
}

export function ServiceForm({
  def,
  sections,
  onSaved,
  saveLabel = 'Save',
  secondary,
}: {
  def: ServiceDef
  sections: Sections
  onSaved: (sections: Sections) => void
  saveLabel?: string
  secondary?: React.ReactNode
}) {
  const saved = useMemo(() => sections[def.id] ?? {}, [sections, def.id])
  const [values, setValues] = useState<Values>(() => initialValues(def, saved))
  const [parts, setParts] = useState<Record<string, UrlParts>>(() => initialParts(def, saved))
  const [test, setTest] = useState<TestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (name: string, value: string | boolean) => {
    setValues((v) => ({ ...v, [name]: value }))
    setError(null)
  }

  const runTest = async () => {
    setTesting(true)
    setError(null)
    try {
      const result = await api.testService(def.id, toPayload(def, values, saved))
      setTest(result)
      if (result.ok) {
        // Pre-select sensible defaults from what the service reported.
        setValues((v) => {
          const next = { ...v }
          for (const f of def.fields) {
            if (f.kind !== 'choice' || next[f.name] || f.optional) continue
            const options = choiceOptions(f, result)
            if (options.length) next[f.name] = options[0]
          }
          return next
        })
      }
    } catch (e) {
      setTest({ ok: false, detail: (e as Error).message })
    } finally {
      setTesting(false)
    }
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const response = await api.saveSettings(toPayload(def, values, saved))
      onSaved(response.sections)
      setValues(initialValues(def, response.sections[def.id] ?? {}))
      setParts(initialParts(def, response.sections[def.id] ?? {}))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const hasTest = def.id !== 'letterboxd'

  return (
    <div className="space-y-4">
      {def.keyHint && (
        <p className="rounded-lg bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground ring-1 ring-white/[0.06]">
          {def.keyHint}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {def.fields.map((f) =>
          f.kind === 'url' ? (
            <div key={f.name} className="sm:col-span-2">
              <UrlInput
                id={`f-${f.name}`}
                parts={parts[f.name]}
                hostPlaceholder={placeholderHost(f)}
                onChange={(p) => {
                  setParts((all) => ({ ...all, [f.name]: p }))
                  set(f.name, joinUrl(p))
                }}
              />
            </div>
          ) : (
            <FieldInput
              key={f.name}
              field={f}
              value={values[f.name]}
              saved={saved[f.name]}
              test={test}
              onChange={(v) => set(f.name, v)}
            />
          ),
        )}
      </div>
      {test && (
        <div className="text-xs">
          {test.ok ? (
            <SuccessLine>
              Connected{test.version ? ` · ${test.version}` : ''}
              {typeof test.server_name === 'string' ? ` · ${test.server_name}` : ''}
              {typeof test.indexers === 'number' ? ` · ${test.indexers} indexers` : ''}
              {typeof test.metadata_lookup === 'string'
                ? ` · metadata: ${test.metadata_lookup}`
                : ''}
              {typeof test.bot === 'string' ? ` · ${test.bot}` : ''}
              {typeof test.user === 'string' ? ` · ${test.user}` : ''}
              {typeof test.sample === 'string' ? ` · ${test.sample}` : ''}
              {typeof test.reply === 'string' ? ` · replied “${test.reply}”` : ''}
            </SuccessLine>
          ) : (
            <p className="flex items-start gap-1.5 text-danger">
              <AlertCircle className="mt-px size-3.5 shrink-0" />
              {test.detail}
            </p>
          )}
        </div>
      )}
      {error && (
        <p className="flex items-start gap-1.5 text-xs text-danger">
          <AlertCircle className="mt-px size-3.5 shrink-0" />
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {hasTest && (
          <Button type="button" onClick={runTest} loading={testing}>
            {!testing && <Plug className="size-4" />}
            Test
          </Button>
        )}
        <Button type="button" variant="primary" onClick={save} loading={saving}>
          {saveLabel}
        </Button>
        {secondary}
      </div>
    </div>
  )
}

function choiceOptions(field: FieldDef, test: TestResult | null): string[] {
  if (!test?.ok || !field.from) return []
  if (field.from === 'root_folders') return (test.root_folders ?? []).map((r) => r.path)
  return (test[field.from] as string[] | undefined) ?? []
}

function FieldInput({
  field,
  value,
  saved,
  test,
  onChange,
}: {
  field: FieldDef
  value: string | boolean
  saved: SettingValue | undefined
  test: TestResult | null
  onChange: (v: string | boolean) => void
}) {
  const id = `f-${field.name}`
  const wide = field.kind === 'url' || field.kind === 'secret' || field.kind === 'ids'
  if (field.kind === 'toggle') {
    return (
      <div className="sm:col-span-2">
        <Toggle
          checked={Boolean(value)}
          onChange={onChange}
          label={field.label}
          description={field.hint}
        />
      </div>
    )
  }
  let control: React.ReactNode
  if (field.kind === 'secret') {
    control = (
      <SecretInput
        id={id}
        saved={isSecret(saved) && saved.set}
        value={String(value)}
        onChange={onChange}
        placeholder={field.placeholder}
      />
    )
  } else if (field.kind === 'choice') {
    const options = choiceOptions(field, test)
    const current = String(value)
    const all = current && !options.includes(current) ? [current, ...options] : options
    control = all.length ? (
      <Select id={id} value={current} onChange={(e) => onChange(e.target.value)}>
        {field.optional && <option value="">— same as default —</option>}
        {all.map((o) => {
          const free =
            field.from === 'root_folders'
              ? test?.root_folders?.find((r) => r.path === o)?.free_gb
              : undefined
          return (
            <option key={o} value={o}>
              {o}
              {free !== undefined ? `  ·  ${free} GB free` : ''}
            </option>
          )
        })}
      </Select>
    ) : (
      <div className="flex h-10 items-center rounded-lg px-3.5 text-xs text-muted-foreground ring-1 ring-white/[0.06] ring-dashed">
        Test the connection to choose
      </div>
    )
  } else {
    control = (
      <Input
        id={id}
        type={field.kind === 'number' ? 'number' : field.kind === 'url' ? 'url' : 'text'}
        inputMode={field.kind === 'ids' ? 'numeric' : undefined}
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        spellCheck={false}
        autoComplete="off"
      />
    )
  }
  return (
    <Field
      label={field.label + (field.optional ? '' : '')}
      hint={field.kind === 'choice' ? field.hint : field.hint}
      htmlFor={id}
      className={cn(wide && 'sm:col-span-2')}
    >
      {control}
    </Field>
  )
}

export function ServiceCard({
  def,
  sections,
  onSaved,
  defaultOpen = false,
}: {
  def: ServiceDef
  sections: Sections
  onSaved: (sections: Sections) => void
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const configured = isConfigured(def, sections[def.id])
  return (
    <Panel className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-white/[0.02]"
      >
        <ServiceMonogram name={def.title} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{def.title}</span>
            {def.adult && <Badge>18+</Badge>}
            {def.recommended && !configured && <Badge tone="accent">Recommended</Badge>}
          </div>
          <p className="truncate text-xs text-muted-foreground">{def.tagline}</p>
        </div>
        {configured ? <Badge tone="success">Configured</Badge> : <Badge>Not set</Badge>}
        <ChevronDown
          className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="border-t border-white/[0.06] px-5 py-5">
          <ServiceForm def={def} sections={sections} onSaved={onSaved} />
        </div>
      )}
    </Panel>
  )
}

const MONOGRAM_COLORS: Record<string, string> = {
  Jellyfin: 'from-[#7b5cd6] to-[#3aa0d8]',
  Sonarr: 'from-[#2d9cdb] to-[#1d5f8a]',
  Radarr: 'from-[#f0b429] to-[#b7791f]',
  Whisparr: 'from-[#c2477b] to-[#7a2a4e]',
  Prowlarr: 'from-[#e66b3b] to-[#9c3d1c]',
  qBittorrent: 'from-[#3b82c4] to-[#1f4f7a]',
  TMDB: 'from-[#22c1a0] to-[#0d7d6a]',
  OMDb: 'from-[#d4a64a] to-[#8a6a2a]',
  Trakt: 'from-[#e5484d] to-[#8f2427]',
  AniList: 'from-[#3db4f2] to-[#1b6d99]',
  StashDB: 'from-[#8b7cf6] to-[#4c3fa8]',
  Telegram: 'from-[#2aabee] to-[#1a78a8]',
}

export function ServiceMonogram({ name, className }: { name: string; className?: string }) {
  return (
    <div
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-sm font-semibold text-white shadow-inner ring-1 ring-white/10',
        MONOGRAM_COLORS[name] ?? 'from-white/20 to-white/5',
        className,
      )}
    >
      {name.slice(0, 2)}
    </div>
  )
}
