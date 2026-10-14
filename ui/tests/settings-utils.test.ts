import { describe, expect, it } from 'vitest'

import { isSecret } from '@/lib/api'
import { SERVICES } from '@/lib/services'
import { isConfigured } from '@/lib/settings-utils'

describe('isConfigured', () => {
  it('is true once the first required field is set', () => {
    expect(isConfigured(SERVICES.sonarr, { SONARR_URL: 'http://sonarr:8989' })).toBe(true)
    expect(isConfigured(SERVICES.sonarr, { SONARR_URL: null })).toBe(false)
    expect(isConfigured(SERVICES.sonarr, undefined)).toBe(false)
  })

  it('reads secret placeholders', () => {
    expect(isConfigured(SERVICES.tmdb, { TMDB_API_KEY: { set: true } })).toBe(true)
    expect(isConfigured(SERVICES.tmdb, { TMDB_API_KEY: { set: false } })).toBe(false)
  })
})

describe('service definitions', () => {
  it('every field name is unique and upper-case', () => {
    const names = Object.values(SERVICES).flatMap((s) => s.fields.map((f) => f.name))
    expect(new Set(names).size).toBe(names.length)
    for (const n of names) expect(n).toMatch(/^[A-Z0-9_]+$/)
  })

  it('adult integrations are flagged', () => {
    expect(SERVICES.whisparr.adult).toBe(true)
    expect(SERVICES.stashdb.adult).toBe(true)
  })
})

describe('isSecret', () => {
  it('distinguishes secret placeholders from values', () => {
    expect(isSecret({ set: true })).toBe(true)
    expect(isSecret('x')).toBe(false)
    expect(isSecret([1, 2])).toBe(false)
    expect(isSecret(null)).toBe(false)
  })
})
