---
name: Broad error handlers hide programming errors
description: Feed routes convert every exception to 503; check server logs before blaming upstream
---

Live-feed routes convert any exception into a 503 `feed_unavailable`, so a plain programming error looks identical to a real upstream outage.

**Why:** Broad except-to-503 is correct for genuine feed failures but swallows tracebacks; the only evidence is in the API server logs.

**How to apply:** When a live endpoint 503s, read the API logs for the underlying traceback before assuming the external feed is down.
