# Changelog

All notable changes to Maestarr. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org) — while it is 0.x, minor versions may
change behaviour.

## [Unreleased]

### Added
- **Caching**: watch history, libraries, favourites and the taste profile are kept in
  the database, so pages open at once even after a restart. They refresh when older
  than an interval (12 h / 1 day / 1 week) — lazily on your next visit, or on a
  schedule with *Refresh in the background* (off by default). *Refresh now* in
  Settings → General → Caching rebuilds everything.
- **Shelves stay put**: picks and shelves are cached and refreshed every 6 h / 12 h /
  1 day (default) / 1 week, or only by hand; *Not for me* still applies at once.
- **Home is the "For you" page**: *Picks for tonight* is a sliding shelf (still
  filterable by tags), followed by every other shelf, with a loading screen while
  they are first built. Discover keeps search and the Adult tab.
- **Picks for tonight are ready to watch**: the shelf leads with films and series you
  have downloaded but not watched, best match first; only when there are too few is
  it topped up with suggestions that still have to be fetched.
- **More taste signals**: Jellyfin favourites, Seerr requests, Trakt watchlist and
  AniList favourites and plan-to-watch now shape the picks, each weighted for how much
  it says.
- Settings → Discovery: *Show adult downloads on the home page* (off by default).

### Changed
- With 18+ off, adult downloads (Whisparr's qBittorrent category, plus "adult",
  "whisparr", "xxx") are hidden from the assistant — not listed, inspected or
  removed — and XXX results are dropped from indexer searches.
- The tag suggestions dropdown has a solid background.

### Changed
- A cancelled turn also lists the steps that were still running when it was stopped.

## [0.5.0] - 2026-10-15

### Added
- **Shelves like a streaming app** on the home page and Discover → *For you*: top
  picks, series for you, "Because you watched …", "More with <favourite person>",
  "<Movies/Series> about <favourite theme>", and "Waiting in your library" (downloaded
  weeks ago, never watched).
- **Smarter picks**: the taste profile now also counts what you add to Sonarr/Radarr
  (at a lower weight than what you watch) and what you open or search in Maestarr.
  Suggestions you keep scrolling past come back less and less often (1, 2, 4, 8 … up
  to 60 days); **Not for me** on any tile hides a title for a year and counts its
  themes against similar ones.
- **Tag filters**: one-tap chips of your strongest themes on "Picks for tonight" and in
  Discover, plus a tag search with autocomplete; tagged picks always carry the tag.
- **Detailed search** in Discover (Movies / Series / Anime): text, tags, people (with
  autocomplete), genres, year range, minimum rating, original language, runtime and
  sort.
- The assistant gets the same search: `discover_titles`, `find_people`, `find_tags`,
  and `recommend` accepts tags.


### Also in this release
- The assistant can turn monitoring on or off without deleting anything (series,
  season, episodes, movie, Whisparr scene) and remove an item from its app, files
  kept unless asked; both need approval.
- The chat no longer scrolls sideways; only recommendation rows, wide tables and
  code blocks scroll horizontally.

## [0.4.1] - 2026-10-15

### Changed
- A turn's progress is saved as it happens — before every model request, so after
  each round of tool calls. A cancelled turn now shows everything it had done, the
  half-written answer, and **Cancelled** on the assistant's reply.


## [0.4.0] - 2026-10-15

### Added
- **Cancel a turn**: a Cancel button next to the running reply (and the stop button
  in the composer). Your message is always saved; a turn that is stopped, or cut off
  by a page reload or a closed tab, is kept as **Cancelled** in the conversation.
- Opening a conversation starts at its latest message.
- Telegram: a search button for each recommended title under the poster album, and
  approvals as a formatted card with Approve / Deny buttons.


## [0.3.0] - 2026-10-15

### Added
- **Reply language** (Settings → General, and in onboarding): pick any language and
  Maestarr answers in it — in the web chat, on Telegram, in card reasons and in the
  release judge's rationale. Titles and overviews come in that language too, where
  TMDB has them. "Same as my message" follows whatever you write in.
- **Telegram that looks like Telegram**: replies are sent as Telegram formatting
  instead of raw Markdown, tables become bullet lists, recommendations arrive as a
  poster album with the reason under each, and judged releases come as a numbered
  list with a download button per release and "More results".


## [0.2.2] - 2026-10-15

### Added
- The details popup opens from the home page too: "Picks for tonight" and
  "Recently added" (where it offers to find a better release).

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

[Unreleased]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/ekinbasarkomur/Maestarr/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ekinbasarkomur/Maestarr/releases/tag/v0.2.0
