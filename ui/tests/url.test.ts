import { describe, expect, it } from 'vitest'

import { joinUrl, parseUrl } from '@/lib/url'

describe('parseUrl', () => {
  it('splits a full address', () => {
    expect(parseUrl('https://media.example.com:8443/sonarr', '8989')).toEqual({
      ssl: true,
      host: 'media.example.com',
      port: '8443',
      base: '/sonarr',
    })
  })
  it('fills the default port for an empty value', () => {
    expect(parseUrl('', '8989')).toEqual({ ssl: false, host: '', port: '8989', base: '' })
  })
  it('uses the scheme default when the address has no port', () => {
    expect(parseUrl('https://sonarr.example.com', '8989').port).toBe('443')
  })
})

describe('joinUrl', () => {
  it('builds an address and drops a default port', () => {
    expect(joinUrl({ ssl: false, host: 'sonarr', port: '8989', base: '' })).toBe(
      'http://sonarr:8989',
    )
    expect(joinUrl({ ssl: true, host: 'x.example.com', port: '443', base: 'sonarr/' })).toBe(
      'https://x.example.com/sonarr',
    )
  })
  it('tolerates a pasted scheme or path in the host box', () => {
    expect(joinUrl({ ssl: false, host: 'http://127.0.0.1/whatever', port: '8702', base: '' })).toBe(
      'http://127.0.0.1:8702',
    )
  })
  it('is empty without a host', () => {
    expect(joinUrl({ ssl: false, host: ' ', port: '8989', base: '' })).toBe('')
  })
  it('round-trips', () => {
    const url = 'http://192.168.1.10:7878/radarr'
    expect(joinUrl(parseUrl(url, '7878'))).toBe(url)
  })
})
