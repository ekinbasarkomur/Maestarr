"""The Maestarr agent: one pydantic-ai Agent, shared by every interface.

Output is `str | DeferredToolRequests`: a run that hits a state-changing tool
pauses and returns the pending approvals; the interface asks the user and
resumes the run with `DeferredToolResults`.
"""

from __future__ import annotations

import functools
from datetime import date
from typing import Any, Union

from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai import Agent, DeferredToolRequests, RunContext

from maestarr.agent.tools import toolset
from maestarr.config import Settings, get_settings
from maestarr.llm import ModelNotConfigured, build_model
from maestarr.agent.channel import CHANNEL
from maestarr.agent.progress import record_progress
from maestarr.language import reply_language
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
- To find titles by tags, people, years, genres, rating or language use
  discover_titles (find_tags / find_people to look names up). For "something for
  me" use recommend; pass tags when the user names themes.
- For recommendations, use recommend: translate moods into concrete English
  theme keywords (mood_keywords). Prefer titles the user has not watched; titles
  already in the library are an easy "watch tonight" option — say so. Offer to add
  and fetch the ones they like.
- Use search_library before adding to avoid duplicates; get ids from
  lookup_title_to_add (series/anime: tvdb_id, movies: tmdb_id).
- Whenever you recommend titles or scenes, finish by calling show_recommendations
  with your picks (real ids, one-sentence why each); the user sees them as cards
  with a Search button, so keep your text reply short.
- When the user asks to search/get a title from such a card, find it in the
  library (add it if missing, after approval) and run judge_releases to rank
  the releases; for a scene use whisparr_add with its StashDB id as foreign_id.
- judge_releases and more_releases are shown to the user as a pick list with all the
  numbers. NEVER list or re-describe the releases in your reply: say in at most two
  sentences which one you recommend and why. When they ask for more options call
  more_releases with its results_id and next_offset. When they pick a release, call
  grab_release with that guid (for the judge's own pick use_judge_selection=true).
- Whisparr ids: whisparr_lookup and whisparr_add return movie_id; judge Whisparr items
  with judge_releases(movie_id=..., app="whisparr").
- Adult tools (whisparr_*, adult_search, adult_recommend, adult_discover) only when the user explicitly asks.
- If a tool returns an error about configuration, tell the user exactly which
  setting is missing.
- Never invent ids, guids or numbers; get them from tools.
- An earlier reply of exactly "⏹ Cancelled" means the user stopped that turn; do not
  resume it unless they ask again.
"""


def _dynamic_instructions(ctx: RunContext[Services]) -> str:
    svc = ctx.deps
    configured = [
        name
        for name in ("sonarr", "radarr", "whisparr", "prowlarr", "qbittorrent", "jellyfin", "tmdb", "omdb", "trakt", "stashdb")
        if getattr(svc, name, None) is not None
    ]
    prefs = svc.preferences()
    language = reply_language(svc.settings.MAESTARR_LANGUAGE)
    lines = [
        f"Today is {date.today().isoformat()}.",
        (
            f"Always write your replies in {language}, whatever language the user writes in — "
            "including the `why` of recommendation cards and any explanation of releases. "
            "Keep titles, release names and technical terms as they are."
            if language
            else "Reply in the language the user writes in."
        ),
        "Configured integrations: " + (", ".join(configured) or "none") + ".",
    ]
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        lines.append(
            "Adult content is switched off: never search for, suggest or discuss adult titles, and treat "
            "adult downloads as if they did not exist (do not list, inspect or remove them); if asked, "
            "say it can be enabled under Settings → Discovery."
        )
    if CHANNEL.get() == "telegram":
        lines.append(
            "You are replying in Telegram, which cannot show tables or headings: no Markdown tables, "
            "no # headings. Use short paragraphs and bullet lists; **bold** only for titles."
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
        # Saves each step of a turn as it happens, so a cancelled turn keeps its state.
        capabilities=[ProcessHistory(processor=record_progress)],
        retries=2,
        name="maestarr",
    )
    return agent


@functools.lru_cache(maxsize=1)
def get_agent() -> Agent[Services, AgentOutput]:
    return create_agent(get_settings())
