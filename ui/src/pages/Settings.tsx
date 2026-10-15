import { Copy, KeyRound, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router'

import { AdultSwitch } from '@/components/AdultSwitch'
import { AiForm } from '@/components/AiForm'
import { CachingSettings } from '@/components/CachingSettings'
import { LanguagePicker } from '@/components/LanguagePicker'
import { useStatus } from '@/hooks/useStatus'
import { ServiceCard, ServiceForm } from '@/components/ServiceForm'
import { TelegramForm } from '@/components/TelegramForm'
import {
  Badge,
  Button,
  Field,
  Input,
  Panel,
  PasswordInput,
  Select,
  Spinner,
  StatusDot,
  SuccessLine,
  Toggle,
} from '@/components/ui/primitives'
import { api, type Preferences, type Sections } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { SERVICE_NAMES, SERVICES } from '@/lib/services'
import { cn } from '@/lib/utils'

const TABS = [
  { id: 'general', label: 'General' },
  { id: 'ai', label: 'AI model' },
  { id: 'media', label: 'Media server' },
  { id: 'services', label: 'Services' },
  { id: 'discovery', label: 'Discovery' },
  { id: 'telegram', label: 'Telegram' },
  { id: 'proxy', label: 'Proxy' },
  { id: 'preferences', label: 'Download preferences' },
  { id: 'api', label: 'API & MCP' },
]

export default function SettingsPage() {
  const { tab = 'general' } = useParams()
  const navigate = useNavigate()
  const [sections, setSections] = useState<Sections | null>(null)
  const [apiTokenSet, setApiTokenSet] = useState(false)

  useEffect(() => {
    api
      .settings()
      .then((r) => {
        setSections(r.sections)
        setApiTokenSet(Boolean(r.api_token_set))
      })
      .catch(() => setSections({}))
  }, [])

  useEffect(() => {
    if (!TABS.some((t) => t.id === tab)) navigate('/settings/general', { replace: true })
  }, [tab, navigate])

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8">
        <h1 className="mb-6 text-2xl font-semibold tracking-tight">Settings</h1>
        <div className="grid gap-6 md:grid-cols-[200px_1fr]">
          <nav className="flex gap-1 overflow-x-auto md:flex-col">
            {TABS.map((t) => (
              <NavLink
                key={t.id}
                to={`/settings/${t.id}`}
                className={({ isActive }) =>
                  cn(
                    'rounded-lg px-3 py-2 text-sm whitespace-nowrap transition',
                    isActive
                      ? 'bg-white/[0.08] text-foreground'
                      : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
                  )
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          <div className="min-w-0 space-y-4">
            {!sections ? (
              <Spinner />
            ) : (
              <>
                {tab === 'general' && (
                  <Section title="Language" subtitle="The language Maestarr answers you in.">
                    <LanguagePicker sections={sections} onSaved={setSections} />
                  </Section>
                )}
                {tab === 'general' && (
                  <Section
                    title="Caching"
                    subtitle="Faster pages: slow sources are read once and kept."
                  >
                    <CachingSettings sections={sections} onSaved={setSections} />
                  </Section>
                )}
                {tab === 'general' && <GeneralTab />}
                {tab === 'ai' && (
                  <Section
                    title="AI model"
                    subtitle="The model that chats, judges releases and recommends."
                  >
                    <AiForm sections={sections} onSaved={setSections} />
                  </Section>
                )}
                {tab === 'media' && (
                  <Section
                    title="Jellyfin"
                    subtitle="Watch history for recommendations. Read-only."
                  >
                    <ServiceForm
                      def={SERVICES.jellyfin}
                      sections={sections}
                      onSaved={setSections}
                    />
                  </Section>
                )}
                {tab === 'services' &&
                  ['sonarr', 'radarr', 'qbittorrent', 'prowlarr', 'whisparr'].map((id) => (
                    <ServiceCard
                      key={id}
                      def={SERVICES[id]}
                      sections={sections}
                      onSaved={setSections}
                    />
                  ))}
                {tab === 'discovery' &&
                  ['seerr', 'tmdb', 'omdb', 'trakt', 'anilist', 'stashdb'].map((id) => (
                    <ServiceCard
                      key={id}
                      def={SERVICES[id]}
                      sections={sections}
                      onSaved={setSections}
                    />
                  ))}
                {tab === 'discovery' && <AdultSwitch sections={sections} onSaved={setSections} />}
                {tab === 'telegram' && (
                  <Section title="Telegram" subtitle={SERVICES.telegram.tagline}>
                    <TelegramForm sections={sections} onSaved={setSections} />
                  </Section>
                )}
                {tab === 'proxy' && (
                  <Section title="Proxy" subtitle={SERVICES.proxy.tagline}>
                    <ServiceForm def={SERVICES.proxy} sections={sections} onSaved={setSections} />
                  </Section>
                )}
                {tab === 'preferences' && <PreferencesTab />}
                {tab === 'api' && <ApiTab tokenSet={apiTokenSet} onChange={setApiTokenSet} />}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <Panel className="p-6">
      <div className="mb-5">
        <h2 className="font-semibold tracking-tight">{title}</h2>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {children}
    </Panel>
  )
}

function GeneralTab() {
  const status = useStatus(30_000)
  const { state } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const change = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.changePassword(current, next)
      setMessage({ ok: true, text: 'Password changed — sign in again on your other devices.' })
      setCurrent('')
      setNext('')
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Section
        title="Status"
        subtitle={status ? `Maestarr ${status.version} · ${status.model}` : 'Checking…'}
      >
        {!status ? (
          <Spinner />
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {status.services.map((s) => (
              <li
                key={s.name}
                className="flex items-center gap-3 rounded-lg bg-white/[0.03] px-3 py-2.5 ring-1 ring-white/[0.06]"
              >
                <StatusDot state={!s.configured ? 'off' : s.ok ? 'ok' : 'down'} />
                <span className="text-sm">{SERVICE_NAMES[s.name] ?? s.name}</span>
                <span
                  className="ml-auto truncate text-xs text-muted-foreground"
                  title={s.detail ?? undefined}
                >
                  {!s.configured
                    ? (s.detail ?? 'not set')
                    : s.ok
                      ? s.version
                      : (s.detail ?? 'unreachable')}
                </span>
              </li>
            ))}
            <li className="flex items-center gap-3 rounded-lg bg-white/[0.03] px-3 py-2.5 ring-1 ring-white/[0.06]">
              <StatusDot state={status.model_ready ? 'ok' : 'down'} />
              <span className="text-sm">AI model</span>
              <span className="ml-auto truncate text-xs text-muted-foreground">
                {status.model_ready ? status.model : 'not configured'}
              </span>
            </li>
          </ul>
        )}
      </Section>
      <Section title="Account" subtitle={`Signed in as ${state?.user?.username}`}>
        <form onSubmit={change} className="grid max-w-lg gap-4 sm:grid-cols-2">
          <Field label="Current password" htmlFor="cp">
            <PasswordInput
              id="cp"
              autoComplete="current-password"
              value={current}
              onChange={setCurrent}
            />
          </Field>
          <Field label="New password" htmlFor="np" hint="At least 8 characters.">
            <PasswordInput id="np" autoComplete="new-password" value={next} onChange={setNext} />
          </Field>
          <div className="sm:col-span-2">
            <Button type="submit" loading={busy} disabled={!current || next.length < 8}>
              Change password
            </Button>
            {message && (
              <p className={cn('mt-2 text-xs', message.ok ? 'text-success' : 'text-danger')}>
                {message.text}
              </p>
            )}
          </div>
        </form>
      </Section>
    </>
  )
}

const RES = [480, 720, 1080, 2160]

function PreferencesTab() {
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .preferences()
      .then(setPrefs)
      .catch(() => undefined)
  }, [])
  if (!prefs) return <Spinner />
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => {
    setPrefs({ ...prefs, [k]: v })
    setSaved(false)
  }
  const list = (v: string[]) => v.join(', ')
  const parse = (s: string) =>
    s
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)

  return (
    <Section
      title="Download preferences"
      subtitle="How the release judge weighs quality, size and swarm health. The assistant can change these too."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Audio languages" hint="In order. “Original” means the title's own language.">
          <Input
            value={list(prefs.audio_languages)}
            onChange={(e) => set('audio_languages', parse(e.target.value))}
          />
        </Field>
        <Field label="Subtitle languages">
          <Input
            value={list(prefs.subtitle_languages)}
            onChange={(e) => set('subtitle_languages', parse(e.target.value))}
          />
        </Field>
        <Field label="Lowest resolution">
          <Select
            value={prefs.min_resolution}
            onChange={(e) => set('min_resolution', Number(e.target.value))}
          >
            {RES.map((r) => (
              <option key={r} value={r}>
                {r}p
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Highest resolution">
          <Select
            value={prefs.max_resolution}
            onChange={(e) => set('max_resolution', Number(e.target.value))}
          >
            {RES.map((r) => (
              <option key={r} value={r}>
                {r}p
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Max GB per episode" hint="Soft cap; empty = no cap.">
          <Input
            type="number"
            min={0}
            step={0.1}
            value={prefs.max_gb_per_episode ?? ''}
            onChange={(e) =>
              set('max_gb_per_episode', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </Field>
        <Field label="Max GB per movie" hint="Soft cap; empty = no cap.">
          <Input
            type="number"
            min={0}
            step={0.5}
            value={prefs.max_gb_per_movie ?? ''}
            onChange={(e) =>
              set('max_gb_per_movie', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </Field>
        <Field label="Minimum live seeders">
          <Input
            type="number"
            min={0}
            value={prefs.min_live_seeders}
            onChange={(e) => set('min_live_seeders', Number(e.target.value))}
          />
        </Field>
        <Field
          label="Minimum 1080p bitrate (Mbps)"
          hint="Below this a 1080p encode counts as starved."
        >
          <Input
            type="number"
            min={0}
            step={0.5}
            value={prefs.min_1080p_mbps}
            onChange={(e) => set('min_1080p_mbps', Number(e.target.value))}
          />
        </Field>
        <Field label="Preferred release groups">
          <Input
            value={list(prefs.prefer_groups)}
            onChange={(e) => set('prefer_groups', parse(e.target.value))}
          />
        </Field>
        <Field label="Groups to avoid">
          <Input
            value={list(prefs.avoid_groups)}
            onChange={(e) => set('avoid_groups', parse(e.target.value))}
          />
        </Field>
        <div className="space-y-3 sm:col-span-2">
          <Toggle
            checked={prefs.allow_remux}
            onChange={(v) => set('allow_remux', v)}
            label="Allow remuxes"
            description="Untouched Blu-ray video; the largest files."
          />
          <Toggle
            checked={prefs.prefer_season_packs}
            onChange={(v) => set('prefer_season_packs', v)}
            label="Prefer season packs"
          />
        </div>
        <Field
          label="Notes for the judge"
          className="sm:col-span-2"
          hint="Plain language, e.g. “Old cartoons don't need remux quality.”"
        >
          <textarea
            value={prefs.notes}
            onChange={(e) => set('notes', e.target.value)}
            rows={3}
            className="w-full rounded-lg bg-black/25 px-3.5 py-2.5 text-sm ring-1 ring-white/10 outline-none focus:ring-2 focus:ring-ring/50"
          />
        </Field>
      </div>
      <div className="mt-5 flex items-center gap-3">
        <Button
          variant="primary"
          loading={busy}
          onClick={async () => {
            setBusy(true)
            const res = await api.savePreferences(prefs)
            setPrefs(res.saved)
            setSaved(true)
            setBusy(false)
          }}
        >
          Save
        </Button>
        {saved && <SuccessLine>Saved</SuccessLine>}
      </div>
    </Section>
  )
}

function ApiTab({ tokenSet, onChange }: { tokenSet: boolean; onChange: (v: boolean) => void }) {
  const [token, setToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const base = window.location.origin
  const create = async () => {
    const res = await api.createApiToken()
    setToken(res.token)
    onChange(true)
  }
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  const mcpConfig = JSON.stringify(
    {
      mcpServers: {
        maestarr: {
          type: 'http',
          url: `${base}/mcp`,
          headers: { Authorization: `Bearer ${token ?? '<your API key>'}` },
        },
      },
    },
    null,
    2,
  )
  return (
    <>
      <Section
        title="API key"
        subtitle="For MCP clients (Claude Desktop, Claude Code…) and scripts. The web UI uses your login instead."
      >
        <div className="flex flex-wrap items-center gap-3">
          {tokenSet ? <Badge tone="success">An API key exists</Badge> : <Badge>No API key</Badge>}
          <Button onClick={create}>
            {tokenSet ? <RefreshCw className="size-4" /> : <KeyRound className="size-4" />}
            {tokenSet ? 'Replace key' : 'Create key'}
          </Button>
          {tokenSet && (
            <Button
              variant="ghost"
              onClick={async () => {
                await api.deleteApiToken()
                setToken(null)
                onChange(false)
              }}
            >
              <Trash2 className="size-4" />
              Revoke
            </Button>
          )}
        </div>
        {token && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-primary">Copy it now — it will not be shown again.</p>
            <div className="flex gap-2">
              <Input
                readOnly
                value={token}
                className="font-mono"
                onFocus={(e) => e.target.select()}
              />
              <Button onClick={() => copy(token)}>
                <Copy className="size-4" />
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>
        )}
      </Section>
      <Section
        title="MCP"
        subtitle="Every tool the assistant has, for any MCP client. Destructive tools are marked as such."
      >
        <p className="mb-2 text-sm text-muted-foreground">
          Streamable HTTP endpoint:{' '}
          <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-xs">
            {base}/mcp
          </code>
        </p>
        <pre className="scroll-thin overflow-x-auto rounded-lg bg-black/30 p-4 font-mono text-xs text-muted-foreground ring-1 ring-white/[0.06]">
          {mcpConfig}
        </pre>
        <p className="mt-3 text-xs text-muted-foreground">
          Local clients can also run <code className="font-mono">maestarr serve-mcp</code> over
          stdio.
        </p>
      </Section>
    </>
  )
}
