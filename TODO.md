# TODO – Voice Agent Enhancements

## Immediate Ideas
- [ ] **Angle Hint** (✅ MVP added): Allow `--angle` to steer tone for all generated items.
- [ ] **Per-item Angles**: Accept `--angles-file angles.yaml` mapping item index → hint.
- [ ] **Selective Regeneration**: Generate posts only for user-picked items (`1`, `1,3`, `all`).
- [ ] **Interactive Selection**: Show scored items in terminal, prompt for selection before generation.
- [ ] **Improved Help Formatting**: Clean up `--help` output for better readability.

## Workflow & Debug
- [ ] **Separate Parsing/Scoring/Generation modules** clearly for easier debugging and testing.
- [ ] **Dry-run Mode**: Run full workflow without making GPT calls (use saved mock responses).
- [ ] **Logging Levels**: Add `--verbose` and `--quiet` modes.

## Output
- [ ] **Write to Dated Markdown File**: Already partially implemented; expand to include post meta (scores, hashtags, angle).
- [ ] **Tagging in Filenames**: Include strategy or model in output filename for easier history tracking.

## Feeds & Scoring
- [ ] **Dynamic Feed List**: Support multiple `.txt` feed files for different topics.
- [ ] **Refined Scoring Filters**: Use GPT to reject off-topic items before ranking.
- [ ] **Budget Guard per Step**: Separate budget caps for scoring and generation.

## Future Experiments
- [ ] **Auto-Post to LinkedIn** (with manual review stage).
- [ ] **Content Style Profiles**: Save/reuse style strategies for different audiences.
- [ ] **Integration with Slack or Email**: Deliver top stories + posts directly to a team channel.
- [ ] Add `todo done` command:
      - Allow marking TODO.md items as done by index or partial text match
      - Replace `- [ ]` with `- [x]` and keep timestamp intact
      - Optional: auto-move completed items to a "Done" section at the bottom
- [ ] Add `cache` subcommand:
      - `cache clear` → delete SEEN_CACHE_FILE (reset seen-links)
      - `cache stats` → print count of cached links + last 5 entries
      - `cache export <path>` → write current cache to a JSON file
      - Safety: ask for `--yes` confirmation before `clear`

---
