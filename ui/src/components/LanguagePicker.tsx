import { Check } from 'lucide-react'
import { useState } from 'react'

import { Field, Input, Select } from '@/components/ui/primitives'
import { api, type Sections } from '@/lib/api'

/** Common choices; anything else can be typed under "Other". */
const LANGUAGES = [
  'English',
  'Turkish',
  'German',
  'French',
  'Spanish',
  'Italian',
  'Portuguese',
  'Dutch',
  'Polish',
  'Russian',
  'Ukrainian',
  'Swedish',
  'Norwegian',
  'Danish',
  'Finnish',
  'Czech',
  'Greek',
  'Romanian',
  'Hungarian',
  'Arabic',
  'Hebrew',
  'Persian',
  'Hindi',
  'Japanese',
  'Korean',
  'Chinese',
  'Indonesian',
  'Vietnamese',
  'Thai',
]
const OTHER = '__other__'

/** The language Maestarr answers in; saved as soon as it changes. */
export function LanguagePicker({
  sections,
  onSaved,
}: {
  sections: Sections
  onSaved: (sections: Sections) => void
}) {
  const saved = String(sections.general?.MAESTARR_LANGUAGE ?? 'auto')
  const known = saved === 'auto' || LANGUAGES.includes(saved)
  const [choice, setChoice] = useState(known ? saved : OTHER)
  const [custom, setCustom] = useState(known ? '' : saved)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | string>('idle')

  const save = async (value: string) => {
    if (!value.trim()) return
    setState('saving')
    try {
      const res = await api.saveSettings({ MAESTARR_LANGUAGE: value.trim() })
      onSaved(res.sections)
      setState('saved')
    } catch (e) {
      setState((e as Error).message)
    }
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field
        label="Reply language"
        htmlFor="lang"
        hint="Maestarr answers in this language in the chat and on Telegram, and shows titles and overviews in it where available."
      >
        <Select
          id="lang"
          value={choice}
          onChange={(e) => {
            setChoice(e.target.value)
            if (e.target.value !== OTHER) void save(e.target.value)
          }}
        >
          <option value="auto">Same as my message</option>
          {LANGUAGES.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
          <option value={OTHER}>Other…</option>
        </Select>
      </Field>
      {choice === OTHER && (
        <Field label="Language" htmlFor="lang-other" hint="Any language the AI model speaks.">
          <Input
            id="lang-other"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onBlur={() => void save(custom)}
            onKeyDown={(e) => e.key === 'Enter' && void save(custom)}
            placeholder="e.g. Catalan"
          />
        </Field>
      )}
      <p className="text-xs text-muted-foreground sm:col-span-2">
        {state === 'saving' ? (
          'Saving…'
        ) : state === 'saved' ? (
          <span className="inline-flex items-center gap-1 text-success">
            <Check className="size-3.5" /> Saved — the next reply uses it.
          </span>
        ) : state !== 'idle' ? (
          <span className="text-danger">{state}</span>
        ) : null}
      </p>
    </div>
  )
}
