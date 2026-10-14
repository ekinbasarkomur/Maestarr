import { useState } from 'react'

import { Badge, Panel, Toggle } from '@/components/ui/primitives'
import { api, type Sections } from '@/lib/api'

/** The 18+ master switch: saved on click, gates Whisparr and StashDB everywhere. */
export function AdultSwitch({
  sections,
  onSaved,
}: {
  sections: Sections
  onSaved: (sections: Sections) => void
}) {
  const on = Boolean(sections.adult?.MAESTARR_ADULT_CONTENT)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const flip = async (next: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.saveSettings({ MAESTARR_ADULT_CONTENT: next })
      onSaved(res.sections)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel className="p-5">
      <div className="flex items-start justify-between gap-4">
        <Toggle
          checked={on}
          onChange={(v) => !busy && flip(v)}
          label="Adult content"
          description={
            on
              ? 'Whisparr and StashDB are in use. Adult titles only come up when you ask for them.'
              : 'Off: Maestarr never contacts Whisparr or StashDB, and search, discovery and recommendations show no adult results.'
          }
        />
        <Badge>18+</Badge>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </Panel>
  )
}
