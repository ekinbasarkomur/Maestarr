"""User preferences that steer release judging and recommendations.

Stored as JSON next to the database. The agent can read and update them
("from now on prefer smaller files"), so they evolve with the conversation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    audio_languages: list[str] = Field(
        default_factory=lambda: ["Original"],
        description="Wanted audio languages in order; 'Original' means the title's original language.",
    )
    subtitle_languages: list[str] = Field(default_factory=lambda: ["English"])
    max_resolution: Literal[480, 720, 1080, 2160] = 2160
    min_resolution: Literal[480, 720, 1080, 2160] = 720
    allow_remux: bool = True
    prefer_season_packs: bool = True
    max_gb_per_episode: Optional[float] = Field(default=None, description="Soft cap per TV episode")
    max_gb_per_movie: Optional[float] = Field(default=None, description="Soft cap per movie")
    min_live_seeders: int = 2
    prefer_groups: list[str] = Field(default_factory=list)
    avoid_groups: list[str] = Field(default_factory=list)
    # Below this estimated video bitrate a 1080p release is considered starved.
    min_1080p_mbps: float = 2.5
    notes: str = Field(
        default="",
        description="Free-form taste/quality notes the judge should respect, written by the user.",
    )


def load_preferences(path: Path) -> Preferences:
    if path.exists():
        return Preferences.model_validate_json(path.read_text())
    return Preferences()


def save_preferences(path: Path, prefs: Preferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs.model_dump(), indent=2, ensure_ascii=False))
