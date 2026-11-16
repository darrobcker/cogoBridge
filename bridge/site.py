"""A site's own pages, served at / in place of home and the docs (`bridge serve --site`, BRIDGE_SITE).

Only the paths in `PAGES`, so the site's scripts, tests and notes stay unserved; anything else is the server's own
not-found page. Inline scripts run only by their hash. The server's own pages (the policy, Allow, invites, the yes
page) stay the server's, dressed by a theme like any other.
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# The top of the site's tree that is served: pages, and what they load. Anything else there — scripts,
# validation, notes, package files, its theme — is not.
PAGES = {"index.html", "assets", "docs", "fonts", "src", "styles", "support", "vendor", "why"}
SITE_POLICY = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
               "script-src 'self'{inline}; connect-src 'self'; object-src 'none'; base-uri 'none'; "
               "form-action 'self'; frame-ancestors 'none'")
_INLINE = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


class SiteFiles(StaticFiles):
    """The site's files, only under `PAGES`. A page gets a policy that runs its own inline scripts by their hash
    and nothing else inline."""

    def __init__(self, directory: Path):
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope) -> Response:
        top = path.strip("/").split("/")[0] if path.strip("/") not in ("", ".") else "index.html"
        if top not in PAGES:
            raise HTTPException(404)  # the server's own not-found page, as for a page that is missing
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        if response.headers.get("content-type", "").startswith("text/html"):
            target = getattr(response, "path", None)
            hashes = _hashes(Path(target).read_bytes()) if target else ""
            response.headers["Content-Security-Policy"] = SITE_POLICY.format(inline=hashes)
        return response


def _hashes(page: bytes) -> str:
    return "".join(f" 'sha256-{base64.b64encode(hashlib.sha256(m.group(1)).digest()).decode()}'"
                   for m in _INLINE.finditer(page))
