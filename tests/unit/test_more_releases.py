"""more_releases pages through the rest of a judged search, scored, best first."""

from __future__ import annotations

import time

import pytest

from maestarr.clients.base import ServiceError
from maestarr.config import get_settings
from maestarr.domain import ReleaseCandidate
from maestarr.judge.judge import JudgeRequest
from maestarr.ops.releases import more_releases
from maestarr.services import Services


def cand(n: int, **kw: object) -> ReleaseCandidate:
    return ReleaseCandidate(app="radarr", guid=f"g{n}", indexer_id=1, title=f"Movie.1080p.{n}", seeders=n, **kw)  # type: ignore[arg-type]


async def test_pages_and_scores_the_rest():
    svc = Services.from_settings(get_settings())
    rest = [cand(n, resolution=1080, size=4 * 1024**3) for n in range(1, 12)]
    svc.memo["results:abc"] = {"request": JudgeRequest(subject="X (2000)", candidates=rest), "rest": rest, "at": time.time()}
    first = await more_releases(svc, "abc", limit=5)
    assert first["depth"] == "quick" and first["next_offset"] == 5 and first["more_available"] == 6
    assert len(first["assessed"]) == 5 and all(r["score"] for r in first["assessed"])
    second = await more_releases(svc, "abc", offset=first["next_offset"], limit=10)
    assert len(second["assessed"]) == 6 and second["more_available"] == 0
    assert "g1" in svc.assessments  # grab_release can use them
    await svc.aclose()


async def test_expired_results_ask_for_a_new_search():
    svc = Services.from_settings(get_settings())
    with pytest.raises(ServiceError, match="expired"):
        await more_releases(svc, "missing")
    await svc.aclose()
