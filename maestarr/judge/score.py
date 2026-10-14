"""Deterministic scoring of an assessed release.

The score is a transparent sum of named contributions — every point added or
taken away is written into `reasons`, and anything disqualifying goes into
`blockers`. The LLM sees exactly these lines, so its verdict rests on the same
evidence a human would check.
"""

from __future__ import annotations

import math
from typing import Optional

from maestarr.domain import GiB, ReleaseAssessment
from maestarr.preferences import Preferences

_HARD_REJECTIONS = ("blocklisted", "blacklisted")


def score_assessment(
    a: ReleaseAssessment,
    prefs: Preferences,
    *,
    free_bytes: Optional[int] = None,
    min_free_bytes: int = 0,
    expected_units: int = 1,
) -> ReleaseAssessment:
    """Fill `score`, `reasons` and `blockers` in place and return the assessment.

    `expected_units` is the number of episodes the release is meant to cover
    (1 for a movie), used for per-episode size and bitrate checks.
    """
    c = a.candidate
    reasons: list[str] = []
    blockers: list[str] = []
    score = 50.0

    # --- the app's own verdict (quality profile + custom formats) -----------
    if c.custom_format_score:
        delta = max(-25.0, min(25.0, c.custom_format_score / 40.0))
        score += delta
        reasons.append(f"custom-format score {c.custom_format_score:+d} ({delta:+.0f})")
    for rejection in c.rejections:
        if any(word in rejection.lower() for word in _HARD_REJECTIONS):
            blockers.append(f"{c.app}: {rejection}")
        else:
            score -= 6
            reasons.append(f"{c.app} rejection: {rejection} (-6)")

    # --- resolution ---------------------------------------------------------
    res = c.resolution or 0
    if res:
        if res > prefs.max_resolution:
            blockers.append(f"{res}p is above the {prefs.max_resolution}p limit")
        elif res < prefs.min_resolution:
            score -= 15
            reasons.append(f"{res}p is below the preferred {prefs.min_resolution}p (-15)")
        else:
            res_bonus = {2160: 10, 1080: 8, 720: 3}.get(res, 0)
            score += res_bonus
            reasons.append(f"{res}p (+{res_bonus})")
    if c.quality and "remux" in c.quality.lower() and not prefs.allow_remux:
        score -= 20
        reasons.append("remux while remuxes are not wanted (-20)")

    # --- groups -------------------------------------------------------------
    group = (c.release_group or "").lower()
    if group and group in {g.lower() for g in prefs.avoid_groups}:
        blockers.append(f"release group {c.release_group} is on the avoid list")
    if group and group in {g.lower() for g in prefs.prefer_groups}:
        score += 8
        reasons.append(f"preferred group {c.release_group} (+8)")

    # --- live swarm -----------------------------------------------------------
    swarm = a.swarm
    if swarm is not None:
        seeders = swarm.seeders
        label = "live" if swarm.method == "scrape" else "indexer-reported"
        if seeders == 0 and swarm.method == "scrape":
            blockers.append("no live seeders right now")
        elif seeders < prefs.min_live_seeders:
            score -= 12
            reasons.append(f"only {seeders} {label} seeders (-12)")
        else:
            seed_bonus = min(25.0, math.log2(1 + seeders) * 4)
            score += seed_bonus
            reasons.append(f"{seeders} {label} seeders (+{seed_bonus:.0f})")
        if swarm.method == "scrape" and c.seeders and c.seeders > 3 * max(seeders, 1):
            reasons.append(f"indexer claimed {c.seeders} seeders, trackers report {seeders}")

    # --- what is inside -----------------------------------------------------
    r = a.report
    if r is not None:
        if r.suspicious_files:
            blockers.append(f"contains executables/archives ({len(r.suspicious_files)}) — likely fake")
        if r.video_files == 0 and a.contents is not None:
            blockers.append("no video files inside")
        if r.junk_files:
            score -= 3
            reasons.append(f"{len(r.junk_files)} junk/ad files (-3)")
        if r.foreign_titles:
            reasons.append("pack also holds another show: " + ", ".join(r.foreign_titles) + " — select files")
        if r.wanted_episodes_total:
            ratio = (r.wanted_episodes_covered or 0) / r.wanted_episodes_total
            cover_bonus = 25 * ratio
            score += cover_bonus
            reasons.append(
                f"covers {r.wanted_episodes_covered}/{r.wanted_episodes_total} wanted episodes (+{cover_bonus:.0f})"
            )
            if ratio == 0:
                blockers.append("none of the wanted episodes are inside")
        if r.est_bitrate_mbps is not None and res >= 1080:
            floor = prefs.min_1080p_mbps * (2.0 if res >= 2160 else 1.0)
            if r.est_bitrate_mbps < floor:
                score -= 8
                reasons.append(f"~{r.est_bitrate_mbps} Mbps is thin for {res}p (-8)")
            else:
                reasons.append(f"~{r.est_bitrate_mbps} Mbps video")
        if r.sample_files and r.video_files == 0:
            blockers.append("only sample files")
    if a.contents is None and a.candidate.is_torrent:
        reasons.append("file list unavailable")

    # --- size -------------------------------------------------------------------
    units = max(1, expected_units)
    per_unit_gb = c.size / GiB / units
    cap = prefs.max_gb_per_movie if units == 1 and not c.full_season and not c.episode_numbers else prefs.max_gb_per_episode
    if cap and per_unit_gb > cap:
        over = min(20.0, (per_unit_gb / cap - 1) * 20)
        score -= over
        reasons.append(f"{per_unit_gb:.1f} GB per item is over the {cap} GB cap (-{over:.0f})")
    if free_bytes is not None and c.size > max(0, free_bytes - min_free_bytes):
        blockers.append(
            f"needs {c.size_gb} GB but only {free_bytes / GiB:.0f} GB is free"
            + (f" (keeping {min_free_bytes / GiB:.0f} GB spare)" if min_free_bytes else "")
        )

    a.score = round(score, 1)
    a.reasons = reasons
    a.blockers = blockers
    return a
