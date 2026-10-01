"""The only web pages: home, the invite page and the connect page it leads to, the Allow page an app's sign-in opens,
the consent text, which is also the privacy policy and the terms, and one saying an address has no page.

Everything after that happens in the chat. There is no inbox, no settings page and no password, and no page knows
who anyone is: a person and their first membership are made at their AI's first tool call through a connection
Allow made, so a page previewed, reloaded or pressed twice makes nobody.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from mcp.server.auth.provider import construct_redirect_uri
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import net
from .store import Store

DAY, YEAR = "public, max-age=86400", "public, max-age=31536000, immutable"
# What a page may load and run: this server's own files, and the images a page's script makes from them. Styles may
# be inline (the plain frame's are); scripts may not, so text that got past escaping could not run. No form-action:
# Chrome holds a form's redirect to it too, and Allow's answer goes on to the app that asked.
POLICY = ("default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; "
          "base-uri 'none'; frame-ancestors 'none'")


class _Kept(StaticFiles):
    """/static, with how long a browser may keep each file: one asked for with ?v= (a theme's versioned asset) never
    changes under that name, so a year; the rest a day."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            versioned = "v" in parse_qs(scope.get("query_string", b"").decode())
            response.headers["Cache-Control"] = YEAR if versioned else DAY
        return response


AIS = ("claude", "chatgpt")         # anything else is "another AI"
INVITE, AI = "bridge_invite", "bridge_ai"   # the cookies: an invite code, and the app pressed for; no more (§5)
# Where each app's sign-in returns. An invite pressed for one of these goes only to a sign-in that returns there, so
# someone else's app, allowed by a person tricked into it, cannot take the community along (review).
RETURNS = {"claude": ("claude.ai", "claude.com"), "chatgpt": ("chatgpt.com", "openai.com")}


def _their_app(ai: str, redirect_uri: str) -> bool:
    host = urlparse(redirect_uri).hostname or ""
    return ai not in RETURNS or any(host == d or host.endswith("." + d) for d in RETURNS[ai])


def _version() -> str:
    """The commit this code is, so a deploy can tell the new code is the one answering."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "dev"


def create_app(store: Store, *, base_url: str, operator: str = "", claude_listing: str = "",
               chatgpt_listing: str = "", contact: str = "", openai_challenge: str = "", theme: str = "") -> Starlette:
    """`operator` is who runs this server, named on the pages because they can read everything; `contact`, how to
    reach them, for the help a directory listing asks to link to. `openai_challenge`: the token OpenAI's plugin portal
    asks this host to show, to prove it is the publisher's. `theme`: a directory whose `templates/` are found before
    these and whose `static/` is served at /static — a server's own look, kept out of the protocol's code. A theme
    replaces the frame (`base.html`) and may replace `home.html`; the other pages' words, which say who can read
    what before anyone presses a button, are these."""
    here = Path(__file__).parent
    looks = [Path(theme)] if theme else []
    env = Environment(loader=ChoiceLoader([FileSystemLoader(str(d / "templates")) for d in [*looks, here]]),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    static = next(d / "static" for d in [*looks, here] if (d / "static").is_dir())
    base = base_url.rstrip("/")
    connector = f"{base}/mcp"
    version = _version()
    # Claude's own install link: it opens the add-connector dialog prefilled, and the person confirms. A listing in
    # Claude's directory replaces it once there is one.
    claude_add = claude_listing or ("https://claude.ai/customize/connectors?modal=add-custom-connector&connectorName="
                                    f"Bridge&connectorUrl={quote(connector, safe='')}")

    def page(name: str, status: int = 200, **context) -> HTMLResponse:
        response = HTMLResponse(env.get_template(name).render(operator=operator, connector=connector, contact=contact,
                                                              claude_add=claude_add, claude_listed=bool(claude_listing),
                                                              chatgpt_listing=chatgpt_listing, **context),
                                status_code=status)
        response.headers["Content-Security-Policy"] = POLICY
        # A proxy passes it as it is: Cloudflare wrote its analytics script into every page (review).
        response.headers["Cache-Control"] = "no-transform"
        return response

    def remember(response: Response, code: str, ai: str = "") -> Response:
        # Lax: an Allow form posted from another site does not carry them (PROTOCOL.md §5). A page only viewed
        # forgets an app pressed for on another.
        secure = base.startswith("https")
        response.set_cookie(INVITE, code, max_age=86400, httponly=True, samesite="lax", secure=secure)
        if ai:
            response.set_cookie(AI, ai, max_age=86400, httponly=True, samesite="lax", secure=secure)
        else:
            response.delete_cookie(AI, httponly=True, samesite="lax", secure=secure)
        return response

    async def home(request: Request) -> Response:
        return page("home.html")

    async def health(request: Request) -> Response:
        try:
            store.one("SELECT 1 FROM kv LIMIT 1")
        except sqlite3.Error:
            return JSONResponse({"ok": False}, status_code=503)
        return JSONResponse({"ok": True, "version": version})

    async def consent(request: Request) -> Response:
        return page("consent.html")

    async def favicon(request: Request) -> Response:
        return FileResponse(static / "favicon.ico", media_type="image/x-icon", headers={"Cache-Control": DAY})

    async def challenge(request: Request) -> Response:
        return PlainTextResponse(openai_challenge) if openai_challenge else PlainTextResponse("", status_code=404)

    async def join(request: Request) -> Response:
        community = net.community_by_invite(store, request.path_params["invite"])
        if community is None:
            return page("invalid.html", 404)
        link = f"{base}/join/{community['invite_code']}"
        if request.method != "POST":    # chat apps fetch links to preview them, some by HEAD
            return remember(page("join.html", community=community, link=link, small=net.small(store, community["id"])),
                            community["invite_code"])
        ai = (await request.form()).get("ai", "")
        ai = ai if ai in AIS else "other"
        # A press, not a person: counted by the AI chosen, so presses can be read against Allows and first calls.
        net.log_call(store, f"join-page {ai} {community['id']}")
        return remember(page("connect.html", community=community, ai=ai, link=link), community["invite_code"], ai)

    async def allow(request: Request) -> Response:
        """An app's sign-in: one button. The page names the app, where it sends the person back, and the community
        the invite page remembered; it asks for nothing and knows nobody."""
        form = await request.form() if request.method == "POST" else {}
        ref = form.get("r") or request.query_params.get("r", "")
        waiting = net.sign_in_waiting(store, ref) if ref else None
        if waiting is None:
            return page("expired.html", 400)
        invite = request.cookies.get(INVITE, "")[:40]
        if not _their_app(request.cookies.get(AI, ""), waiting["redirect_uri"]):
            invite = ""
        if request.method != "POST":
            info = json.loads(net.client(store, waiting["client_id"]) or "{}")
            community = store.one("SELECT id, name FROM communities WHERE invite_code=?", invite)
            response = page("allow.html", ref=ref, app=(info.get("client_name") or "An app")[:60],
                            host=urlparse(waiting["redirect_uri"]).hostname or "",
                            community=community, small=bool(community) and net.small(store, community["id"]))
            response.headers["Cache-Control"] = "no-store, no-transform"
            return response
        if form.get("choice") != "allow":
            gone = net.deny(store, ref) or waiting
            return RedirectResponse(construct_redirect_uri(gone["redirect_uri"], error="access_denied",
                                                           state=gone["state"]), status_code=303)
        allowed = net.allow(store, ref, invite)
        if allowed is None:
            return page("expired.html", 400)
        data, code = allowed
        net.log_call(store, f"allow {urlparse(data['redirect_uri']).hostname or ''}"[:80])
        return RedirectResponse(construct_redirect_uri(data["redirect_uri"], code=code, state=data["state"]),
                                status_code=303)

    async def missing(request: Request, exc: Exception) -> Response:
        return page("missing.html", 404)

    return Starlette(exception_handlers={404: missing},
                     routes=[Route("/", home), Route("/health", health), Route("/consent", consent),
                             Route("/privacy", consent), Route("/terms", consent),
                             Route("/.well-known/openai-apps-challenge", challenge),
                             Route("/favicon.ico", favicon), Mount("/static", _Kept(directory=static)),
                             Route("/allow", allow, methods=["GET", "POST"]),
                             Route("/join/{invite}", join, methods=["GET", "POST"])])
