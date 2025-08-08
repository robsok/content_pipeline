import json
import os
from openai import OpenAI
from typing import Optional
from core.usage_guard import BudgetGuard 

def _client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    return OpenAI(api_key=key)

def score_items(items: list[dict], strategy_text: str, model: Optional[str] = None) -> list[dict]:
    env_model = os.getenv("MODEL_SCORING") or "gpt-4o-mini"
    model = model or env_model

    # NEW: guard init + pre-check
    guard = BudgetGuard()
    if not guard.can_spend_more():
        raise RuntimeError(f"Daily cost limit reached (${guard.spent} / ${guard.max_daily}). Aborting scoring.")

    brief = []
    for it in items:
        brief.append({
            "title": it["title"],
            "link": it["link"],
            "summary": it["summary"][:600],
            "published_ts": it["published_ts"],
            "feed": it["feed"],
        })

    schema_hint = """Return strict JSON only:
{"items":[{"title":"...","link":"...","why_relevant":"...",
"scores":{"relevance":0,"locality":0,"novelty":0,"actionability":0,"timeliness":0},
"total":0}]}"""

    user_prompt = f"""
Strategy:
{strategy_text}

Score each item using this rubric:
- relevance (0-5): matches strategy (voice, leadership, presence, org dev, women in leadership, ACT/Canberra, innovation).
- locality (0-3): ACT/Canberra preferred; otherwise Australia.
- novelty (0-3): new angle, not repetitive.
- actionability (0-3): can we say something practical for our audience?
- timeliness (0-2): prefer last 7 days.
Explain briefly 'why_relevant'.

Items:
{json.dumps(brief, ensure_ascii=False)}

{schema_hint}
"""

    client = _client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "Be precise. Output valid JSON only."},
            {"role": "user", "content": user_prompt},
        ],
    )

    # Record usage cost (SDK object-safe)
    try:
        u = getattr(resp, "usage", None)
        pt = int(getattr(u, "prompt_tokens", 0) or 0)
        ct = int(getattr(u, "completion_tokens", 0) or 0)
        guard.add_response(model, pt, ct, meta={"stage": "scoring", "items": len(items)})
        if not guard.can_spend_more():
            print(f"[Budget] Daily limit now reached (${guard.spent} / ${guard.max_daily}).")
    except Exception as e:
        print(f"[WARN] Could not record usage: {e}")


    content = resp.choices[0].message.content
    if content is None:
        raise RuntimeError("Model returned no content for scoring")
    raw = content.strip()
    data = json.loads(raw)  # raise if invalid -> easier debugging
    return data["items"]

def rank_items(scored: list[dict]) -> list[dict]:
    # Sort by total desc; keep stable order otherwise
    return sorted(scored, key=lambda x: x.get("total", 0), reverse=True)
