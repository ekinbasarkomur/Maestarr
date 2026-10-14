"""The Maestarr agent: one pydantic-ai Agent, shared by every interface.

Output is `str | DeferredToolRequests`: a run that hits a state-changing tool
pauses and returns the pending approvals; the interface asks the user and
resumes the run with `DeferredToolResults`.
"""

from __future__ import annotations

import functools
from datetime import date
from typing import Any, Union

from pydantic_ai import Agent, DeferredToolRequests, RunContext

from maestarr.agent.tools import toolset
from maestarr.config import Settings, get_settings
from maestarr.llm import ModelNotConfigured, build_model
from maestarr.services import Services

AgentOutput = Union[str, DeferredToolRequests]

BASE_INSTRUCTIONS = """\
You are Maestarr, the maestro of the user's home media stack: Sonarr (series and
anime), Radarr (movies), optionally Whisparr (adult), Prowlarr (indexers),
qBittorrent (downloads) and Jellyfin (playback and watch history), plus TMDB,
IMDb ratings, AniList and other databases.

How you work:
- Answer in the user's language. Be concise; use short lists, real numbers, and
  name things exactly (titles, seasons, sizes, seeders).
- Before downloading anything, use judge_releases: it fetches each candidate's
  real file list and LIVE seeders and scores them. Present the verdict (chosen
  release, size, live seeders, why) and only then call grab_release.
- Indexer seeder counts can be stale; trust live numbers.
- For complete-series packs or titles Sonarr cannot map, use search_indexers, then
  judge_releases(guids=[...]) with the series_id, and grab with file selection and
  overrides. After such a download finishes, run manual_import (dry_run first).
- Tools that change something (grab, add, delete, import, remove torrents) ask the
  user for approval automatically; call them directly when the user wants the
  action — do not ask "shall I?" in text first.
- Deleting library files does not free space while a torrent still holds the
  hardlinked data; say so and offer remove_torrents(delete_files=true).
- For recommendations, use recommend: translate moods into concrete English
  theme keywords (mood_keywords). Prefer titles the user has not watched; titles
  already in the library are an easy "watch tonight" option — say so. Offer to add
  and fetch the ones they like.
- Use search_library before adding to avoid duplicates; get ids from
  lookup_title_to_add (series/anime: tvdb_id, movies: tmdb_id).
- Adult tools (whisparr_*, adult_search) only when the user explicitly asks.
- If a tool returns an error about configuration, tell the user exactly which
  setting is missing.
- Never invent ids, guids or numbers; get them from tools.
"""


def _dynamic_instructions(ctx: RunContext[Services]) -> str:
    svc = ctx.deps
    configured = [
        name
        for name in ("sonarr", "radarr", "whisparr", "prowlarr", "qbittorrent", "jellyfin", "tmdb", "omdb", "trakt", "stashdb")
        if getattr(svc, name, None) is not None
    ]
    prefs = svc.preferences()
    lines = [
        f"Today is {date.today().isoformat()}.",
        "Configured integrations: " + (", ".join(configured) or "none") + ".",
    ]
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        lines.append(
            "Adult content is switched off: never search for, suggest or discuss adult titles; if asked, "
            "say it can be enabled under Settings → Discovery."
        )
    if prefs.notes:
        lines.append(f"The user's standing preferences: {prefs.notes}")
    return "\n".join(lines)


def create_agent(settings: Settings, model: Any = None) -> Agent[Services, AgentOutput]:
    if model is None:
        try:
            model = build_model(settings)
        except ModelNotConfigured:
            model = None  # runs fail until an AI provider is set up; the API says so
    agent: Agent[Services, AgentOutput] = Agent(
        model,
        deps_type=Services,
        output_type=[str, DeferredToolRequests],  # type: ignore[arg-type]
        instructions=[BASE_INSTRUCTIONS, _dynamic_instructions],
        toolsets=[toolset],
        retries=2,
        name="maestarr",
    )
    return agent


@functools.lru_cache(maxsize=1)
def get_agent() -> Agent[Services, AgentOutput]:
    return create_agent(get_settings())
