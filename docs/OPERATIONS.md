# Operations: running a server

A server is one process and one SQLite file. What matters is that the file survives and that its operator knows
when the server is down. This is how to keep one up on a Mac or a Linux machine behind a Cloudflare tunnel.

## How it runs

Three long-running pieces, restarted if they exit:

- the server, `~/bridge-live/.venv/bin/bridge serve --port 8770`, with `BRIDGE_BASE_URL` (the public address) and
  `BRIDGE_OPERATOR` (who runs it, named on every page because they can read everything). `~/bridge-live` is a
  detached git worktree that only `scripts/deploy` moves, so editing a checkout changes nothing live;
- `cloudflared tunnel run --url http://127.0.0.1:8770 <tunnel>`, carrying the public hostname to that port;
- `scripts/tick` from the live tree every ten minutes: backups, trimming logs, down alerts.

On a Mac these are the LaunchAgents in `ops/launchd/`; on Linux, three systemd units doing the same, with
`BRIDGE_RESTART="sudo systemctl restart <unit>"` for the deploy. Data is in `~/.bridge` (`bridge.db` with its
`-wal` and `-shm`, and the logs), backups in `~/.bridge-backups`. `/health` reads the database and answers
`{"ok": true, "version": "<commit>"}`, or 503. Settings beyond those two are in `bridge/cli.py`.

## Installing the agents on a Mac, once

```bash
mkdir -p ~/.bridge/launchd && for p in ops/launchd/*.plist; do sed -e "s|__HOME__|$HOME|g" \
  -e "s|__BASE_URL__|https://your.host|g" -e "s|__OPERATOR__|Your Name|g" \
  -e "s|__NOTIFY__|https://ntfy.sh/a-long-random-topic|g" "$p" > ~/.bridge/launchd/"$(basename "$p")"; done
tmutil addexclusion ~/.bridge ~/.bridge-backups       # backups must not outlive the 15 days members are told
cp ~/.bridge/launchd/*.plist ~/Library/LaunchAgents/ && scripts/deploy <commit>
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/bridge.tick.plist
```

## Deploying

```bash
git push && scripts/deploy <commit>
```

It refuses a commit not on `origin/main` or a tree with uncommitted changes (`--force` skips both). Then,
printing each step, it builds the commit in a throwaway worktree, runs ruff and the suite five times, opens a
copy of the live database with the new code (so a migration is rehearsed on the copy), backs up, moves
`~/bridge-live` to the commit, restarts the server, and waits for `/health` to name the commit. A failure before
the move leaves everything as it was. Deploying an older commit is the rollback; across a schema migration it
also needs a backup from before it. Deploy a safety change as its own release, and a run of them one commit at a
time, each checked live before the next: a rollback then undoes only the last.

## A theme

`BRIDGE_THEME` names a directory whose `templates/` are found before the server's own and whose `static/` is
served at `/static`: a server's own look, kept out of this repository. A theme replaces `base.html` (the frame:
fonts, colours, images) and may replace `home.html`; the other pages' words, which say who can read what before
anyone presses a button, stay the server's own. A `favicon.ico` in its `static/` replaces the server's.

## Restoring from a backup

Only when the live file is lost or damaged. Anything written after the backup is lost, including what people
deleted or stopped since: delete again anyone you learn deleted themselves since the backup.

```bash
launchctl bootout gui/$(id -u)/bridge.server &&
  mkdir -p ~/.bridge/aside && mv ~/.bridge/bridge.db* ~/.bridge/aside/ &&
  cp ~/.bridge-backups/bridge-<time>.db ~/.bridge/bridge.db &&
  chmod 600 ~/.bridge/bridge.db &&
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/bridge.server.plist
```

Move `-wal` and `-shm` aside with the database (the `*` does): a WAL left beside a restored file is replayed
into it. Delete `~/.bridge/aside` once the server answers.

## Someone who wants to start a community and has no invite

Nobody needs one: they add Bridge at the address on the home page, press Allow, and ask their AI to start a
community ("Start a Bridge community called …"), which gives them its link.

## A lost connection

A connection is whoever holds the app it is in; nothing else says who anyone is. Someone who removed Bridge
from their only app, or lost that app account, has a new, empty account the next time they add it. If they still
have Bridge working anywhere, that app gives a code (`setup` with another_app) and they need nobody. If not,
the operator makes one, `uv run bridge code <person id>` (the person found by the contact on file in a backup
from before the request), and sends it only to that contact, never in the channel the request came in; otherwise
it goes nowhere. Its use ends every other connection of theirs. A deletion asked for by someone who has lost
every connection goes the same way.

Never delete a `connectors` row: people who connected before sign-in still use their own link, and a deleted
person's row is what makes a link of theirs say so.

## Changing the hostname

A connection is tied to the address its app added. Keep the old hostname routed to the server, beside the new one,
for as long as anyone still uses it: their connections keep working there, and only people who add Bridge
afterwards use the new one. Turning the old one off makes every such person sign in again, as someone new, unless
they bring a code over. A directory listing has to be resubmitted with the new address.

## Listing in the app directories

Until Bridge is listed, the connect page has people add the address themselves: `<base>/mcp`, OAuth sign-in.
Once a listing exists, put its page in the server agent's environment and restart; the invite and connect pages
then send people there, and stop saying a computer or a paid plan is needed.

- **Claude** (`BRIDGE_CLAUDE_LISTING`, `https://claude.ai/directory/connectors/<slug>`): submit from any paid
  account at claude.ai/directory/manage. It asks for the address, the documentation (`<base>/`), the privacy
  policy (`<base>/privacy`), a test account — none is needed: a reviewer presses Allow, and an invite link to a
  community with a few needs in it shows them something — and seven policy acknowledgements. An automated review
  lists it as Community. Every tool already carries a title and a read-only or destructive hint.
- **ChatGPT** (`BRIDGE_CHATGPT_LISTING`, `https://chatgpt.com/plugins/<id>`): a plugin package (a manifest in the
  Agent Plugins format with the listing text, the four listing URLs, a logo, and five positive and three negative
  review cases) uploaded at platform.openai.com/plugins under a verified identity. The portal then shows a
  domain-verification token: put it in `BRIDGE_OPENAI_CHALLENGE`, restart, and it is served at
  `/.well-known/openai-apps-challenge`. Connect the MCP server there (OAuth; it registers itself) and let it scan
  the tools; its one event, `waiting`, shows beside them. Review also needs a demo video and sign-in instructions
  for the reviewer: "no credentials: press Allow". The listing URLs are `/`, `/#help` (which shows `BRIDGE_CONTACT`
  if set), `/privacy` and `/terms`. A person reviews it, and it must suit 13–17-year-olds. To try being woken: in a
  chat, say "Watch Bridge" and what to do; someone else's reply then wakes that chat.

## What tick does

- Runs `scripts/backup` when the newest backup is over a day old, and deletes its backups older than 14 days
  (the consent page says 15: a day's margin for a machine that was off).
- Trims `server.log`, `tunnel.log` and `tick.log` to their last megabyte once one passes 5 MB.
- With `BRIDGE_OPERATOR_NOTIFY` set: after two failed checks of the public `/health` in a row, posts
  one line there, at most hourly, and one when it answers again; also when a backup fails.

A machine that is off sends nothing. The ntfy lines say only up, down, or that a backup failed.

## The ntfy budget

Members' nudges and the alerts above all go to ntfy.sh from the server's machine. Its free tier allows 250
messages a day per IP, and a free account shares that limit (ntfy issues #1963 and #1726). `bridge stats` shows
the day's nudges (`nudges_today`). Two accounts replying to each other every ten minutes can pass 250 a day on
their own, and the down alert is then lost with the rest. Before members' nudges near 200 a day, move the
operator's alerts elsewhere, and pay for a tier or run ntfy yourself.