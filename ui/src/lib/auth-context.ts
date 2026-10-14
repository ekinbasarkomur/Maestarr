import { createContext, useContext } from 'react'

import type { AuthState } from '@/lib/api'

export interface AuthContextValue {
  state: AuthState | null
  error: string | null
  refresh: () => Promise<AuthState | null>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
