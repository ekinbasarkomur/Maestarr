import { useCallback, useEffect, useState, type ReactNode } from 'react'

import { api, type AuthState } from '@/lib/api'
import { AuthContext } from '@/lib/auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const next = await api.authState()
      setState(next)
      setError(null)
      return next
    } catch (e) {
      setError((e as Error).message)
      return null
    }
  }, [])

  useEffect(() => {
    let alive = true
    api
      .authState()
      .then((next) => alive && setState(next))
      .catch((e) => alive && setError((e as Error).message))
    return () => {
      alive = false
    }
  }, [])

  return <AuthContext.Provider value={{ state, error, refresh }}>{children}</AuthContext.Provider>
}
