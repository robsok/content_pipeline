# pipeline.py
import os, sys
from pathlib import Path
from dotenv import load_dotenv
from core.cli import main as core_main
import os

load_dotenv()

main_dir = os.environ.get("MAIN_DIR", "").strip()

def _expand_main_dir_env():
    """Expand $MAIN_DIR occurrences in a few key env vars after dotenv load."""
    main_dir = os.environ.get("MAIN_DIR", "").strip()
    if not main_dir:
        return
    for key in ("FEEDS_FILE", "STRATEGY_FILE", "OUTPUT_DIR", "SEEN_CACHE_FILE", "MARKDOWN_PREFIX"):
        val = os.environ.get(key)
        if not val:
            continue
        os.environ[key] = val.replace("$MAIN_DIR", main_dir)


def load_agent_env(agent_dir: Path):
    env_path = agent_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    # If MAIN_DIR isn't set, use this agent_dir by default
    os.environ.setdefault("MAIN_DIR", str(agent_dir))
    # Expand $MAIN_DIR placeholders (if present)
    _expand_main_dir_env()
    # Point core at this agent's config
    os.environ.setdefault("FEEDS_FILE", str(agent_dir / "feeds.txt"))
    os.environ.setdefault("STRATEGY_FILE", str(agent_dir / "strategy.md"))
    os.environ.setdefault("OUTPUT_DIR", str(agent_dir / "output"))
    # Optional: prefix per agent
    if "MARKDOWN_PREFIX" not in os.environ:
        os.environ["MARKDOWN_PREFIX"] = f"{agent_dir.name}_"

def main():
    # inside main()
    if len(sys.argv) < 3 or sys.argv[1] in ("--help","-h","help"):
        # list agents for convenience
        agents_dir = Path("agents")
        found = [p.name for p in agents_dir.iterdir() if p.is_dir()]
        print("Usage: python pipeline.py <agent_name> <command> [args...]")
        print("Commands: fetch | score | list | generate")
        print("\nExamples:")
        print("  python pipeline.py voice_act fetch")
        print("  python pipeline.py voice_act score --model-scoring gpt-4o-mini")
        print("  python pipeline.py voice_act generate 1,3 --angle \"Women in leadership lens\" --email")
        print("  python pipeline.py voice_act list")
        print("\nAvailable agents:", ", ".join(found) if found else "(none)")
        sys.exit(0)


    agent_name = sys.argv[1]
    agent_dir = Path("agents") / agent_name
    if not agent_dir.exists():
        print(f"Agent not found: {agent_dir}")
        sys.exit(1)

    load_agent_env(agent_dir)

    # Shift args so core CLI sees <command> [args...]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    core_main()

if __name__ == "__main__":
    main()
