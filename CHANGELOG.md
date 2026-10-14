# Changelog

All notable changes to Maestarr. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org) — while it is 0.x, minor versions may
change behaviour.

## [Unreleased]

## [0.2.1] - 2026-10-15

### Added
- Seerr (Overseerr / Jellyseerr) as a metadata source: search, Discover,
  recommendations and details work without a TMDB account, through Seerr's own
  TMDB access. A TMDB key, when set, is still used first.
- TMDB attribution in the README.

## [0.2.0] - 2026-10-15

The first public release.

### Chat and recommendations
- Chat with your stack in the web UI, on Telegram, or from any MCP client;
  every change (add, download, delete) waits for your approval.
- Recommendations from your watch history (Jellyfin, Trakt, AniList, Letterboxd)
  with moods; with no history yet, your Sonarr/Radarr library stands in.
- Picks appear as a swipeable row of cards — poster, description, the reason it
  was picked — with a **Search** button that adds the title and judges its releases.
- A details popup for any title: backdrop or trailer, ratings, runtime, genres,
  tags, cast, and Search & download.

### Release judge
- Reads a release's real file list without downloading it (qBittorrent
  `fetchMetadata`), scrapes trackers for live seeders, and checks coverage,
  packs hiding another show, executables, junk and bitrate before choosing.
- After judging, a pick list with a Download button on each release and
  **Show more results** to page through the rest of the search.
- Pack surgery: download only the files you need and import them.

### Setup and settings
- Browser-based onboarding with a connection test for every service; address
  fields split into SSL / host / port / URL base; password show/hide.
- Quality profiles and root folders are pre-selected from what your library uses.
- Telegram pairs itself: test the token, send `/start`, done.
- Proxy settings like Sonarr/Radarr/Prowlarr (HTTP or SOCKS5, ignored addresses,
  bypass for local addresses); UDP tracker scrapes are skipped while it is on.
- One switch for adult content (off by default): while off, Whisparr and StashDB
  are never contacted. When on, Discover gets an Adult tab.

### Reliability
- The home screen is served from cache and refreshed in the background, so a
  slow Jellyfin or Sonarr never leaves it blank.
- Long release searches are allowed up to 30 minutes, with a clear message.
- A chat that contained a "thinking" reply no longer fails on the next message.

[Unreleased]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ekinbasarkomur/Maestarr/releases/tag/v0.2.0
