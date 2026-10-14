"""Release operations — search, judge, inspect, grab, select files, import."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
import uuid
from typing import Any, Optional

from maestarr.clients.base import ServiceError
from maestarr.domain import JudgeResult, ReleaseAssessment, ReleaseCandidate
from maestarr.judge.contents import parse_episode
from maestarr.judge.judge import JudgeRequest, enrich, judge, prerank
from maestarr.judge.score import score_assessment
from maestarr.services import Services

logger = logging.getLogger(__name__)


def _brief(c: ReleaseCandidate) -> dict[str, Any]:
    return {
        "guid": c.guid,
        "title": c.title,
        "indexer": c.indexer,
        "size_gb": c.size_gb,
        "seeders": c.seeders,
        "quality": c.quality,
        "languages": c.languages[:3],
        "cf_score": c.custom_format_score,
        "rejections": c.rejections[:3],
        "full_season": c.full_season,
        "age_days": c.age_days,
        "protocol": c.protocol,
    }


def _remember(svc: Services, releases: list[ReleaseCandidate]) -> None:
    now = time.time()
    for r in releases:
        svc.releases[r.guid] = (now, r)
    # Sonarr/Radarr keep their search cache ~30 minutes; forget older ones.
    for guid, (seen, _) in list(svc.releases.items()):
        if now - seen > 1800:
            svc.releases.pop(guid, None)
            svc.assessments.pop(guid, None)


def get_release(svc: Services, guid: str) -> ReleaseCandidate:
    entry = svc.releases.get(guid)
    if not entry:
        raise ServiceError("maestarr", "unknown or expired release guid — search again")
    return entry[1]


async def find_releases(
    svc: Services,
    *,
    series_id: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    movie_id: Optional[int] = None,
    app: str = "radarr",
    limit: int = 25,
) -> dict[str, Any]:
    """Interactive search through Sonarr/Radarr/Whisparr (uses the user's quality profile)."""
    if movie_id is not None:
        releases = await svc.need_movie_app(app).releases(movieId=movie_id)
    elif series_id is not None:
        sonarr = svc.need_sonarr()
        if episode is not None:
            if season is None:
                raise ServiceError("maestarr", "an episode search needs the season too")
            eps = await sonarr.episodes(series_id)
            match = next((e for e in eps if e["seasonNumber"] == season and e["episodeNumber"] == episode), None)
            if not match:
                raise ServiceError("sonarr", f"S{season:02d}E{episode:02d} not found")
            releases = await sonarr.releases(episodeId=match["id"])
        elif season is not None:
            releases = await sonarr.releases(seriesId=series_id, seasonNumber=season)
        else:
            raise ServiceError("maestarr", "give a season (or season+episode) for series searches")
    else:
        raise ServiceError("maestarr", "give series_id+season or movie_id")
    _remember(svc, releases)
    ordered = sorted(releases, key=lambda r: (bool(r.rejections), -r.custom_format_score, -(r.seeders or 0)))
    return {
        "total": len(releases),
        "accepted_by_app": sum(1 for r in releases if not r.rejections),
        "releases": [_brief(r) for r in ordered[:limit]],
    }


async def search_indexers(svc: Services, query: str, kind: str = "any", limit: int = 25) -> dict[str, Any]:
    """Free-text search across all Prowlarr indexers (packs the apps cannot map)."""
    releases = await svc.need_prowlarr().search(query, kind=kind, limit=100)
    _remember(svc, releases)
    ordered = sorted(releases, key=lambda r: -(r.seeders or 0))
    return {"total": len(releases), "releases": [_brief(r) for r in ordered[:limit]]}


async def _context_for(svc: Services, releases: list[ReleaseCandidate], series_id: Optional[int], season: Optional[int],
                       episode: Optional[int], movie_id: Optional[int], app: str = "radarr") -> JudgeRequest:
    titles: list[str] = []
    wanted: Optional[set[tuple[int, int]]] = None
    runtime: Optional[int] = None
    units = 1
    path: Optional[str] = None
    subject = "release search"
    if series_id is not None and svc.sonarr:
        series = await svc.sonarr.series_by_id(series_id)
        titles = [series["title"]] + [a["title"] for a in series.get("alternateTitles") or []]
        runtime = series.get("runtime") or None
        path = series.get("path")
        eps = await svc.sonarr.episodes(series_id)
        wanted = {
            (e["seasonNumber"], e["episodeNumber"])
            for e in eps
            if (season is None or e["seasonNumber"] == season)
            and (episode is None or e["episodeNumber"] == episode)
            and e["seasonNumber"] > 0
        }
        units = max(1, len(wanted))
        subject = series["title"] + (f" S{season:02d}" if season is not None else "") + (f"E{episode:02d}" if episode is not None else "")
    elif movie_id is not None and (svc.whisparr if app == "whisparr" else svc.radarr):
        movie = await svc.need_movie_app(app).movie_by_id(movie_id)
        titles = [movie["title"], movie.get("originalTitle") or ""]
        runtime = movie.get("runtime") or None
        path = movie.get("path")
        subject = f"{movie['title']} ({movie.get('year')})"
    free = await svc.free_bytes(path)
    return JudgeRequest(
        subject=subject,
        candidates=releases,
        wanted_titles=[t for t in titles if t],
        wanted_episodes=wanted,
        runtime_minutes=runtime,
        expected_units=units,
        free_bytes=free,
        min_free_bytes=int(svc.settings.MAESTARR_MIN_FREE_GB * 1024**3),
    )


async def judge_releases(
    svc: Services,
    *,
    series_id: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    movie_id: Optional[int] = None,
    guids: Optional[list[str]] = None,
    app: str = "radarr",
    use_llm: bool = True,
) -> dict[str, Any]:
    """Search (unless guids are given), enrich the best candidates and decide."""
    if guids:
        releases = [get_release(svc, g) for g in guids]
        app = next((r.app for r in releases if r.app in ("radarr", "whisparr")), app)
    else:
        await find_releases(svc, series_id=series_id, season=season, episode=episode, movie_id=movie_id, app=app)
        wanted_app = app if movie_id is not None else "sonarr"
        releases = [r for _, r in svc.releases.values() if r.app == wanted_app and _matches(r, series_id, movie_id)]
    if not releases:
        return {"verdict": None, "message": "no releases found"}
    if series_id is None and movie_id is None:
        series_id = next((r.series_id for r in releases if r.series_id), None)
        movie_id = next((r.movie_id for r in releases if r.movie_id), None)
    request = await _context_for(svc, releases, series_id, season, episode, movie_id, app)
    model = None
    if use_llm:
        from maestarr.llm import build_model

        try:
            model = build_model(svc.settings)
        except ValueError:
            model = None
    result = await judge(request, svc.resolver, svc.preferences(), top_n=svc.settings.MAESTARR_ENRICH_TOP_N, model=model)
    for a in result.assessments:
        svc.assessments[a.candidate.guid] = a
    if result.verdict.chosen_guid and result.verdict.select_paths:
        svc.memo[f"selection:{result.verdict.chosen_guid}"] = list(result.verdict.select_paths)
    out = summarize(result)
    # Keep the rest of the search, best first, for "show more results".
    judged = {a.candidate.guid for a in result.assessments}
    hashes = {(a.candidate.info_hash or "").lower() for a in result.assessments} - {""}
    rest = [
        r for r in prerank(releases, svc.preferences())
        if r.guid not in judged and (r.info_hash or "").lower() not in hashes
    ]
    results_id = uuid.uuid4().hex[:8]
    svc.memo[f"results:{results_id}"] = {"request": request, "rest": rest, "at": time.time()}
    out["results_id"] = results_id
    out["more_available"] = len(rest)
    return out


async def more_releases(
    svc: Services, results_id: str, *, offset: int = 0, limit: int = 8, deep: bool = False
) -> dict[str, Any]:
    """The next releases of a judged search, best first.

    Quick by default (scored on what the indexer and the app report); `deep`
    also reads their file lists and live seeders, like judge_releases.
    """
    entry = svc.memo.get(f"results:{results_id}")
    if not entry or time.time() - entry["at"] > 1800:
        raise ServiceError("maestarr", "those results expired — run judge_releases again")
    request: JudgeRequest = entry["request"]
    page = entry["rest"][offset : offset + max(1, min(limit, 20))]
    prefs = svc.preferences()
    if deep:
        assessments = await enrich(request, page, svc.resolver, len(page))
    else:
        assessments = [ReleaseAssessment(candidate=c) for c in page]
    for a in assessments:
        earlier = list(a.reasons)
        score_assessment(a, prefs, free_bytes=request.free_bytes, min_free_bytes=request.min_free_bytes,
                         expected_units=request.expected_units)
        a.reasons = earlier + a.reasons
        svc.assessments[a.candidate.guid] = a
    assessments.sort(key=lambda a: (not a.viable, -a.score))
    next_offset = offset + len(page)
    return {
        "subject": request.subject,
        "results_id": results_id,
        "depth": "full" if deep else "quick",
        "offset": offset,
        "next_offset": next_offset,
        "more_available": max(0, len(entry["rest"]) - next_offset),
        "assessed": [_row(a) for a in assessments],
    }


def _matches(r: ReleaseCandidate, series_id: Optional[int], movie_id: Optional[int]) -> bool:
    if series_id is not None:
        return r.series_id in (None, series_id)
    if movie_id is not None:
        return r.movie_id in (None, movie_id)
    return True


def _row(a: ReleaseAssessment) -> dict[str, Any]:
    r = a.report
    return {
        "guid": a.candidate.guid,
        "title": a.candidate.title,
        "size_gb": a.candidate.size_gb,
        "score": a.score,
        "indexer_seeders": a.candidate.seeders,
        "live_seeders": a.swarm.seeders if a.swarm else None,
        "swarm_source": a.swarm.method if a.swarm else None,
        "videos": r.video_files if r else None,
        "coverage": f"{r.wanted_episodes_covered}/{r.wanted_episodes_total}" if r and r.wanted_episodes_total else None,
        "avg_file_gb": r.avg_video_gb if r else None,
        "bitrate_mbps": r.est_bitrate_mbps if r else None,
        "notes": (r.notes if r else [])[:3],
        "reasons": a.reasons[:6],
        "blockers": a.blockers,
        "quality": a.candidate.quality,
        "indexer": a.candidate.indexer,
    }


def summarize(result: JudgeResult) -> dict[str, Any]:
    v = result.verdict
    return {
        "subject": result.subject,
        "decided_by": result.decided_by,
        "verdict": {
            "chosen_guid": v.chosen_guid,
            "runner_up_guid": v.runner_up_guid,
            "rationale": v.rationale,
            "confidence": v.confidence,
            "warnings": v.warnings,
            "files_to_select": len(v.select_paths) or None,
            "select_paths": v.select_paths[:200],
        },
        "assessed": [_row(a) for a in result.assessments],
    }


async def inspect_release(svc: Services, guid: str) -> dict[str, Any]:
    """The file tree of one release, folder by folder, with the content analysis."""
    release = get_release(svc, guid)
    assessment = svc.assessments.get(guid)
    contents = assessment.contents if assessment else None
    if contents is None:
        resolved = await svc.resolver.contents(release)
        if not resolved.contents:
            return {"guid": guid, "error": resolved.error or "file list unavailable"}
        contents = resolved.contents
    folders: dict[str, dict[str, Any]] = {}
    for f in contents.files:
        parts = f.path.split("/")
        folder = "/".join(parts[1:-1]) if len(parts) > 2 else "(root)"
        entry = folders.setdefault(folder, {"files": 0, "gb": 0.0, "examples": []})
        entry["files"] += 1
        entry["gb"] += f.size / 1024**3
        if len(entry["examples"]) < 2:
            entry["examples"].append(parts[-1])
    return {
        "guid": guid,
        "name": contents.name,
        "info_hash": contents.info_hash,
        "total_gb": round(contents.total_size / 1024**3, 2),
        "files": len(contents.files),
        "folders": [{"folder": k, "files": v["files"], "gb": round(v["gb"], 2), "examples": v["examples"]} for k, v in folders.items()][:40],
        "analysis": assessment.report.model_dump(exclude={"episodes"}) if assessment and assessment.report else None,
    }


async def grab_release(
    svc: Services,
    guid: str,
    *,
    select_paths: Optional[list[str]] = None,
    use_judge_selection: bool = True,
    override_series_id: Optional[int] = None,
    override_episodes: Optional[list[int]] = None,
    override_season: Optional[int] = None,
    override_movie_id: Optional[int] = None,
) -> dict[str, Any]:
    """Send a release to the download client through its *arr app.

    For packs, only `select_paths` (or the judge's selection) is downloaded:
    once the torrent appears in qBittorrent every other file is set to
    "do not download".
    """
    release = get_release(svc, guid)
    assessment: Optional[ReleaseAssessment] = svc.assessments.get(guid)
    paths = select_paths
    if paths is None and use_judge_selection:
        paths = svc.memo.get(f"selection:{guid}") or None
    info_hash = (assessment.contents.info_hash if assessment and assessment.contents else None) or release.info_hash

    if release.app == "prowlarr":
        qbit = svc.need_qbittorrent()
        source = release.magnet_url if (release.magnet_url or "").startswith("magnet:") else release.download_url
        if not source:
            raise ServiceError("maestarr", "release has no link to send")
        # Use the category the *arr app watches, so it can import the result.
        cats = await qbit.categories()
        options = ("movies", "radarr") if override_movie_id else ("tv", "tv-sonarr", "sonarr")
        category = next((c for c in options if c in cats), None)
        await qbit.add(urls=[source], category=category)
        result: dict[str, Any] = {"sent_to": "qbittorrent", "category": category,
                                  "note": "added directly; import it with manual_import when finished"}
    else:
        app = svc.need_sonarr() if release.app == "sonarr" else svc.need_movie_app(release.app)
        episode_ids: Optional[list[int]] = None
        if override_series_id is not None and svc.sonarr:
            eps = await svc.sonarr.episodes(override_series_id)
            episode_ids = [
                e["id"] for e in eps
                if (override_season is None or e["seasonNumber"] == override_season)
                and (override_episodes is None or e["episodeNumber"] in override_episodes)
                and e["seasonNumber"] > 0
            ]
        await app.grab(
            release,
            series_id=override_series_id,
            episode_ids=episode_ids,
            movie_id=override_movie_id,
        )
        result = {"sent_to": release.app, "title": release.title}

    if paths and info_hash and svc.qbittorrent:
        applied = await _apply_selection(svc, info_hash, paths)
        result["file_selection"] = applied
    elif paths:
        result["file_selection"] = "could not apply: infohash unknown — use select_torrent_files once it appears"
    result["info_hash"] = info_hash
    return result


async def _apply_selection(svc: Services, info_hash: str, keep_paths: list[str], wait: float = 90.0) -> dict[str, Any]:
    qbit = svc.need_qbittorrent()
    deadline = time.monotonic() + wait
    files: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        try:
            files = await qbit.files(info_hash)
        except ServiceError:
            files = []
        if files:
            break
        await asyncio.sleep(3)
    if not files:
        return {"applied": False, "reason": "torrent did not appear in qBittorrent in time"}
    return await set_files(svc, info_hash, keep_paths=keep_paths, files=files)


async def set_files(
    svc: Services,
    info_hash: str,
    *,
    keep_paths: Optional[list[str]] = None,
    keep_globs: Optional[list[str]] = None,
    files: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Download only matching files of a torrent; everything else gets priority 0."""
    qbit = svc.need_qbittorrent()
    files = files or await qbit.files(info_hash)
    keep_set = {p.strip("/") for p in keep_paths or []}

    def wanted(name: str) -> bool:
        if name.strip("/") in keep_set:
            return True
        tail = name.split("/", 1)[-1]
        if tail in keep_set:
            return True
        return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(tail, g) for g in keep_globs or [])

    keep = [f["index"] for f in files if wanted(f["name"])]
    drop = [f["index"] for f in files if not wanted(f["name"])]
    if not keep:
        return {"applied": False, "reason": "nothing matched — refusing to deselect every file"}
    await qbit.set_file_priority(info_hash, keep, 1)
    await qbit.set_file_priority(info_hash, drop, 0)
    kept_bytes = sum(f["size"] for f in files if f["index"] in set(keep))
    return {"applied": True, "kept_files": len(keep), "skipped_files": len(drop), "download_gb": round(kept_bytes / 1024**3, 2)}


async def manual_import(
    svc: Services,
    download_id: str,
    *,
    series_id: Optional[int] = None,
    movie_id: Optional[int] = None,
    only_seasons: Optional[list[int]] = None,
    dry_run: bool = False,
    app: str = "radarr",
) -> dict[str, Any]:
    """Import a finished download into the right series/movie.

    Files Sonarr cannot map by itself are mapped from their own SxxEyy markers
    onto `series_id`'s episodes. `only_seasons` restricts what is imported
    (e.g. the seasons 1-4 of a pack whose 5-6 belong to another show).
    """
    if movie_id is not None:
        radarr = svc.need_movie_app(app)
        scan = await radarr.manual_import_scan(download_id=download_id.upper(), movie_id=movie_id)
        files = [
            {"path": f["path"], "movieId": movie_id, "quality": f.get("quality"), "languages": f.get("languages") or [],
             "releaseGroup": f.get("releaseGroup"), "downloadId": download_id.upper(), "indexerFlags": f.get("indexerFlags", 0)}
            for f in scan if not _is_sample(f)
        ]
        if dry_run:
            return {"would_import": [f["path"].rsplit("/", 1)[-1] for f in files]}
        if not files:
            return {"imported": 0, "reason": "Radarr found no importable files"}
        cmd = await radarr.manual_import(files)
        return {"imported": len(files), "command_id": cmd.get("id")}

    sonarr = svc.need_sonarr()
    scan = await sonarr.manual_import_scan(download_id=download_id.upper(), series_id=series_id)
    episodes = await sonarr.episodes(series_id) if series_id is not None else []
    by_number = {(e["seasonNumber"], e["episodeNumber"]): e["id"] for e in episodes}
    planned: list[dict[str, Any]] = []
    skipped: list[str] = []
    for f in scan:
        if _is_sample(f):
            continue
        ep_ids = [e["id"] for e in f.get("episodes") or []]
        sid = (f.get("series") or {}).get("id") or series_id
        if series_id is not None and sid != series_id:
            ep_ids, sid = [], series_id
        if not ep_ids:
            refs = parse_episode(f.get("relativePath") or f["path"])
            ep_ids = [by_number[(r.season, r.episode)] for r in refs if (r.season, r.episode) in by_number]
            seasons_of_file = {r.season for r in refs}
        else:
            seasons_of_file = {e["seasonNumber"] for e in f.get("episodes") or []}
        if only_seasons is not None and not (seasons_of_file & set(only_seasons)):
            skipped.append(f["path"].rsplit("/", 1)[-1])
            continue
        if not ep_ids or sid is None:
            skipped.append(f["path"].rsplit("/", 1)[-1])
            continue
        planned.append(
            {
                "path": f["path"],
                "seriesId": sid,
                "episodeIds": ep_ids,
                "quality": f.get("quality"),
                "languages": f.get("languages") or [],
                "releaseGroup": f.get("releaseGroup"),
                "downloadId": download_id.upper(),
                "indexerFlags": f.get("indexerFlags", 0),
                "releaseType": f.get("releaseType", "singleEpisode"),
            }
        )
    if dry_run or not planned:
        return {
            "would_import": len(planned),
            "examples": [p["path"].rsplit("/", 1)[-1] for p in planned[:5]],
            "skipped": skipped[:20],
        }
    cmd = await sonarr.manual_import(planned)
    return {"imported": len(planned), "skipped": len(skipped), "command_id": cmd.get("id")}


def _is_sample(f: dict[str, Any]) -> bool:
    return any("sample" in str(r).lower() for r in f.get("rejections") or []) and "sample" in f.get("path", "").lower()
