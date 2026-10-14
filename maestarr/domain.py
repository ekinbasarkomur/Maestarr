"""Domain models shared by every layer (clients, judge, agent, API, MCP).

Everything here is a plain pydantic model so it serialises the same way into an
LLM tool result, an HTTP response and an MCP tool result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

MediaKind = Literal["movie", "series", "anime"]
GiB = 1024**3


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Releases
# --------------------------------------------------------------------------


class ReleaseCandidate(BaseModel):
    """One search result as Sonarr/Radarr (or Prowlarr) reported it.

    Sonarr/Radarr already parse the release name and score it against the
    user's quality profile and custom formats; we keep their verdict
    (`rejections`, `custom_format_score`) and add our own evidence on top.
    """

    app: Literal["sonarr", "radarr", "whisparr", "prowlarr"]
    guid: str
    indexer_id: int
    indexer: str = ""
    title: str
    size: int = 0
    protocol: str = "torrent"
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    age_days: Optional[float] = None
    download_url: Optional[str] = None
    magnet_url: Optional[str] = None
    info_hash: Optional[str] = None
    info_url: Optional[str] = None
    quality: Optional[str] = None
    resolution: Optional[int] = None
    languages: list[str] = Field(default_factory=list)
    release_group: Optional[str] = None
    custom_formats: list[str] = Field(default_factory=list)
    custom_format_score: int = 0
    rejections: list[str] = Field(default_factory=list)
    full_season: bool = False
    season_number: Optional[int] = None
    episode_numbers: list[int] = Field(default_factory=list)
    # Sonarr's "mapped" ids for the episodes this release covers, when known.
    episode_ids: list[int] = Field(default_factory=list)
    series_id: Optional[int] = None
    movie_id: Optional[int] = None
    # The app's own quality/language objects, needed verbatim to override its
    # mapping when grabbing (`shouldOverride`). Not shown to the model.
    quality_raw: Optional[dict] = Field(default=None, exclude=True, repr=False)
    languages_raw: list[dict] = Field(default_factory=list, exclude=True, repr=False)

    @property
    def size_gb(self) -> float:
        return round(self.size / GiB, 2)

    @property
    def is_torrent(self) -> bool:
        return self.protocol.lower() == "torrent"


class SwarmStats(BaseModel):
    """Live swarm numbers, as opposed to what the indexer advertised."""

    seeders: int = 0
    leechers: int = 0
    completed: Optional[int] = None
    method: Literal["scrape", "qbittorrent", "indexer", "none"] = "none"
    trackers_answered: int = 0
    trackers_tried: int = 0
    checked_at: datetime = Field(default_factory=utcnow)
    note: Optional[str] = None


class TorrentFile(BaseModel):
    path: str
    size: int

    @property
    def size_gb(self) -> float:
        return round(self.size / GiB, 3)


class TorrentContents(BaseModel):
    name: str
    info_hash: Optional[str] = None
    files: list[TorrentFile] = Field(default_factory=list)
    trackers: list[str] = Field(default_factory=list)
    source: Literal["torrent-file", "probe", "qbittorrent"] = "torrent-file"

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)


class EpisodeRef(BaseModel):
    season: int
    episode: int


class ContentReport(BaseModel):
    """What is really inside a torrent, derived from its file list."""

    video_files: int = 0
    total_video_gb: float = 0.0
    episodes: list[EpisodeRef] = Field(default_factory=list)
    seasons: list[int] = Field(default_factory=list)
    # Distinct series names spotted in filenames that do NOT look like the
    # wanted title (e.g. "The New Batman Adventures" inside a BTAS pack).
    foreign_titles: list[str] = Field(default_factory=list)
    suspicious_files: list[str] = Field(default_factory=list)  # .exe, .lnk, .scr ...
    junk_files: list[str] = Field(default_factory=list)  # ads, .txt, .url ...
    sample_files: list[str] = Field(default_factory=list)
    subtitle_files: int = 0
    containers: list[str] = Field(default_factory=list)  # mkv, mp4 ...
    avg_video_gb: Optional[float] = None
    est_bitrate_mbps: Optional[float] = None
    wanted_episodes_covered: Optional[int] = None
    wanted_episodes_total: Optional[int] = None
    notes: list[str] = Field(default_factory=list)


class ReleaseAssessment(BaseModel):
    """A candidate plus every piece of evidence Maestarr gathered about it."""

    candidate: ReleaseCandidate
    swarm: Optional[SwarmStats] = None
    contents: Optional[TorrentContents] = None
    report: Optional[ContentReport] = None
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    @property
    def viable(self) -> bool:
        return not self.blockers


class JudgeVerdict(BaseModel):
    """The final pick, with its justification (LLM or deterministic)."""

    chosen_guid: Optional[str] = Field(
        default=None, description="guid of the chosen release, or null if none is acceptable"
    )
    rationale: str = Field(description="Two to five sentences explaining the choice")
    confidence: Literal["low", "medium", "high"] = "medium"
    runner_up_guid: Optional[str] = None
    # For packs: only download these paths (relative, as in the torrent).
    select_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JudgeResult(BaseModel):
    subject: str
    assessments: list[ReleaseAssessment]
    verdict: JudgeVerdict
    decided_by: Literal["llm", "rules"] = "rules"


# --------------------------------------------------------------------------
# Library / discovery
# --------------------------------------------------------------------------


class MediaRef(BaseModel):
    """A title, independent of where it came from."""

    kind: MediaKind
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    anilist_id: Optional[int] = None
    overview: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    rating: Optional[float] = None  # 0-10
    votes: Optional[int] = None
    imdb_rating: Optional[float] = None
    original_language: Optional[str] = None
    runtime_minutes: Optional[int] = None
    poster_url: Optional[str] = None
    in_library: Optional[bool] = None
    watched: Optional[bool] = None


class Recommendation(BaseModel):
    item: MediaRef
    score: float
    why: list[str] = Field(default_factory=list)


class WatchEvent(BaseModel):
    kind: MediaKind
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    watched_at: Optional[datetime] = None
    rating: Optional[float] = None  # user's own rating, 0-10, when known
    source: str = "jellyfin"
    play_count: int = 1


class TasteProfile(BaseModel):
    """Weighted summary of what the user watches."""

    genres: dict[str, float] = Field(default_factory=dict)
    keywords: dict[str, float] = Field(default_factory=dict)
    languages: dict[str, float] = Field(default_factory=dict)
    decades: dict[str, float] = Field(default_factory=dict)
    people: dict[str, float] = Field(default_factory=dict)
    seeds: list[MediaRef] = Field(default_factory=list)  # top titles used as seeds
    history_size: int = 0
    built_at: datetime = Field(default_factory=utcnow)

    def top(self, field: str, n: int = 8) -> list[str]:
        weights: dict[str, float] = getattr(self, field)
        return [k for k, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:n]]


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    ok: bool = False
    version: Optional[str] = None
    detail: Optional[str] = None
