---
name: Frontend browser smoke runtime
description: Environment requirements for running the production frontend browser smoke gate.
---

The frontend browser smoke gate must install its Playwright browser during the command and declare Chromium's runtime libraries in `.replit` so a fresh validation environment can launch it.

**Why:** The workspace does not provide a system browser by default, and the downloaded headless shell fails without shared graphics, text, and audio libraries.

**How to apply:** Keep the browser install in the repeatable smoke command, and update the declared system packages if a future Playwright/browser revision adds a missing shared-library requirement.

Production smoke fixtures that bypass authentication must also provide a loaded
health response and minimal route-shaped payloads; otherwise startup overlays or
lazy panels remain in loading states and mask the route assertion.

**Why:** The production API enforces sessions independently of the session
bootstrap response, so a fake authenticated session alone produces 401 console
errors and incomplete screens.

**How to apply:** Intercept protected API calls in browser smoke and return
small valid fixtures for health, slate, season, and wire endpoints.