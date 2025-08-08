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

def draft_posts(scored_top: list[dict], strategy_text: str, model: Optional[str] = None, angle_hint: Optional[str] | None = None) -> str:
    env_model = os.getenv("MODEL_GENERATION") or "gpt-4o-mini"
    model = model or env_model

    guard = BudgetGuard()
    if not guard.can_spend_more():
        raise RuntimeError(f"Daily cost limit reached (${guard.spent} / ${guard.max_daily}). Aborting generation.")

    brief = [{"title": it["title"], "link": it["link"]} for it in scored_top]

    hint_block = f"\nAngle hint (apply across items): {angle_hint}\n" if angle_hint else ""

    user_prompt = f"""
Strategy (tone, audience, rules):
{strategy_text}
{hint_block}
For each item, produce:
1) One-line angle/headline (<= 90 chars).
2) A 120–160 word LinkedIn post in Australian English.
   - Concrete “so what” for our audience.
   - No emojis. Avoid fluff. Don’t overclaim—stick to the item.
3) 3–5 relevant hashtags.
4) A one-line 'Why this matters' note to the author (not for posting).

Items (JSON):
{json.dumps(brief, ensure_ascii=False)}

Return as Markdown, with sections per item:
## {{title}}
**Angle:** ...
**Post:** ...
**Hashtags:** #...
**Why this matters (note to me):** ...
"""

    client = _client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.7,
        messages=[
            {"role": "system", "content": "You craft credible, concise LinkedIn content. No emojis."},
            {"role": "user", "content": user_prompt},
        ],
    )

    # Record usage cost (SDK object-safe)
    try:
        u = getattr(resp, "usage", None)
        pt = int(getattr(u, "prompt_tokens", 0) or 0)
        ct = int(getattr(u, "completion_tokens", 0) or 0)
        guard.add_response(model, pt, ct, meta={"stage": "generation", "items": len(scored_top)})
        if not guard.can_spend_more():
            print(f"[Budget] Daily limit now reached (${guard.spent} / ${guard.max_daily}).")
    except Exception as e:
        print(f"[WARN] Could not record usage: {e}")

    content = resp.choices[0].message.content or ""
    return content
