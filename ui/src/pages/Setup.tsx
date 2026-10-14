import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { AiForm } from '@/components/AiForm'
import { ServiceCard, ServiceForm } from '@/components/ServiceForm'
import { Button, Field, Input, Logo, Panel, Spinner } from '@/components/ui/primitives'
import { api, type Sections } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { SERVICES } from '@/lib/services'
import { cn } from '@/lib/utils'

type StepId = 'account' | 'ai' | 'media' | 'services' | 'discovery' | 'telegram' | 'done'

const STEPS: { id: StepId; title: string; subtitle: string }[] = [
  { id: 'account', title: 'Your account', subtitle: 'The login for this Maestarr.' },
  { id: 'ai', title: 'AI model', subtitle: 'The brain that talks and decides.' },
  { id: 'media', title: 'Media server', subtitle: 'Where you watch — for your taste.' },
  { id: 'services', title: 'Your stack', subtitle: 'Sonarr, Radarr, downloads.' },
  { id: 'discovery', title: 'Discovery', subtitle: 'Databases for search and picks.' },
  { id: 'telegram', title: 'Telegram', subtitle: 'Optional: chat from your phone.' },
  { id: 'done', title: 'Ready', subtitle: 'Start conducting.' },
]

export default function SetupPage() {
  const { state, refresh } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState<StepId>(state?.has_account ? 'ai' : 'account')
  const [sections, setSections] = useState<Sections | null>(null)

  useEffect(() => {
    if (state?.has_account && state.user)
      api
        .settings()
        .then((r) => setSections(r.sections))
        .catch(() => setSections({}))
  }, [state?.has_account, state?.user])

  const index = STEPS.findIndex((s) => s.id === step)
  const go = (delta: number) =>
    setStep(STEPS[Math.min(STEPS.length - 1, Math.max(1, index + delta))].id)

  const finish = async () => {
    await api.completeSetup()
    await refresh()
    navigate('/', { replace: true })
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-5xl">
        <header className="mb-8 flex items-center gap-3">
          <Logo className="size-9" />
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Welcome to Maestarr</h1>
            <p className="text-sm text-muted-foreground">
              A few steps and your stack has a conductor.
            </p>
          </div>
        </header>
        <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
          <Stepper current={index} />
          <Panel className="p-6 sm:p-8">
            <div className="mb-6">
              <p className="text-xs font-medium tracking-wider text-primary uppercase">
                Step {index + 1} of {STEPS.length}
              </p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight">{STEPS[index].title}</h2>
              <p className="text-sm text-muted-foreground">{STEPS[index].subtitle}</p>
            </div>
            {step === 'account' && (
              <AccountStep
                onDone={async () => {
                  await refresh()
                  setStep('ai')
                }}
              />
            )}
            {step !== 'account' && !sections && <Spinner />}
            {step !== 'account' && sections && (
              <StepBody
                step={step}
                sections={sections}
                setSections={setSections}
                next={() => go(1)}
              />
            )}
            {step !== 'account' && step !== 'done' && sections && (
              <div className="mt-8 flex items-center justify-between border-t border-white/[0.06] pt-5">
                <Button variant="ghost" onClick={() => go(-1)} disabled={index <= 1}>
                  <ArrowLeft className="size-4" />
                  Back
                </Button>
                <Button variant="secondary" onClick={() => go(1)}>
                  {step === 'ai' ? 'Next' : 'Skip / next'}
                  <ArrowRight className="size-4" />
                </Button>
              </div>
            )}
            {step === 'done' && sections && (
              <DoneStep sections={sections} onFinish={finish} onBack={() => go(-1)} />
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}

function Stepper({ current }: { current: number }) {
  return (
    <ol className="glass hidden h-fit rounded-2xl p-3 lg:block">
      {STEPS.map((s, i) => (
        <li
          key={s.id}
          className={cn(
            'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition',
            i === current ? 'bg-white/[0.06] text-foreground' : 'text-muted-foreground',
          )}
        >
          <span
            className={cn(
              'flex size-6 items-center justify-center rounded-full text-[11px] font-semibold ring-1',
              i < current && 'bg-primary text-primary-foreground ring-primary',
              i === current && 'ring-primary text-primary',
              i > current && 'ring-white/15',
            )}
          >
            {i < current ? <Check className="size-3.5" /> : i + 1}
          </span>
          {s.title}
        </li>
      ))}
    </ol>
  )
}

function AccountStep({ onDone }: { onDone: () => Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const mismatch = confirm.length > 0 && confirm !== password

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 8) return setError('Use at least 8 characters.')
    if (password !== confirm) return setError('The passwords do not match.')
    setBusy(true)
    try {
      await api.setupAccount(username.trim(), password)
      await onDone()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-4">
      <Field label="Username" htmlFor="u">
        <Input
          id="u"
          autoFocus
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </Field>
      <Field label="Password" htmlFor="p" hint="At least 8 characters.">
        <Input
          id="p"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field
        label="Confirm password"
        htmlFor="c"
        hint={mismatch ? 'Does not match yet.' : undefined}
      >
        <Input
          id="c"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </Field>
      {error && <p className="text-sm text-danger">{error}</p>}
      <Button
        type="submit"
        variant="primary"
        loading={busy}
        disabled={!username.trim() || !password}
      >
        Create account
        <ArrowRight className="size-4" />
      </Button>
    </form>
  )
}

function StepBody({
  step,
  sections,
  setSections,
  next,
}: {
  step: StepId
  sections: Sections
  setSections: (s: Sections) => void
  next: () => void
}) {
  if (step === 'ai') {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Maestarr needs a language model to chat, judge releases and pick recommendations. Use a
          cloud provider, or point it at your own Ollama.
        </p>
        <AiForm
          sections={sections}
          saveLabel="Save and continue"
          onSaved={(s) => {
            setSections(s)
            next()
          }}
        />
      </div>
    )
  }
  if (step === 'media') {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Maestarr reads what you have watched to learn your taste. Nothing is changed on your
          server.
        </p>
        <ServiceForm
          def={SERVICES.jellyfin}
          sections={sections}
          saveLabel="Save and continue"
          onSaved={(s) => {
            setSections(s)
            next()
          }}
        />
        <p className="text-xs text-muted-foreground">Plex and Emby support is on the roadmap.</p>
      </div>
    )
  }
  if (step === 'services') {
    return (
      <div className="space-y-3">
        {['sonarr', 'radarr', 'qbittorrent', 'prowlarr', 'whisparr'].map((id, i) => (
          <ServiceCard
            key={id}
            def={SERVICES[id]}
            sections={sections}
            onSaved={setSections}
            defaultOpen={i === 0}
          />
        ))}
      </div>
    )
  }
  if (step === 'discovery') {
    return (
      <div className="space-y-3">
        {['tmdb', 'omdb', 'trakt', 'anilist', 'stashdb'].map((id, i) => (
          <ServiceCard
            key={id}
            def={SERVICES[id]}
            sections={sections}
            onSaved={setSections}
            defaultOpen={i === 0}
          />
        ))}
      </div>
    )
  }
  if (step === 'telegram') {
    return <ServiceForm def={SERVICES.telegram} sections={sections} onSaved={setSections} />
  }
  return null
}

function DoneStep({
  sections,
  onFinish,
  onBack,
}: {
  sections: Sections
  onFinish: () => Promise<void>
  onBack: () => void
}) {
  const [busy, setBusy] = useState(false)
  const summary = useMemo(() => {
    const has = (section: string, field: string) => {
      const v = sections[section]?.[field]
      return typeof v === 'object' && v !== null && !Array.isArray(v) ? v.set : Boolean(v)
    }
    return [
      {
        label: 'AI model',
        ok: has('ai', 'MAESTARR_LLM_API_KEY') || has('ai', 'MAESTARR_MODEL_BASE_URL'),
      },
      { label: 'Jellyfin', ok: has('jellyfin', 'JELLYFIN_URL') },
      { label: 'Sonarr', ok: has('sonarr', 'SONARR_URL') },
      { label: 'Radarr', ok: has('radarr', 'RADARR_URL') },
      { label: 'qBittorrent', ok: has('qbittorrent', 'QBITTORRENT_URL') },
      { label: 'Prowlarr', ok: has('prowlarr', 'PROWLARR_URL') },
      { label: 'Whisparr', ok: has('whisparr', 'WHISPARR_URL') },
      { label: 'TMDB', ok: has('tmdb', 'TMDB_API_KEY') },
      { label: 'Telegram', ok: has('telegram', 'TELEGRAM_BOT_TOKEN') },
    ]
  }, [sections])
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Everything can be changed later under Settings. Anything you skipped simply stays hidden
        from the assistant.
      </p>
      <ul className="grid gap-2 sm:grid-cols-3">
        {summary.map((s) => (
          <li
            key={s.label}
            className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-2 text-sm ring-1 ring-white/[0.06]"
          >
            <span className={cn('size-2 rounded-full', s.ok ? 'bg-success' : 'bg-white/20')} />
            {s.label}
            <span className="ml-auto text-xs text-muted-foreground">
              {s.ok ? 'connected' : 'skipped'}
            </span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t border-white/[0.06] pt-5">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="size-4" />
          Back
        </Button>
        <Button
          variant="primary"
          size="lg"
          loading={busy}
          onClick={async () => {
            setBusy(true)
            await onFinish()
          }}
        >
          Open Maestarr
          <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}
