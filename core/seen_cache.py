# seen_cache.py
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

def _cache_path() -> Path:
    return Path(os.getenv("SEEN_CACHE_FILE", "output/cache/seen_links.json"))

def load_seen_links() -> dict[str, str]:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_seen_links(cache: dict[str, str]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def filter_new_items(items: list[dict], ignore_cache: bool = False) -> list[dict]:
    """
    Returns only items with links not in the cache.
    Updates cache with newly seen links (unless ignore_cache=True).
    """
    if ignore_cache:
        return items

    seen = load_seen_links()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    new_items: list[dict] = []
    for it in items:
        link = (it.get("link") or "").strip()
        # if no link, fall back to title+feed as a weak identifier
        if not link:
            link = f"{it.get('feed','')}|{it.get('title','')}"
        if link and link not in seen:
            new_items.append(it)
            seen[link] = now_iso

    if new_items:
        save_seen_links(seen)
    return new_items
