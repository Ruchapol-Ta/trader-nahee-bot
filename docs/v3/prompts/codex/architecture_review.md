# Codex Prompt: V3 Architecture Review

```text
Review the Signal Bot V3 foundation as a strict senior engineer.

Context:
- V2 already works and must remain the source of signal generation.
- V3 should interpret V2 outputs into decisions.
- Do not rewrite V2 scoring, filtering, or Telegram sending.
- Do not enable V3 behavior unless explicitly requested.

Review focus:
1. Module boundaries
   - Is V3 additive?
   - Does decision_engine.py avoid owning V2 screening logic?
   - Does position_sizing.py own sizing math instead of the formatter?
   - Does journal.py stay focused on storage?

2. Formatter bloat
   - Is Telegram formatting display-only?
   - Are decision rules kept out of message_formatter.py?
   - Is V2 output preserved when V3 data is absent or disabled?

3. Duplicated logic
   - Are V2 grade, setup, liquidity, and relative strength checks reused as inputs instead of recomputed?
   - Is risk logic duplicated between risk_engine.py, decision_engine.py, and position_sizing.py?

4. Decision logic leakage
   - Are ENTER / WAIT / WATCHLIST_ONLY / AVOID rules centralized?
   - Are risk flags generated consistently?
   - Are user-facing reasons produced by the decision layer, not scattered across modules?

5. Config sprawl
   - Are flags minimal and safe by default?
   - Are risk settings named clearly?
   - Is there any config that enables V3 Telegram output accidentally?

6. Test gaps
   - Are V2 compatibility tests present?
   - Are formatter compatibility tests present?
   - Are invalid sizing and missing-data cases covered?
   - Are journal write and failure cases covered?
   - Is shadow-mode behavior tested or at least reviewable through logs?

Return:
- Overall verdict
- Critical issues
- Medium-risk issues
- Nice-to-have improvements
- Files that need changes
- Suggested test additions
- Readiness score from 1-10

Do not change code unless explicitly asked.
```
