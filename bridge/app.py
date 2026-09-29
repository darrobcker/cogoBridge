"""One ASGI app: the pages at /, sign-in, everyone's assistant at /mcp, and the older own links at /c/<secret>/mcp."""
from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url, create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route

from .mcp_server import create_mcp
from .oauth import SCOPE, Provider
from .store import Store
from .web import create_app as create_web


def create_app(store: Store, *, base_url: str, operator: str = "", **site: str) -> Starlette:
    """`site`: what the pages say beyond the server's own state (`web.create_app`), such as Bridge's page in each
    app's directory once it has one."""
    base = base_url.rstrip("/")
    # One MCP app answers both doors: who is calling is read from each request, never from its session.
    mcp_app = create_mcp(store, base_url=base, operator=operator).streamable_http_app(streamable_http_path="/mcp",
                                                                                      host="0.0.0.0")
    provider = Provider(store, base)
    # Through AuthSettings, which keeps a bare host without the "/" pydantic adds: issuers are compared exactly.
    settings = AuthSettings(issuer_url=base, resource_server_url=f"{base}/mcp", validate_token_resource=False)
    issuer, resource = settings.issuer_url, settings.resource_server_url
    metadata = create_protected_resource_routes(resource_url=resource, authorization_servers=[issuer],
                                                scopes_supported=[SCOPE], resource_name="Bridge",
                                                resource_documentation=AnyHttpUrl(f"{base}/"))
    signed_in = RequireAuthMiddleware(mcp_app, [], build_resource_metadata_url(resource))
    routes = [
        *create_auth_routes(provider, issuer_url=issuer, service_documentation_url=AnyHttpUrl(f"{base}/"),
                            client_registration_options=ClientRegistrationOptions(
                                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
                            revocation_options=RevocationOptions(enabled=True)),
        *metadata,
        # Some apps look for the resource's metadata without the path RFC 9728 puts after it.
        Route("/.well-known/oauth-protected-resource", endpoint=metadata[0].endpoint, methods=["GET", "OPTIONS"]),
        Route("/mcp", endpoint=signed_in),
        Mount("/c/{secret}", app=mcp_app),
        Mount("/", app=create_web(store, base_url=base, operator=operator, **site)),
    ]
    middleware = [Middleware(_OneHost, www=f"www.{urlparse(base).hostname}", base=base),
                  Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(ProviderTokenVerifier(provider))),
                  Middleware(AuthContextMiddleware)]
    return Starlette(routes=routes, middleware=middleware,
                     lifespan=lambda app: mcp_app.router.lifespan_context(mcp_app))


class _OneHost:
    """www. goes to the address itself: sign-in is issued for one name, and a page reached at another would hand out
    links an app would treat as a different server."""

    def __init__(self, app, *, www: str, base: str):
        self.app, self.www, self.base = app, www.encode(), base

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and dict(scope["headers"]).get(b"host", b"").split(b":")[0] == self.www:
            query = scope.get("query_string", b"").decode()
            there = self.base + scope["path"] + (f"?{query}" if query else "")
            await RedirectResponse(there, 301)(scope, receive, send)
            return
        await self.app(scope, receive, send)
