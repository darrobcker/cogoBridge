"""The web client (PROTOCOL.md §5): where a person does themselves what their assistant could do for them.

Its API is one route per operation, each a call into `net`, where the rules are: nothing here decides anything a
tool would not. A browser signs in with a code from a connection its person already has, and holds the new
connection's secret in a cookie its pages' scripts cannot read; each call opens that person's key for itself alone,
as an MCP call does. What members wrote goes out as JSON values, read as a reader sees them, with the label §3 rule 4
asks for beside what poses as the system; the pages put it on screen as text, never as markup.

With `site`, the server also serves the client's own files: only the paths in `PAGES`, so a theme's scripts, tests
and notes stay unserved. Inline scripts run only by their hash.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from . import guard, net, vault
from .mcp_server import _poses
from .passkeys import Passkeys

YESES_SHOWN = 100                   # the newest yeses the web client lists
BODY_LIMIT = 64 * 1024              # a need or a message is at most a few thousand characters (net.MAX_TEXT)
SESSION_S = 180 * 86400             # how long a browser keeps the cookie after its last call; each call renews it
# Member-written values, wherever they sit in what `net` returns: each is read as a reader sees it (invisible
# characters dropped, compatibility forms folded), and what may pose as the system gets a label beside it.
MEMBER = {"text", "need", "community", "name", "contact", "about", "wrote", "communities", "small"}
POSES = {"text", "need", "wrote"}
# Each tool, and the routes that do what it does: tests/test_site.py fails when a tool has none.
PARITY = {"check": ("/waiting", "/yeses"), "setup": ("/setup", "/code"), "go": ("/post",), "reply": ("/reply",),
          "agree": ("/agree", "/confirm", "/take-back", "/withdraw"), "pass": ("/pass",),
          "community": ("/community",), "forget_me": ("/forget",)}


def _member(value):
    """`net`'s answer as the browser gets it: member text read as a reader sees it, and labelled where it poses as
    the system or its moderators. Ids, counts and times pass as they are."""
    if isinstance(value, list):
        return [_member(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, v in value.items():
        if key in MEMBER and isinstance(v, str):
            out[key] = guard.visible(v)
            if key in POSES and _poses(out[key]):
                out[f"{key}_poses"] = True
        elif key in MEMBER and isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            # A report's messages, a need's communities: each string as above, the labels beside them in order.
            out[key] = [guard.visible(x) for x in v]
            if key in POSES and any(_poses(x) for x in out[key]):
                out[f"{key}_poses"] = [_poses(x) for x in out[key]]
        else:
            out[key] = _member(v)
    return out


def create_site(store, *, base_url: str, dev_sessions: Path | None = None) -> list[Route]:
    """The routes under /api. `dev_sessions`: the file `bridge demo` wrote, naming each demo person's connection
    secret; only `bridge serve --dev` passes it, and only for a server on this machine."""
    base = base_url.rstrip("/")
    keys = Passkeys(store, base)
    origin = "{0.scheme}://{0.netloc}".format(urlparse(base))
    secure = base.startswith("https://")
    # Over plain http the cookie could be read on the way: only a server of one's own machine may (security review).
    if not secure and not _loopback(base):
        raise ValueError("the web client needs an https address, unless it is on this machine")
    if dev_sessions is not None and not (not secure and _loopback(base)):
        raise ValueError("the demo sign-in is only for a server on this machine")
    cookie = cookie_name(base)

    def answer(body, status: int = 200) -> JSONResponse:
        response = JSONResponse(body, status_code=status)
        response.headers["Cache-Control"] = "no-store"
        return response

    def keep(response: Response, secret: str) -> Response:
        # Lax, so the Allow page, reached through an app's redirect, can see who is signed in here; what changes
        # anything is turned away unless it is JSON from this site's own pages (`body`), however it was sent.
        response.set_cookie(cookie, secret, max_age=SESSION_S, path="/", secure=secure, httponly=True,
                            samesite="lax")
        return response

    def forget(response: Response) -> Response:
        response.delete_cookie(cookie, path="/", secure=secure, httponly=True, samesite="lax")
        return response

    async def body(request: Request) -> dict:
        """A POST's JSON, only from this server's own pages: a form or a fetch from anywhere else is turned away
        before anything is read, whatever cookie it carried."""
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise _Turned(415, "send JSON")
        if request.headers.get("origin", origin) != origin:
            raise _Turned(403, "not from this site")
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            raise _Turned(403, "not from this site")
        # Read no further than the limit: a body read whole first could be gigabytes (security review).
        try:
            if int(request.headers.get("content-length") or 0) > BODY_LIMIT:
                raise _Turned(413, "too long")
        except ValueError:
            raise _Turned(400, "send JSON") from None
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > BODY_LIMIT:
                raise _Turned(413, "too long")
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise _Turned(400, "send JSON") from None
        if not isinstance(data, dict):
            raise _Turned(400, "send a JSON object")
        return data

    def signed_in(tool: str, work: Callable[..., object], *, session: bool = False):
        """A route for one operation: the person behind the cookie, their key held for this call alone, then
        `work(person)` in the same thread. What `net` refuses is said as it said it; what is not theirs carries
        no detail; a cookie that opens nothing is signed out."""
        async def route(request: Request) -> Response:
            secret = request.cookies.get(cookie, "")[:200]
            try:
                args = await body(request) if request.method == "POST" else dict(request.query_params)
            except _Turned as turned:
                return answer({"refused": turned.reason}, turned.status)

            def run():
                with vault.keys():
                    try:
                        person = net.person_for_site(store, secret, f"site {tool}")
                    except (net.NotYours, net.Refused):
                        return None, None
                    try:
                        # `session`: what makes a new way in also checks, in its own transaction, that this
                        # browser is still signed in (net._still_signed_in).
                        return person, (work(person, args, secret) if session else work(person, args))
                    except net.NotYours:
                        return person, ({"error": "not_yours"}, 404)
                    except net.Refused as exc:
                        return person, ({"refused": str(exc)}, 400)
                    except vault.Locked:
                        return person, ({"refused": net.LOCKED}, 409)
            person, result = await run_in_threadpool(run)
            if person is None:
                return forget(answer({"error": "signed_out"}, 401))
            if isinstance(result, tuple):
                return answer(*result)
            response = answer(_member(result))
            if isinstance(result, dict) and result.get("signed_out"):
                return forget(response)
            return keep(response, secret)
        return route

    def text(args: dict, key: str, limit: int = net.MAX_TEXT * 2) -> str:
        value = args.get(key, "")
        if not isinstance(value, str):
            raise net.Refused(f"{key} must be text")
        return value[:limit]

    def number(args: dict, key: str, default, kind=int):
        value = args.get(key, default)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise net.Refused(f"{key} must be a number")
        try:
            return kind(value)
        except ValueError:
            raise net.Refused(f"{key} must be a number") from None

    def flag(args: dict, key: str) -> bool:
        value = args.get(key, False)
        return value is True or value in ("1", "true")

    # -- the operations ----------------------------------------------------------------------------------------

    def waiting(person, args):
        net.sweep(store)
        inbox = net.inbox(store, person, passed=flag(args, "passed"), needs_from=text(args, "needs_from") or None)
        inbox.pop("yes_link", None)             # a bearer secret: the browser confirms through its own connection
        for conversation in inbox["conversations"]:
            if conversation.get("yes_waits"):   # which yes Confirm confirms, as the yes page's link points at it
                conversation["yes"] = net.waitingYes(store, person, conversation["id"])
        return inbox

    def yes_page(person) -> str:
        link = net.yesLink(store, person)
        if not link:
            raise net.NotYours()
        return link

    def yeses(person, args):
        link = net.yesLink(store, person)
        return {"yeses": (net.yesPage(store, link, limit=YESES_SHOWN) or []) if link else [],
                "days": net.YES_WAITS_S // 86400}

    def post(person, args):
        community = text(args, "community_id")
        need = net.go(store, person, text(args, "text"), community or None, people=number(args, "people", 1),
                      days=number(args, "days", 7, float))
        small = [c["name"] for c in net.me(store, person)["communities"]
                 if c["small"] and (not community or c["id"] == net._ref(community))]
        return {"id": need, "small": small}

    def reply(person, args):
        revision = args.get("revision")
        conversation, outcome = net.reply(store, person, text(args, "to"), text(args, "text"),
                                          agree_too=flag(args, "agree"),
                                          revision=None if revision is None else number(args, "revision", 0))
        return {"conversation": conversation, "outcome": outcome,
                "yes": net.waitingYes(store, person, conversation) if flag(args, "agree") else None}

    def agree(person, args):
        conversation, revision = text(args, "conversation"), args.get("revision")
        outcome = net.agree(store, person, conversation,
                            revision=None if revision is None else number(args, "revision", 0),
                            one_more=flag(args, "one_more"))
        return {"outcome": outcome, "yes": net.waitingYes(store, person, conversation)}

    def confirm(person, args):
        return {"outcome": net.confirmYes(store, yes_page(person), text(args, "yes"))}

    def take_back(person, args):
        return {"outcome": net.revokeYes(store, yes_page(person), text(args, "yes"))}

    def withdraw(person, args):
        return {"outcome": net.withdraw(store, person, text(args, "conversation"))}

    def pass_(person, args):
        results = []
        for ref in [r for r in re.split(r"[\s,]+", text(args, "ref")) if r.strip("[]")][:50]:
            try:
                results.append({"ref": ref, "outcome": net.pass_on(store, person, ref)})
            except net.NotYours:
                results.append({"ref": ref, "error": "not_yours"})
            except net.Refused as exc:
                results.append({"ref": ref, "refused": str(exc)})
        if not results:
            raise net.Refused("give at least one id")
        return {"results": results}

    def community(person, args):
        action, cid, ref = text(args, "action"), text(args, "community_id"), text(args, "ref")
        if action == "create":
            created, code = net.create_community(store, person, text(args, "name"))
            return {"id": created, "invite": f"{base}/join/{code}"}
        if action == "join":
            found = net.join_by_invite(store, person, text(args, "invite_link"))
            return {"id": found["id"], "name": found["name"]}
        if action == "report":
            net.report(store, person, ref)
            return {"done": True}
        if action in ("dismiss", "remove") and not cid and ref.strip().lower().strip("[]").startswith("r-"):
            cid = net.report_community(store, person, ref) or ""
        if not cid:
            raise net.Refused("which community?")
        if action in ("invite", "new_link"):
            return {"invite": f"{base}/join/{net.invite_code(store, person, cid, new=action == 'new_link')}"}
        if action == "leave":
            return {"owner_left": bool(net.leave(store, person, cid))}
        if action == "rename":
            net.rename(store, person, cid, text(args, "name"))
            return {"done": True}
        if action == "remove":
            net.remove(store, person, ref, cid)
            return {"done": True}
        if action == "dismiss":
            net.dismiss(store, person, ref, cid)
            return {"done": True}
        raise net.Refused("unknown action")

    def setup(person, args):
        fields = {k: text(args, k, 4000) or None for k in ("name", "contact", "about", "notify")}
        done = net.setup(store, person, **fields)
        return {"outcome": done, "me": net.me(store, person)}

    def code(person, args):
        """A code for another app, or, with `new_link`, one whose use ends every other connection (as `setup`)."""
        return {"code": net.link_code(store, person, replace=flag(args, "new_link"))}

    def forget_me(person, args):
        net.forget_me(store, person, text(args, "confirm"))
        return {"signed_out": True}

    # -- signing in and out ------------------------------------------------------------------------------------

    async def meta(request: Request) -> Response:
        return answer({"base": base, "connector": f"{base}/mcp", "days": net.YES_WAITS_S // 86400})

    def session(make: Callable[[dict], tuple[str, dict]]):
        """A route that signs this browser in, every way it can: `make(data)` returns the new connection's secret and
        what to answer. The browser's last connection, which the new cookie replaces, ends with it."""
        async def route(request: Request) -> Response:
            try:
                data = await body(request)
            except _Turned as turned:
                return answer({"refused": turned.reason}, turned.status)
            before = request.cookies.get(cookie, "")[:200]

            def run():
                with vault.keys():
                    made = make(data)
                if before and not demo(before):
                    net.site_sign_out(store, before)
                return made
            try:
                secret, said = await run_in_threadpool(run)
            except net.Refused as exc:
                return answer({"refused": str(exc)}, 400)
            except net.NotYours:
                return answer({"error": "not_yours"}, 404)
            return keep(answer({"signed_in": True, **said}), secret)
        return route

    def string(data: dict, key: str, limit: int = 200) -> str:
        value = data.get(key, "")
        return value[:limit] if isinstance(value, str) else ""

    def credential(data: dict) -> dict:
        value = data.get("credential")
        if not isinstance(value, dict):
            raise net.Refused("send the passkey's answer")
        return value

    sign_in = session(lambda data: (net.site_sign_in(store, string(data, "code", 80)), {}))
    passkey_sign_in = session(lambda data: (keys.sign_in(credential(data), data.get("prf")), {}))

    def recovery_sign_in(data):
        secret, fresh = net.recovery_sign_in(store, string(data, "code", 120))
        return secret, {"recovery": fresh}     # the code that replaces the one just used, shown once

    async def start(request: Request) -> Response:
        """Starting on the web, from an invite or not. A browser already signed in joins the invite's community as
        its own person instead of making a second account."""
        if net.site_person(store, request.cookies.get(cookie, "")[:200]):
            return await signed_in("start", joined_now)(request)
        return await session(lambda data: (net.start_on_site(store, string(data, "invite", 400)), {}))(request)

    def joined_now(person, args):
        if not text(args, "invite"):
            raise net.Refused("you are signed in already")
        found = net.join_by_invite(store, person, text(args, "invite"))
        return {"joined": {"id": found["id"], "name": found["name"]}}

    async def invite(request: Request) -> Response:
        """What an invite opens to, for the page that starts someone there: its name, and whether it is small."""
        found = await run_in_threadpool(net.community_by_invite, store, request.query_params.get("code", "")[:400])
        if not found:
            return answer({"error": "not_yours"}, 404)
        return answer(_member({"name": found["name"], "small": net.small(store, found["id"])}))

    # Passkeys and the recovery code, signed in: adding, keying, removing, a new code, and what there is.
    def add_options(person, args):
        return keys.options_to_add(person)

    def add_passkey(person, args, secret):
        return {"opens": keys.add(person, credential(args), args.get("prf"), secret)}

    def key_options(person, args):
        if text(args, "id") not in net.passkey_ids(store, person):
            raise net.NotYours()
        return keys.options_to_use(person, text(args, "id"))

    def key_passkey(person, args, secret):
        keys.key(person, credential(args), args.get("prf"), secret)
        return {"opens": True}

    def remove_passkey(person, args):
        net.remove_passkey(store, person, text(args, "id"))
        return {"done": True}

    def recovery(person, args, secret):
        return {"code": net.new_recovery_code(store, person, session=secret)}

    def ways_in(person, args):
        return net.ways_in(store, person)

    async def use_options(request: Request) -> Response:
        try:
            await body(request)
        except _Turned as turned:
            return answer({"refused": turned.reason}, turned.status)
        return answer(await run_in_threadpool(keys.options_to_use))

    def demo(secret: str) -> bool:
        """A demo person's connection, which `bridge serve --dev` keeps for switching back to."""
        try:
            return dev_sessions is not None and secret in json.loads(dev_sessions.read_text()).values()
        except (OSError, ValueError):
            return False

    async def sign_out(request: Request) -> Response:
        try:
            await body(request)
        except _Turned as turned:
            return answer({"refused": turned.reason}, turned.status)
        secret = request.cookies.get(cookie, "")[:200]
        if not demo(secret):
            await run_in_threadpool(net.site_sign_out, store, secret)
        return forget(answer({"signed_out": True}))

    routes = [
        Route("/meta", meta),
        Route("/sign-in", sign_in, methods=["POST"]),
        Route("/sign-out", sign_out, methods=["POST"]),
        Route("/start", start, methods=["POST"]),
        Route("/invite", invite),
        Route("/passkey/sign-in-options", use_options, methods=["POST"]),
        Route("/passkey/sign-in", passkey_sign_in, methods=["POST"]),
        Route("/recovery/sign-in", session(recovery_sign_in), methods=["POST"]),
        Route("/passkey/add-options", signed_in("passkey", add_options), methods=["POST"]),
        Route("/passkey/add", signed_in("passkey", add_passkey, session=True), methods=["POST"]),
        Route("/passkey/key-options", signed_in("passkey", key_options), methods=["POST"]),
        Route("/passkey/key", signed_in("passkey", key_passkey, session=True), methods=["POST"]),
        Route("/passkey/remove", signed_in("passkey", remove_passkey), methods=["POST"]),
        Route("/recovery", signed_in("recovery", recovery, session=True), methods=["POST"]),
        Route("/ways-in", signed_in("check", ways_in)),
        Route("/waiting", signed_in("check", waiting)),
        Route("/yeses", signed_in("check", yeses)),
        Route("/post", signed_in("go", post), methods=["POST"]),
        Route("/reply", signed_in("reply", reply), methods=["POST"]),
        Route("/agree", signed_in("agree", agree), methods=["POST"]),
        Route("/confirm", signed_in("confirm", confirm), methods=["POST"]),
        Route("/take-back", signed_in("take_back", take_back), methods=["POST"]),
        Route("/withdraw", signed_in("agree", withdraw), methods=["POST"]),
        Route("/pass", signed_in("pass", pass_), methods=["POST"]),
        Route("/community", signed_in("community", community), methods=["POST"]),
        Route("/setup", signed_in("setup", setup), methods=["POST"]),
        Route("/code", signed_in("setup", code), methods=["POST"]),
        Route("/forget", signed_in("forget_me", forget_me), methods=["POST"]),
    ]
    if dev_sessions is not None:
        routes += _dev(dev_sessions, body, answer, keep)
    return routes


def cookie_name(base_url: str) -> str:
    """__Host-: only over https, for this host alone, for every path; the plain name on one's own machine."""
    return "__Host-bridge" if base_url.startswith("https://") else "bridge"


def _loopback(url: str) -> bool:
    return urlparse(url).hostname in ("127.0.0.1", "localhost")


class _Turned(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def _dev(sessions: Path, body, answer, keep) -> list[Route]:
    """On a server of one's own machine, `bridge serve --dev` only: sign in as anyone `bridge demo` made, to see the
    client as each of them."""
    def people() -> dict:
        try:
            return json.loads(sessions.read_text())
        except (OSError, ValueError):
            return {}

    async def who(request: Request) -> Response:
        if not _loopback("http://" + request.headers.get("host", "")):
            return answer({"refused": "only on this machine"}, 404)
        return answer({"people": list(people())})

    async def sign_in_as(request: Request) -> Response:
        # Only asked for at this machine's own address: a tunnel forwarding here carries its public host.
        if not _loopback("http://" + request.headers.get("host", "")):
            return answer({"refused": "only on this machine"}, 404)
        try:
            data = await body(request)
        except _Turned as turned:
            return answer({"refused": turned.reason}, turned.status)
        secret = people().get(str(data.get("name", "")))
        if not secret:
            return answer({"refused": "no such demo person"}, 404)
        return keep(answer({"signed_in": True}), secret)
    return [Route("/dev/people", who), Route("/dev/sign-in-as", sign_in_as, methods=["POST"])]


# -- the client's own files ----------------------------------------------------------------------------------------

# The top of the client's tree that is served: pages, and what they load. Anything else there — scripts,
# validation, notes, package files — is not.
PAGES = {"index.html", "assets", "docs", "fonts", "privacy", "src", "styles", "support", "terms", "tinker",
         "vendor", "view", "why"}
SITE_POLICY = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
               "script-src 'self'{inline}; connect-src 'self'; object-src 'none'; base-uri 'none'; "
               "form-action 'self'; frame-ancestors 'none'")
_INLINE = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


class SiteFiles(StaticFiles):
    """The client's files, only under `PAGES`. A page gets a policy that runs its own inline scripts by their hash
    and nothing else inline. `dev`: never kept, so a reload always shows the file as it is now."""

    def __init__(self, directory: Path, *, dev: bool = False):
        super().__init__(directory=directory, html=True)
        self.dev, self.root = dev, Path(directory).resolve()

    async def get_response(self, path: str, scope) -> Response:
        top = path.strip("/").split("/")[0] if path.strip("/") not in ("", ".") else "index.html"
        if top not in PAGES:
            return Response("Not found", 404, media_type="text/plain")
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store" if self.dev else "no-cache"
        if response.headers.get("content-type", "").startswith("text/html"):
            target = getattr(response, "path", None)
            hashes = _hashes(Path(target).read_bytes()) if target else ""
            response.headers["Content-Security-Policy"] = SITE_POLICY.format(inline=hashes)
        return response


def _hashes(page: bytes) -> str:
    return "".join(f" 'sha256-{base64.b64encode(hashlib.sha256(m.group(1)).digest()).decode()}'"
                   for m in _INLINE.finditer(page))
