"""The agent's toolset — one `FunctionToolset[Services]` shared by the web chat,
Telegram and the MCP server.

Conventions:
- Every tool is a thin wrapper over `maestarr.ops`; logic lives there.
- A failing external service returns `{"error": ...}` instead of raising, so the
  model can explain it or try something else.
- State-changing tools raise `ApprovalRequired` (with a one-line summary for the
  approval card) until the user approves that exact call.
- Tools whose integration is not configured are hidden from the model.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Awaitable, Callable, Literal, Optional, TypeVar

from pydantic_ai import ApprovalRequired, FunctionToolset, RunContext, ToolDefinition

from maestarr.clients.base import ServiceError
from maestarr.ops import discovery, downloads, library, releases
from maestarr.ops import picks as picks_ops
from maestarr.services import Services

logger = logging.getLogger(__name__)

Ctx = RunContext[Services]
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

toolset: FunctionToolset[Services] = FunctionToolset(id="maestarr")

# Tool name → services it needs; checked by `_prepare` every step.
NEEDS: dict[str, tuple[str, ...]] = {}
# Tools that change something; MCP marks them destructive.
WRITE_TOOLS: set[str] = set()


async def _prepare(ctx: Ctx, tool_def: ToolDefinition) -> Optional[ToolDefinition]:
    for service in NEEDS.get(tool_def.name, ()):
        if getattr(ctx.deps, service, None) is None:
            return None
    return tool_def


def tool(*needs: str, write: bool = False) -> Callable[[F], F]:
    """Register a tool: hide it when `needs` are unconfigured, soften errors."""

    def decorator(fn: F) -> F:
        NEEDS[fn.__name__] = needs
        if write:
            WRITE_TOOLS.add(fn.__name__)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except ApprovalRequired:
                raise
            except ServiceError as exc:
                return {"error": str(exc)}

        toolset.tool(prepare=_prepare)(wrapper)
        return fn

    return decorator


def approve(ctx: Ctx, summary: str) -> None:
    """Pause this call for the user's approval (no-op once approved)."""
    if not ctx.tool_call_approved:
        raise ApprovalRequired(metadata={"summary": summary})


# --------------------------------------------------------------------------
# Status & library (read-only)
# --------------------------------------------------------------------------


@tool()
async def service_status(ctx: Ctx) -> list[dict[str, Any]]:
    """Which integrations (Sonarr, Radarr, qBittorrent, Jellyfin, TMDB ...) are configured and reachable."""
    return [s.model_dump(exclude_none=True) for s in await ctx.deps.status()]


@tool()
async def search_library(ctx: Ctx, term: str) -> list[dict[str, Any]]:
    """Find series/anime (Sonarr) and movies (Radarr) ALREADY in the library by title.

    Args:
        term: Part of the title, e.g. "batman".
    """
    return await library.search_library(ctx.deps, term)


@tool("sonarr")
async def series_details(ctx: Ctx, series_id: int) -> dict[str, Any]:
    """Seasons of a library series: episode counts, files, size, qualities and missing episodes.

    Args:
        series_id: Sonarr series id (from search_library).
    """
    return await library.series_details(ctx.deps, series_id)


@tool()
async def movie_details(ctx: Ctx, movie_id: int, app: Literal["radarr", "whisparr"] = "radarr") -> dict[str, Any]:
    """A library movie's (or Whisparr scene's) file, size and quality.

    Args:
        movie_id: Radarr/Whisparr item id (from search_library).
        app: "whisparr" for adult items, otherwise "radarr".
    """
    return await library.movie_details(ctx.deps, movie_id, app)


@tool()
async def download_queue(ctx: Ctx) -> list[dict[str, Any]]:
    """What Sonarr and Radarr are downloading/importing right now, with progress and problems."""
    return await library.queue(ctx.deps)


@tool()
async def disk_usage(ctx: Ctx) -> list[dict[str, Any]]:
    """Free and total space of the media disks."""
    return await library.disk_usage(ctx.deps)


@tool("sonarr")
async def wanted_missing(ctx: Ctx) -> list[dict[str, Any]]:
    """Monitored episodes that have aired but have no file."""
    return await library.wanted_missing(ctx.deps)


@tool()
async def lookup_title_to_add(ctx: Ctx, term: str, kind: Literal["series", "anime", "movie"]) -> list[dict[str, Any]]:
    """Look a title up in Sonarr/Radarr's metadata to get the id needed to ADD it.

    Args:
        term: Title to look up.
        kind: "series" or "anime" (Sonarr, gives tvdb_id) or "movie" (Radarr, gives tmdb_id).
    """
    return await library.lookup(ctx.deps, term, kind)


# --------------------------------------------------------------------------
# Releases
# --------------------------------------------------------------------------


@tool()
async def find_releases(
    ctx: Ctx,
    series_id: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    movie_id: Optional[int] = None,
    app: Literal["radarr", "whisparr"] = "radarr",
) -> dict[str, Any]:
    """Interactive search for downloadable releases via Sonarr/Radarr/Whisparr (uses the user's
    quality profile). Lists releases without judging them; prefer judge_releases to choose.

    Args:
        series_id: Sonarr series id; requires season.
        season: Season number.
        episode: Episode number within the season, for a single episode.
        movie_id: Radarr (or Whisparr) item id.
        app: Which app movie_id belongs to.
    """
    return await releases.find_releases(ctx.deps, series_id=series_id, season=season, episode=episode, movie_id=movie_id, app=app)


@tool("prowlarr")
async def search_indexers(ctx: Ctx, query: str, kind: Literal["movie", "series", "anime", "any"] = "any") -> dict[str, Any]:
    """Free-text search on every indexer through Prowlarr — for complete-series packs and
    releases Sonarr/Radarr cannot map. Results can be judged with judge_releases(guids=...).

    Args:
        query: Search text, e.g. "Batman Animated Series complete".
        kind: Category filter.
    """
    return await releases.search_indexers(ctx.deps, query, kind)


@tool()
async def judge_releases(
    ctx: Ctx,
    series_id: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    movie_id: Optional[int] = None,
    guids: Optional[list[str]] = None,
    app: Literal["radarr", "whisparr"] = "radarr",
) -> dict[str, Any]:
    """Search and JUDGE releases: for the best candidates fetch the real file list and LIVE
    tracker seeders, analyse coverage/foreign content/junk/bitrate, score them and pick one
    with a rationale. Use this before grabbing anything. Takes 30-120 seconds.

    Args:
        series_id: Sonarr series id (with season, optionally episode).
        season: Season number.
        episode: Episode number for a single episode.
        movie_id: Radarr movie id.
        guids: Judge specific releases from an earlier search instead of searching again.
        app: Which app movie_id belongs to (radarr or whisparr).
    """
    out = await releases.judge_releases(
        ctx.deps, series_id=series_id, season=season, episode=episode, movie_id=movie_id, guids=guids, app=app
    )
    out["note"] = PICKER_NOTE
    return out


PICKER_NOTE = (
    "The user sees these releases as a pick list with a Download button on each and a "
    "'Show more results' option. Reply in one or two sentences (your pick and why); do not "
    "list the releases or repeat their numbers. Grab only when the user picks one."
)


@tool()
async def more_releases(ctx: Ctx, results_id: str, offset: int = 0, limit: int = 8, deep: bool = False) -> dict[str, Any]:
    """The next releases of a search you already judged, best first — use when the user wants
    more options ("show more results"). Quick scoring by default; deep=True also reads file
    lists and live seeders (slower).

    Args:
        results_id: results_id from judge_releases (or the previous more_releases).
        offset: Where to continue: next_offset from the previous call, 0 for the first page.
        limit: How many releases (max 20).
        deep: Inspect contents and live seeders too.
    """
    out = await releases.more_releases(ctx.deps, results_id, offset=offset, limit=limit, deep=deep)
    out["note"] = PICKER_NOTE
    return out


@tool()
async def inspect_release(ctx: Ctx, guid: str) -> dict[str, Any]:
    """Show what is inside one release: folders, file counts, sizes and the content analysis.

    Args:
        guid: Release guid from find_releases/search_indexers/judge_releases.
    """
    return await releases.inspect_release(ctx.deps, guid)


@tool(write=True)
async def grab_release(
    ctx: Ctx,
    guid: str,
    select_paths: Optional[list[str]] = None,
    use_judge_selection: bool = True,
    override_series_id: Optional[int] = None,
    override_season: Optional[int] = None,
    override_episodes: Optional[list[int]] = None,
    override_movie_id: Optional[int] = None,
) -> dict[str, Any]:
    """Download a release (asks the user first). For packs, only the judge's selected files
    (or `select_paths`) are downloaded. Overrides map a release Sonarr/Radarr could not identify.

    Args:
        guid: Release guid.
        select_paths: Exact torrent paths to download; everything else is skipped.
        use_judge_selection: Apply the file selection judge_releases proposed.
        override_series_id: Force this Sonarr series.
        override_season: With override_series_id: the season it covers.
        override_episodes: With override_series_id: episode numbers it covers.
        override_movie_id: Force this Radarr movie.
    """
    release = releases.get_release(ctx.deps, guid)
    selection = select_paths or (ctx.deps.memo.get(f"selection:{guid}") if use_judge_selection else None)
    extra = f", only {len(selection)} selected files" if selection else ""
    approve(ctx, f"Download {release.title} ({release.size_gb} GB{extra}) via {release.app}")
    return await releases.grab_release(
        ctx.deps, guid, select_paths=select_paths, use_judge_selection=use_judge_selection,
        override_series_id=override_series_id, override_season=override_season,
        override_episodes=override_episodes, override_movie_id=override_movie_id,
    )


@tool("qbittorrent", write=True)
async def select_torrent_files(
    ctx: Ctx, info_hash: str, keep_paths: Optional[list[str]] = None, keep_globs: Optional[list[str]] = None
) -> dict[str, Any]:
    """Download only some files of a torrent already in qBittorrent (others set to skip).

    Args:
        info_hash: Torrent hash.
        keep_paths: Exact file paths to keep.
        keep_globs: Glob patterns to keep, e.g. ["*/Season 1*/*", "*/Season 4*/*"].
    """
    approve(ctx, f"Change file selection of torrent {info_hash[:10]}… (keep {len(keep_paths or [])} paths, {len(keep_globs or [])} patterns)")
    return await releases.set_files(ctx.deps, info_hash, keep_paths=keep_paths, keep_globs=keep_globs)


@tool(write=True)
async def manual_import(
    ctx: Ctx,
    download_id: str,
    series_id: Optional[int] = None,
    movie_id: Optional[int] = None,
    only_seasons: Optional[list[int]] = None,
    dry_run: bool = True,
    app: Literal["radarr", "whisparr"] = "radarr",
) -> dict[str, Any]:
    """Import a finished download into a series or movie, mapping files by their SxxEyy names.
    Run with dry_run=true first to show the plan; the real import asks the user.

    Args:
        download_id: The torrent hash (download id).
        series_id: Target Sonarr series.
        movie_id: Target Radarr movie.
        only_seasons: Import only these seasons (e.g. skip another show's folders in a pack).
        dry_run: Only report what would be imported.
        app: Which app movie_id belongs to.
    """
    if not dry_run:
        target = f"series {series_id}" if series_id is not None else f"movie {movie_id}"
        approve(ctx, f"Import download {download_id[:10]}… into {target}" + (f", seasons {only_seasons}" if only_seasons else ""))
    return await releases.manual_import(
        ctx.deps, download_id, series_id=series_id, movie_id=movie_id, only_seasons=only_seasons, dry_run=dry_run, app=app
    )


# --------------------------------------------------------------------------
# Library changes
# --------------------------------------------------------------------------


@tool("sonarr", write=True)
async def add_series(
    ctx: Ctx,
    tvdb_id: int,
    title: str,
    anime: bool = False,
    monitor: Literal["all", "future", "missing", "existing", "firstSeason", "latestSeason", "none"] = "all",
    search_now: bool = False,
    quality_profile: Optional[str] = None,
) -> dict[str, Any]:
    """Add a series (or anime) to Sonarr. Keep search_now false when the user wants to pick
    releases themselves (then use judge_releases per season).

    Args:
        tvdb_id: From lookup_title_to_add.
        title: Title, for the approval message.
        anime: Use anime series type (absolute numbering, anime root folder).
        monitor: Which episodes to monitor.
        search_now: Let Sonarr automatically search and grab right away.
        quality_profile: Profile name; the first profile when omitted.
    """
    approve(ctx, f"Add series {title} (tvdb {tvdb_id}){' as anime' if anime else ''}{', and search now' if search_now else ''}")
    return await library.add_series(ctx.deps, tvdb_id, anime=anime, monitor=monitor, search_now=search_now, quality_profile=quality_profile)


@tool("radarr", write=True)
async def add_movie(ctx: Ctx, tmdb_id: int, title: str, search_now: bool = False, quality_profile: Optional[str] = None) -> dict[str, Any]:
    """Add a movie to Radarr.

    Args:
        tmdb_id: TMDB id (from lookup_title_to_add, search_titles or recommend).
        title: Title, for the approval message.
        search_now: Let Radarr search and grab automatically by its own rules.
        quality_profile: Profile name; the first profile when omitted.
    """
    approve(ctx, f"Add movie {title} (tmdb {tmdb_id}){', and search now' if search_now else ''}")
    return await library.add_movie(ctx.deps, tmdb_id, search_now=search_now, quality_profile=quality_profile)


@tool(write=True)
async def start_automatic_search(
    ctx: Ctx,
    series_id: Optional[int] = None,
    season: Optional[int] = None,
    movie_id: Optional[int] = None,
    app: Literal["radarr", "whisparr"] = "radarr",
) -> dict[str, Any]:
    """Let Sonarr/Radarr/Whisparr search AND grab automatically by their own rules (no judging).

    Args:
        series_id: Sonarr series id.
        season: Limit to this season.
        movie_id: Radarr/Whisparr item id.
        app: Which app movie_id belongs to.
    """
    approve(ctx, "Start an automatic search-and-grab in " + (app.capitalize() if movie_id is not None else "Sonarr"))
    return await library.trigger_search(ctx.deps, series_id=series_id, season=season, movie_id=movie_id, app=app)


@tool("sonarr", write=True)
async def delete_episode_files(
    ctx: Ctx, series_id: int, seasons: Optional[list[int]] = None, episodes: Optional[list[int]] = None, unmonitor: bool = False
) -> dict[str, Any]:
    """Delete episode files from disk through Sonarr (whole seasons, or episodes of ONE season).
    Reports torrents that still hold the data (hardlinks) so they can be removed too.

    Args:
        series_id: Sonarr series id.
        seasons: Season numbers to delete.
        episodes: Episode numbers (use with exactly one season).
        unmonitor: Also unmonitor them so they are not downloaded again.
    """
    approve(ctx, f"DELETE files of series {series_id}, seasons {seasons or 'all'}{f', episodes {episodes}' if episodes else ''}")
    return await library.delete_series_files(ctx.deps, series_id, seasons=seasons, episodes=episodes, unmonitor=unmonitor)


@tool(write=True)
async def delete_movie_file(
    ctx: Ctx, movie_id: int, unmonitor: bool = False, app: Literal["radarr", "whisparr"] = "radarr"
) -> dict[str, Any]:
    """Delete a movie's (or Whisparr item's) file from disk through Radarr/Whisparr.

    Args:
        movie_id: Radarr/Whisparr item id.
        unmonitor: Also unmonitor it so it is not downloaded again.
        app: Which app movie_id belongs to.
    """
    approve(ctx, f"DELETE the file of {app} item {movie_id}")
    return await library.delete_movie_file(ctx.deps, movie_id, unmonitor=unmonitor, app=app)


@tool(write=True)
async def set_monitoring(
    ctx: Ctx,
    app: Literal["sonarr", "radarr", "whisparr"],
    item_id: int,
    monitored: bool,
    season: Optional[int] = None,
    episodes: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Turn monitoring ON or OFF without deleting anything — the way to stop (or resume)
    downloads of a series, a season, some episodes, a movie or a Whisparr scene.

    Args:
        app: The app the item lives in.
        item_id: Sonarr series id, or Radarr/Whisparr movie id (from search_library).
        monitored: True to monitor, False to stop monitoring.
        season: Sonarr only: just this season (or the season of `episodes`).
        episodes: Sonarr only: just these episode numbers of `season`.
    """
    title = await library.item_title(ctx.deps, app, item_id)
    scope = f" season {season}" if season is not None and not episodes else ""
    scope += f" S{season:02d} episodes {', '.join(map(str, episodes))}" if episodes and season is not None else ""
    approve(ctx, f"{'Monitor' if monitored else 'Stop monitoring'} {title}{scope} in {app.capitalize()}")
    return await library.set_monitored(ctx.deps, app=app, item_id=item_id, monitored=monitored, season=season, episodes=episodes)


@tool(write=True)
async def remove_from_library(
    ctx: Ctx,
    app: Literal["sonarr", "radarr", "whisparr"],
    item_id: int,
    delete_files: bool = False,
    exclude: bool = False,
) -> dict[str, Any]:
    """Remove a series, movie or Whisparr scene from its app entirely. Files are kept
    unless delete_files is true. Use set_monitoring instead to only stop downloads.

    Args:
        app: The app the item lives in.
        item_id: Sonarr series id, or Radarr/Whisparr movie id.
        delete_files: Also delete its files from disk.
        exclude: Add an import exclusion so lists do not add it back.
    """
    title = await library.item_title(ctx.deps, app, item_id)
    what = " AND DELETE ITS FILES" if delete_files else " (files kept)"
    approve(ctx, f"Remove {title} from {app.capitalize()}{what}")
    return await library.remove_from_library(ctx.deps, app=app, item_id=item_id, delete_files=delete_files, exclude=exclude)


@tool("whisparr")
async def whisparr_lookup(ctx: Ctx, term: str, item_type: Literal["scene", "movie"] = "scene") -> list[dict[str, Any]]:
    """Find an adult scene or movie in Whisparr's metadata (to add it). Only use when the
    user explicitly asks for adult content.

    Args:
        term: Title, studio or performer.
        item_type: "scene" or "movie".
    """
    return await library.whisparr_lookup(ctx.deps, term, item_type)


@tool("whisparr", write=True)
async def whisparr_add(
    ctx: Ctx, foreign_id: str, title: str, item_type: Literal["scene", "movie"] = "scene", search_now: bool = False
) -> dict[str, Any]:
    """Add an adult scene or movie to Whisparr (asks the user first).

    Args:
        foreign_id: foreign_id from whisparr_lookup.
        title: Title, for the approval message.
        item_type: "scene" or "movie".
        search_now: Let Whisparr search and grab automatically.
    """
    approve(ctx, f"Add {item_type} {title} to Whisparr{', and search now' if search_now else ''}")
    return await library.whisparr_add(ctx.deps, foreign_id, item_type=item_type, search_now=search_now)


# --------------------------------------------------------------------------
# Download client
# --------------------------------------------------------------------------


@tool("qbittorrent")
async def list_torrents(ctx: Ctx, category: Optional[str] = None, only_active: bool = False) -> dict[str, Any]:
    """Torrents in qBittorrent with progress, speed, connected and swarm seeders.

    Args:
        category: Only this category (e.g. "tv", "movies", "anime").
        only_active: Only unfinished downloads.
    """
    return await downloads.torrents(ctx.deps, category=category, only_active=only_active)


@tool("qbittorrent")
async def torrent_files(ctx: Ctx, info_hash: str) -> dict[str, Any]:
    """Files of a torrent in qBittorrent and which of them are selected.

    Args:
        info_hash: Torrent hash.
    """
    return await downloads.torrent_files(ctx.deps, info_hash)


@tool("qbittorrent", write=True)
async def remove_torrents(ctx: Ctx, hashes: list[str], delete_files: bool = False) -> dict[str, Any]:
    """Remove torrents from qBittorrent, optionally with their downloaded data
    (needed to actually free space after deleting hardlinked library files).

    Args:
        hashes: Torrent hashes.
        delete_files: Also delete the downloaded data.
    """
    approve(ctx, f"Remove {len(hashes)} torrent(s){' AND delete their data' if delete_files else ''}")
    return await downloads.remove_torrents(ctx.deps, hashes, delete_files=delete_files)


# --------------------------------------------------------------------------
# Discovery & taste
# --------------------------------------------------------------------------


@tool("tmdb")
async def search_titles(ctx: Ctx, query: str, kind: Literal["movie", "series", "anime"] = "movie", year: Optional[int] = None) -> list[dict[str, Any]]:
    """Search the movie/TV/anime databases (TMDB, AniList for anime); marks titles already in the library.

    Args:
        query: Title or partial title.
        kind: movie, series or anime.
        year: Release year, to disambiguate.
    """
    return await discovery.search_titles(ctx.deps, query, kind, year)


@tool("tmdb")
async def title_details(ctx: Ctx, kind: Literal["movie", "series", "anime"], tmdb_id: Optional[int] = None, anilist_id: Optional[int] = None) -> dict[str, Any]:
    """Full details of a title: overview, genres, themes, people, TMDB and IMDb ratings,
    similar titles, and whether it is in the library (with its series_id/movie_id).

    Args:
        kind: movie, series or anime.
        tmdb_id: TMDB id.
        anilist_id: AniList id (anime).
    """
    return await discovery.title_details(ctx.deps, kind, tmdb_id, anilist_id)


@tool()
async def recent_watch_history(ctx: Ctx, limit: int = 25) -> list[dict[str, Any]]:
    """What the user watched recently (Jellyfin, plus Trakt/AniList/Letterboxd when configured).

    Args:
        limit: How many entries.
    """
    return await discovery.recent_history(ctx.deps, limit)


@tool("tmdb")
async def taste_profile(ctx: Ctx, refresh: bool = False) -> dict[str, Any]:
    """The user's taste profile from their history: top genres, themes, people, languages, decades.

    Args:
        refresh: Rebuild instead of using the cached profile (6 h).
    """
    return discovery.profile_summary(await discovery.taste_profile(ctx.deps, refresh))


@tool("tmdb")
async def recommend(
    ctx: Ctx,
    kind: Literal["movie", "series", "anime"] = "movie",
    mood: Optional[str] = None,
    mood_keywords: Optional[list[str]] = None,
    genres: Optional[list[str]] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    language: Optional[str] = None,
    max_runtime: Optional[int] = None,
    min_rating: float = 6.0,
    limit: int = 8,
    include_owned: bool = True,
) -> dict[str, Any]:
    """Personal recommendations from the user's watch history, optionally for a mood.
    Translate the user's mood into concrete TMDB-style theme keywords in `mood_keywords`
    (e.g. "melancholic" → ["melancholy", "loneliness", "grief"]).

    Args:
        kind: movie, series or anime.
        mood: A mood word, e.g. "melancholic", "cozy", "mind-bending".
        mood_keywords: Theme keywords describing the mood (English).
        genres: TMDB genre names to focus on, e.g. ["Drama", "Science Fiction"].
        year_from: Earliest release year.
        year_to: Latest release year.
        language: Original language ISO 639-1 code, e.g. "ja", "fr".
        max_runtime: Maximum runtime in minutes.
        min_rating: Minimum TMDB rating (0-10).
        limit: Number of recommendations.
        include_owned: Include titles already in the library (marked in_library).
    """
    return await discovery.recommendations(
        ctx.deps, kind=kind, mood=mood, mood_keywords=mood_keywords, genres=genres, year_from=year_from,
        year_to=year_to, language=language, max_runtime=max_runtime, min_rating=min_rating, limit=limit,
        include_owned=include_owned,
    )


@tool("stashdb")
async def adult_search(ctx: Ctx, query: str, what: Literal["scenes", "performers"] = "scenes") -> list[dict[str, Any]]:
    """Search StashDB (adult scene database). Only available when the user enabled it.

    Args:
        query: Search text.
        what: scenes or performers.
    """
    return await discovery.adult_search(ctx.deps, query, what)


@tool("stashdb")
async def adult_recommend(ctx: Ctx, query: Optional[str] = None, limit: int = 12) -> dict[str, Any]:
    """Adult scene picks: new scenes from the studios and performers in the user's Whisparr
    library (or StashDB matches for `query`). Only when the user asks for adult content.

    Args:
        query: Optional search text (studio, performer, theme). Leave empty for library-based picks.
        limit: How many scenes.
    """
    return await discovery.adult_picks(ctx.deps, query, limit)


@tool()
async def show_recommendations(ctx: Ctx, picks: list[picks_ops.Pick]) -> dict[str, Any]:
    """Show your recommendations to the user as visual cards: poster or scene image,
    description, your reason, and a Search button under each.

    Call it ONCE with your final picks whenever you recommend titles or scenes (after
    choosing them with recommend, search_titles, adult_recommend or adult_search). Give
    real ids from those tools (tmdb_id / tvdb_id / stash_id). Afterwards reply with one or
    two sentences; do not repeat each title's details, the cards show them.

    Args:
        picks: The chosen items, best first, each with a one-sentence `why`.
    """
    return await picks_ops.present(ctx.deps, picks)


# --------------------------------------------------------------------------
# Preferences
# --------------------------------------------------------------------------


@tool()
async def get_preferences(ctx: Ctx) -> dict[str, Any]:
    """The user's saved download preferences (languages, resolution limits, size caps, notes)."""
    return downloads.get_preferences(ctx.deps)


@tool()
async def update_preferences(ctx: Ctx, changes: dict[str, Any]) -> dict[str, Any]:
    """Save preference changes the user asked for, e.g. {"max_gb_per_episode": 1.5} or
    {"notes": "prefer original audio with English subtitles"}. Keys: audio_languages,
    subtitle_languages, max_resolution, min_resolution, allow_remux, prefer_season_packs,
    max_gb_per_episode, max_gb_per_movie, min_live_seeders, prefer_groups, avoid_groups,
    min_1080p_mbps, notes.

    Args:
        changes: Keys to change and their new values.
    """
    return downloads.update_preferences(ctx.deps, changes)
