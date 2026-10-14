import { AlertCircle, Plug } from 'lucide-react'
import { useState } from 'react'

import { Button, Field, Input, SecretInput, SuccessLine } from '@/components/ui/primitives'
import { api, isSecret, type Sections, type TestResult } from '@/lib/api'
import { PROVIDERS } from '@/lib/services'
import { cn } from '@/lib/utils'

export function AiForm({
  sections,
  onSaved,
  saveLabel = 'Save',
}: {
  sections: Sections
  onSaved: (sections: Sections) => void
  saveLabel?: string
}) {
  const ai = sections.ai ?? {}
  const [provider, setProvider] = useState(String(ai.MAESTARR_LLM_PROVIDER ?? 'anthropic'))
  const [model, setModel] = useState(String(ai.MAESTARR_MODEL ?? ''))
  const [key, setKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(String(ai.MAESTARR_MODEL_BASE_URL ?? ''))
  const [test, setTest] = useState<TestResult | null>(null)
  const [busy, setBusy] = useState<'test' | 'save' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const def = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0]
  const keySaved =
    isSecret(ai.MAESTARR_LLM_API_KEY) &&
    ai.MAESTARR_LLM_API_KEY.set &&
    provider === ai.MAESTARR_LLM_PROVIDER

  const choose = (id: string) => {
    const next = PROVIDERS.find((p) => p.id === id)
    setProvider(id)
    if (next && (!model || PROVIDERS.some((p) => p.defaultModel === model)))
      setModel(next.defaultModel)
    setTest(null)
    setError(null)
  }

  const payload = () => {
    const out: Record<string, unknown> = {
      MAESTARR_LLM_PROVIDER: provider,
      MAESTARR_MODEL: model.trim() || def.defaultModel,
      MAESTARR_MODEL_BASE_URL: def.needsUrl ? baseUrl.trim() || null : null,
    }
    if (key.trim()) out.MAESTARR_LLM_API_KEY = key.trim()
    return out
  }

  const runTest = async () => {
    setBusy('test')
    try {
      setTest(await api.testService('ai', payload()))
    } catch (e) {
      setTest({ ok: false, detail: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    setBusy('save')
    setError(null)
    try {
      const res = await api.saveSettings(payload())
      setKey('')
      onSaved(res.sections)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => choose(p.id)}
            className={cn(
              'rounded-xl px-3.5 py-3 text-left ring-1 transition',
              provider === p.id
                ? 'bg-primary/10 ring-primary/50'
                : 'bg-white/[0.03] ring-white/[0.08] hover:bg-white/[0.06]',
            )}
          >
            <div className="text-sm font-medium">{p.name}</div>
            <div className="text-xs text-muted-foreground">{p.blurb}</div>
          </button>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Model"
          htmlFor="ai-model"
          hint={
            def.defaultModel ? `e.g. ${def.defaultModel}` : 'The model name your server exposes'
          }
        >
          <Input
            id="ai-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={def.defaultModel}
            spellCheck={false}
          />
        </Field>
        {def.needsUrl && (
          <Field label="Server address" htmlFor="ai-url">
            <Input
              id="ai-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={def.urlPlaceholder}
              spellCheck={false}
            />
          </Field>
        )}
        <Field
          label={def.needsKey ? 'API key' : 'API key (if your server needs one)'}
          htmlFor="ai-key"
          hint={def.keyHint}
          className="sm:col-span-2"
        >
          <SecretInput id="ai-key" saved={Boolean(keySaved)} value={key} onChange={setKey} />
        </Field>
      </div>
      {test &&
        (test.ok ? (
          <SuccessLine>The model answered: “{String(test.reply)}”</SuccessLine>
        ) : (
          <p className="flex items-start gap-1.5 text-xs text-danger">
            <AlertCircle className="mt-px size-3.5 shrink-0" />
            {test.detail}
          </p>
        ))}
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex gap-2">
        <Button onClick={runTest} loading={busy === 'test'}>
          {busy !== 'test' && <Plug className="size-4" />}
          Test
        </Button>
        <Button variant="primary" onClick={save} loading={busy === 'save'}>
          {saveLabel}
        </Button>
      </div>
    </div>
  )
}
