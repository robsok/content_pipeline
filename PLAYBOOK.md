# Agent Duplication & Setup Playbook

## Quick-start (copy + configure)
1. **Copy the folder**
    ```bash
    cp -r ~/Agents/voice_agent ~/Agents/<new_agent_name>
    cd ~/Agents/<new_agent_name>
    ```

2. **Rename the entry file (optional)**
    ```bash
    mv voice_agent.py <new_agent_name>.py
    ```
    *(If you rename it, update your run commands accordingly.)*

3. **Create a fresh venv (safe, even if you copied `.venv`)**
    ```bash
    deactivate 2>/dev/null || true
    rm -rf .venv
    uv venv .venv
    source .venv/bin/activate
    uv pip install --python .venv/bin/python -r requirements.txt
    ```

4. **Update config files**
    - `feeds.txt` → new Google Alerts RSS URLs (one per line).
    - `strategy.md` → new audience/themes/exclusions.
    - `.env` → keep the same model/budget or change as needed (see template below).

5. **Smoke test**
    ```bash
    python <new_agent_name>.py fetch
    python <new_agent_name>.py score
    python <new_agent_name>.py list
    python <new_agent_name>.py generate 1 --angle "Trial angle"
    ```

6. **Archive check**  
   Confirm `output/runs/YYYY-MM-DD/` and `output/<prefix>_YYYY-MM-DD.md` are created in **this** agent folder.

---

## `.env` template (per-agent)
```env
OPENAI_API_KEY=sk-...            # OK to reuse; or create a new restricted key per agent
FEEDS_FILE=feeds.txt
STRATEGY_FILE=strategy.md
OUTPUT_DIR=output
MARKDOWN_PREFIX=<new_agent_name>_
TOP_N=3
MODEL_SCORING=gpt-4o-mini
MODEL_GENERATION=gpt-4o-mini
MAX_DAILY_COST_USD=0.50          # per-agent budget guard

# Optional: tweak pricing if models change
# PRICE_GPT4O_MINI_IN=0.00015
# PRICE_GPT4O_MINI_OUT=0.0006
