export interface UrlParts {
  ssl: boolean
  host: string
  port: string
  base: string
}

/** Split a saved address into the Seerr-style parts.
 *  "https://media.example.com:8443/sonarr" → ssl, host, port 8443, base /sonarr */
export function parseUrl(value: string, defaultPort: string): UrlParts {
  if (!value) return { ssl: false, host: '', port: defaultPort, base: '' }
  try {
    const u = new URL(value.includes('://') ? value : `http://${value}`)
    const ssl = u.protocol === 'https:'
    return {
      ssl,
      host: u.hostname,
      port: u.port || (ssl ? '443' : '80'),
      base: u.pathname === '/' ? '' : u.pathname.replace(/\/$/, ''),
    }
  } catch {
    return { ssl: false, host: value, port: defaultPort, base: '' }
  }
}

/** Join the parts back into one address ("" when there is no host). */
export function joinUrl(p: UrlParts): string {
  const host = p.host
    .trim()
    .replace(/^https?:\/\//, '')
    .replace(/\/.*$/, '')
  if (!host) return ''
  const port = p.port.trim()
  const defaultPort = p.ssl ? '443' : '80'
  let base = p.base.trim()
  if (base && !base.startsWith('/')) base = `/${base}`
  base = base.replace(/\/+$/, '')
  return `${p.ssl ? 'https' : 'http'}://${host}${port && port !== defaultPort ? `:${port}` : ''}${base}`
}
