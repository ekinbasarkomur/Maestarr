/** Recommendation cards sent by the agent's show_recommendations tool. */

export interface PickCard {
  kind: 'movie' | 'series' | 'anime' | 'scene'
  title: string
  year?: number | null
  why: string
  image?: string | null
  overview?: string | null
  rating?: number | null
  in_library?: boolean
  tmdb_id?: number | null
  tvdb_id?: number | null
  stash_id?: string | null
  studio?: string | null
  date?: string | null
  performers?: string[]
  minutes?: number | null
}

export const KIND_LABEL = { movie: 'Movie', series: 'Series', anime: 'Anime', scene: 'Scene' }

/** What the Search button asks the agent to do for one card. */
export function searchPrompt(c: PickCard): string {
  const year = c.year ? `, ${c.year}` : ''
  if (c.kind === 'scene')
    return `Find releases for the scene "${c.title}"${c.stash_id ? ` (StashDB ${c.stash_id})` : ''}: add it to Whisparr if it is missing, then judge the releases.`
  if (c.kind === 'movie')
    return `Search releases for "${c.title}"${year}${c.tmdb_id ? `, tmdb ${c.tmdb_id}` : ''}: add it to Radarr if it is missing, then judge the releases.`
  return `Search releases for the ${c.kind} "${c.title}"${year}${c.tvdb_id ? `, tvdb ${c.tvdb_id}` : ''}: add it to Sonarr if it is missing, then judge the releases.`
}
