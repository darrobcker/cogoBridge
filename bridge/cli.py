"""Operator commands, for whoever hosts a server. Members never need them.

Configuration is environment variables: BRIDGE_HOME (where the database lives, default ~/.bridge),
BRIDGE_BASE_URL (the public URL, when not using --tunnel or --hostname), BRIDGE_OPERATOR (your name,
shown on the pages, which say what you cannot read), BRIDGE_SOURCE (where the code you run is published, linked
from them), BRIDGE_CONTACT (how people reach you, on the help the directories link to), and for the directories
(docs/OPERATIONS.md): BRIDGE_CLAUDE_LISTING, BRIDGE_CHATGPT_LISTING and BRIDGE_OPENAI_CHALLENGE; BRIDGE_THEME, a
directory with a server's own look; BRIDGE_SITE (or --site), the web client's directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import net

HOME = Path(os.environ.get("BRIDGE_HOME", Path.home() / ".bridge"))


def _store():
    HOME.mkdir(parents=True, exist_ok=True)
    return net.open_store(HOME / "bridge.db")


def _base_url() -> str:
    saved = HOME / "url.txt"
    return (os.environ.get("BRIDGE_BASE_URL") or (saved.read_text().strip() if saved.exists() else "")
            or "http://127.0.0.1:8770")


def cmd_serve(args) -> None:
    import uvicorn

    from . import notify
    from .app import create_app
    store = _store()
    store.on_nudge = notify.send    # only for people who asked for nudges, and apps that asked to be woken
    store.on_wake = lambda sub: notify.wake(sub, net.WAITING, lambda: net.drop_subscription(store, sub["id"]))
    url = os.environ.get("BRIDGE_BASE_URL") or f"http://127.0.0.1:{args.port}"
    site = args.site or os.environ.get("BRIDGE_SITE", "")
    if site and not (Path(site) / "index.html").is_file():
        sys.exit(f"bridge serve: --site {site} has no index.html")
    # Before anything starts, a tunnel above all: the demo sign-in lets anyone be anyone (security review).
    if args.dev and (args.hostname or args.tunnel or not _on_this_machine(url, args.host)):
        sys.exit("bridge serve --dev runs only at http://127.0.0.1 or http://localhost, bound to 127.0.0.1, "
                 "with no tunnel")
    if args.hostname:
        # A named Cloudflare tunnel gives a stable URL. Once, beforehand:
        # `cloudflared tunnel create <name>` and `cloudflared tunnel route dns <name> <hostname>`.
        subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "run", "--url",
                          f"http://127.0.0.1:{args.port}", args.named_tunnel],
                         stdout=subprocess.DEVNULL,
                         stderr=open(HOME / "tunnel.log", "a"))  # noqa: SIM115 — the tunnel keeps it open
        url = f"https://{args.hostname}"
    elif args.tunnel:
        url = _quick_tunnel(args.port)
    (HOME / "url.txt").write_text(url)
    print(f"Bridge: {url}", file=sys.stderr)
    pages = {key: os.environ.get(f"BRIDGE_{key.upper()}", "")
             for key in ("claude_listing", "chatgpt_listing", "contact", "openai_challenge", "theme", "source")}
    app = create_app(store, base_url=url, operator=os.environ.get("BRIDGE_OPERATOR", ""), site=site, dev=args.dev,
                     dev_sessions=HOME / "demo-sessions.json" if args.dev else None, **pages)
    # No access log: the older connector links carry their secret in the URL, and sign-in its request.
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)


def _on_this_machine(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and host == "127.0.0.1"


def cmd_demo(args) -> None:
    """A scratch home full of made-up people, for working on the web client: refuses the default home, the live
    one, and any home that already has a database."""
    from . import demo
    if "BRIDGE_HOME" not in os.environ or HOME.resolve() in {(Path.home() / d).resolve() for d in (".bridge",
                                                                                                    "bridge-live")}:
        sys.exit("bridge demo: set BRIDGE_HOME to a new scratch directory")
    people = demo.seed(HOME)
    print(f"demo: {len(people)} people in {HOME}. Serve it with: BRIDGE_HOME={HOME} bridge serve --site <dir> --dev",
          file=sys.stderr)


def _quick_tunnel(port: int) -> str:
    """A throwaway trycloudflare.com URL, for trying it out."""
    proc = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    found: list[str] = []

    def read() -> None:
        for line in proc.stderr:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match and not found:
                found.append(match.group())
    threading.Thread(target=read, daemon=True).start()
    for _ in range(60):
        if found:
            return found[0]
        time.sleep(0.5)
    sys.exit("cloudflared did not report a URL in 30s")


def cmd_community(args) -> None:
    """A fresh server's first community, owned by a new person, and the code that makes the operator's own AI that
    person: add Bridge at /mcp, press Allow, and give the chat the code. Everyone else starts one from their
    chat."""
    store = _store()
    owner = net.new_person(store)
    community_id, code = net.create_community(store, owner, args.name)
    print(f"{community_id}\ninvite: {_base_url()}/join/{code}\nits owner: add Bridge to your own AI at "
          f"{_base_url()}/mcp, press Allow, and say \"Use this Bridge code: "
          f"{net.link_code(store, owner, replace=True)}\" within the hour")


def cmd_code(args) -> None:
    """A code for someone who lost every connection, sent only as docs/OPERATIONS.md says: its use ends every other
    connection of theirs."""
    print(net.link_code(_store(), args.person, replace=True))


def cmd_stats(args) -> None:
    print(json.dumps(net.stats(_store()), indent=1))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="bridge", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the server; leave it open")
    serve.add_argument("--port", type=int, default=8770)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--tunnel", action="store_true", help="a throwaway public URL via cloudflared")
    serve.add_argument("--hostname", help="your own hostname, with --named-tunnel")
    serve.add_argument("--named-tunnel", dest="named_tunnel")
    serve.add_argument("--site", help="the web client's directory, served at / with its API at /api")
    serve.add_argument("--dev", action="store_true", help="on this machine only: sign in as any demo person")
    serve.set_defaults(run=cmd_serve)
    demo = commands.add_parser("demo", help="fill a new scratch BRIDGE_HOME with made-up people, for the web client")
    demo.set_defaults(run=cmd_demo)
    community = commands.add_parser("community", help="start a community with a new owner; prints both links")
    community.add_argument("name")
    community.set_defaults(run=cmd_community)
    code = commands.add_parser("code", help="a code that gives a person back their account (docs/OPERATIONS.md)")
    code.add_argument("person", help="their id, p-…")
    code.set_defaults(run=cmd_code)
    stats = commands.add_parser("stats", help="counts only: people, needs, conversations, deals, tool calls")
    stats.set_defaults(run=cmd_stats)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
