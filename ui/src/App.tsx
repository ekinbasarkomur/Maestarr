import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { Logo, Spinner } from '@/components/ui/primitives'
import { useAuth } from '@/lib/auth-context'

// One chunk per page: the login screen does not pay for the chat's markdown
// and streaming code.
const ChatPage = lazy(() => import('@/pages/Chat'))
const DiscoverPage = lazy(() => import('@/pages/Discover'))
const HomePage = lazy(() => import('@/pages/Home'))
const LoginPage = lazy(() => import('@/pages/Login'))
const SettingsPage = lazy(() => import('@/pages/Settings'))
const SetupPage = lazy(() => import('@/pages/Setup'))

function PageFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner />
    </div>
  )
}

export default function App() {
  const { state, error } = useAuth()
  const location = useLocation()

  if (!state) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <Logo className="size-12 opacity-90" />
        {error ? (
          <p className="text-sm text-danger">Cannot reach the Maestarr server: {error}</p>
        ) : (
          <Spinner />
        )}
      </div>
    )
  }

  const needsSetup = !state.has_account || (state.user && !state.setup_complete)
  if (needsSetup && location.pathname !== '/setup') return <Navigate to="/setup" replace />
  if (state.has_account && !state.user && location.pathname !== '/login')
    return <Navigate to="/login" replace />

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/setup" element={needsSetup ? <SetupPage /> : <Navigate to="/" replace />} />
        <Route path="/login" element={state.user ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
          <Route path="/discover" element={<DiscoverPage />} />
          <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
          <Route path="/settings/:tab" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
