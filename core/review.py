# core/review.py
import os
import json, re, secrets
from datetime import datetime
from pathlib import Path
from core.io_utils import run_dir_for_today, save_json, write_text
from core.scoring import rank_items

def _base_output() -> str:
    # Always take OUTPUT_DIR from env; fallback to "output"
    return os.getenv("OUTPUT_DIR", "output")

def _short_token(n=6) -> str:
    return secrets.token_hex(n // 2)

def build_review(ranked: list[dict], max_items: int | None = None, min_total: int = 10) -> tuple[str, dict]:
    """Return (plain_text, index_map) and write both into today's run dir."""
    # Filter by total score first
    ranked = [it for it in ranked if it.get("total", 0) >= min_total]
    ranked = ranked[:max_items] if max_items else ranked

    # Use env-driven base output
    today_dir = run_dir_for_today(_base_output())
    token = _short_token()

    lines = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"[content_pipeline] Review - {date_str} (run {token})")
    lines.append("")
    lines.append("Reply with numbers (e.g., 1,3-5) to generate posts.")
    lines.append("")

    index_map = {"run_id": token, "items": []}

    for i, it in enumerate(ranked, 1):
        ttl = (it.get("title") or "").strip()
        why = (it.get("why_relevant") or "").strip()
        if len(ttl) > 120: ttl = ttl[:117] + "..."
        if len(why) > 240: why = why[:237] + "..."
        total = it.get("total", 0)
        url = it.get("link") or ""
        feed = it.get("feed") or ""
        lines.append(f"{i}) [{total}] {ttl}")
        if url:  lines.append(f"    {url}")
        if feed: lines.append(f"    Source: {feed}")
        if why:  lines.append(f"    Why: {why}")
        index_map["items"].append({"i": i, "id": it.get("id") or it.get("link") or "", "url": url})
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"

    write_text(body, today_dir / "scored_review.txt")
    save_json(index_map, today_dir / "index_map.json")
    return body, index_map

_sel_re = re.compile(r"^\s*[\d,\-\s]+\s*$")

def parse_selection_line(s: str) -> list[int]:
    if not s or not _sel_re.match(s): return []
    picks = set()
    for part in s.split(","):
        part = part.strip()
        if not part: continue
        if "-" in part:
            try:
                a, b = [int(x) for x in part.split("-", 1)]
                if a <= b:
                    for k in range(a, b+1): picks.add(k)
            except Exception:
                continue
        else:
            try:
                picks.add(int(part))
            except Exception:
                continue
    return sorted(picks)

def load_index_map() -> dict:
    # Read from the same env-driven base output dir
    p = run_dir_for_today(_base_output()) / "index_map.json"
    return json.loads(p.read_text(encoding="utf-8"))
