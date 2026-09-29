"""Wake-ups: one fixed line to the ntfy.sh topic the server made for a person, and an empty event, signed, to each app
that subscribed to be woken for them (MCP Events), when something is aimed at them.

Never waited on: a wake-up that fails is a wake-up not sent, and nothing else changes. A failure is printed to the
server's log, without the topic or the address.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import secrets
import socket
import ssl
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

LINE = b"Something is waiting for you on Bridge. Open your AI and say: check Bridge."
TIMEOUT_S = 10
TRIES = 3                           # an event, with a wait of 2 and then 8 seconds between tries


def _post(link: str) -> None:
    request = urllib.request.Request(link, data=LINE, method="POST",
                                     headers={"Title": "Bridge", "Content-Type": "text/plain"})
    try:
        urllib.request.urlopen(request, timeout=5).close()
    except Exception as exc:        # whatever went wrong, nothing waits on it
        print(f"Bridge: a nudge was not sent: {exc!r}", file=sys.stderr)


def send(link: str) -> None:
    threading.Thread(target=_post, args=(link,), daemon=True).start()


# -- MCP Events -------------------------------------------------------------------------------------------------

class Unsafe(Exception):
    """An address the server will not post to."""


def sign(secret: str, message_id: str, timestamp: int, body: bytes) -> str:
    """Standard Webhooks: HMAC-SHA256 over "id.timestamp.body", keyed by the base64 after "whsec_"."""
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{message_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def usable_secret(secret: str) -> bool:
    try:
        return secret.startswith("whsec_") and 24 <= len(base64.b64decode(secret[6:], validate=True)) <= 64
    except ValueError:
        return False


class _Pinned(http.client.HTTPSConnection):
    """Connects to the address that was checked, and verifies TLS for the name asked for: a name that resolved to a
    public address when checked could resolve to a private one when connecting (DNS rebinding)."""

    def __init__(self, host: str, port: int, address: str):
        super().__init__(host, port, timeout=TIMEOUT_S, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


# IPv6 forms that carry an IPv4 address, which `is_global` judges as IPv6: NAT64 and the old IPv4-compatible form.
_CARRIERS = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "::/96")]


def _public(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%")[0])
    if ip.version == 6:
        inner = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None) or next(
            (ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF) for n in _CARRIERS if ip in n), None)
        if inner is not None and not inner.is_global:
            return False
    return ip.is_global


def _public_address(url: str) -> tuple[str, int, str]:
    """HTTPS, and every address the name resolves to is public: never the server's own machine or network, which an
    app choosing the address could otherwise reach through it."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise Unsafe("the address must be https")
    port = parsed.port or 443
    try:
        found = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise Unsafe("the address does not resolve") from exc
    if not found or not all(_public(a) for a in found):
        raise Unsafe("the address is not a public one")
    return parsed.hostname, port, sorted(found)[0]


def _https_post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    """One POST, no redirects followed. Tests replace it."""
    host, port, address = _public_address(url)
    parsed = urlparse(url)
    connection = _Pinned(host, port, address)
    try:
        connection.request("POST", (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else ""), body, headers)
        response = connection.getresponse()
        return response.status, response.read(64 * 1024)
    finally:
        connection.close()


def _signed(sub: dict, message_id: str, body: bytes) -> dict[str, str]:
    now = int(time.time())
    return {"Content-Type": "application/json", "webhook-id": message_id, "webhook-timestamp": str(now),
            "webhook-signature": sign(sub["secret"], message_id, now, body), "X-MCP-Subscription-Id": sub["id"]}


def verify(sub: dict) -> str:
    """The app proves the address is its own by echoing a fresh challenge. Returns '' or why it failed."""
    challenge = secrets.token_urlsafe(24)
    body = json.dumps({"type": "verification", "challenge": challenge}).encode()
    try:
        status, answer = _https_post(sub["url"], body, _signed(sub, f"msg_verification_{secrets.token_hex(8)}", body))
    except Unsafe:
        return "unsafe_url"
    except (OSError, http.client.HTTPException):
        return "timeout"
    try:
        echoed = json.loads(answer).get("challenge", "")
    except (ValueError, AttributeError):
        echoed = ""
    ok = 200 <= status < 300 and isinstance(echoed, str) and hmac.compare_digest(echoed, challenge)
    return "" if ok else "challenge_failed"


def event(name: str) -> bytes:
    """One event with nothing in it: never what or who (PROTOCOL.md §5). Serialized once, since the signature covers
    these exact bytes."""
    return json.dumps({"eventId": f"evt_{secrets.token_hex(12)}", "name": name,
                       "timestamp": datetime.now(UTC).isoformat(timespec="seconds"), "data": {},
                       "cursor": None}).encode()


def _deliver(sub: dict, body: bytes, gone: Callable[[], None], wait: Callable[[float], None]) -> None:
    message_id = json.loads(body)["eventId"]
    for attempt in range(TRIES):
        try:
            status, _ = _https_post(sub["url"], body, _signed(sub, message_id, body))
        except Unsafe as exc:
            print(f"Bridge: an event was not sent: {exc}", file=sys.stderr)
            return
        except (OSError, http.client.HTTPException):
            status = 0
        if 200 <= status < 300:
            return
        if status in (410, 413):
            if status == 410:
                gone()
            return
        if attempt + 1 < TRIES:
            wait(2 * 4 ** attempt)
    print(f"Bridge: an event was not delivered after {TRIES} tries (last status {status})", file=sys.stderr)


def wake(sub: dict, name: str, gone: Callable[[], None]) -> None:
    threading.Thread(target=_deliver, args=(sub, event(name), gone, time.sleep), daemon=True).start()
