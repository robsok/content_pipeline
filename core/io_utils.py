import json
import os
from datetime import datetime
from pathlib import Path

def ensure_dir(path: str | Path):
    Path(path).mkdir(parents=True, exist_ok=True)

def run_dir_for_today(base: str = "output") -> Path:
    d = Path(base) / "runs" / datetime.now().strftime("%Y-%m-%d")
    ensure_dir(d)
    return d

def save_json(obj, path: str | Path):
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def read_json(path: str | Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_text(text: str, path: str | Path):
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)

def append_text(text: str, path: str | Path):
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "a", encoding="utf-8") as f:
        f.write(text)
