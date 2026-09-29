---
name: Live season is a backend contract
description: Never hardcode the live year in UI or route validation; derive it from the API
---

The live MLB season comes from the backend clock and is exposed as `season` on `/api/teams-live`. Every frontend label, live-mode check, screener year list, and omnisearch navigation must derive from that value; backend route validation must compare against `current_season()`, not a literal year.

**Why:** When the calendar rolls over, hardcoded years silently mislabel data or reject the live season. Tests in `tests/test_live_season_contract.py` pin this contract, including the clock-advance case.

**How to apply:** New live-season surfaces read the year from the teams-live hook (with a generic "LIVE" fallback while loading); never bake the current year into copy, query params, or FastAPI `Query` bounds.
