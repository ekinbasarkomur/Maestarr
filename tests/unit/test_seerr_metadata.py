"""Seerr stands in for TMDB: requests are mapped, answers come back in TMDB's shape."""

from __future__ import annotations

import httpx
import respx

from maestarr.clients.seerr import SeerrMetadataClient

BASE = "http://seerr:5055/api/v1"


@respx.mock
async def test_discover_maps_tmdb_filters_to_seerr_names():
    route = respx.get(f"{BASE}/discover/movies").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1, "title": "X", "posterPath": "/x.jpg", "genreIds": [18]}]})
    )
    client = SeerrMetadataClient("http://seerr:5055", "k")
    hits = await client.discover("movie", with_genres="18|35", **{"vote_average.gte": 7, "primary_release_date.gte": "2000-01-01"})
    params = route.calls.last.request.url.params
    assert params["genre"] == "18,35" and params["voteAverageGte"] == "7" and params["primaryReleaseDateGte"] == "2000-01-01"
    assert route.calls.last.request.headers["X-Api-Key"] == "k"
    assert hits == [{"id": 1, "title": "X", "poster_path": "/x.jpg", "genre_ids": [18]}]
    await client.aclose()


@respx.mock
async def test_search_keeps_the_asked_kind_and_year():
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json={"results": [
        {"id": 1, "mediaType": "movie", "title": "Arrival", "releaseDate": "2016-11-10"},
        {"id": 2, "mediaType": "movie", "title": "The Arrival", "releaseDate": "1996-05-31"},
        {"id": 3, "mediaType": "tv", "name": "Arrival"},
    ]}))
    client = SeerrMetadataClient("http://seerr:5055", "k")
    assert [h["id"] for h in await client.search("movie", "arrival", 2016)] == [1]
    assert [h["id"] for h in await client.search("tv", "arrival")] == [3]
    await client.aclose()
