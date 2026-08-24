---
name: Frontend browser smoke runtime
description: Environment requirements for running the production frontend browser smoke gate.
---

The frontend browser smoke gate must install its Playwright browser during the command and declare Chromium's runtime libraries in `.replit` so a fresh validation environment can launch it.

**Why:** The workspace does not provide a system browser by default, and the downloaded headless shell fails without shared graphics, text, and audio libraries.

**How to apply:** Keep the browser install in the repeatable smoke command, and update the declared system packages if a future Playwright/browser revision adds a missing shared-library requirement.