import { AlertCircle, ExternalLink, Plug, Send, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button, Field, Input, SecretInput, Spinner, SuccessLine } from '@/components/ui/primitives'
import { api, isSecret, type Sections } from '@/lib/api'

/**
 * Telegram in three moves: paste the token, test it, send /start to the bot.
 * The page long-polls the server for that /start and allows the chat itself.
 */
export function TelegramForm({
  sections,
  onSaved,
}: {
  sections: Sections
  onSaved: (sections: Sections) => void
}) {
  const tg = sections.telegram ?? {}
  const tokenSaved = isSecret(tg.TELEGRAM_BOT_TOKEN) && tg.TELEGRAM_BOT_TOKEN.set
  const allowed = Array.isArray(tg.TELEGRAM_ALLOWED_CHAT_IDS)
    ? (tg.TELEGRAM_ALLOWED_CHAT_IDS as number[])
    : []
  const [token, setToken] = useState('')
  const [botName, setBotName] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const [connected, setConnected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [manual, setManual] = useState('')
  const alive = useRef(true)
  // Bumped on cancel so an in-flight poll loop stops after its current request.
  const run = useRef(0)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const tokenField = () => (token.trim() ? { TELEGRAM_BOT_TOKEN: token.trim() } : {})

  const save = async (ids: number[]) => {
    const res = await api.saveSettings({ ...tokenField(), TELEGRAM_ALLOWED_CHAT_IDS: ids })
    setToken('')
    onSaved(res.sections)
  }

  const waitForStart = async () => {
    const mine = ++run.current
    setWaiting(true)
    setError(null)
    setConnected(null)
    try {
      while (alive.current && run.current === mine) {
        const res = await api.telegramPair(tokenField())
        if (run.current !== mine) return
        if (!res.ok) {
          setError(res.detail ?? 'pairing failed')
          return
        }
        if (!res.waiting && res.chat_id) {
          await save([...new Set([...allowed, res.chat_id])])
          setConnected(res.name ?? String(res.chat_id))
          return
        }
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      if (run.current === mine) setWaiting(false)
    }
  }

  const test = async () => {
    setBusy(true)
    setError(null)
    setBotName(null)
    try {
      const res = await api.testService('telegram', tokenField())
      if (!res.ok) {
        setError(res.detail ?? 'token rejected')
        return
      }
      setBotName(String(res.bot))
      void waitForStart()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    try {
      await save(allowed.filter((x) => x !== id))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const addManual = async () => {
    const id = Number(manual.trim())
    if (!Number.isInteger(id)) return setError('a chat id is a whole number')
    try {
      await save([...new Set([...allowed, id])])
      setManual('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handle = botName?.replace(/^@/, '')

  return (
    <div className="space-y-5">
      <Field
        label="Bot token"
        htmlFor="tg-token"
        hint="Talk to @BotFather in Telegram → /newbot, then paste the token it gives you."
      >
        <SecretInput id="tg-token" saved={Boolean(tokenSaved)} value={token} onChange={setToken} />
      </Field>

      {!waiting && !botName && (
        <Button onClick={test} loading={busy} disabled={!token.trim() && !tokenSaved}>
          {!busy && <Plug className="size-4" />}
          Test and connect
        </Button>
      )}

      {botName && (waiting || connected) && (
        <div className="rounded-xl bg-white/[0.03] p-4 ring-1 ring-white/[0.08]">
          <SuccessLine>Token works: {botName}</SuccessLine>
          {waiting && (
            <div className="mt-3 space-y-3">
              <p className="text-sm">
                Now open your bot in Telegram and send <code className="font-mono">/start</code>.
                This page picks up your chat by itself.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                {handle && (
                  <a
                    href={`https://t.me/${handle}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-sm text-primary ring-1 ring-primary/40 hover:bg-primary/25"
                  >
                    <Send className="size-3.5" />
                    Open {botName}
                    <ExternalLink className="size-3" />
                  </a>
                )}
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Spinner className="size-3.5" />
                  Waiting for /start…
                </span>
                <Button
                  variant="ghost"
                  onClick={() => {
                    run.current++
                    setWaiting(false)
                    setBotName(null)
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {connected && <SuccessLine>Connected: {connected}. Say hi to your bot.</SuccessLine>}
        </div>
      )}

      {error && (
        <p className="flex items-start gap-1.5 text-xs text-danger">
          <AlertCircle className="mt-px size-3.5 shrink-0" />
          {error}
        </p>
      )}

      <div className="space-y-2 border-t border-white/[0.06] pt-4">
        <p className="text-xs font-medium text-muted-foreground">Allowed chats</p>
        {allowed.length === 0 && (
          <p className="text-xs text-muted-foreground">None yet: the bot answers no one.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {allowed.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.05] px-2.5 py-1 font-mono text-xs ring-1 ring-white/[0.08]"
            >
              {id}
              <button
                type="button"
                aria-label={`Remove ${id}`}
                onClick={() => remove(id)}
                className="text-muted-foreground hover:text-danger"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="Add a chat id by hand"
            className="max-w-xs font-mono"
            inputMode="numeric"
          />
          <Button variant="secondary" onClick={addManual} disabled={!manual.trim()}>
            Add
          </Button>
        </div>
      </div>
    </div>
  )
}
