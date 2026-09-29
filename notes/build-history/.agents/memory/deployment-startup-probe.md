---
name: Deployment startup probe & process split
description: Why production runs one FastAPI process plus a lightweight SPA server, and how to avoid promote-step probe timeouts
---

## Rule
In production, only the api-server artifact runs the full FastAPI app (backend.main). The web artifact must run the lightweight static server (backend.serve_spa) — never a second copy of backend.main.

**Why:** The first publish failed at the promote step: two full FastAPI processes (pandas/sklearn imports + model loading) took ~25s to open their ports on the small deploy machine, and the deployer's startup probe gave up right as they came up. Two copies also ran the snapshot/grade schedulers twice.

**How to apply:**
- Keep backend.serve_spa free of heavy imports (starlette only); its port must open in ~1s.
- Any new in-process scheduler belongs in backend.main only — it runs solely in the api-server service in production.
- The deployer probes each service's route prefix ("/" and "/api"), not necessarily the configured health.startup path — both must return 200 quickly once ports are open.
- If backend.main startup gets slower (new models, prefetch), re-check that a single process still opens its port well under ~25s, or move work to post-startup background tasks.
