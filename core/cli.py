# voice_agent.py
import argparse
import os
import textwrap
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from core.io_utils import run_dir_for_today, save_json, read_json, write_text, append_text
from core.parsing import fetch_items
from core.scoring import score_items, rank_items
from core.generation import draft_posts
from core.seen_cache import filter_new_items
from core.emailer import send_email

# ---------- helpers ----------

def load_feeds_list(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Feeds file not found: {path}")
    urls = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    if not urls:
        raise ValueError(f"No feed URLs found in {path}")
    return urls

def load_strategy(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Strategy file not found: {p}")
    # Do NOT strip() — keep headings/lists exactly as written
    return p.read_text(encoding="utf-8")

def to_markdown_digest(items: list[dict], ideas_text: str | None) -> str:
    lines = []
    lines.append(f"# Leadership Insight – Google Alerts Digest")
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n")
    if not items:
        lines.append("_No items found._")
    else:
        lines.append("## Items")
        for i, it in enumerate(items, 1):
            date_str = "n/a"
            if it.get("published_ts"):
                from datetime import datetime as dt
                date_str = dt.fromtimestamp(it["published_ts"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"\n### {i}. [{it['title']}]({it['link']})")
            lines.append(f"- **Source:** {it['feed']}")
            lines.append(f"- **Published:** {date_str}")
            if it.get("summary"):
                lines.append(f"- **Summary:** {it['summary']}")
    if ideas_text:
        lines.append("\n## Suggested LinkedIn Angles & Drafts\n")
        lines.append(ideas_text.strip())
    return "\n".join(lines) + "\n"

def parse_selection(selection: str | None, total_items: int, default_top_n: int) -> list[int]:
    """
    Convert selection to 1-based indices:
      - None  -> top N
      - "all" -> [1..total]
      - "1,3" -> [1,3]
      - "2"   -> [2]
    """
    if total_items <= 0:
        return []
    if not selection:
        return list(range(1, min(default_top_n, total_items) + 1))
    s = selection.strip().lower()
    if s == "all":
        return list(range(1, total_items + 1))
    picks = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            i = int(part)
            if 1 <= i <= total_items:
                picks.add(i)
        except ValueError:
            pass
    return sorted(picks)

# ---------- commands ----------

def cmd_fetch(args):
    feeds_file = os.getenv("FEEDS_FILE", "feeds.txt")
    feeds = load_feeds_list(feeds_file)
    items = fetch_items(feeds)
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    raw_path = outdir / "raw_items.json"
    save_json(items, raw_path)
    print(f"Fetched {len(items)} items → {raw_path}")

def cmd_score(args):
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    raw_path = outdir / "raw_items.json"
    items = read_json(raw_path)
    strategy = load_strategy(os.getenv("STRATEGY_FILE", "strategy.md"))
    model = args.model_scoring or os.getenv("MODEL_SCORING", "gpt-4o-mini")
    scored = score_items(items, strategy, model=model)
    scored_path = outdir / "scored_items.json"
    save_json(scored, scored_path)
    print(f"Scored {len(scored)} items → {scored_path}")

    # Optional budget echo
    try:
        from usage_guard import BudgetGuard
        g = BudgetGuard()
        print(f"[Budget] Spent today: ${g.spent:.4f} / ${g.max_daily:.2f}")
    except Exception:
        pass

def cmd_list(args):
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    scored_path = outdir / "scored_items.json"
    scored = read_json(scored_path)
    ranked = rank_items(scored)
    if not ranked:
        print("No scored items. Run: python voice_agent.py score")
        return
    for i, it in enumerate(ranked, 1):
        total = it.get("total", 0)
        title = it.get("title", "")[:120]
        why = it.get("why_relevant", "")
        if len(why) > 160:
            why = why[:157] + "..."
        print(f"{i}) {title}  [total={total}]")
        if why:
            print(f"    why: {why}")

def cmd_generate(args):
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    scored_path = outdir / "scored_items.json"
    scored = read_json(scored_path)
    ranked = rank_items(scored)
    if not ranked:
        print("No scored items. Run: python voice_agent.py score")
        return

    top_n = args.top_n or int(os.getenv("TOP_N", "3"))
    picks = parse_selection(args.selection, len(ranked), top_n)
    if not picks:
        print("No valid selection. Try `python voice_agent.py list` first.")
        return

    chosen_scored = [ranked[i-1] for i in picks]
    strategy = load_strategy(os.getenv("STRATEGY_FILE", "strategy.md"))
    model = args.model_generation or os.getenv("MODEL_GENERATION", "gpt-4o-mini")
    ideas_md = draft_posts(chosen_scored, strategy, model=model, angle_hint=args.angle)


    # Build digest from raw items (only for chosen links)
    raw_items = read_json(outdir / "raw_items.json")
    chosen_links = {c["link"] for c in chosen_scored}
    filtered = [it for it in raw_items if it["link"] in chosen_links]
    digest = to_markdown_digest(filtered, ideas_md)

    # Write daily MD (append if exists)
    prefix = os.getenv("MARKDOWN_PREFIX", "voice_agent_")
    md_path = Path(os.getenv("OUTPUT_DIR", "output")) / f"{prefix}{datetime.now().strftime('%Y-%m-%d')}.md"
    if md_path.exists():
        append_text("\n---\n\n", md_path)
        append_text(digest, md_path)
    else:
        write_text(digest, md_path)

    print(f"Wrote Markdown digest for picks {picks} → {md_path}")
    #
    if args.email:
        from core.emailer import send_email
        subject = f"Digest – {datetime.now().strftime('%Y-%m-%d')}"
        body = "Attached: daily digest with selected posts.\n"
        try:
            send_email(subject, body, attachments=[str(md_path)])
            print("Emailed digest to configured recipients.")
        except Exception as e:
            print(f"[EMAIL] Error: {e}")


    # Optional budget echo
    try:
        from usage_guard import BudgetGuard
        g = BudgetGuard()
        print(f"[Budget] Spent today: ${g.spent:.4f} / ${g.max_daily:.2f}")
    except Exception:
        pass

# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""
            Voice Agent – Workflow & Parameters
            -----------------------------------

            Typical run order:
                1. fetch     – Fetch RSS/Atom feed items and save them as JSON.
                2. score     – Send parsed items + strategy to GPT for scoring/ranking.
                3. list      – Show ranked items with numeric IDs.
                4. generate  – Generate LinkedIn-style posts for selected items.

            Examples:
                python voice_agent.py fetch
                python voice_agent.py score --model-scoring gpt-4o-mini
                python voice_agent.py list
                python voice_agent.py generate            # defaults to top-N from .env
                python voice_agent.py generate 1          # just item #1
                python voice_agent.py generate 1 --angle "Focus on practical voice coaching takeaways"
                python voice_agent.py generate 1,3        # items #1 and #3
                python voice_agent.py generate 1,3 --angle "Women in leadership implications for ACT agencies"
                python voice_agent.py generate all        # all ranked items (careful: cost)


            Notes:
                • Selection grammar for `generate`:
                    - none     → top N (from --top-n or TOP_N in .env)
                    - "all"    → all items
                    - "1,3"    → items #1 and #3
                    - "2"      → item #2
                • Budget guard:
                    - Set MAX_DAILY_COST_USD in .env to cap daily spend.
                    - We track usage per day in output/usage/.
        """),
        formatter_class=argparse.RawTextHelpFormatter
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Fetch and store RSS/Atom feed items")
    p_fetch.add_argument("--ignore-cache", action="store_true",
                     help="Do not use seen-links cache; fetch/save all items (may cause duplicates).")
    p_fetch.set_defaults(func=cmd_fetch)

    p_score = sub.add_parser("score", help="Score parsed items using GPT")
    p_score.add_argument("--model-scoring", help="OpenAI model for scoring (default: from .env MODEL_SCORING)")
    p_score.set_defaults(func=cmd_score)

    p_list = sub.add_parser("list", help="List ranked items with IDs")
    p_list.set_defaults(func=cmd_list)

    p_gen = sub.add_parser("generate", help="Generate LinkedIn posts from scored items")
    p_gen.add_argument("selection", nargs="?", default=None,
                       help="Selection: e.g. '1', '1,3', or 'all'. Omit to use --top-n / TOP_N.")
    p_gen.add_argument("--top-n", type=int, help="Number of top items when no selection is given (default: TOP_N)")
    p_gen.add_argument("--model-generation", help="OpenAI model for generation (default: from .env MODEL_GENERATION)")
    p_gen.add_argument("--angle", help="Angle hint applied to all selected items (e.g. 'focus on voice coaching takeaways').")
    p_gen.add_argument("--email", action="store_true",
                   help="Email the Markdown digest to EMAIL_TO after generating.")

    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
