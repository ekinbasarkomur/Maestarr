"""Candidate generation and taste/mood scoring.

Candidates come from three places: TMDB "recommendations"/"similar" of the
user's strongest seeds, TMDB discover on their top genres, and — when a mood is
given — discover on the mood's keywords. Each candidate is scored against the
profile per dimension with diminishing returns (`1 - 1/(1+Σ√w)`), blended
(keywords 0.45, genres 0.25, people 0.2, language 0.05, decade 0.05), boosted by
mood overlap and lightly by rating. Already-watched titles are dropped; titles
already in the library are kept and marked (they are the cheapest "yes").
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from maestarr.clients.tmdb import TmdbClient, credits_people, tmdb_kind
from maestarr.domain import MediaKind, MediaRef, Recommendation, TasteProfile
from maestarr.taste.profile import DetailsCache

WEIGHTS = {"keywords": 0.45, "genres": 0.25, "people": 0.20, "languages": 0.05, "decades": 0.05}

# A small starter lexicon so common moods work without the model's help;
# the agent passes its own keywords for anything else.
MOOD_LEXICON: dict[str, dict[str, list[str]]] = {
    "melancholic": {"genres": ["Drama"], "keywords": ["melancholy", "loneliness", "grief", "solitude", "nostalgia"]},
    "sad": {"genres": ["Drama"], "keywords": ["grief", "loss", "tragedy"]},
    "cozy": {"genres": ["Comedy", "Family", "Romance"], "keywords": ["feel-good", "friendship", "small town"]},
    "feel-good": {"genres": ["Comedy"], "keywords": ["feel-good", "friendship", "heartwarming"]},
    "mind-bending": {"genres": ["Science Fiction", "Mystery"], "keywords": ["mind-bending", "nonlinear timeline", "twist ending", "time loop"]},
    "tense": {"genres": ["Thriller"], "keywords": ["suspense", "paranoia", "cat and mouse"]},
    "scary": {"genres": ["Horror"], "keywords": ["supernatural", "haunting", "survival horror"]},
    "romantic": {"genres": ["Romance"], "keywords": ["love", "romance", "relationship"]},
    "epic": {"genres": ["Adventure", "Fantasy", "War"], "keywords": ["epic", "quest", "battle"]},
    "funny": {"genres": ["Comedy"], "keywords": ["satire", "dark comedy", "absurdism"]},
    "inspiring": {"genres": ["Drama"], "keywords": ["inspirational", "underdog", "based on true story"]},
}


@dataclass
class RecommendRequest:
    kind: MediaKind = "movie"
    mood: Optional[str] = None
    mood_keywords: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    language: Optional[str] = None
    max_runtime: Optional[int] = None
    min_rating: float = 6.0
    limit: int = 8
    include_owned: bool = True


def dim_score(values: list[str], weights: dict[str, float]) -> Optional[float]:
    """Diminishing-returns match of an item's values against one profile dimension.

    >>> round(dim_score(["a", "b"], {"a": 1.0, "b": 0.25}), 3)
    0.6
    >>> dim_score([], {"a": 1.0}) is None
    True
    """
    if not values or not weights:
        return None
    total = sum(math.sqrt(weights[v]) for v in values if v in weights)
    return 1 - 1 / (1 + total)


def taste_score(ref: MediaRef, people: list[str], profile: TasteProfile) -> tuple[float, list[str]]:
    parts = {
        "keywords": dim_score(ref.keywords, profile.keywords),
        "genres": dim_score(ref.genres, profile.genres),
        "people": dim_score(people, profile.people),
        "languages": dim_score([ref.original_language] if ref.original_language else [], profile.languages),
        "decades": dim_score([f"{ref.year // 10 * 10}s"] if ref.year else [], profile.decades),
    }
    present = {k: v for k, v in parts.items() if v is not None}
    if not present:
        return 0.0, []
    weight_sum = sum(WEIGHTS[k] for k in present)
    score = sum(WEIGHTS[k] * v for k, v in present.items()) / weight_sum
    why: list[str] = []
    shared_kw = [k for k in ref.keywords if k in profile.keywords][:4]
    if shared_kw:
        why.append("themes you watch: " + ", ".join(shared_kw))
    shared_people = [p for p in people if p in profile.people][:3]
    if shared_people:
        why.append("people you like: " + ", ".join(shared_people))
    shared_genres = [g for g in ref.genres if g in profile.genres][:3]
    if shared_genres and not shared_kw:
        why.append("genres you watch: " + ", ".join(shared_genres))
    return score, why


async def resolve_mood(tmdb: TmdbClient, req: RecommendRequest) -> tuple[list[int], list[str], list[str]]:
    """→ (keyword ids, keyword names, genre names) for the requested mood."""
    words = list(req.mood_keywords)
    genres = list(req.genres)
    if req.mood:
        entry = MOOD_LEXICON.get(req.mood.lower().strip())
        if entry:
            words += [w for w in entry["keywords"] if w not in words]
            genres += [g for g in entry["genres"] if g not in genres]
        elif not words:
            words.append(req.mood)
    found = await asyncio.gather(*(tmdb.search_keywords(w) for w in words[:8]))
    ids: list[int] = []
    names: list[str] = []
    for word, hits in zip(words, found):
        exact = [h for h in hits if h["name"].lower() == word.lower()] or hits[:1]
        for h in exact:
            ids.append(h["id"])
            names.append(h["name"])
    return ids, names, genres


async def recommend(
    req: RecommendRequest,
    profile: TasteProfile,
    cache: DetailsCache,
    *,
    owned: set[tuple[str, int]],
    watched: set[tuple[str, int]],
) -> list[Recommendation]:
    tmdb = cache.tmdb
    kind = tmdb_kind(req.kind)
    mood_ids, mood_names, mood_genres = await resolve_mood(tmdb, req) if (req.mood or req.mood_keywords) else ([], [], [])
    genre_ids = await tmdb.genre_ids(kind, req.genres or mood_genres or profile.top("genres", 3))

    date_key = "primary_release_date" if kind == "movie" else "first_air_date"
    base_filters: dict[str, Any] = {
        "vote_count.gte": 150 if kind == "movie" else 60,
        "vote_average.gte": req.min_rating,
        f"{date_key}.gte": f"{req.year_from}-01-01" if req.year_from else None,
        f"{date_key}.lte": f"{req.year_to}-12-31" if req.year_to else None,
        "with_original_language": req.language,
        "with_runtime.lte": req.max_runtime,
    }
    if req.kind == "anime":
        base_filters["with_genres"] = "16"
        base_filters["with_original_language"] = req.language or "ja"

    calls = []
    if mood_ids:
        calls.append(tmdb.discover(kind, with_keywords="|".join(map(str, mood_ids)), **base_filters))
        calls.append(tmdb.discover(kind, with_keywords="|".join(map(str, mood_ids)), sort_by="popularity.desc", **base_filters))
    if genre_ids:
        g_filters = dict(base_filters)
        g_filters.setdefault("with_genres", "|".join(map(str, genre_ids)))
        calls.append(tmdb.discover(kind, **g_filters))
    seed_details = [
        cache.details(kind, s.tmdb_id) for s in profile.seeds if s.tmdb_id and tmdb_kind(s.kind) == kind
    ][:8]
    pools = await asyncio.gather(*calls)
    seeds = await asyncio.gather(*seed_details)

    candidates: dict[int, dict[str, Any]] = {}
    origin: dict[int, set[str]] = {}
    for pool, label in zip(pools, ["mood"] * (2 if mood_ids else 0) + (["genre"] if genre_ids else [])):
        for item in pool:
            candidates.setdefault(item["id"], item)
            origin.setdefault(item["id"], set()).add(label)
    for seed, det in zip(profile.seeds, seeds):
        if not det or mood_ids:  # with an explicit mood, seeds only rank, they do not source
            continue
        for block in ("recommendations", "similar"):
            for item in (det.get(block) or {}).get("results", [])[:10]:
                candidates.setdefault(item["id"], item)
                origin.setdefault(item["id"], set()).add(f"like {seed.title}")

    pool_ids = [i for i in candidates if (kind, i) not in watched]
    if not req.include_owned:
        pool_ids = [i for i in pool_ids if (kind, i) not in owned]
    # Cheap pre-score on genres/rating, then fetch details for the best 40.
    pre = sorted(pool_ids, key=lambda i: -(candidates[i].get("vote_average") or 0) * (1 + len(origin.get(i, ()))))[:40]
    details = await asyncio.gather(*(cache.details(kind, i) for i in pre))

    recs: list[Recommendation] = []
    mood_set = {m.lower() for m in mood_names}
    for tmdb_id, det in zip(pre, details):
        if not det:
            continue
        ref = await tmdb.to_ref(kind, det, anime=req.kind == "anime")
        if ref.rating is not None and ref.rating < req.min_rating:
            continue
        if req.max_runtime and ref.runtime_minutes and ref.runtime_minutes > req.max_runtime:
            continue
        people = credits_people(det)
        score, why = taste_score(ref, people, profile)
        if mood_set:
            hits = [k for k in ref.keywords if k.lower() in mood_set]
            score += 0.25 * min(1.0, len(hits) / 2)
            if hits:
                why.insert(0, "mood: " + ", ".join(hits))
        if ref.rating:
            score *= 0.85 + 0.15 * min(1.0, ref.rating / 8.5)
        for label in sorted(origin.get(tmdb_id, set())):
            if label.startswith("like "):
                why.append(f"because you watched {label[5:]}")
                score += 0.05
                break
        ref.in_library = (kind, tmdb_id) in owned
        recs.append(Recommendation(item=ref, score=round(score, 3), why=why[:4]))
    recs.sort(key=lambda r: -r.score)
    return recs[: req.limit]
