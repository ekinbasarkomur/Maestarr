/** One definition per integration: drives the onboarding wizard and Settings. */

export type FieldKind = 'url' | 'secret' | 'text' | 'number' | 'toggle' | 'ids' | 'choice'

export interface FieldDef {
  name: string
  label: string
  kind: FieldKind
  placeholder?: string
  hint?: string
  /** For `choice`: filled from the connection test result. */
  from?: 'quality_profiles' | 'root_folders' | 'users'
  /** For `choice`: a fixed list of [value, label] pairs. */
  options?: [string, string][]
  optional?: boolean
}

export interface ServiceDef {
  id: string
  title: string
  tagline: string
  keyHint?: string
  fields: FieldDef[]
  adult?: boolean
  recommended?: boolean
}

const url = (name: string, placeholder: string): FieldDef => ({
  name,
  label: 'Address',
  kind: 'url',
  placeholder,
})
const key = (name: string, hint?: string): FieldDef => ({
  name,
  label: 'API key',
  kind: 'secret',
  hint,
})

export const SERVICES: Record<string, ServiceDef> = {
  jellyfin: {
    id: 'jellyfin',
    title: 'Jellyfin',
    tagline: 'Your watch history powers the recommendations.',
    keyHint: 'Jellyfin → Dashboard → API Keys → +',
    fields: [
      url('JELLYFIN_URL', 'http://jellyfin:8096'),
      key('JELLYFIN_API_KEY'),
      {
        name: 'JELLYFIN_USER',
        label: 'Whose history',
        kind: 'choice',
        from: 'users',
        optional: true,
        hint: 'Defaults to the first administrator.',
      },
    ],
    recommended: true,
  },
  sonarr: {
    id: 'sonarr',
    title: 'Sonarr',
    tagline: 'Series and anime.',
    keyHint: 'Sonarr → Settings → General → Security → API Key',
    fields: [
      url('SONARR_URL', 'http://sonarr:8989'),
      key('SONARR_API_KEY'),
      {
        name: 'SONARR_QUALITY_PROFILE',
        label: 'Default quality profile',
        kind: 'choice',
        from: 'quality_profiles',
      },
      {
        name: 'SONARR_ROOT_FOLDER',
        label: 'Default root folder',
        kind: 'choice',
        from: 'root_folders',
      },
      {
        name: 'SONARR_ANIME_QUALITY_PROFILE',
        label: 'Anime quality profile',
        kind: 'choice',
        from: 'quality_profiles',
        optional: true,
      },
      {
        name: 'SONARR_ANIME_ROOT_FOLDER',
        label: 'Anime root folder',
        kind: 'choice',
        from: 'root_folders',
        optional: true,
      },
    ],
  },
  radarr: {
    id: 'radarr',
    title: 'Radarr',
    tagline: 'Movies.',
    keyHint: 'Radarr → Settings → General → Security → API Key',
    fields: [
      url('RADARR_URL', 'http://radarr:7878'),
      key('RADARR_API_KEY'),
      {
        name: 'RADARR_QUALITY_PROFILE',
        label: 'Default quality profile',
        kind: 'choice',
        from: 'quality_profiles',
      },
      {
        name: 'RADARR_ROOT_FOLDER',
        label: 'Default root folder',
        kind: 'choice',
        from: 'root_folders',
      },
    ],
  },
  whisparr: {
    id: 'whisparr',
    title: 'Whisparr',
    tagline: 'Adult scenes and movies (v3). Optional.',
    keyHint: 'Whisparr → Settings → General → Security → API Key',
    adult: true,
    fields: [
      url('WHISPARR_URL', 'http://whisparr:6969'),
      key('WHISPARR_API_KEY'),
      {
        name: 'WHISPARR_QUALITY_PROFILE',
        label: 'Default quality profile',
        kind: 'choice',
        from: 'quality_profiles',
      },
      {
        name: 'WHISPARR_ROOT_FOLDER',
        label: 'Default root folder',
        kind: 'choice',
        from: 'root_folders',
      },
    ],
  },
  prowlarr: {
    id: 'prowlarr',
    title: 'Prowlarr',
    tagline: 'Free-text searches across all indexers — for complete-series packs.',
    keyHint: 'Prowlarr → Settings → General → Security → API Key',
    fields: [url('PROWLARR_URL', 'http://prowlarr:9696'), key('PROWLARR_API_KEY')],
  },
  qbittorrent: {
    id: 'qbittorrent',
    title: 'qBittorrent',
    tagline: 'Reads torrent contents without downloading, selects files inside packs.',
    fields: [
      url('QBITTORRENT_URL', 'http://qbittorrent:8080'),
      {
        name: 'QBITTORRENT_USERNAME',
        label: 'Username',
        kind: 'text',
        optional: true,
        hint: 'Leave empty if “bypass authentication for localhost” covers Maestarr.',
      },
      { name: 'QBITTORRENT_PASSWORD', label: 'Password', kind: 'secret', optional: true },
      {
        name: 'QBITTORRENT_HOST_HEADER',
        label: 'Host header',
        kind: 'text',
        optional: true,
        placeholder: 'localhost:8080',
        hint: 'Only needed when qBittorrent sits behind a port map and rejects the request.',
      },
    ],
  },
  seerr: {
    id: 'seerr',
    title: 'Seerr',
    tagline:
      'Metadata without a TMDB account: Seerr (Overseerr/Jellyseerr) answers search, discover and details with its own key.',
    keyHint: 'Seerr → Settings → General → API Key.',
    fields: [url('SEERR_URL', 'http://seerr:5055'), key('SEERR_API_KEY')],
    recommended: true,
  },
  tmdb: {
    id: 'tmdb',
    title: 'TMDB',
    tagline:
      'Titles, themes and posters for search and recommendations. Not needed if Seerr is connected.',
    keyHint: 'themoviedb.org → Settings → API — the v3 key or the read access token both work.',
    fields: [key('TMDB_API_KEY')],
  },
  omdb: {
    id: 'omdb',
    title: 'OMDb',
    tagline: 'IMDb ratings next to every title.',
    keyHint: 'omdbapi.com/apikey.aspx — the free tier allows 1,000 lookups a day.',
    fields: [key('OMDB_API_KEY')],
  },
  trakt: {
    id: 'trakt',
    title: 'Trakt',
    tagline: 'Adds your Trakt history and ratings (public profiles).',
    keyHint: 'trakt.tv → Settings → Your API Apps → New Application → Client ID',
    fields: [
      { name: 'TRAKT_CLIENT_ID', label: 'Client ID', kind: 'secret' },
      { name: 'TRAKT_USERNAME', label: 'Username', kind: 'text' },
    ],
  },
  anilist: {
    id: 'anilist',
    title: 'AniList',
    tagline: 'Adds your anime list. No key needed, the profile must be public.',
    fields: [{ name: 'ANILIST_USERNAME', label: 'Username', kind: 'text' }],
  },
  stashdb: {
    id: 'stashdb',
    title: 'StashDB',
    tagline: 'Adult scene database. Off unless you enable it.',
    keyHint: 'stashdb.org → your profile → API key',
    adult: true,
    fields: [
      { name: 'STASHDB_ENABLED', label: 'Enable StashDB', kind: 'toggle' },
      key('STASHDB_API_KEY'),
    ],
  },
  telegram: {
    id: 'telegram',
    title: 'Telegram',
    tagline: 'Chat with Maestarr from your phone, approve downloads with a tap.',
    keyHint:
      'Talk to @BotFather → /newbot. Then send /start to your bot: it replies with your chat id.',
    fields: [
      { name: 'TELEGRAM_BOT_TOKEN', label: 'Bot token', kind: 'secret' },
      {
        name: 'TELEGRAM_ALLOWED_CHAT_IDS',
        label: 'Allowed chat ids',
        kind: 'ids',
        placeholder: '123456789, 987654321',
        hint: 'Only these chats get answers.',
      },
    ],
  },
}

SERVICES.proxy = {
  id: 'proxy',
  title: 'Proxy',
  tagline:
    'Send Maestarr’s outbound traffic through a proxy, like Sonarr, Radarr and Prowlarr do: metadata, the AI provider, tracker scrapes and Telegram. Your *arr apps on the LAN stay direct.',
  keyHint:
    'Same fields as Sonarr/Radarr → Settings → General → Proxy. A VPN container such as Gluetun usually offers an HTTP proxy on port 8888 (publish it to reach it from Maestarr).',
  fields: [
    { name: 'MAESTARR_PROXY_ENABLED', label: 'Use a proxy', kind: 'toggle' },
    {
      name: 'MAESTARR_PROXY_TYPE',
      label: 'Type',
      kind: 'choice',
      options: [
        ['http', 'HTTP(S)'],
        ['socks5', 'SOCKS5'],
      ],
    },
    { name: 'MAESTARR_PROXY_HOST', label: 'Host', kind: 'text', placeholder: '127.0.0.1' },
    { name: 'MAESTARR_PROXY_PORT', label: 'Port', kind: 'number', placeholder: '8888' },
    { name: 'MAESTARR_PROXY_USERNAME', label: 'Username', kind: 'text', optional: true },
    { name: 'MAESTARR_PROXY_PASSWORD', label: 'Password', kind: 'secret', optional: true },
    {
      name: 'MAESTARR_PROXY_BYPASS',
      label: 'Ignored addresses',
      kind: 'text',
      optional: true,
      placeholder: '*.example.lan, nas.mydomain.com',
      hint: 'Comma-separated hosts that go direct; use * as a wildcard, like the *arr apps.',
    },
    {
      name: 'MAESTARR_PROXY_BYPASS_LOCAL',
      label: 'Bypass proxy for local addresses',
      kind: 'toggle',
    },
    {
      name: 'MAESTARR_PROXY_UDP_DIRECT',
      label: 'Scrape UDP trackers directly',
      kind: 'toggle',
      hint: 'A proxy cannot carry UDP. Off: UDP trackers are skipped while the proxy is on, so your IP never reaches them; seeders then come from the indexer.',
    },
  ],
}

export const SECTION_OF: Record<string, string> = Object.fromEntries(
  Object.keys(SERVICES).map((k) => [k, k]),
)

export interface ProviderDef {
  id: string
  name: string
  blurb: string
  defaultModel: string
  needsKey: boolean
  needsUrl: boolean
  keyHint?: string
  urlPlaceholder?: string
}

export const PROVIDERS: ProviderDef[] = [
  {
    id: 'anthropic',
    name: 'Anthropic',
    blurb: 'Claude models',
    defaultModel: 'claude-sonnet-5-5',
    needsKey: true,
    needsUrl: false,
    keyHint: 'console.anthropic.com → API Keys',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    blurb: 'GPT models',
    defaultModel: 'gpt-5.4',
    needsKey: true,
    needsUrl: false,
    keyHint: 'platform.openai.com → API keys',
  },
  {
    id: 'google',
    name: 'Google',
    blurb: 'Gemini models',
    defaultModel: 'gemini-3.1-pro-preview',
    needsKey: true,
    needsUrl: false,
    keyHint: 'aistudio.google.com → Get API key',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    blurb: 'Any model, one key',
    defaultModel: 'anthropic/claude-sonnet-5-5',
    needsKey: true,
    needsUrl: false,
    keyHint: 'openrouter.ai → Keys',
  },
  {
    id: 'ollama',
    name: 'Ollama',
    blurb: 'Local models, free',
    defaultModel: 'qwen3:14b',
    needsKey: false,
    needsUrl: true,
    urlPlaceholder: 'http://ollama:11434',
  },
  {
    id: 'openai-compat',
    name: 'Compatible',
    blurb: 'LM Studio, vLLM, LiteLLM…',
    defaultModel: '',
    needsKey: false,
    needsUrl: true,
    urlPlaceholder: 'http://localhost:1234/v1',
  },
]

/** Proper names for the service ids the API reports. */
export const SERVICE_NAMES: Record<string, string> = {
  sonarr: 'Sonarr',
  radarr: 'Radarr',
  whisparr: 'Whisparr',
  prowlarr: 'Prowlarr',
  qbittorrent: 'qBittorrent',
  jellyfin: 'Jellyfin',
  tmdb: 'TMDB',
  omdb: 'OMDb',
  trakt: 'Trakt',
  anilist: 'AniList',
  stashdb: 'StashDB',
}
