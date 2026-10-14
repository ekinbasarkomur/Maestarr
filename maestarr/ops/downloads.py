"""Download-client operations (qBittorrent) and preferences."""

from __future__ import annotations

from typing import Any, Optional

from maestarr.domain import GiB
from maestarr.preferences import Preferences
from maestarr.services import Services

_ACTIVE = {"downloading", "stalledDL", "metaDL", "forcedDL", "queuedDL", "checkingDL", "allocating"}


async def torrents(svc: Services, *, category: Optional[str] = None, only_active: bool = False, limit: int = 40) -> dict[str, Any]:
    qbit = svc.need_qbittorrent()
    items = await qbit.torrents(category=category)
    info = await qbit.transfer_info()
    rows = []
    for t in sorted(items, key=lambda t: -t.get("added_on", 0)):
        if only_active and t.get("state") not in _ACTIVE:
            continue
        rows.append(
            {
                "hash": t["hash"],
                "name": t["name"],
                "category": t.get("category"),
                "state": t.get("state"),
                "progress_pct": round(100 * t.get("progress", 0), 1),
                "size_gb": round((t.get("size") or 0) / GiB, 2),
                "down_mbps": round((t.get("dlspeed") or 0) * 8 / 1e6, 1),
                "seeds_connected": t.get("num_seeds"),
                "seeds_in_swarm": t.get("num_complete"),
                "eta_min": round(t["eta"] / 60) if t.get("eta") and t["eta"] < 8640000 else None,
                "ratio": round(t.get("ratio", 0), 2),
            }
        )
    return {
        "download_mbps": round((info.get("dl_info_speed") or 0) * 8 / 1e6, 1),
        "upload_mbps": round((info.get("up_info_speed") or 0) * 8 / 1e6, 1),
        "connection": info.get("connection_status"),
        "torrents": rows[:limit],
        "total": len(rows),
    }


async def torrent_files(svc: Services, info_hash: str, limit: int = 80) -> dict[str, Any]:
    files = await svc.need_qbittorrent().files(info_hash)
    return {
        "files": [
            {"index": f["index"], "name": f["name"], "size_gb": round(f["size"] / GiB, 2),
             "selected": f.get("priority", 1) > 0, "progress_pct": round(100 * f.get("progress", 0))}
            for f in files[:limit]
        ],
        "total_files": len(files),
        "selected_gb": round(sum(f["size"] for f in files if f.get("priority", 1) > 0) / GiB, 2),
    }


async def remove_torrents(svc: Services, hashes: list[str], *, delete_files: bool) -> dict[str, Any]:
    qbit = svc.need_qbittorrent()
    found = await qbit.torrents(hashes=hashes)
    if not found:
        return {"removed": 0, "reason": "no such torrents"}
    await qbit.delete(*[t["hash"] for t in found], delete_files=delete_files)
    return {
        "removed": len(found),
        "deleted_data": delete_files,
        "names": [t["name"] for t in found],
        "freed_gb": round(sum(t.get("size", 0) for t in found) / GiB, 2) if delete_files else 0,
    }


def get_preferences(svc: Services) -> dict[str, Any]:
    return svc.preferences().model_dump()


def update_preferences(svc: Services, changes: dict[str, Any]) -> dict[str, Any]:
    current = svc.preferences().model_dump()
    unknown = [k for k in changes if k not in current]
    current.update({k: v for k, v in changes.items() if k in current})
    prefs = Preferences.model_validate(current)
    svc.save_preferences(prefs)
    return {"saved": prefs.model_dump(), "ignored_unknown_keys": unknown}
