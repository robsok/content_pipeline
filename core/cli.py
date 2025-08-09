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
from core.usage_guard import BudgetGuard
from core.review import build_review, load_index_map, parse_selection_line
from core.imap_poll import find_latest_selection


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
        subject = f"Digest – {datetime.now().strftime('%Y-%m-%d')}"
        # Send the digest inline as plain text
        body = digest  # plain text; Markdown characters are fine in text/plain
        try:
            send_email(subject, body)  # no attachments
            print("Emailed digest (inline) to configured recipients.")
        except Exception:
            print("[EMAIL] Failed to send inline digest; see traceback above.")
            raise


    # Optional budget echo
    try:
        from usage_guard import BudgetGuard
        g = BudgetGuard()
        print(f"[Budget] Spent today: ${g.spent:.4f} / ${g.max_daily:.2f}")
    except Exception:
        pass


def cmd_review_email(args):
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    scored = read_json(outdir / "scored_items.json")
    ranked = rank_items(scored)
    if not ranked:
        print("No scored items for today. Run: python pipeline.py <agent> score")
        return

    min_total = args.min_total or int(os.getenv("MIN_TOTAL", "10"))

    body, index_map = build_review(
        ranked,
        max_items=args.max_items,
        min_total=min_total
    )
    subject = f"[content_pipeline] Review - {datetime.now().strftime('%Y-%m-%d')} (run {index_map['run_id']})"

    try:
        send_email(subject, body)
        print(f"Sent review email for {len(index_map['items'])} items. See: {outdir/'scored_review.txt'}")
    except Exception:
        print("[EMAIL] Failed to send review email; see traceback above.")
        raise

def cmd_review_poll(args):
    # Idempotence marker
    outdir = run_dir_for_today(os.getenv("OUTPUT_DIR", "output"))
    marker = outdir / "review_processed.json"

    if args.reset and marker.exists():
        marker.unlink(missing_ok=True)
        print("Reset: cleared processed marker for today.")

    if marker.exists() and not args.force:
        print("Already processed a reply for today. Use --force to override, or --reset to clear.")
        return

    # Load map built by review-email
    index_map = load_index_map()
    run_id = index_map.get("run_id") or ""
    sel_line, uid, frm = find_latest_selection(run_id)
    if not sel_line:
        print("No valid reply found yet. Will try again later.")
        return

    picks = parse_selection_line(sel_line)
    if not picks:
        print(f"Reply found (from {frm}) but no valid selection in line: {sel_line!r}")
        return

    # Reuse the existing generate flow programmatically
    # Construct argparse-style namespace for cmd_generate
    gen_args = argparse.Namespace(
        selection=",".join(str(i) for i in picks),
        top_n=None,
        model_generation=None,
        angle=args.angle,
        email=args.email_on_generate,
    )
    print(f"Reply from {frm} → selection {picks}. Triggering generate...")
    cmd_generate(gen_args)

    # Write processed marker
    from core.io_utils import save_json
    save_json(
        {
            "run_id": run_id,
            "selection": picks,
            "email_uid": uid,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "from": frm,
        },
        marker,
    )
    print(f"Marked processed → {marker}")

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
                python pipeline.py <agent> fetch
                python pipeline.py <agent> score --model-scoring gpt-4o-mini
                python pipeline.py <agent> list
                python pipeline.py <agent> generate            # defaults to top-N from .env
                python pipeline.py <agent> generate 1          # just item #1
                python pipeline.py <agent> generate 1 --angle "Focus on practical voice coaching takeaways"
                python pipeline.py <agent> generate 1,3        # items #1 and #3
                python pipeline.py <agent> generate 1,3 --angle "Women in leadership implications for ACT agencies"
                python pipeline.py <agent> generate all        # all ranked items (careful: cost)


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
    p_gen.add_argument(
        "--email",
        action="store_true",
        help="Email the digest inline as plain text to EMAIL_TO after generating."
    )
    p_rev_email = sub.add_parser("review-email", help="Email a numbered plain-text list of today's scored items")
    p_rev_email.add_argument("--max-items", type=int, default=int(os.getenv("REVIEW_MAX_ITEMS", "30")),
                             help="Limit the number of items listed (default: 30)")
    p_rev_email.add_argument("--min-total", type=int, help="Only include items with total score >= this (default: MIN_TOTAL or 10)")

    p_rev_email.set_defaults(func=cmd_review_email)

    p_rev_poll = sub.add_parser("review-poll", help="Poll mailbox for a reply and trigger generate")
    p_rev_poll.add_argument("--force", action="store_true",
                            help="Ignore processed marker and run anyway")
    p_rev_poll.add_argument("--reset", action="store_true",
                            help="Delete processed marker for today before polling")
    p_rev_poll.add_argument("--angle", help="Angle hint applied when generating from a reply")
    p_rev_poll.add_argument("--email-on-generate", action="store_true",
                            help="If set, pass --email to generate after a valid reply")
    p_rev_poll.set_defaults(func=cmd_review_poll)



    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
