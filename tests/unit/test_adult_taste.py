"""Adult shelves: scoring and the separate impressions table (no real data)."""

from maestarr.taste.adult import AdultFeedbackStore, score

PROFILE = {
    "performers": {"fav": ["A", 4.0, "FEMALE"], "lib": ["B", 1.0, "FEMALE"], "man": ["M", 6.0, "MALE"]},
    "studios": {"s1": ["Studio One", 4.0]},
    "tags": {"Theme": 3.0, "Other": 1.0},
    "themes": ["Theme"],
    "favourite_performers": ["fav"],
    "favourite_studios": ["s1"],
    "avoid": {},
}


def scene(performers, studio=None, tags=()):
    return {"id": "x", "performer_ids": performers, "studio_id": studio, "tags": list(tags)}


def test_favourites_rank_first_and_explain_themselves():
    fav, why = score(scene(["fav"], "s1", ["Theme"]), PROFILE)
    other, _ = score(scene(["lib"]), PROFILE)
    assert fav > other
    assert why[0] == "With A, one of your favourites"
    assert why[1] == "From Studio One, a favourite studio"


def test_men_count_less_and_are_not_named_as_the_reason():
    man, why = score(scene(["man"]), PROFILE)
    woman, _ = score(scene(["fav"]), PROFILE)
    assert man < woman
    assert not any("M," in w for w in why)


def test_avoided_tags_pull_a_scene_down():
    base, _ = score(scene(["fav"], tags=["Theme"]), PROFILE)
    avoided, _ = score(scene(["fav"], tags=["Theme"]), {**PROFILE, "avoid": {"Theme": 3}})
    assert avoided < base


async def test_not_for_me_hides_a_scene_and_remembers_its_themes(tmp_path):
    store = AdultFeedbackStore(tmp_path / "a.sqlite3")
    await store.shown([("s-1", "One"), ("s-2", "Two")], now=1000.0)
    await store.react({"id": "s-2", "title": "Two", "performer_ids": ["p"], "performers": ["P"],
                       "studio_id": "st", "studio": "St", "tags": ["T"]}, "dismiss", now=1000.0)
    state = await store.state(now=1000.0 + 13 * 3600)
    assert "s-2" in state.hidden
    assert state.disliked[0]["tags"] == ["T"]
    assert state.disliked[0]["studio"] == ["st", "St"]
