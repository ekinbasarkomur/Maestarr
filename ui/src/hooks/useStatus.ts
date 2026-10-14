import { useEffect, useState } from 'react'

import { api, type StatusResponse } from '@/lib/api'

export function useStatus(intervalMs = 60_000) {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .status()
        .then((s) => alive && setStatus(s))
        .catch(() => undefined)
    void load()
    const t = window.setInterval(load, intervalMs)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [intervalMs])
  return status
}
