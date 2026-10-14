"""Read a torrent's file list like a careful human would.

Answers: which episodes are really in here, is part of it a different show,
is anything executable hiding among the videos, how much is junk, and what
bitrate does the size imply.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Optional

from maestarr.domain import ContentReport, EpisodeRef, TorrentContents

VIDEO_EXT = {"mkv", "mp4", "avi", "m4v", "ts", "m2ts", "mov", "wmv", "webm", "mpg", "mpeg"}
SUB_EXT = {"srt", "ass", "ssa", "sub", "idx", "vtt", "sup"}
SUSPICIOUS_EXT = {
    "exe", "msi", "scr", "bat", "cmd", "com", "lnk", "vbs", "js", "jar", "ps1",
    "apk", "dmg", "pif", "cpl", "reg", "hta", "iso", "rar", "zip", "7z",
}
JUNK_EXT = {"txt", "url", "html", "htm", "website", "torrent"}

_SXXEYY = re.compile(r"(?<![a-z0-9])s(\d{1,2})[ ._-]?e(\d{1,3})(?:[ ._-]?e(\d{1,3}))?", re.I)
_NXNN = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{2,3})(?![0-9])", re.I)
_SEASON_DIR = re.compile(r"(?:season|series|staffel|saison|temporada)[ ._-]*(\d{1,2})", re.I)
_EP_ONLY = re.compile(r"(?<![a-z0-9])(?:e|ep|episode)[ ._-]?(\d{1,3})(?![0-9])", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def ext_of(path: str) -> str:
    """
    >>> ext_of("a/b/Movie.Name.MKV"), ext_of("README")
    ('mkv', '')
    """
    base = path.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def parse_episode(path: str) -> list[EpisodeRef]:
    """Season/episode numbers encoded in a path.

    >>> [(e.season, e.episode) for e in parse_episode("Show/Season 2 (1993)/Batman T.A.S - S02 E10 - Harlequinade.mp4")]
    [(2, 10)]
    >>> [(e.season, e.episode) for e in parse_episode("Show.S01E01E02.1080p.mkv")]
    [(1, 1), (1, 2)]
    >>> [(e.season, e.episode) for e in parse_episode("Show/Season 03/Episode 7.mkv")]
    [(3, 7)]
    >>> parse_episode("Movie.2019.1080p.mkv")
    []
    """
    base = path.rsplit("/", 1)[-1]
    match = _SXXEYY.search(base)
    if match:
        season = int(match.group(1))
        first = int(match.group(2))
        last = int(match.group(3)) if match.group(3) else first
        return [EpisodeRef(season=season, episode=e) for e in range(first, max(first, last) + 1)]
    match = _NXNN.search(base)
    if match:
        return [EpisodeRef(season=int(match.group(1)), episode=int(match.group(2)))]
    season_dir = _SEASON_DIR.search(path)
    ep = _EP_ONLY.search(base)
    if season_dir and ep:
        return [EpisodeRef(season=int(season_dir.group(1)), episode=int(ep.group(1)))]
    return []


def _tokens(text: str) -> list[str]:
    """
    >>> _tokens("Batman T.A.S"), _tokens("Batman T A S - Bane"), _tokens("Tom & Jerry")
    (['batman', 'tas'], ['batman', 'tas', 'bane'], ['tom', 'and', 'jerry'])
    """
    text = text.lower().replace("&", " and ")
    raw = [t for t in re.split(r"[^a-z0-9]+", text) if t]
    # Runs of single letters are an acronym written with dots or spaces:
    # "T.A.S" / "T A S" → "tas".
    out: list[str] = []
    run: list[str] = []
    for token in raw + [""]:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if len(run) >= 2:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        if token:
            out.append(token)
    return out


def title_matches(candidate: str, wanted: Iterable[str]) -> bool:
    """Does a filename's show title look like (an abbreviation of) a wanted title?

    >>> title_matches("Batman T.A.S", ["Batman: The Animated Series"])
    True
    >>> title_matches("The New Batman Adventures", ["Batman: The Animated Series"])
    False
    >>> title_matches("batman the animated series", ["Batman: The Animated Series"])
    True
    """
    cand = [t for t in _tokens(candidate) if not t.isdigit()]
    if not cand:
        return True
    for title in wanted:
        words = _tokens(title)
        acronyms = {
            "".join(w[0] for w in words[i:j])
            for i in range(len(words))
            for j in range(i + 2, len(words) + 1)
        }
        if all(t in words or t in acronyms for t in cand):
            return True
        overlap = len(set(cand) & set(words)) / max(len(set(cand) | set(words)), 1)
        if overlap >= 0.6:
            return True
    return False


def show_title_of(path: str) -> Optional[str]:
    """The show name a file claims, i.e. the text before its episode marker.

    >>> show_title_of("Pack/Season 5 (1997)/The New Batman Adventures - S01 E01 - Holiday Knights (1080p).mp4")
    'The New Batman Adventures'
    >>> show_title_of("Pack/Season 1/S01E01.mkv") is None
    True
    """
    base = path.rsplit("/", 1)[-1]
    match = _SXXEYY.search(base) or _NXNN.search(base)
    if not match:
        return None
    head = base[: match.start()]
    head = re.sub(r"[._]+", " ", head)
    head = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", head)
    head = _YEAR.sub(" ", head)
    head = re.sub(r"[\s\-–:]+$", "", head).strip(" -–_.")
    return head or None


def analyze(
    contents: TorrentContents,
    *,
    wanted_titles: Iterable[str] = (),
    wanted_episodes: Optional[set[tuple[int, int]]] = None,
    runtime_minutes: Optional[int] = None,
) -> ContentReport:
    """Build a ContentReport from a file list."""
    titles = [t for t in wanted_titles if t]
    report = ContentReport()
    videos = []
    containers: Counter[str] = Counter()
    seen: set[tuple[int, int]] = set()
    foreign: Counter[str] = Counter()
    for f in contents.files:
        ext = ext_of(f.path)
        base = f.path.rsplit("/", 1)[-1]
        lower = base.lower()
        if ext in SUSPICIOUS_EXT:
            report.suspicious_files.append(f.path)
            continue
        if ext in SUB_EXT:
            report.subtitle_files += 1
            continue
        if ext in JUNK_EXT:
            report.junk_files.append(f.path)
            continue
        if ext not in VIDEO_EXT:
            continue
        if re.search(r"(^|[^a-z])sample([^a-z]|$)", lower):
            report.sample_files.append(f.path)
            continue
        videos.append(f)
        containers[ext] += 1
        for ref in parse_episode(f.path):
            seen.add((ref.season, ref.episode))
        claimed = show_title_of(f.path)
        if claimed and titles and not title_matches(claimed, titles):
            foreign[claimed] += 1

    report.video_files = len(videos)
    total = sum(v.size for v in videos)
    report.total_video_gb = round(total / 1024**3, 2)
    report.containers = [c for c, _ in containers.most_common()]
    report.episodes = [EpisodeRef(season=s, episode=e) for s, e in sorted(seen)]
    report.seasons = sorted({s for s, _ in seen})
    report.foreign_titles = [name for name, _ in foreign.most_common(5)]
    if videos:
        avg = total / len(videos)
        report.avg_video_gb = round(avg / 1024**3, 2)
        if runtime_minutes:
            report.est_bitrate_mbps = round(avg * 8 / (runtime_minutes * 60) / 1e6, 1)
    if wanted_episodes:
        covered = wanted_episodes & seen
        report.wanted_episodes_total = len(wanted_episodes)
        report.wanted_episodes_covered = len(covered)
        missing = sorted(wanted_episodes - seen)
        if missing and len(missing) <= 12:
            report.notes.append("missing: " + ", ".join(f"S{s:02d}E{e:02d}" for s, e in missing))
        elif missing:
            report.notes.append(f"missing {len(missing)} of the wanted episodes")
    if foreign:
        report.notes.append(
            "contains files of another show: " + ", ".join(f"{n} ({c} files)" for n, c in foreign.most_common(3))
        )
    if report.suspicious_files:
        report.notes.append(f"{len(report.suspicious_files)} executable/archive files — likely fake or malware")
    return report


def select_paths(
    contents: TorrentContents,
    *,
    wanted_titles: Iterable[str],
    wanted_episodes: Optional[set[tuple[int, int]]] = None,
    include_subtitles: bool = True,
) -> list[str]:
    """Paths worth downloading from a pack: videos (and their subs) of the wanted
    show and, when given, only the wanted episodes. Junk and other shows are left out.
    """
    titles = [t for t in wanted_titles if t]
    keep: list[str] = []
    for f in contents.files:
        ext = ext_of(f.path)
        if ext not in VIDEO_EXT and not (include_subtitles and ext in SUB_EXT):
            continue
        if ext in VIDEO_EXT and re.search(r"(^|[^a-z])sample([^a-z]|$)", f.path.rsplit("/", 1)[-1].lower()):
            continue
        claimed = show_title_of(f.path)
        if claimed and titles and not title_matches(claimed, titles):
            continue
        if wanted_episodes is not None:
            refs = {(r.season, r.episode) for r in parse_episode(f.path)}
            if not refs or not (refs & wanted_episodes):
                continue
        keep.append(f.path)
    return keep
