"""SQLite: the schema, one connection, one lock.

One connection is shared by the web event loop and the MCP SDK's worker threads. Two threads inside
`BEGIN` on one connection raise, and interleaved reads return rows that are not there — so every
statement takes the lock, and every command that reads before it writes runs inside `transaction()`.
At this scale serialising is free; being subtly wrong is not.
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

SCHEMA_VERSION = 9

# Sign-in (OAuth, PROTOCOL.md §5).
SIGN_IN = """
-- One per connection: an app its person signed in from. `person_id` is '' until the app's first tool call, which
-- makes the person. `invite`: the community whose invite page sent them to Allow, joined at that call, and
-- `invite_key` its key; `person_key` the person's private key. Both locked under the connection's renewal token.
CREATE TABLE grants (
  id TEXT PRIMARY KEY, client_id TEXT NOT NULL, person_id TEXT NOT NULL DEFAULT '', invite TEXT NOT NULL DEFAULT '',
  created_t REAL NOT NULL, revoked_t REAL, invite_key TEXT NOT NULL DEFAULT '', person_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX grants_by_person ON grants(person_id, revoked_t);
-- Hashed, each of: a sign-in waiting on the Allow page (`request`), an authorization code (`code`), an access or a
-- renewal token (`access`, `refresh`), an app's subscription to be woken (`subscription`, by its id). `data`: what the
-- next step needs, as JSON.
CREATE TABLE tokens (
  hash TEXT PRIMARY KEY, kind TEXT NOT NULL, grant_id TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '',
  created_t REAL NOT NULL, expires_t REAL
);
CREATE INDEX tokens_by_grant ON tokens(grant_id);
-- Apps registered for sign-in (RFC 7591), as the MCP SDK describes them.
CREATE TABLE clients (id TEXT PRIMARY KEY, info TEXT NOT NULL, created_t REAL NOT NULL);
-- A code from the chat, hashed, that makes another connection this person's. `replace`: its use ends every other.
-- `person_key`: their private key, locked under the code; empty in one the operator made, who holds no key.
CREATE TABLE link_codes (
  hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, replace INTEGER NOT NULL, created_t REAL NOT NULL, used_t REAL,
  person_key TEXT NOT NULL DEFAULT ''
);
-- Counts per day: people whose first community this is (`joins g-…`), people made with no invite (`uninvited`).
CREATE TABLE daily (k TEXT NOT NULL, day INTEGER NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (k, day));
"""

# From each older version to the next, applied in order when a database is opened: `{version: script}`, each script
# ending with the next version's `PRAGMA user_version`, or a function of the connection that does the same: 8 → 9,
# which locks everything, is `net._lock_everything`, registered by net. This repository starts at version 7.
MIGRATIONS: dict[int, str | Callable[[sqlite3.Connection], None]] = {
    # 7 → 8: a conversation holds any number of people, each by the need that brought them in or as its starter.
    # A two-person conversation becomes its responder, the starter, in seat 1 and the need's author in seat 2; a yes
    # given then was given with both of them in it.
    7: """
BEGIN;
CREATE TABLE conversations8 (
  id TEXT PRIMARY KEY, starter_id TEXT NOT NULL, created_t REAL NOT NULL, last_t REAL NOT NULL, deal_t REAL
);
INSERT INTO conversations8 SELECT id, responder_id, created_t, last_t, deal_t FROM conversations;
CREATE TABLE conversation_needs (
  conversation_id TEXT NOT NULL, need_id TEXT NOT NULL, author_id TEXT NOT NULL, via TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (conversation_id, need_id)
);
INSERT INTO conversation_needs SELECT id, need_id, author_id, via FROM conversations;
CREATE TABLE conversation_people (
  conversation_id TEXT NOT NULL, person_id TEXT NOT NULL, seat INTEGER NOT NULL, yes_t REAL, yes_in TEXT NOT NULL
  DEFAULT '', passed_t REAL, dealt INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (conversation_id, person_id)
);
INSERT INTO conversation_people SELECT id, responder_id, 1, responder_yes_t, '1,2', responder_passed_t,
  deal_t IS NOT NULL FROM conversations;
INSERT INTO conversation_people SELECT id, author_id, 2, author_yes_t, '1,2', author_passed_t,
  deal_t IS NOT NULL FROM conversations;
DROP TABLE conversations;
ALTER TABLE conversations8 RENAME TO conversations;
CREATE INDEX conversations_by_starter ON conversations(starter_id, last_t);
CREATE INDEX conversation_needs_by_need ON conversation_needs(need_id);
CREATE INDEX conversation_people_by_person ON conversation_people(person_id);
ALTER TABLE reports ADD COLUMN seat INTEGER NOT NULL DEFAULT 0;
PRAGMA user_version=8;
COMMIT;
""",
}


SCHEMA = """
-- `name` and `contact` are shown to one person only: the other side of a deal. `about` is never shown
-- to anyone; it is the person's own assistant's notes, read back to it and nothing else. All three are locked under
-- the person's own key (bridge/vault.py); `public` is the half anyone may seal to them with.
-- `notify`: the ntfy.sh topic the server made for their nudges, if they asked for one; `nudged_t`: the last sent.
-- The server sends to it with nobody's connection behind the call, so it is kept as it is.
CREATE TABLE people (
  id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
  about TEXT NOT NULL DEFAULT '', created_t REAL NOT NULL, deleted_t REAL,
  notify TEXT NOT NULL DEFAULT '', nudged_t REAL, public TEXT NOT NULL DEFAULT ''
);
-- A person's key from before locks, for the connections they already had: each takes its own copy at its next
-- use, and this goes when they all have, or at `until_t`. The only key kept open.
CREATE TABLE escrow (person_id TEXT PRIMARY KEY, private TEXT NOT NULL, until_t REAL NOT NULL);
-- The secret in a person's own connector URL, hashed: how people connected before sign-in (PROTOCOL.md §5).
-- Nothing makes a new one but the operator's and the simulations' own tools.
CREATE TABLE connectors (
  secret_hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, created_t REAL NOT NULL, revoked_t REAL,
  person_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX connectors_by_person ON connectors(person_id, revoked_t);
-- `created_by` owns the community: only they replace the invite link or remove someone. Its name, and its invite
-- code (any member may pass the link on), are locked under its key; the key under the code, which is how a
-- newcomer gets it; the code is found by `invite_hash`.
CREATE TABLE communities (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_by TEXT NOT NULL, invite_hash TEXT NOT NULL UNIQUE,
  invite_code TEXT NOT NULL, link_key TEXT NOT NULL, created_t REAL NOT NULL
);
-- `banned_t`: removed by the owner; the invite link no longer lets them back in. `key`: the community's key, sealed
-- to this member.
CREATE TABLE memberships (
  person_id TEXT NOT NULL, community_id TEXT NOT NULL, joined_t REAL NOT NULL, left_t REAL, banned_t REAL,
  key TEXT NOT NULL DEFAULT '', PRIMARY KEY (person_id, community_id)
);
CREATE INDEX memberships_by_community ON memberships(community_id, left_t);
-- What someone's assistant sent out. Its author is shown to nobody. `wants`: how many deals fill it; 0 means none do. A
-- full need reaches nobody new and stays open, conversations and all, until its author closes it or it expires.
-- `deals`: how many it has had, kept here because the conversations themselves are deleted long before a
-- year-long need ends.
-- `text` is locked under the need's key, which is sealed to its author (`author_key`) and locked under each
-- community's it was sent to; `same` marks its words for its author alone, so it is not sent twice.
CREATE TABLE needs (
  id TEXT PRIMARY KEY, author_id TEXT NOT NULL, text TEXT NOT NULL,
  created_t REAL NOT NULL, expires_t REAL NOT NULL, closed_t REAL,
  wants INTEGER NOT NULL DEFAULT 1, deals INTEGER NOT NULL DEFAULT 0,
  author_key TEXT NOT NULL DEFAULT '', same TEXT NOT NULL DEFAULT ''
);
CREATE INDEX needs_by_author ON needs(author_id, created_t);
CREATE TABLE need_communities (
  need_id TEXT NOT NULL, community_id TEXT NOT NULL, key TEXT NOT NULL DEFAULT '', PRIMARY KEY (need_id, community_id)
);
CREATE INDEX need_communities_by_community ON need_communities(community_id);
-- Every member's assistant sees every open need in their communities. A pass says "not for us": it
-- hides the need from that one assistant and is reported to nobody.
CREATE TABLE passes (
  need_id TEXT NOT NULL, person_id TEXT NOT NULL, t REAL NOT NULL, PRIMARY KEY (need_id, person_id)
);
-- People, none named to the others, whose assistants are talking about one need or several. Its starter opened
-- it on needs that reached them; each need's author is in it by that need. `last_t`: when someone last answered
-- someone else; a second message before an answer does not move it, so a week unanswered ends it.
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, starter_id TEXT NOT NULL, created_t REAL NOT NULL, last_t REAL NOT NULL, deal_t REAL
);
CREATE INDEX conversations_by_starter ON conversations(starter_id, last_t);
-- The needs a conversation was opened on. `via`: the community its starter saw that need through, fixed when it
-- opens. The starter and that need's author are shown it, and an owner can act between those two only there.
CREATE TABLE conversation_needs (
  conversation_id TEXT NOT NULL, need_id TEXT NOT NULL, author_id TEXT NOT NULL, via TEXT NOT NULL DEFAULT '',
  key TEXT NOT NULL DEFAULT '', PRIMARY KEY (conversation_id, need_id)
);
CREATE INDEX conversation_needs_by_need ON conversation_needs(need_id);
-- Everyone in a conversation, by seat: its starter is 1. A yes is to the conversation as it stands: any message
-- clears every one, and `yes_in` is who was still in it when it was given, so one given before someone went no
-- longer counts. `dealt`: in it, with a yes, when it became a deal; each such person has the others' names.
-- `key`: the conversation's, sealed to them; its messages, and the needs it is on (`conversation_needs.key`), open
-- with it.
CREATE TABLE conversation_people (
  conversation_id TEXT NOT NULL, person_id TEXT NOT NULL, seat INTEGER NOT NULL, yes_t REAL, yes_in TEXT NOT NULL
  DEFAULT '', passed_t REAL, dealt INTEGER NOT NULL DEFAULT 0, key TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (conversation_id, person_id)
);
CREATE INDEX conversation_people_by_person ON conversation_people(person_id);
-- A person's name and contact, sealed at their yes to each other person in the conversation, shown only once it is
-- a deal: nobody else's connection is behind the call that makes one, so each hands theirs over when they say yes.
CREATE TABLE reveals (
  conversation_id TEXT NOT NULL, from_id TEXT NOT NULL, to_id TEXT NOT NULL, sealed TEXT NOT NULL,
  PRIMARY KEY (conversation_id, from_id, to_id)
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, sender_id TEXT NOT NULL, text TEXT NOT NULL,
  t REAL NOT NULL
);
CREATE INDEX messages_by_conversation ON messages(conversation_id, id);
CREATE INDEX messages_by_sender ON messages(sender_id, t);
-- A member reporting a need, or someone in a conversation (by `seat`), to the owner of the community it came
-- through. The owner is shown what the reported side wrote, never who either of them is.
CREATE TABLE reports (
  id TEXT PRIMARY KEY, community_id TEXT NOT NULL, reporter_id TEXT NOT NULL, reported_id TEXT NOT NULL,
  need_id TEXT NOT NULL DEFAULT '', conversation_id TEXT NOT NULL DEFAULT '', t REAL NOT NULL, closed_t REAL,
  seat INTEGER NOT NULL DEFAULT 0, key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX reports_by_community ON reports(community_id, closed_t);
CREATE INDEX reports_by_reporter ON reports(reporter_id, t);
-- One row per tool call: who, which tool, when. No arguments, no text. And one per Join press on an invite
-- page: person '', tool "join-page <ai> <community id>".
CREATE TABLE calls (t REAL NOT NULL, person_id TEXT NOT NULL, tool TEXT NOT NULL);
CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
""" + SIGN_IN


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        # Deleted rows otherwise stay as bytes in free pages, which every backup copies whole: forget_me would
        # reach backups long after the 15 days members are told (review).
        self.db.execute("PRAGMA secure_delete=ON")
        self._lock = threading.RLock()
        self._depth = 0
        self._clock: Callable[[], float] = time.time
        # Called with the ntfy.sh topic the server made for them, after something aimed at them is committed; and with
        # each subscription of an app that asked to be woken for them.
        self.on_nudge: Callable[[str], None] | None = None
        self.on_wake: Callable[[dict], None] | None = None
        self._create_or_check()

    def _create_or_check(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        empty = not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        if empty:
            self.db.executescript(SCHEMA)
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            return
        if version < SCHEMA_VERSION:
            # A migration that needs the rules' code registers itself there: a Store opened on its own, as the deploy's
            # rehearsal does, found none and refused the live database (2026-10-02).
            from . import net  # noqa: F401
        while version < SCHEMA_VERSION and version in MIGRATIONS:
            step = MIGRATIONS[version]
            step(self.db) if callable(step) else self.db.executescript(step)
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"{self.path} has schema version {version}; this code needs "
                               f"{SCHEMA_VERSION}. Move the file aside, or migrate it.")

    # -- clock (tests inject a fake one) ----------------------------------------------------------
    def now(self) -> float:
        return self._clock()

    def set_clock(self, fn: Callable[[], float]) -> None:
        self._clock = fn

    # -- transactions -----------------------------------------------------------------------------
    @contextlib.contextmanager
    def transaction(self):
        """One writer at a time, and read-then-write is atomic. Re-entrant: a command called from
        inside another joins the transaction already open."""
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self.db.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            finally:
                self._depth = 0

    def empty_log(self) -> None:
        """Copy the write-ahead log into the file and empty it, so pages a deletion replaced are not left in it: a
        checkpoint reuses the log but never empties it (review). Never waits: behind a backup's read it waited
        five seconds holding the lock every call takes; the next one empties it then. Only outside a transaction,
        whose pages are not in the file yet."""
        with self._lock:
            if self._depth:
                return
            wait = self.db.execute("PRAGMA busy_timeout").fetchone()[0]
            self.db.execute("PRAGMA busy_timeout=0")
            try:
                self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            finally:
                self.db.execute(f"PRAGMA busy_timeout={int(wait)}")

    # -- statements -------------------------------------------------------------------------------
    def one(self, sql: str, *args) -> sqlite3.Row | None:
        with self._lock:
            return self.db.execute(sql, args).fetchone()

    def all(self, sql: str, *args) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    def exec(self, sql: str, *args) -> sqlite3.Cursor:
        with self._lock:
            return self.db.execute(sql, args)
