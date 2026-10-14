"""The release judge pipeline.

1. Pre-rank every candidate cheaply (the app's verdict, indexer seeders, size).
2. Enrich the top N concurrently: file list + live swarm.
3. Analyse contents, score with transparent reasons.
4. Decide: an LLM reads the evidence and writes a verdict with a rationale;
   without a usable model, the highest-scoring viable release wins.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional

from maestarr.domain import JudgeResult, JudgeVerdict, ReleaseAssessment, ReleaseCandidate
from maestarr.judge.contents import analyze, select_paths
from maestarr.judge.score import score_assessment
from maestarr.preferences import Preferences
from maestarr.torrent.resolve import ReleaseResolver, Resolved, live_swarm

logger = logging.getLogger(__name__)

JUDGE_INSTRUCTIONS = """\
You are the release judge of Maestarr, an assistant for a home media server.
You receive candidate torrent releases for ONE title, each with evidence:
the media manager's own verdict (custom-format score, rejections), LIVE swarm
numbers from the trackers, what is really inside (file list analysis) and a
transparent rule-based score with reasons and blockers.

Pick the single best release for the user. Rules:
- Never pick a release with blockers.
- Live seeders matter more than indexer-reported ones; a dead swarm is useless.
- Respect the user's preferences and notes exactly.
- A pack that also contains another show is fine if the wanted files can be
  selected; say so in warnings.
- Prefer covering all wanted episodes over marginal quality gains.
- Quality is worth disk space only when the difference would be visible.
- If nothing is acceptable, return chosen_guid = null and explain why.
Write the rationale for the user in plain language (2-5 sentences), mentioning
the concrete numbers that decided it.
"""


@dataclass
class JudgeRequest:
    subject: str
    candidates: list[ReleaseCandidate]
    wanted_titles: list[str] = field(default_factory=list)
    wanted_episodes: Optional[set[tuple[int, int]]] = None
    runtime_minutes: Optional[int] = None
    expected_units: int = 1
    free_bytes: Optional[int] = None
    min_free_bytes: int = 0


def prerank(candidates: Iterable[ReleaseCandidate], prefs: Preferences) -> list[ReleaseCandidate]:
    """Cheap ordering before the expensive enrichment.

    >>> from maestarr.domain import ReleaseCandidate as R
    >>> a = R(app="sonarr", guid="a", indexer_id=1, title="a", seeders=50, custom_format_score=100)
    >>> b = R(app="sonarr", guid="b", indexer_id=1, title="b", seeders=500, rejections=["Wrong season"])
    >>> c = R(app="sonarr", guid="c", indexer_id=1, title="c", seeders=5, protocol="usenet")
    >>> [r.guid for r in prerank([b, c, a], Preferences())]
    ['a', 'b', 'c']
    """

    def key(c: ReleaseCandidate) -> tuple:
        res_ok = not c.resolution or prefs.min_resolution <= c.resolution <= prefs.max_resolution
        return (
            0 if c.is_torrent else 1,
            0 if not c.rejections else 1,
            0 if res_ok else 1,
            -c.custom_format_score,
            -(c.seeders or 0),
        )

    return sorted(candidates, key=key)


async def enrich(
    request: JudgeRequest, ranked: list[ReleaseCandidate], resolver: ReleaseResolver, top_n: int
) -> list[ReleaseAssessment]:
    top = [c for c in ranked if c.is_torrent][:top_n]
    resolved: list[Resolved] = await asyncio.gather(*(resolver.contents(c) for c in top))
    pairs = list(zip(top, resolved))
    # The same torrent often comes back from several indexers; keep the copy
    # the app likes best (it was ranked first).
    seen: set[str] = set()
    unique = []
    for candidate, res in pairs:
        key = (res.info_hash or candidate.info_hash or "").lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append((candidate, res))
    pairs = unique
    swarms = await live_swarm(pairs)
    out: list[ReleaseAssessment] = []
    for candidate, res in pairs:
        a = ReleaseAssessment(candidate=candidate, swarm=swarms.get(candidate.guid), contents=res.contents)
        if res.contents:
            a.report = analyze(
                res.contents,
                wanted_titles=request.wanted_titles,
                wanted_episodes=request.wanted_episodes,
                runtime_minutes=request.runtime_minutes,
            )
        elif res.error:
            a.reasons.append(res.error)
        out.append(a)
    return out


def rules_verdict(assessments: list[ReleaseAssessment], request: JudgeRequest) -> JudgeVerdict:
    viable = sorted((a for a in assessments if a.viable), key=lambda a: -a.score)
    if not viable:
        why = "; ".join(f"{a.candidate.title[:60]}: {', '.join(a.blockers)}" for a in assessments[:4])
        return JudgeVerdict(chosen_guid=None, rationale=f"No acceptable release. {why}", confidence="high")
    best = viable[0]
    runner = viable[1] if len(viable) > 1 else None
    reasons = "; ".join(best.reasons[:5])
    return JudgeVerdict(
        chosen_guid=best.candidate.guid,
        runner_up_guid=runner.candidate.guid if runner else None,
        rationale=f"Highest score ({best.score}): {best.candidate.title}. {reasons}.",
        confidence="medium" if runner and runner.score > best.score - 5 else "high",
        select_paths=_pack_selection(best, request),
        warnings=[n for n in (best.report.notes if best.report else [])],
    )


def _pack_selection(a: ReleaseAssessment, request: JudgeRequest) -> list[str]:
    """Only return a selection when it actually drops something."""
    if not a.contents or not a.report:
        return []
    needs = bool(a.report.foreign_titles or a.report.junk_files or a.report.suspicious_files)
    if request.wanted_episodes and a.report.episodes:
        have = {(e.season, e.episode) for e in a.report.episodes}
        needs = needs or bool(have - request.wanted_episodes)
    if not needs:
        return []
    return select_paths(a.contents, wanted_titles=request.wanted_titles, wanted_episodes=request.wanted_episodes)


def evidence_for_llm(assessments: list[ReleaseAssessment], prefs: Preferences, request: JudgeRequest) -> str:
    rows = []
    for a in assessments:
        c = a.candidate
        rows.append(
            {
                "guid": c.guid,
                "title": c.title,
                "indexer": c.indexer,
                "size_gb": c.size_gb,
                "quality": c.quality,
                "languages": c.languages,
                "group": c.release_group,
                "custom_formats": c.custom_formats,
                "indexer_seeders": c.seeders,
                "live_swarm": a.swarm.model_dump(include={"seeders", "leechers", "method"}) if a.swarm else None,
                "contents": a.report.model_dump(exclude={"episodes"}) if a.report else None,
                "score": a.score,
                "reasons": a.reasons,
                "blockers": a.blockers,
            }
        )
    return json.dumps(
        {
            "title": request.subject,
            "wanted_episodes": len(request.wanted_episodes) if request.wanted_episodes else None,
            "free_space_gb": round(request.free_bytes / 1024**3) if request.free_bytes else None,
            "preferences": prefs.model_dump(),
            "candidates": rows,
        },
        ensure_ascii=False,
        default=str,
    )


async def llm_verdict(model: object, assessments: list[ReleaseAssessment], prefs: Preferences, request: JudgeRequest) -> JudgeVerdict:
    from pydantic_ai import Agent

    agent: Agent[None, JudgeVerdict] = Agent(model, output_type=JudgeVerdict, instructions=JUDGE_INSTRUCTIONS)  # type: ignore[call-overload]
    result = await agent.run(evidence_for_llm(assessments, prefs, request))
    verdict = result.output
    known = {a.candidate.guid: a for a in assessments}
    if verdict.chosen_guid and verdict.chosen_guid not in known:
        raise ValueError("model chose an unknown guid")
    if verdict.chosen_guid and known[verdict.chosen_guid].blockers:
        raise ValueError("model chose a blocked release")
    if verdict.chosen_guid and not verdict.select_paths:
        verdict.select_paths = _pack_selection(known[verdict.chosen_guid], request)
    return verdict


async def judge(
    request: JudgeRequest,
    resolver: ReleaseResolver,
    prefs: Preferences,
    *,
    top_n: int = 6,
    model: object = None,
) -> JudgeResult:
    ranked = prerank(request.candidates, prefs)
    assessments = await enrich(request, ranked, resolver, top_n)
    for a in assessments:
        existing_reasons = list(a.reasons)
        score_assessment(
            a,
            prefs,
            free_bytes=request.free_bytes,
            min_free_bytes=request.min_free_bytes,
            expected_units=request.expected_units,
        )
        a.reasons = existing_reasons + a.reasons
    assessments.sort(key=lambda a: (not a.viable, -a.score))
    decided_by = "rules"
    verdict = rules_verdict(assessments, request)
    if model is not None and assessments:
        try:
            verdict = await llm_verdict(model, assessments, prefs, request)
            decided_by = "llm"
        except Exception as exc:  # noqa: BLE001 — the rules verdict stands
            logger.warning("LLM verdict failed, using rules: %s", exc)
    return JudgeResult(subject=request.subject, assessments=assessments, verdict=verdict, decided_by=decided_by)  # type: ignore[arg-type]
