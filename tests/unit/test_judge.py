"""Release judge: content analysis, scoring, verdicts — on real-world file names."""

from __future__ import annotations

from maestarr.domain import ReleaseAssessment, ReleaseCandidate, SwarmStats, TorrentContents, TorrentFile
from maestarr.judge.contents import analyze, select_paths
from maestarr.judge.judge import JudgeRequest, rules_verdict
from maestarr.judge.score import score_assessment
from maestarr.preferences import Preferences

GB = 1024**3
ROOT = "BATMAN The Animated Series (1992-1999) - COMPLETE Season 1-6, TV S01-S06 and 2 Movies - 1080p BluRay x264"


def btas_pack() -> TorrentContents:
    files = []
    for ep in range(1, 11):
        files.append(TorrentFile(path=f"{ROOT}/Season 3 (1994)/Batman T.A.S - S03 E{ep:02d} - Title (1080p - BluRay).mp4", size=int(0.28 * GB)))
        files.append(TorrentFile(path=f"{ROOT}/Season 3 (1994)/Batman T.A.S - S03 E{ep:02d} - Title (1080p - BluRay).srt", size=20_000))
    for ep in range(1, 14):
        files.append(TorrentFile(path=f"{ROOT}/Season 5 (1997)/The New Batman Adventures - S01 E{ep:02d} - X (1080p - BluRay).mp4", size=int(0.24 * GB)))
    files.append(TorrentFile(path=f"{ROOT}/[TGx]Downloaded from torrentgalaxy.to .txt", size=585))
    return TorrentContents(name=ROOT, info_hash="0b5543f0c16f2c0c957d20ff884b57ba22908aa9", files=files)


WANTED = {(3, e) for e in range(1, 11)}
TITLES = ["Batman: The Animated Series"]


def test_analysis_finds_coverage_foreign_show_and_junk():
    report = analyze(btas_pack(), wanted_titles=TITLES, wanted_episodes=WANTED, runtime_minutes=22)
    assert report.wanted_episodes_covered == 10 and report.wanted_episodes_total == 10
    assert report.foreign_titles == ["The New Batman Adventures"]
    assert len(report.junk_files) == 1 and report.subtitle_files == 10
    assert report.video_files == 23
    assert report.est_bitrate_mbps is not None and 1 < report.est_bitrate_mbps < 3


def test_selection_keeps_only_the_wanted_show():
    paths = select_paths(btas_pack(), wanted_titles=TITLES, wanted_episodes=WANTED)
    assert len(paths) == 20  # 10 videos + 10 subtitles
    assert all("Season 3" in p for p in paths)


def test_executables_block_a_release():
    contents = TorrentContents(
        name="Show.S06E03.1080p.WEB-DL",
        files=[TorrentFile(path="Show.S06E03.1080p.WEB-DL/Show.S06E03.1080p.WEB-DL.exe", size=2_000_000)],
    )
    candidate = ReleaseCandidate(app="sonarr", guid="g", indexer_id=1, title=contents.name, size=2_000_000, resolution=1080)
    a = ReleaseAssessment(candidate=candidate, contents=contents, report=analyze(contents, wanted_titles=["Show"]))
    score_assessment(a, Preferences())
    assert any("executables" in b for b in a.blockers)
    assert any("no video" in b for b in a.blockers)


def _candidate(guid: str, **kw) -> ReleaseCandidate:
    base = dict(app="sonarr", guid=guid, indexer_id=1, title=guid, size=3 * GB, resolution=1080)
    base.update(kw)
    return ReleaseCandidate(**base)


def test_dead_swarm_blocks_and_live_seeders_win():
    dead = ReleaseAssessment(candidate=_candidate("dead", seeders=58, custom_format_score=500),
                             swarm=SwarmStats(seeders=0, method="scrape", trackers_answered=3))
    alive = ReleaseAssessment(candidate=_candidate("alive", seeders=5),
                              swarm=SwarmStats(seeders=40, method="scrape", trackers_answered=3))
    for a in (dead, alive):
        score_assessment(a, Preferences())
    assert dead.blockers == ["no live seeders right now"]
    verdict = rules_verdict([dead, alive], JudgeRequest(subject="x", candidates=[]))
    assert verdict.chosen_guid == "alive"


def test_resolution_limit_and_disk_space():
    big = ReleaseAssessment(candidate=_candidate("uhd", resolution=2160, size=80 * GB))
    score_assessment(big, Preferences(max_resolution=1080), free_bytes=100 * GB, min_free_bytes=50 * GB)
    assert any("above the 1080p limit" in b for b in big.blockers)
    assert any("only 100 GB is free" in b for b in big.blockers)


def test_no_acceptable_release_gives_null_verdict():
    blocked = ReleaseAssessment(candidate=_candidate("b"), blockers=["no live seeders right now"])
    verdict = rules_verdict([blocked], JudgeRequest(subject="x", candidates=[]))
    assert verdict.chosen_guid is None and "No acceptable release" in verdict.rationale
