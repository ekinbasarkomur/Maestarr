# How Maestarr works

## The pieces

```
 web UI (React) ─┐                       ┌─ Sonarr / Radarr / Whisparr  (search, grab, import, delete)
 Telegram bot  ──┼─ FastAPI ─ pydantic-ai agent ─ tools ─┼─ Prowlarr                     (free-text search)
 MCP clients   ──┘   (auth, settings,     (typed, with    ├─ qBittorrent                  (file lists, file selection)
                      chat stream)          approvals)    ├─ trackers                     (live scrape)
                                                          └─ Jellyfin, TMDB, OMDb, AniList, Trakt, StashDB
```

- `maestarr/ops/` holds the operations. The agent's tools (`maestarr/agent/tools.py`)
  and the MCP server (`maestarr/server.py`) are thin wrappers over them, so the web
  chat, Telegram and MCP behave identically.
- State-changing tools raise pydantic-ai's `ApprovalRequired`; a run pauses and
  each interface asks the user (approval card, Telegram buttons). MCP clients get
  the destructive flag and ask on their side.
- Settings live in SQLite (`configstore.py`); environment variables are only
  defaults. Saving a setting rebuilds the service clients and restarts the
  Telegram bot.

## The release judge

`maestarr/judge/` decides what to download:

1. **Pre-rank** every result of an interactive search cheaply: the app's own
   rejections and custom-format score, resolution limits, indexer seeders.
2. **Enrich** the best few (default 6):
   - the file list — from the `.torrent` behind the download link, from a torrent
     already in qBittorrent, from qBittorrent 5.2+'s `fetchMetadata` (adds
     nothing), or from a probe that stops on metadata and is deleted;
   - live swarm numbers — a UDP/HTTP scrape of the trackers (the maximum across
     trackers, never the sum).
3. **Analyse** the files: which episodes are inside, whether part of a pack is a
   different show, executables or junk, samples, the bitrate a size implies.
4. **Score** with named reasons and blockers, then let the model write the verdict
   (or take the best viable score when no model is set). For packs, the verdict
   includes the exact files to download.

## Recommendations

`maestarr/taste/` turns history into a weighted profile — each title counts
recency × your rating × rewatches — over genres, TMDB keywords, people, language
and decade. Candidates come from TMDB recommendations of your strongest titles,
discover queries on your top genres, and mood keywords; each is scored per
dimension with diminishing returns. Already-watched titles are dropped; owned ones
are kept and marked.
