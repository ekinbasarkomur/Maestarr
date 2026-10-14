"""`judge`, `recommend` and `telegram` commands — the core features without the UI."""

from __future__ import annotations

import json
from typing import Optional

import typer

from maestarr.cli.program import app


def _run(coro_factory):  # type: ignore[no-untyped-def]
    import asyncio

    from maestarr.config import get_settings
    from maestarr.services import Services

    async def main():  # type: ignore[no-untyped-def]
        svc = Services.from_settings(get_settings())
        try:
            return await coro_factory(svc)
        finally:
            await svc.aclose()

    return asyncio.run(main())


@app.command()
def judge(
    series_id: Optional[int] = typer.Option(None, help="Sonarr series id"),
    season: Optional[int] = typer.Option(None, help="Season number"),
    episode: Optional[int] = typer.Option(None, help="Episode number"),
    movie_id: Optional[int] = typer.Option(None, help="Radarr (or Whisparr) item id"),
    whisparr: bool = typer.Option(False, help="movie_id belongs to Whisparr"),
    llm: bool = typer.Option(False, help="Let the configured model write the verdict"),
) -> None:
    """Search and judge releases for a season/episode/movie (read-only)."""
    from maestarr.ops.releases import judge_releases

    result = _run(
        lambda svc: judge_releases(
            svc, series_id=series_id, season=season, episode=episode, movie_id=movie_id,
            app="whisparr" if whisparr else "radarr", use_llm=llm,
        )
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
def recommend(
    kind: str = typer.Option("movie", help="movie, series or anime"),
    mood: Optional[str] = typer.Option(None, help="e.g. melancholic, cozy, mind-bending"),
    limit: int = typer.Option(8),
) -> None:
    """Personal recommendations from the watch history."""
    from maestarr.ops.discovery import recommendations

    result = _run(lambda svc: recommendations(svc, kind=kind, mood=mood, limit=limit))  # type: ignore[arg-type]
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
def telegram() -> None:
    """Run only the Telegram bot (it also starts inside `maestarr serve` when configured)."""
    import asyncio

    from maestarr.api.chat import get_store
    from maestarr.services import get_services
    from maestarr.telegram.bot import run_bot

    asyncio.run(run_bot(get_services(), get_store()))
