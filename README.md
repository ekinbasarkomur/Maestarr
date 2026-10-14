<p align="center">
  <img src="docs/logo.svg" width="96" alt="Maestarr logo" />
</p>

<h1 align="center">Maestarr</h1>

<p align="center">
  <b>An AI conductor for your *arr stack.</b><br />
  Chat with your library, get picks from your own watch history, and let it choose the best release —<br />
  after looking inside the torrent and checking the live swarm.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-d4a64a" alt="GPL-3.0" /></a>
  <img src="https://img.shields.io/badge/python-3.12+-3776ab" alt="Python 3.12+" />
  <a href="https://github.com/ekinbasarkomur/Maestarr/actions/workflows/ci.yml"><img src="https://github.com/ekinbasarkomur/Maestarr/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/ekinbasarkomur/Maestarr/releases"><img src="https://img.shields.io/github/v/release/ekinbasarkomur/Maestarr?color=d4a64a" alt="Release" /></a>
  <a href="https://github.com/ekinbasarkomur/Maestarr/pkgs/container/maestarr"><img src="https://img.shields.io/badge/ghcr.io-maestarr-2496ed?logo=docker&logoColor=white" alt="Docker image" /></a>
  <img src="https://img.shields.io/badge/status-early%20development-e06c6c" alt="Early development" />
  <img src="https://img.shields.io/badge/vibecoded-yes-8b7cf6" alt="Vibecoded" />
</p>

<p align="center">
  <img src="docs/demo.gif" alt="Maestarr: picks as cards, a details popup with the trailer, and a judged release list" />
</p>

Maestarr sits next to Sonarr, Radarr, Prowlarr, qBittorrent and Jellyfin and
adds the judgement they cannot make on their own. Every action still goes
through their APIs, so your quality profiles, history and hardlinks keep
working exactly as before — and nothing is downloaded, added or deleted
without your approval.

> [!NOTE]
> **Vibecoded.** Maestarr is built largely by prompting an AI coding agent
> (Claude Code) and reviewing what it writes. It has tests and runs on a real
> stack, but read the code before you trust it with your library. Issues and
> pull requests are very welcome.

## Features

- **Chat** with your stack in the web UI, on **Telegram**, or from any **MCP**
  client (Claude Desktop, Claude Code, …).
- **Release judge** — for the best candidates of an interactive search it reads
  the real file list (without downloading), scrapes the trackers for **live**
  seeders, and checks episode coverage, packs that hide another show,
  executables and junk, and the bitrate a size implies. Then it picks one and
  says why.
- **Pick from the ranking** — after judging, the chat shows the top releases
  as a list with a Download button on each, and **Show more results** pages
  through the rest of the search (quick-scored, or checked in depth on request).
- **Pack surgery** — download only the files you need from a big pack and
  import them into the right series.
- **Recommendations from your history** (Jellyfin, Trakt, AniList, Letterboxd)
  with moods — *melancholic*, *cozy*, *mind-bending* — TMDB metadata (through your
  Seerr, or your own TMDB key) and IMDb ratings. Titles you already own are flagged as an easy “watch tonight”. With no
  history yet, your Sonarr/Radarr library stands in for it.
- **Picks as cards** — when the assistant recommends something, the chat shows
  a swipeable row of cards: the poster Sonarr/Radarr use, a description, the
  reason it was picked, and a **Search** button that adds the title and judges
  its releases.
- **Library control** — add, search, check the queue and disks, delete what
  you watched (and the torrents still holding its data).
- **Approval first** — every change waits for your approval: a card in the UI,
  buttons in Telegram, a destructive flag over MCP.
- **Set up in the browser** — a guided first run, with a connection test for
  every service and every setting editable later. No config files. Telegram
  pairs itself: test the bot token, send `/start`, done.
- **Adult content behind one switch** — off by default. While it is off,
  Maestarr never contacts Whisparr or StashDB and shows no adult results. When
  it is on, Discover gets an Adult tab with new scenes from the studios and
  performers in your Whisparr library.
- **Any model** — Anthropic, OpenAI, Google, OpenRouter, a local Ollama, or any
  OpenAI-compatible server.
- **Proxy support** — the same proxy settings as Sonarr/Radarr/Prowlarr (HTTP
  or SOCKS5, credentials, ignored addresses, bypass for local addresses). Metadata
  lookups, the AI provider, tracker scrapes and Telegram go through it; your apps on
  the LAN stay direct. While a proxy is on, UDP trackers are skipped so your IP
  never reaches them.

## Screenshots

<p align="center"><img src="docs/screenshots/chat.png" width="720" alt="Recommendations as cards in the chat, each with a Search button" /></p>

| Home | Settings |
| --- | --- |
| ![Home: downloads, library and recently added](docs/screenshots/home.png) | ![Settings with live service status](docs/screenshots/settings.png) |
| **Details** | **Release judge** |
| ![A title's details: backdrop, trailer, ratings, tags](docs/screenshots/details.png) | ![Judged releases as a pick list with Download buttons](docs/screenshots/release-picker.png) |

| Onboarding | Service setup |
| --- | --- |
| ![Choosing an AI provider during setup](docs/screenshots/setup-ai.png) | ![Testing Sonarr and picking defaults](docs/screenshots/setup-services.png) |
| **Download preferences** | **On a phone** |
| ![Download preferences](docs/screenshots/preferences.png) | <img src="docs/screenshots/mobile.png" width="260" alt="Maestarr on a phone" /> |

## Supported apps

| App | Used for | Required |
| --- | --- | --- |
| [Sonarr](https://sonarr.tv) v4 | series and anime: search, grab, import, delete | one of Sonarr/Radarr |
| [Radarr](https://radarr.video) v5+ | movies | one of Sonarr/Radarr |
| [qBittorrent](https://www.qbittorrent.org) 4.6+ / 5.x | torrent contents, file selection, live swarm | recommended |
| [Prowlarr](https://prowlarr.com) | free-text searches for complete-series packs | optional |
| [Jellyfin](https://jellyfin.org) 10.10+ / 12 | watch history for recommendations | recommended |
| [Seerr](https://docs.seerr.dev) (Overseerr / Jellyseerr) | titles, themes and posters through Seerr's own TMDB access — no TMDB account needed | recommended |
| [TMDB](https://www.themoviedb.org) | the same, with your own key (used instead of Seerr when set) | optional |
| [OMDb](https://www.omdbapi.com) | IMDb ratings | optional |
| [Trakt](https://trakt.tv), [AniList](https://anilist.co), Letterboxd export | more history | optional |
| [Whisparr](https://whisparr.com) v3, [StashDB](https://stashdb.org) | adult content — only while the 18+ switch is on | optional |
| Telegram | chat from your phone | optional |

## Installation

Maestarr ships as one Docker image for amd64 and arm64 (the web UI is built in).

```yaml
# compose.yml
services:
  maestarr:
    image: ghcr.io/ekinbasarkomur/maestarr:latest   # or pin a version, e.g. :0.2
    container_name: maestarr
    init: true
    restart: unless-stopped
    volumes:
      - ./data:/data            # settings, conversations, logs
    ports:
      - "127.0.0.1:8709:8709"
    networks:
      - arr                     # the network your Sonarr/Radarr are on

networks:
  arr:
    external: true
```

```bash
docker compose up -d
```

Open **http://127.0.0.1:8709** and follow the setup: create your account,
pick an AI provider, then connect your apps — on the same Docker network they
are reachable by name (`http://sonarr:8989`, `http://radarr:7878`,
`http://qbittorrent:8080`).

> [!IMPORTANT]
> Maestarr can add and delete things in your library. Keep it on a trusted
> network or behind a reverse proxy with TLS.

### Without Docker

```bash
git clone https://github.com/ekinbasarkomur/Maestarr.git && cd Maestarr
python3.12 -m venv .venv && .venv/bin/pip install -e .
(cd ui && npm ci && npm run build)
.venv/bin/maestarr serve        # http://127.0.0.1:8709
```

## Configuration

Everything is configured in the web UI and stored in Maestarr's SQLite
database. Only a few startup values are environment variables:

| Variable | Default | |
| --- | --- | --- |
| `MAESTARR_DATA_DIR` | `/data` in Docker | database, preferences, logs |
| `MAESTARR_HOST` / `MAESTARR_PORT` | `0.0.0.0` / `8709` | where the server listens |
| `MAESTARR_LOG_LEVEL` | `INFO` | |

Any other setting may also be given as an environment variable (see
[`.env.example`](.env.example)) — useful for automated deployments. Values
saved in the UI take precedence.

## MCP and Telegram

- **MCP** — create an API key under *Settings → API & MCP* and point your
  client at `http://<maestarr>/mcp` (streamable HTTP, `Authorization: Bearer`).
  The Settings page shows a ready-made config. Local clients can also run
  `maestarr serve-mcp` over stdio.
- **Telegram** — create a bot with @BotFather and paste its token under
  *Settings → Telegram*. Send `/start` to the bot: it replies with your chat id
  to allow. Downloads and deletions arrive as approve/deny buttons.

## Command line

```text
maestarr serve        web UI, API, MCP endpoint and Telegram bot
maestarr doctor       which integrations are configured and reachable
maestarr judge        judge releases for a season or movie (read-only)
maestarr recommend    recommendations from your history
maestarr serve-mcp    MCP over stdio
```

## Roadmap

- [x] Release judge with file lists and live tracker scrape
- [x] Chat agent with approval-gated tools (web, Telegram, MCP)
- [x] Recommendations from history and moods
- [x] Browser-based setup and settings
- [x] Guided Telegram setup: test the bot token, then send `/start` to the bot and Maestarr picks up the chat ID itself
- [ ] "Maestarr picks" collections synced into Jellyfin, Plex and Emby
- [ ] Jellyfin plugin: chat inside the Jellyfin web UI
- [ ] Plex connector (history, collections, webhooks) and Emby plugin
- [ ] Transmission and Deluge support
- [x] Published Docker image and releases

Research on media-server plugins: Jellyfin server plugins are official and a
chat page is possible through community plugins (Plugin Pages / File
Transformation); Emby supports plugin pages; Plex no longer has a plugin
system, so it will be integrated through its API instead.

## Updating

```bash
docker compose pull && docker compose up -d
```

Settings and conversations live in `./data` and survive updates. See the
[changelog](CHANGELOG.md) for what changed.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest          # backend
cd ui && npm ci && npm run verify   # UI: lint, typecheck, tests
npm run dev                         # UI with hot reload on :5173
```

Backend: FastAPI, [pydantic-ai](https://ai.pydantic.dev), httpx, SQLite. UI:
React 19, Vite, Tailwind CSS v4, the Vercel AI SDK. See [`docs/`](docs/) for
how the pieces fit together.

## Disclaimer

Maestarr does not host, index or distribute any content. It automates tools
you already run; you are responsible for what you download and for the laws
where you live.

## Acknowledgements

The recommendation weighting is inspired by
[Curatarr](https://github.com/OrchestratedChaos/curatarr). Maestarr builds on
the [Servarr](https://wiki.servarr.com) projects and the
[TRaSH Guides](https://trash-guides.info).

## Contributing

Bug reports, ideas and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues privately
([SECURITY.md](SECURITY.md)).

Maestarr's sister project, [Orchestarr](https://github.com/ekinbasarkomur/Orchestarr),
will install and wire a whole media stack from Maestarr's onboarding.

## Credits

This product uses the TMDB API but is not endorsed or certified by
[TMDB](https://www.themoviedb.org). Scene metadata comes from
[StashDB](https://stashdb.org); IMDb ratings from [OMDb](https://www.omdbapi.com).

## License

[GPL-3.0](LICENSE)
