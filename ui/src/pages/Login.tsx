import { useState } from 'react'

import { Button, Field, Input, Logo, Panel } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

export default function LoginPage() {
  const { refresh } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(username.trim(), password)
      await refresh()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <Panel className="w-full max-w-sm p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Logo className="size-12" />
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Sign in to Maestarr</h1>
            <p className="text-sm text-muted-foreground">
              Your stack is waiting for its conductor.
            </p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Username" htmlFor="u">
            <Input
              id="u"
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field label="Password" htmlFor="p">
            <Input
              id="p"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button
            type="submit"
            variant="primary"
            className="w-full"
            loading={busy}
            disabled={!username || !password}
          >
            Sign in
          </Button>
        </form>
      </Panel>
    </div>
  )
}
