---
name: Frontend build must not require dev-server env vars
description: Deploy builds run without service env vars; keep PORT checks serve-only
---

Deployment build steps run without the `[services.env]` port bindings; only the dev/preview server gets them.

**Why:** A Vite config that threw when `PORT`/`BASE_PATH` were unset broke the production build pipeline, which only supplies those vars at run time.

**How to apply:** Any artifact config that reads env vars must enforce them only for `serve`/`preview`, never at build time; default base paths for builds.
