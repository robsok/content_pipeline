# usage_guard.py
import json
import os
from datetime import datetime
from pathlib import Path

# Default per-1K token pricing (USD). Override via env if needed.
PRICING = {
    "gpt-4o-mini": {
        "in": float(os.getenv("PRICE_GPT4O_MINI_IN", "0.00015")),
        "out": float(os.getenv("PRICE_GPT4O_MINI_OUT", "0.0006")),
    },
    "gpt-4o": {
        "in": float(os.getenv("PRICE_GPT4O_IN", "0.005")),
        "out": float(os.getenv("PRICE_GPT4O_OUT", "0.015")),
    },
    # Add more models here if you use them
}

def _usage_dir(base="output"):
    p = Path(base) / "usage"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _today_path(base="output"):
    return _usage_dir(base) / f"usage_{datetime.now().strftime('%Y-%m-%d')}.json"

class BudgetGuard:
    def __init__(self, max_daily_usd: float | None = None, base_output: str = "output"):
        self.base_output = base_output
        self.max_daily = float(os.getenv("MAX_DAILY_COST_USD", "0.50")) if max_daily_usd is None else max_daily_usd
        self.path = _today_path(base_output)
        self.state = {"spent_usd": 0.0, "entries": []}
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass  # start fresh if file is corrupt

    @property
    def spent(self) -> float:
        return float(self.state.get("spent_usd", 0.0))

    def can_spend_more(self) -> bool:
        return self.spent < self.max_daily

    def add_response(self, model: str, prompt_tokens: int, completion_tokens: int, meta: dict | None = None):
        """Record usage & cost from a single API call."""
        rates = PRICING.get(model)
        if not rates:
            # Fallback to 4o-mini rates if unknown model to avoid surprise costs
            rates = PRICING["gpt-4o-mini"]

        cost_in = (prompt_tokens / 1000.0) * rates["in"]
        cost_out = (completion_tokens / 1000.0) * rates["out"]
        total = cost_in + cost_out

        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_in_usd": round(cost_in, 6),
            "cost_out_usd": round(cost_out, 6),
            "cost_total_usd": round(total, 6),
            "meta": meta or {},
        }
        self.state["entries"].append(entry)
        self.state["spent_usd"] = round(self.spent + total, 6)
        self._flush()

    # usage_guard.py
    def _flush(self):
        try:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            tmp.replace(self.path)  # atomic on same filesystem
        except Exception:
            pass  # best-effort; never break the pipeline on usage logging


