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
      {on && (
        <div className="mt-4 border-t border-white/[0.06] pt-4">
          <Toggle
            checked={Boolean(sections.adult?.MAESTARR_HOME_ADULT_DOWNLOADS)}
            onChange={async (v) => {
              try {
                onSaved((await api.saveSettings({ MAESTARR_HOME_ADULT_DOWNLOADS: v })).sections)
              } catch (e) {
                setError((e as Error).message)
              }
            }}
            label="Show adult downloads on the home page"
            description="Off: Whisparr downloads stay out of the home page's Downloading panel."
          />
        </div>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </Panel>
  )
}
