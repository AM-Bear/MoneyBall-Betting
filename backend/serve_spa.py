"""Minimal production static server for the MONEYLINE SPA.

The deployment router sends `/api` traffic to the FastAPI service, so this
process only serves the built frontend. It deliberately imports nothing heavy
(no pandas/sklearn/model loading) so its port opens within a second or two and
the deployment startup probe passes immediately.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.routing import Route

DIST_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "moneyline" / "dist" / "public"

# Hashed build assets are immutable; everything else must revalidate.
IMMUTABLE_PREFIX = "assets/"


async def spa(request: Request) -> Response:
    path = request.path_params.get("path", "").lstrip("/")
    if path:
        candidate = (DIST_DIR / path).resolve()
        try:
            inside = candidate.is_relative_to(DIST_DIR)
        except ValueError:
            inside = False
        if inside and candidate.is_file():
            headers = (
                {"Cache-Control": "public, max-age=31536000, immutable"}
                if path.startswith(IMMUTABLE_PREFIX)
                else {"Cache-Control": "no-cache"}
            )
            return FileResponse(candidate, headers=headers)
        # A missing build asset (or any file-like path) must 404 rather than
        # silently serving index.html to a JS/CSS request.
        last_segment = path.rsplit("/", 1)[-1]
        if path.startswith(IMMUTABLE_PREFIX) or "." in last_segment:
            return PlainTextResponse("Not found.", status_code=404)
    index_path = DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers={"Cache-Control": "no-cache"})
    return PlainTextResponse(
        "The frontend build is not available in this runtime.", status_code=503
    )


app = Starlette(routes=[Route("/{path:path}", spa)])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "18612")))
