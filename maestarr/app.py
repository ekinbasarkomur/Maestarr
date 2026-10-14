"""FastAPI application for maestarr.

Started via `maestarr serve`, which runs uvicorn against
the `app` object defined here.
"""

from __future__ import annotations

from fastapi import FastAPI

from maestarr import __version__

app = FastAPI(
    title="maestarr",
    description="Maestarr — an AI maestro for your *arr stack: taste-aware recommendations, release judging with live swarm data, and chat control of Sonarr, Radarr, Prowlarr and qBittorrent",
    version=__version__,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}
