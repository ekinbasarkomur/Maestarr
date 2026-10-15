/** Typed client for Maestarr's HTTP API. The session cookie travels automatically. */

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (typeof body?.message === 'string') detail = body.message
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const get = <T>(path: string) => request<T>(path)
const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })

// --- types ------------------------------------------------------------------

export interface User {
  id: number
  username: string
}

export interface AuthState {
  version: string
  has_account: boolean
  setup_complete: boolean
  user: User | null
}

export type SecretState = { set: boolean }
export type SettingValue = string | number | boolean | null | number[] | SecretState
export type Sections = Record<string, Record<string, SettingValue>>

export interface SettingsResponse {
  sections: Sections
  setup_complete: boolean
  api_token_set?: boolean
}

export interface TestResult {
  ok: boolean
  detail?: string
  version?: string
  quality_profiles?: string[]
  root_folders?: { path: string; free_gb: number }[]
  users?: string[]
  [key: string]: unknown
}

export interface TelegramPairResult {
  ok: boolean
  waiting?: boolean
  chat_id?: number
  name?: string
  detail?: string
}

export interface ServiceStatus {
  name: string
  configured: boolean
  ok: boolean
  version?: string | null
  detail?: string | null
}

export interface StatusResponse {
  version: string
  model: string
  model_ready: boolean
  adult_content?: boolean
  services: ServiceStatus[]
}

export interface QueueItem {
  app: string
  queue_id: number
  title: string
  status: string
  state?: string
  progress_pct?: number | null
  size_gb: number
  eta?: string | null
  problems: string[]
}

export interface Disk {
  path: string
  free_gb: number
  total_gb: number
}

export interface Overview {
  /** The server is still building the first overview; ask again shortly. */
  loading?: boolean
  counts: { series: number; episodes_on_disk: number; movies: number; movies_on_disk: number }
  disks: Disk[]
  queue: QueueItem[]
  recently_watched: { kind: string; title: string; year?: number; watched?: string }[]
  recently_added: {
    kind: string
    id: number
    title: string
    year?: number
    poster?: string | null
    tmdb_id?: number | null
    tvdb_id?: number | null
  }[]
}

export interface MediaRef {
  kind: string
  title: string
  year?: number
  tmdb_id?: number
  tvdb_id?: number
  imdb_id?: string
  overview?: string
  genres?: string[]
  themes?: string[]
  rating?: number
  imdb_rating?: number
  poster_url?: string
  in_library?: boolean
  watched?: boolean
  runtime_minutes?: number
  match?: number
  why?: string[]
  movie_id?: number
}

export interface Recommendations {
  based_on: string[]
  recommendations: MediaRef[]
}

export type FeedbackAction = 'open' | 'search' | 'add' | 'dismiss'

export interface DiscoverRow {
  id: string
  title: string
  subtitle?: string | null
  items: MediaRef[]
}

export interface DiscoverRows {
  rows: DiscoverRow[]
  tags: string[]
  genres: string[]
  based_on: string[]
}

export interface SearchParams {
  kind: string
  query?: string
  genres?: string[]
  tags?: string[]
  people?: string[]
  year_from?: number
  year_to?: number
  min_rating?: number
  language?: string
  max_runtime?: number
  sort?: 'relevance' | 'rating' | 'newest' | 'oldest'
  limit?: number
}

export interface SearchResults {
  kind: string
  query?: string | null
  applied: { genres?: string[]; tags?: string[]; people?: string[] }
  results: MediaRef[]
}

export interface Suggestion {
  id: number
  name: string
  department?: string | null
  known_for?: string[]
  image?: string | null
}

/** Query string from an object, skipping empty values. */
export function qs(params: Record<string, unknown>): string {
  return new URLSearchParams(
    Object.entries(params)
      .filter(
        ([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length),
      )
      .map(([k, v]) => [k, String(v)]),
  ).toString()
}

export interface DetailsQuery {
  kind: 'movie' | 'series' | 'anime' | 'scene'
  tmdb_id?: number | null
  tvdb_id?: number | null
  stash_id?: string | null
  title?: string | null
  year?: number | null
}

export interface TitleDetails {
  kind: DetailsQuery['kind']
  title: string
  year?: number | null
  overview?: string | null
  tagline?: string | null
  runtime?: number | null
  certification?: string | null
  genres: string[]
  tags: string[]
  studio?: string | null
  network?: string | null
  director?: string | null
  status?: string | null
  seasons?: number | null
  date?: string | null
  ratings: { source: string; value: string }[]
  trailer?: string | null
  poster?: string | null
  backdrop?: string | null
  logo?: string | null
  in_library?: boolean
  cast: { name: string; role?: string | null; image?: string | null }[]
  links?: { site?: string | null; url: string }[]
  tmdb_id?: number | null
  tvdb_id?: number | null
  stash_id?: string | null
}

export interface AdultPicks {
  based_on: string[]
  scenes: import('./picks').PickCard[]
}

export interface Conversation {
  id: string
  channel: string
  title: string
  created_at: number
  updated_at: number
}

export interface Preferences {
  audio_languages: string[]
  subtitle_languages: string[]
  max_resolution: number
  min_resolution: number
  allow_remux: boolean
  prefer_season_packs: boolean
  max_gb_per_episode: number | null
  max_gb_per_movie: number | null
  min_live_seeders: number
  prefer_groups: string[]
  avoid_groups: string[]
  min_1080p_mbps: number
  notes: string
}

// --- endpoints --------------------------------------------------------------

export const api = {
  authState: () => get<AuthState>('/api/auth/state'),
  setupAccount: (username: string, password: string) =>
    send<{ user: User }>('POST', '/api/auth/setup-account', { username, password }),
  login: (username: string, password: string) =>
    send<{ user: User }>('POST', '/api/auth/login', { username, password }),
  logout: () => send<{ ok: boolean }>('POST', '/api/auth/logout'),
  changePassword: (current_password: string, new_password: string) =>
    send<{ ok: boolean }>('POST', '/api/auth/password', { current_password, new_password }),

  settings: () => get<SettingsResponse>('/api/settings'),
  saveSettings: (fields: Record<string, unknown>) =>
    send<SettingsResponse>('PUT', '/api/settings', { fields }),
  testService: (service: string, fields: Record<string, unknown>) =>
    send<TestResult>('POST', `/api/settings/test/${service}`, { fields }),
  telegramPair: (fields: Record<string, unknown>) =>
    send<TelegramPairResult>('POST', '/api/settings/telegram/pair', { fields }),
  completeSetup: () => send<{ setup_complete: boolean }>('POST', '/api/settings/complete-setup'),
  createApiToken: () => send<{ token: string }>('POST', '/api/settings/api-token'),
  deleteApiToken: () => send<{ deleted: boolean }>('DELETE', '/api/settings/api-token'),

  status: () => get<StatusResponse>('/api/status'),
  overview: () => get<Overview>('/api/overview'),
  recommendations: (kind: string, mood?: string, tags?: string[]) =>
    get<Recommendations>(
      `/api/recommendations?${qs({ kind, mood, tags: tags?.length ? tags.join(',') : undefined })}`,
    ),
  rows: (refresh = false) =>
    get<DiscoverRows>(`/api/discover/rows${refresh ? '?refresh=true' : ''}`),
  search: (params: SearchParams) =>
    get<SearchResults>(
      `/api/discover/search?${qs({
        ...params,
        genres: params.genres?.join(','),
        tags: params.tags?.join(','),
        people: params.people?.join(','),
      })}`,
    ),
  suggest: (type: 'tag' | 'person', q: string) =>
    get<Suggestion[]>(`/api/discover/suggest?${qs({ type, q })}`),
  genres: (kind: string) => get<string[]>(`/api/discover/genres?${qs({ kind })}`),
  taste: () => get<{ tags: string[]; genres: string[]; people: string[] }>('/api/discover/taste'),
  feedback: (body: { kind: string; tmdb_id: number; action: FeedbackAction; title?: string }) =>
    send<{ ok: boolean }>('POST', '/api/feedback', body),
  details: (params: DetailsQuery) =>
    get<TitleDetails>(
      `/api/details?${new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => [k, String(v)]),
      )}`,
    ),
  adult: (query?: string) =>
    get<AdultPicks>(`/api/adult${query ? `?query=${encodeURIComponent(query)}` : ''}`),
  preferences: () => get<Preferences>('/api/preferences'),
  savePreferences: (changes: Partial<Preferences>) =>
    send<{ saved: Preferences }>('PUT', '/api/preferences', changes),

  conversations: () => get<Conversation[]>('/api/conversations'),
  conversation: (id: string) =>
    get<{ id: string; title: string; channel: string; messages: unknown[] }>(
      `/api/conversations/${id}`,
    ),
  renameConversation: (id: string, title: string) =>
    send('PATCH', `/api/conversations/${id}`, { title }),
  deleteConversation: (id: string) => send('DELETE', `/api/conversations/${id}`),
}

export function isSecret(value: SettingValue | undefined): value is SecretState {
  return typeof value === 'object' && value !== null && !Array.isArray(value) && 'set' in value
}
