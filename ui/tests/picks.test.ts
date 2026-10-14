import { describe, expect, it } from 'vitest'

import { searchPrompt } from '@/lib/picks'

describe('searchPrompt', () => {
  it('names the app and id for each kind', () => {
    expect(
      searchPrompt({ kind: 'movie', title: 'Arrival', year: 2016, tmdb_id: 329865, why: '' }),
    ).toContain('tmdb 329865: add it to Radarr')
    expect(searchPrompt({ kind: 'anime', title: 'Frieren', tvdb_id: 424536, why: '' })).toContain(
      'tvdb 424536: add it to Sonarr',
    )
    expect(searchPrompt({ kind: 'scene', title: 'X', stash_id: 'abc', why: '' })).toContain(
      '(StashDB abc): add it to Whisparr',
    )
  })
})
