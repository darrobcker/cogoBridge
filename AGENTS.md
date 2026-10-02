# Working in this repository

For coding agents and new contributors. Read `PROTOCOL.md` first: it is short, and it is the contract.

## Map

| Path | What it is |
|---|---|
| `PROTOCOL.md` | The protocol: roles, objects, rules, operations. Normative. Change it before changing behaviour |
| `bridge/net.py` | The reference implementation of every rule. If a rule is enforced anywhere else, that is a bug |
| `bridge/guard.py` | The pre-deal text guard (rule 1) |
| `bridge/vault.py` | Locks: the keys what members write is kept under, and the keys one call holds (§5) |
| `bridge/store.py` | SQLite schema, one connection, one lock |
| `bridge/mcp_server.py` | One MCP tool per operation (`community` holds its actions); the instructions every assistant receives; what `check` renders |
| `bridge/web.py`, `templates/`, `static/` | The invite pages, the Allow page sign-in opens, the consent page and the not-found page, in plain dress; `BRIDGE_THEME` gives a server its own look. There is no other web surface, on purpose |
| `bridge/oauth.py` | Sign-in: the MCP SDK's OAuth server, answered from `net`, where its rules are |
| `bridge/notify.py` | Wake-ups: the ntfy.sh nudge, and MCP Events signed to the apps that subscribed |
| `bridge/app.py`, `cli.py` | ASGI wiring; operator commands |
| `tests/test_net.py` | One section per protocol rule. Reproductions from audits and simulations live here |
| `tests/test_surface.py` | MCP over a real port, signed in as a real client would; the pages |
| `tests/test_ops.py` | The operator's scripts, against a scratch home and a throwaway repository |
| `docs/DESIGN.md` | Why it is shaped this way, what was measured, what it does not fix |
| `docs/HOSTS.md` | What ChatGPT, Claude and Gemini let a connector do. Dated; re-verify before relying on it |
| `docs/HISTORY.md` | Designs that were tried and dropped, and why |
| `docs/OPERATIONS.md`, `scripts/`, `ops/launchd/` | How the live instance runs: deploy, backups, alerts, its LaunchAgents |

## Commands

```bash
uv sync
uv run pytest -q          # must pass, and must pass five times in a row: there are threads in it
uv run ruff check .       # must be clean
BRIDGE_HOME=/tmp/bridge-dev uv run bridge serve --port 8771
```

8770 is the live port. Once the live instance runs from `~/bridge-live` (`docs/OPERATIONS.md`), it
changes only through `scripts/deploy <commit>`, and editing this checkout changes nothing live.

## Invariants — a change that breaks one of these is wrong, whatever else it fixes

1. Before a deal, nothing returned to a member identifies a counterpart: no person id, name, contact or
   `about`. `tests/test_net.py::test_nothing_identifies_a_counterpart_before_the_deal` scans for it.
2. Nothing a member can observe depends on who else is a member, on whether someone said no, or on who is
   behind any other need or conversation. Four exceptions are named: an owner's count of who has ever
   joined their own community; whether fewer than ten people have ever joined a community; what happens
   to all of one person's things in a community at once (leaving, deleting themselves, being removed),
   including through which shared community they still reach you; and what `PROTOCOL.md` §4 does to keep a
   deal partner from aiming a removal, which can tell an owner, or a member through one, whether a deal partner
   is behind a report. The author-swap test
   (`tests/test_net.py::test_nothing_depends_on_who_wrote_an_anonymous_need`) pins the rest.
3. No model runs on the server and no API key is read. Judgment belongs to each person's own assistant.
4. Member-written text reaches any assistant, its own person's included, only through `mcp_server.said()` —
   but for the piece of it a guard refusal quotes back to its writer.
5. Every write in `net.py` runs inside `store.transaction()`, and none in a person's name writes anything once
   that person is deleted. `tests/test_net.py` finds every writer and checks both.
6. `NotYours` carries no detail. `Refused` carries a reason the caller's assistant can act on.
7. No work per call grows with the size of a community, and the server never chooses, ranks or matches:
   every member's assistant sees every need in its communities.
8. What a member writes is stored only locked, and a call holds the key of no one but the person whose connection
   it came through. Nothing reads a key from anywhere but that call. `tests/test_net.py::
   test_nothing_anyone_wrote_is_kept_readable` scans the database for it; the MCP tests run each call with its own
   keys only, so code that opened someone else's would fail there.

## Conventions

- The product and the code are both Bridge: the package and the command are `bridge`, the settings `BRIDGE_*`.
- One vocabulary everywhere — code, schema, tools, docs: person, community (with an owner), need,
  conversation, deal.
- When an audit, a simulation or a real user finds a bug: reproduce it as a test first, say in the test's
  docstring what went wrong, then fix it.
- Comments say why, not what. Docs state nothing that a code change would silently make false: no test
  counts, no line counts, and the list of operations lives only in `PROTOCOL.md`.
- The schema has a version (`store.SCHEMA_VERSION`). A schema change bumps it and ships a migration.
- Do not add a web page, an email, a score, or a server-side model without changing `docs/DESIGN.md` §6
  first, which says why each is absent.
