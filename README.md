# Maestarr

**An AI maestro for your \*arr stack.** Talk to your media library: ask for a
film that fits your mood, let Maestarr find it, look *inside* the candidate
torrents, check the live swarm, pick the best release for your taste and your
disk — and explain why — before anything is downloaded.

> 🚧 **Status: early development.** The architecture below is the plan the code
> is being built towards; see [Roadmap](#roadmap) for what already works.

> 🤖 **Vibecoded.** Maestarr is built largely by prompting an AI coding agent
> (Claude Code) and reviewing what it writes, rather than typed line by line.
> It has tests and is used on a real stack, but read the code before you trust
> it with your library — and issues/PRs are very welcome.

```
you ▸ recommend me something melancholic, I loved Lost in Translation
maestarr ▸ Three picks from your history (you rewatch quiet, slow 2000s drama):
           1. Paterson (2016) — IMDb 7.3 · not in your library
           2. Columbus (2017) — IMDb 7.2 · not in your library
           3. Aftersun (2022) — IMDb 7.6 · already in Jellyfin, unwatched ▶
you ▸ get Columbus
maestarr ▸ 9 releases found. Best: Columbus.2017.1080p.BluRay.x264-AMIABLE
           (8.1 GB, 41 live seeders — the indexer claimed 12; English audio,
           no junk files). Runner-up is a 2160p WEB-DL but only 2 live seeders.
           Grab it?  [Approve] [Deny]
```

## Why

Sonarr and Radarr are excellent at *rules*: quality profiles, custom formats,
TRaSH scores. What they cannot do is judgement on evidence they never see:

- **What is really inside a pack.** A "Complete S01-S06" pack whose seasons 5-6
  are actually a different series; a 4-file "season" that is missing episodes;
  a release padded with `.exe` and ad `.txt` files.
- **Whether the swarm is alive.** Indexer seeder counts are snapshots — a release
  advertised with 58 seeders may connect to 2. Maestarr scrapes the trackers
  live.
- **Whether quality is worth the space.** A 2.7 GB/episode remux of a 1990s
  cartoon versus a 300 MB encode, given how much disk you have left.
- **What you would actually like.** Your watch history, not a popularity chart.

Maestarr adds that judgement on top of your existing stack. It never replaces
Sonarr/Radarr — every grab, import and delete goes through their APIs, so
history, hardlinks and your quality profiles keep working exactly as before.

## Features

- **Chat** in a built-in web UI, over **Telegram**, or from any **MCP** client
  (Claude Desktop, Claude Code, …).
- **Release judge**: interactive search through Sonarr/Radarr (with your
  profile's scores), then for the top candidates:
  - the full **file list** (from the `.torrent`, or fetched by your own
    qBittorrent without downloading anything),
  - **live seeders/leechers** via UDP/HTTP tracker scrape,
  - episode coverage, foreign-series detection, junk/malware-looking files,
    estimated bitrate,
  - a final pick by the LLM with a written rationale (or a pure rules mode).
- **Pack surgery**: download only the files you need from a big pack and import
  them to the right series/episodes.
- **Taste-aware recommendations** from your Jellyfin history (plus optional
  Trakt, AniList and Letterboxd), TMDB metadata, IMDb ratings — filtered by
  mood ("melancholic", "cosy", "mind-bending"), language, length, decade.
- **Library control**: add series/movies, search, check the queue, free space,
  delete what you watched — all through Sonarr/Radarr (and Whisparr v3 for
  adult scenes/movies, when you configure it).
- **Human in the loop**: anything that changes your stack (grab, add, delete,
  import) asks for approval first — in the web UI, in Telegram (inline
  buttons), and is flagged as destructive to MCP clients.
- **Bring your own model**: Anthropic, OpenAI, or any OpenAI-compatible server
  (Ollama, LM Studio, vLLM, OpenRouter).

## Architecture

```
            ┌──────── web UI (React chat) ───────┐
 Telegram ──┤                                    ├── MCP clients
            └──────────────┬─────────────────────┘
                     FastAPI + pydantic-ai agent
                           │  (typed tools, approvals)
   ┌────────────┬──────────┼───────────┬──────────────┬─────────────┐
 Sonarr      Radarr     Prowlarr   qBittorrent    Jellyfin    TMDB · IMDb ·
 (search,   (search,   (raw        (metadata,     (watch      AniList · Trakt ·
  grab,      grab,      search)     file prio,     history)    Letterboxd ·
  import)    import)                live peers)                StashDB*)
                           │
                 trackers (live scrape)
```

\* StashDB (adult scene database) is supported but **disabled by default**; it
only activates with `STASHDB_ENABLED=true` and an API key.

- **Agent**: [pydantic-ai](https://ai.pydantic.dev/) with typed dependencies
  and one toolset shared by the web UI, Telegram and MCP. Write tools use
  pydantic-ai's deferred-tool approvals.
- **Backend**: FastAPI, httpx, SQLite (conversation history and pending
  approvals). No other database to run.
- **Frontend**: React + Vite + Tailwind, speaking the Vercel AI SDK UI message
  stream; built to static files and served by the backend.

## Quick start

Requirements: Docker, an existing Sonarr and/or Radarr, qBittorrent, and an LLM
API key (or a local Ollama).

```bash
git clone https://github.com/ekinbasarkomur/Maestarr.git maestarr
cd maestarr
cp .env.example .env        # fill in URLs and API keys
docker compose up -d --build
# open http://127.0.0.1:8709
```

Run `docker compose exec maestarr maestarr doctor` to see which integrations
are reachable.

### Local development

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/maestarr doctor
.venv/bin/maestarr serve            # API + built UI on :8709
cd ui && npm install && npm run dev # UI with hot reload on :5173
.venv/bin/python -m pytest
```

## Configuration

Everything is an environment variable (or a line in `.env`). Every integration
is optional; an unconfigured one is simply hidden from the agent.

| Variable | Purpose |
| --- | --- |
| `MAESTARR_MODEL` | pydantic-ai model id, e.g. `anthropic:claude-sonnet-5-5`, `openai:gpt-5.4`, `ollama:qwen3:14b` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | key for the chosen provider |
| `MAESTARR_MODEL_BASE_URL` | OpenAI-compatible endpoint (Ollama, LM Studio, OpenRouter …) |
| `MAESTARR_API_TOKEN` | optional bearer token protecting the web UI and API |
| `SONARR_URL`, `SONARR_API_KEY` | Sonarr |
| `RADARR_URL`, `RADARR_API_KEY` | Radarr |
| `WHISPARR_URL`, `WHISPARR_API_KEY` | Whisparr v3 (adult) — its tools only appear when set |
| `PROWLARR_URL`, `PROWLARR_API_KEY` | Prowlarr (free-form searches) |
| `QBITTORRENT_URL`, `QBITTORRENT_USERNAME`, `QBITTORRENT_PASSWORD` | qBittorrent Web UI |
| `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `JELLYFIN_USER` | watch history |
| `TMDB_API_KEY` | metadata and discovery (v3 key or read-access token) |
| `OMDB_API_KEY` | IMDb ratings (optional) |
| `TRAKT_CLIENT_ID`, `TRAKT_USERNAME` | Trakt history (optional, public profiles) |
| `ANILIST_USERNAME` | AniList anime list (optional, no key needed) |
| `LETTERBOXD_EXPORT` | path to a Letterboxd data export (optional) |
| `STASHDB_ENABLED`, `STASHDB_API_KEY` | adult scene database — off by default |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS` | Telegram bot; only listed chat ids may use it |

See [`.env.example`](.env.example) for the full list with defaults.

## Safety

- Maestarr can add and **delete** media in your stack. Keep it on a trusted
  network, set `MAESTARR_API_TOKEN`, and restrict Telegram to your own chat ids.
- Every state-changing action requires explicit approval.
- Metadata probes run in your own download client under a dedicated
  `maestarr-probe` category and are removed afterwards; nothing is downloaded
  beyond the torrent metadata.
- Maestarr does not host, index or distribute content. It automates the tools
  you already run; you are responsible for what you download and for the laws
  where you live.

## Roadmap

- [x] Project skeleton, configuration, service clients (Sonarr, Radarr,
      Prowlarr, qBittorrent)
- [x] Torrent internals: bencode, `.torrent` parsing, magnets, live UDP/HTTP
      tracker scrape
- [ ] Release judge (content analysis, scoring, LLM verdict)
- [ ] Discovery sources (TMDB, IMDb ratings, AniList, Trakt, Letterboxd, StashDB)
- [ ] Taste profile and mood-aware recommendations
- [ ] pydantic-ai agent with approval-gated tools
- [ ] Web chat UI
- [ ] Telegram bot
- [ ] MCP server
- [ ] Docker image and release

### Inside your media server

Talking to Maestarr from the media server's own interface. Findings so far:

| Server | Plugin possible? | Plan |
| --- | --- | --- |
| **Jellyfin** (10.11 / 12.x) | Partly — server plugins are official (C#/.NET); web-client UI only through community plugins ([Plugin Pages](https://github.com/IAmParadox27/jellyfin-plugin-pages), [File Transformation](https://github.com/IAmParadox27/jellyfin-plugin-file-transformation)) | A Jellyfin plugin with an authenticated streaming proxy to Maestarr's chat and a sidebar chat page; later "Get this" buttons on item pages. Built for both .NET 9 (10.11) and .NET 10 (12.x), distributed through a plugin repository manifest. |
| **Emby** | Partly — plugins can add main/user-menu pages officially (`IHasWebPages`) | Port of the Jellyfin plugin if there is demand; the catalog is curated, so manual install first. |
| **Plex** | **No** — Plex removed its plugin framework; Plex Web has no extension API | API + webhooks only: read history, push collections/playlists, react to "just watched". |

Injected UI never reaches native TV/mobile apps (Android TV, Swiftfin, Roku,
Tizen, Plex/Emby apps). What does reach every client:

- [ ] **"Maestarr picks" collections/playlists** synced to Jellyfin, Emby and Plex
- [ ] **Jellyfin plugin**: chat page in the web UI (proxy + Plugin Pages)
- [ ] "Favourite it to get it": a placeholder picks library where favouriting a
      title asks Maestarr to fetch it (works from any client)
- [ ] Plex connector (history, collections, webhooks)
- [ ] Emby plugin (port of the Jellyfin one)
- [ ] Optional userscript that adds a chat panel to Jellyfin/Emby/Plex Web

## Acknowledgements

The recommendation weighting is inspired by
[Curatarr](https://github.com/OrchestratedChaos/curatarr) (a Plex-only
recommender); Maestarr's implementation is independent. Release decisions build
on the excellent work of the [Servarr](https://wiki.servarr.com/) projects and
[TRaSH Guides](https://trash-guides.info/).

## License

[GPL-3.0](LICENSE) — the same licence as Sonarr, Radarr and Prowlarr.
