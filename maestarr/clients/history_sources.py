"""Extra watch-history sources: Trakt (public profiles) and Letterboxd exports/RSS."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

import httpx

from maestarr.clients.base import HttpService
from maestarr.domain import WatchEvent


class TraktClient(HttpService):
    """Read-only Trakt access to a PUBLIC profile with just a client id."""

    name = "trakt"

    def __init__(self, client_id: str, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__(
            "https://api.trakt.tv",
            headers={
                "Content-Type": "application/json",
                "trakt-api-version": "2",
                "trakt-api-key": client_id,
            },
            transport=transport,
        )

    async def watched(self, user: str) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        for kind, path in (("movie", "movies"), ("series", "shows")):
            data = await self.get_json(f"/users/{user}/watched/{path}")
            for row in data or []:
                media = row.get("movie") or row.get("show") or {}
                ids = media.get("ids") or {}
                events.append(
                    WatchEvent(
                        kind=kind,  # type: ignore[arg-type]
                        title=media.get("title") or "?",
                        year=media.get("year"),
                        tmdb_id=ids.get("tmdb"),
                        tvdb_id=ids.get("tvdb"),
                        imdb_id=ids.get("imdb"),
                        watched_at=_iso(row.get("last_watched_at")),
                        source="trakt",
                        play_count=int(row.get("plays") or 1),
                    )
                )
        # Trakt ratings are 1-10; match them back by title + year.
        rated: dict[tuple[Any, Any], Any] = {}
        for row in await self.get_json(f"/users/{user}/ratings") or []:
            media = row.get("movie") or row.get("show") or {}
            rated[(media.get("title"), media.get("year"))] = row.get("rating")
        for ev in events:
            if rated.get((ev.title, ev.year)) is not None:
                ev.rating = float(rated[(ev.title, ev.year)])
        return events

    async def watchlist(self, user: str) -> list[dict[str, Any]]:
        return await self.get_json(f"/users/{user}/watchlist")

    async def watchlist_events(self, user: str) -> list[WatchEvent]:
        """Titles the user wants to watch — interest, weaker than a watch."""
        events = []
        for row in await self.watchlist(user) or []:
            media = row.get("movie") or row.get("show")
            if not media:
                continue
            ids = media.get("ids") or {}
            events.append(WatchEvent(
                kind="movie" if row.get("movie") else "series", title=media.get("title") or "?",
                year=media.get("year"), tmdb_id=ids.get("tmdb"), tvdb_id=ids.get("tvdb"), imdb_id=ids.get("imdb"),
                watched_at=_iso(row.get("listed_at")), source="watchlist",
            ))
        return events


def letterboxd_export(path: str) -> list[WatchEvent]:
    """Parse a Letterboxd data export (folder or .zip): diary/watched + ratings.

    The export has no TMDB ids; titles are resolved later by name + year.
    """
    files = _read_export(Path(path).expanduser())
    ratings: dict[tuple[str, str], float] = {}
    for row in _rows(files.get("ratings.csv")):
        try:
            ratings[(row["Name"], row["Year"])] = float(row["Rating"]) * 2  # 5-star → 10
        except (KeyError, ValueError):
            continue
    events: dict[tuple[str, str], WatchEvent] = {}
    for name in ("diary.csv", "watched.csv"):
        for row in _rows(files.get(name)):
            key = (row.get("Name", ""), row.get("Year", ""))
            if not key[0]:
                continue
            when = _date(row.get("Watched Date") or row.get("Date"))
            if key in events:
                if name == "diary.csv":
                    events[key].play_count += 1
                continue
            events[key] = WatchEvent(
                kind="movie",
                title=key[0],
                year=int(key[1]) if key[1].isdigit() else None,
                watched_at=when,
                rating=ratings.get(key),
                source="letterboxd",
            )
    return list(events.values())


async def letterboxd_rss(user: str, client: httpx.AsyncClient) -> list[WatchEvent]:
    """Recent diary entries from the public RSS feed (carries TMDB ids)."""
    response = await client.get(f"https://letterboxd.com/{user}/rss/", timeout=20)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    ns = {"letterboxd": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}
    events: list[WatchEvent] = []
    for item in root.iter("item"):
        title = item.findtext("letterboxd:filmTitle", namespaces=ns)
        if not title:
            continue
        rating = item.findtext("letterboxd:memberRating", namespaces=ns)
        tmdb = item.findtext("tmdb:movieId", namespaces=ns)
        year = item.findtext("letterboxd:filmYear", namespaces=ns)
        events.append(
            WatchEvent(
                kind="movie",
                title=title,
                year=int(year) if year and year.isdigit() else None,
                tmdb_id=int(tmdb) if tmdb and tmdb.isdigit() else None,
                watched_at=_date(item.findtext("letterboxd:watchedDate", namespaces=ns)),
                rating=float(rating) * 2 if rating else None,
                source="letterboxd",
            )
        )
    return events


def _read_export(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.is_file() and path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                base = info.filename.rsplit("/", 1)[-1]
                if base.endswith(".csv") and "/" not in info.filename.strip("/"):
                    out[base] = archive.read(info).decode("utf-8-sig")
    elif path.is_dir():
        for csv_path in path.glob("*.csv"):
            out[csv_path.name] = csv_path.read_text(encoding="utf-8-sig")
    return out


def _rows(text: Optional[str]) -> list[dict[str, str]]:
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def _date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
