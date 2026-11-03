"""One ASGI app: the pages at /, sign-in, everyone's assistant at /mcp, and the older own links at /c/<secret>/mcp."""
from __future__ import annotations

from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import (
    build_metadata,
    build_resource_metadata_url,
    cors_middleware,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route

from .mcp_server import create_mcp
from .oauth import SCOPE, Provider
from .store import Store
from .web import _version
from .web import create_app as create_web


def create_app(store: Store, *, base_url: str, operator: str = "", **site: str) -> Starlette:
    """`site`: what the pages say beyond the server's own state (`web.create_app`), such as Bridge's page in each
    app's directory once it has one."""
    base = base_url.rstrip("/")
    # One MCP app answers both doors: who is calling is read from each request, never from its session. So it keeps
    # none: a deploy's restart no longer ends every app's session, and each answer is plain JSON, not a stream.
    mcp_app = _PostOnly(create_mcp(store, base_url=base, operator=operator, version=_version()).streamable_http_app(
        streamable_http_path="/mcp", host="0.0.0.0", stateless_http=True, json_response=True))
    provider = Provider(store, base)
    # Through AuthSettings, which keeps a bare host without the "/" pydantic adds: issuers are compared exactly.
    settings = AuthSettings(issuer_url=base, resource_server_url=f"{base}/mcp", validate_token_resource=False)
    issuer, resource = settings.issuer_url, settings.resource_server_url
    metadata = create_protected_resource_routes(resource_url=resource, authorization_servers=[issuer],
                                                scopes_supported=[SCOPE], resource_name="Bridge",
                                                resource_documentation=AnyHttpUrl(f"{base}/"))
    signed_in = RequireAuthMiddleware(mcp_app, [], build_resource_metadata_url(resource))
    docs, registration = AnyHttpUrl(f"{base}/"), ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE],
                                                                           default_scopes=[SCOPE])
    sign_in = create_auth_routes(provider, issuer_url=issuer, service_documentation_url=docs,
                                 client_registration_options=registration,
                                 revocation_options=RevocationOptions(enabled=True))
    # The SDK takes an app with no secret (PKCE alone) but lists only the secret methods, and _Issuer names this
    # server in every answer to a sign-in; OpenAI's guide asks a server to say both (test).
    said = build_metadata(issuer, docs, registration, RevocationOptions(enabled=True))
    said.token_endpoint_auth_methods_supported = [*said.token_endpoint_auth_methods_supported, "none"]
    said.revocation_endpoint_auth_methods_supported = [*said.revocation_endpoint_auth_methods_supported, "none"]
    said.authorization_response_iss_parameter_supported = True
    at = next(i for i, route in enumerate(sign_in) if route.path == "/.well-known/oauth-authorization-server")
    sign_in[at] = Route(sign_in[at].path, endpoint=cors_middleware(MetadataHandler(said).handle, ["GET", "OPTIONS"]),
                        methods=["GET", "OPTIONS"])
    routes = [
        *sign_in,
        *metadata,
        # Some apps look for the resource's metadata without the path RFC 9728 puts after it.
        Route("/.well-known/oauth-protected-resource", endpoint=metadata[0].endpoint, methods=["GET", "OPTIONS"]),
        Route("/mcp", endpoint=signed_in),
        Mount("/c/{secret}", app=mcp_app),
        Mount("/", app=create_web(store, base_url=base, operator=operator, **site)),
    ]
    middleware = [Middleware(_OneHost, www=f"www.{urlparse(base).hostname}", base=base),
                  Middleware(_Issuer, issuer=str(issuer)),
                  Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(ProviderTokenVerifier(provider))),
                  Middleware(AuthContextMiddleware)]
    return Starlette(routes=routes, middleware=middleware,
                     lifespan=lambda app: mcp_app.app.router.lifespan_context(mcp_app.app))


class _PostOnly:
    """Nothing is pushed to an app down a held-open stream (a wake-up is a signed webhook), so a GET that would open
    one is told so at once (405, as the transport allows), rather than held open with nothing ever coming."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "GET":
            refused = PlainTextResponse("Bridge answers MCP over POST.", 405, headers={"Allow": "POST"})
            await refused(scope, receive, send)
            return
        await self.app(scope, receive, send)


class _Issuer:
    """RFC 9207: every answer to a sign-in that goes back to the app names the server it came from, so an app signed in
    with several cannot be handed one's answer as another's. Answers come from two places, the SDK's own checks at
    /authorize and the Allow page, so they are named here, once, on the way out; the one step within this server
    (the SDK sending the person on to Allow) is left as it is."""

    PATHS = ("/authorize", "/allow")

    def __init__(self, app, *, issuer: str):
        self.app, self.issuer, self.here = app, issuer, urlparse(issuer).netloc

    def _named(self, location: str) -> str:
        """Appended, the rest left byte for byte: parsed and rebuilt, a query loses what parsing drops (`state=`).
        Only the SDK's step on to the Allow page is this server's own; an app may return to an address on this host
        too, and an `iss` its address already carries is replaced, since only this server's may stand (review)."""
        there = urlparse(location)
        if not there.scheme or (there.netloc == self.here and there.path == "/allow"):
            return location
        query = there.query
        if "iss" in parse_qs(query, keep_blank_values=True):
            query = urlencode([(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "iss"])
        iss = urlencode({"iss": self.issuer})
        return urlunparse(there._replace(query=f"{query}&{iss}" if query else iss))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in self.PATHS:
            await self.app(scope, receive, send)
            return

        async def named(message):
            if message["type"] == "http.response.start" and 300 <= message["status"] < 400:
                message = {**message, "headers": [
                    (k, self._named(v.decode("latin-1")).encode("latin-1")) if k.lower() == b"location" else (k, v)
                    for k, v in message.get("headers", [])]}
            await send(message)
        await self.app(scope, receive, named)


class _OneHost:
    """One address and one way in: www. and plain http go to the address itself. Sign-in is issued for one name, and a
    page reached at another would hand out links an app would treat as a different server; a page or a sign-in
    reached over plain http could be read or changed on the way. Behind a proxy the visitor's own scheme is in its
    headers: Cloudflare's CF-Visitor, or else X-Forwarded-Proto. A server whose address is plain http is left be."""

    STAY = (b"strict-transport-security", b"max-age=15552000")   # browsers keep to https for half a year
    # on every answer: a file is taken for what its type says, and a link followed tells nobody where it was found
    EVERY = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]

    def __init__(self, app, *, www: str, base: str):
        self.app, self.www, self.base, self.secure = app, www.encode(), base, base.startswith("https://")

    def _plain(self, headers: dict) -> bool:
        visitor = headers.get(b"cf-visitor")
        if visitor is not None:
            return b'"http"' in visitor.replace(b" ", b"")
        return headers.get(b"x-forwarded-proto", b"").split(b",")[0].strip() == b"http"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if headers.get(b"host", b"").split(b":")[0] == self.www or (self.secure and self._plain(headers)):
            query = scope.get("query_string", b"").decode()
            there = self.base + scope["path"] + (f"?{query}" if query else "")
            # a form or a token request keeps its method and body
            await RedirectResponse(there, 301 if scope["method"] in ("GET", "HEAD") else 308)(scope, receive, send)
            return
        stamps = [*self.EVERY, self.STAY] if self.secure else self.EVERY

        async def stamped(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *stamps]}
            await send(message)
        await self.app(scope, receive, stamped)
