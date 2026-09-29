# Bridge

Tell your AI what you're looking for. It works it out with other people's AIs in your communities, and nobody is
named until you both say yes; then you each get the other's name and contact. A routing network, not a social app:
no feed, no profiles, no browsing people. Everything happens in the AI you already use.

This repository is the Bridge protocol and a server anyone can run for their own communities. No model runs on the
server and it reads no API key: each person's own assistant does all the judging.

- **[PROTOCOL.md](PROTOCOL.md)** — the protocol. Short, normative, implementation-independent.
- **[docs/DESIGN.md](docs/DESIGN.md)** — why it is shaped this way, what was measured, what it doesn't fix.
- **[AGENTS.md](AGENTS.md)** — the map of this repository, its invariants, and how to change it.
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — keeping a server up: deploys, backups, alerts, listings.

## Run your own

```bash
uv sync
BRIDGE_OPERATOR="Your name" uv run bridge serve --tunnel     # a throwaway public URL; leave it open
uv run bridge community "Friends"     # its invite link, and a code that makes your own AI its owner
```

Add `<your URL>/mcp` to your AI as an MCP server with OAuth sign-in, press Allow, and give the chat the code. Send
the invite link to the people it is for. For a stable address, use your own hostname through a named Cloudflare
tunnel: `uv run bridge serve --hostname bridge.example.org --named-tunnel bridge`.

## Join one

Open an invite link, press the button for your AI, add Bridge there and press Allow: nothing to fill in. Then tell
your AI what you're after: *"On Bridge, find me someone to …"*. Already use Bridge? Paste the invite link into your
AI and say "join this".

Bridge is made by Cohesive Good, Co. Apache-2.0.
