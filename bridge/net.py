"""The network: people's own assistants working things out for them, unnamed, inside communities.

This module is the reference implementation of PROTOCOL.md, and the only place its rules live. Someone
tells their assistant "go"; it sends a need to their communities; every other member's assistant sees
it; one replies, which opens a conversation between two people who are not named to each other; when
each person has told their own assistant yes, it is a deal and each is shown the other's name and
contact. Nothing else is ever revealed.

Every function takes the acting person's id and raises `Refused` (with a reason that person's assistant
can act on) or `NotYours` (which says nothing about whether the thing exists).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from pathlib import Path

from . import guard
from .store import Store

NEED_TTL_S = 7 * 86400            # a need stops reaching people after a week, unless its author said otherwise
MIN_DAYS, MAX_DAYS = 0.04, 365    # an hour ("someone at the station now") to a year (a standing offer)
MAX_PEOPLE = 10_000
QUIET_TTL_S = 7 * 86400           # a conversation in which nobody has answered for a week is over
DEAL_SHOWN_S = 30 * 86400         # how long `check` keeps showing a deal
RETAIN_S = 90 * 86400             # ended conversations and closed needs are deleted after this
NEEDS_SHOWN = 20                  # newest open needs `check` lists at once
MESSAGES_SHOWN = 12               # of a conversation where it is their turn
MESSAGES_WAITING = 4              # of one waiting on the other side: nothing to act on, read on every check
NEEDS_PER_DAY = 10
MESSAGES_PER_DAY = 200            # one member cannot flood another, or the lock everyone shares
UNANSWERED = 3                    # messages one person may send in a row before anyone else answers
MAX_IN = 10                       # people in one conversation: its starter, and the authors of the needs it is on
REPORTS_PER_DAY = 10              # nor fill an owner's check with reports (#24)
SMALL = 10                        # under this many ever joined, a community's members may well guess who wrote a need
JOINS_PER_DAY = 100               # people a day for whom a community is their first; the link is the trust boundary
UNINVITED_PER_DAY = 1000          # people a day made with no invite to join: anyone can sign in
APPS_PER_DAY = 1000               # apps registering for sign-in a day, each a row until the sweep
INVITE_CODE = 14                  # characters (69 bits) of an invite code
ACCESS_S = 7 * 86400              # an access token; the renewal token that replaces it never expires (PROTOCOL.md §5)
REQUEST_S = 900                   # a sign-in waiting on the Allow page
AUTH_CODE_S = 300                 # an authorization code, between Allow and the app's token request
LINK_CODE_S = 3600                # a code from the chat that joins another connection to its person
LINK_CODE = 12                    # characters (59 bits) of one, typed by hand from one app into another
WAKE_S = 30 * 86400               # the longest an app's subscription to be woken lasts before it renews it
MAX_TEXT, MAX_NAME, MAX_CONTACT = 2000, 80, 200
NUDGE_EVERY_S = 600               # at most one nudge per person per ten minutes
NTFY = "https://ntfy.sh/"         # where every nudge goes: a topic the server made, never an address a member chose


def nudges_on(notify: str) -> bool:
    """A bare ntfy.sh topic, as the server makes them. A value from before with a query, such as ?email=, had
    ntfy.sh forward the line to an address a member chose (review 3); a plain topic from before still works."""
    return bool(re.fullmatch(re.escape(NTFY) + r"[A-Za-z0-9_-]{1,64}", notify))


class Refused(Exception):
    """The caller's own request cannot be done; the message is written for their assistant to read."""


class NotYours(Exception):
    """Not theirs, or not there. Reported identically, so it says nothing about what exists."""


# -- small things ----------------------------------------------------------------------------------

def open_store(path: str | Path = ":memory:") -> Store:
    return Store(path)


# Ids are copied by hand, by models: short, lowercase, and without characters that look alike.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _new_id(store: Store, table: str, prefix: str, length: int = 8) -> str:
    while True:
        ref = f"{prefix}-" + "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not store.one(f"SELECT 1 FROM {table} WHERE id=?", ref):
            return ref


def _ref(raw: str) -> str:
    """An id as an assistant may hand it back: bracketed, padded, or in the wrong case."""
    return raw.strip().strip("[]").lower()


def _seat_ref(raw: str) -> tuple[str, int | None]:
    """A conversation id, and the number of one person in it when one is given after a colon: c-…:2."""
    head, _, seat = _ref(raw).partition(":")
    return head.strip(), int(seat) if seat.strip().isdigit() else None


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def shown(text: str) -> str:
    """Member text as said() shows it inside the fence: read as a reader sees it, blank lines dropped, and every
    line after the first marked. Kept here, once, because the limits count it: each counted its own copy of
    said()'s rule, right only while the two matched (review)."""
    return "\n| ".join(line for line in guard.visible(text).splitlines() if line.strip())


def _measured(text: str, what: str, limit: int, then: str = "") -> int:
    """Its length as shown, once it is within the limit both as written and as shown."""
    # As written first: counted only as shown, a need could carry a million zero-width spaces (review), and
    # folding a refused megabyte took seconds and, in `setup`, held the store's lock throughout (review).
    if len(text) > limit:
        raise Refused(f"{what} is {len(text)} characters written, invisible ones included; keep it to at most "
                      f"{limit}{then}")
    # As shown too: one U+FDFA folds to eighteen characters, and one-letter lines each take a line mark, so text
    # within the limit as written showed at many times it in every member's check and pushed others out (review).
    n = len(shown(text))
    if n > limit:
        raise Refused(f"{what} is {n} characters as shown; keep it to at most {limit}. An ellipsis … is three "
                      f"and each line after the first two more{then}")
    return n


def _text(raw: str, what: str, limit: int = MAX_TEXT) -> str:
    text = raw.strip()
    if not _measured(text, what, limit):
        # A name and a contact of zero-width spaces completed a deal that handed back nothing (review).
        raise Refused(f"{what} is empty")
    return text


def _unidentifying(store: Store, person_id: str, text: str) -> None:
    me = store.one("SELECT name, contact FROM people WHERE id=?", person_id)
    hit = guard.identifies(text, me["name"], me["contact"])
    if hit and hit.lower() in guard.name_words(me["name"]):
        # Someone named Sunday or Park could not tell why a weekday or a place was refused (audit).
        raise Refused(f"that would identify someone: {hit!r} is your person's own name. If here it is a word, a "
                      "day or a place and not them, write it another way; otherwise describe instead.")
    if hit:
        raise Refused(f"that would identify someone or gives a way to reach them ({hit!r}). Names, "
                      "contacts and links stay out until both people say yes; describe instead.")


def _community_name(raw: str) -> str:
    """Every member and the invite page see it before any deal, so it carries no contact (rule 1); its owner's own
    name may stay, since that is how friends find a community of theirs."""
    name = _text(raw, "the name", 120)
    hit = guard.identifies(name)
    if hit:
        raise Refused(f"a community's name is shown to every member and on its invite page, so it cannot carry a "
                      f"contact or a link ({hit!r}); name it for what it is")
    return name


def alive(store: Store, person_id: str) -> bool:
    return bool(store.one("SELECT 1 FROM people WHERE id=? AND deleted_t IS NULL", person_id))


def _acting(store: Store, person_id: str) -> None:
    """Deleting is final: a call already in flight when its person was erased writes nothing."""
    if not alive(store, person_id):
        raise NotYours()


# -- people ----------------------------------------------------------------------------------------

def new_person(store: Store) -> str:
    with store.transaction():
        pid = _new_id(store, "people", "p", 16)
        store.exec("INSERT INTO people(id, created_t) VALUES (?,?)", pid, store.now())
    return pid


NEW, TESTED, TOO_SOON, OFF = "new", "tested", "too soon", "off"


def setup(store: Store, person_id: str, *, name: str | None = None, contact: str | None = None,
          about: str | None = None, notify: str | None = None) -> str | None:
    """Any of them, whenever. Name and contact are shown only to the other side of a deal. `notify` "on": the
    first time, an unguessable ntfy.sh topic for their nudges (NEW); after that, a test nudge to it (TESTED, or
    TOO_SOON within a day of any nudge). "off" clears it, so a later "on" makes a new one. Returns what `notify` did."""
    if notify is not None:
        notify = {"none": "off"}.get(notify.strip().lower(), notify.strip().lower())
        if notify not in ("on", "off"):
            raise Refused('nudges take notify="on" now (or "off"): the server makes the address. If your tool list '
                          "says to pass a link, it is out of date: in ChatGPT, Settings → Apps → Bridge → "
                          "Refresh; in Claude, a new chat. Nothing was saved: send the other fields again without "
                          'notify, or with notify="on"')
    outcome = None
    with store.transaction():
        _acting(store, person_id)
        if name is not None:
            store.exec("UPDATE people SET name=? WHERE id=?", _text(name, "the name", MAX_NAME), person_id)
        if contact is not None:
            store.exec("UPDATE people SET contact=? WHERE id=?", _text(contact, "the contact", MAX_CONTACT),
                       person_id)
        if about is not None:
            # Refused, never cut: a cut dropped the rules added last and still said "saved" (audit #19).
            about = about.strip()
            if about.startswith("<<<") and about.endswith(">>>"):
                # Copied out of `check` whole, the notes gained a mark on every line at every save (review).
                about = about[3:-3].replace("\n| ", "\n")
            # Notes that show as nothing are none: kept, `check` showed an empty fence as notes to follow (review).
            if not _measured(about, "`about`", MAX_TEXT, ". Nothing was saved: shorten the notes, keeping every "
                             "rule your person gave, and send them all again"):
                about = ""
            store.exec("UPDATE people SET about=? WHERE id=?", about, person_id)
        if notify == "off":
            store.exec("UPDATE people SET notify='' WHERE id=?", person_id)
            outcome = OFF
        elif notify == "on" and not nudges_on(store.one("SELECT notify FROM people WHERE id=?", person_id)["notify"]):
            # 26 of the id alphabet, about 128 bits: typed by hand into the phone app, often off a computer's screen.
            topic = "".join(secrets.choice(_ALPHABET) for _ in range(26))
            store.exec("UPDATE people SET notify=? WHERE id=?", NTFY + topic, person_id)
            outcome = NEW
    if notify == "on" and not outcome:
        # The only nudge a person can set off with nothing aimed at them, so the only one held to a day (review).
        outcome = TESTED if _nudge(store, person_id, every=86400, test=True) else TOO_SOON
    return outcome


def _nudge(store: Store, *people: str, every: float = NUDGE_EVERY_S, test: bool = False) -> int:
    """After a commit: tell whoever asked for it that something is waiting — at their ntfy.sh topic, and to each app
    that subscribed to be woken for them (PROTOCOL.md §5). Never what or who, and never for a yes, which the other
    side must not learn of; one limit for all of a person's wake-ups together. A `test` goes to the topic alone.
    Each is logged, with nobody's id, so stats can show the day's count against ntfy.sh's limit. Returns how many
    people were woken."""
    sent = 0
    for pid in people:
        with store.transaction():
            p = store.one("SELECT notify, nudged_t, deleted_t FROM people WHERE id=?", pid)
            if not p or p["deleted_t"] or (p["nudged_t"] or 0) > store.now() - every:
                continue
            topic = p["notify"] if nudges_on(p["notify"]) else ""
            apps = [] if test else [json.loads(r["data"]) for r in store.all(
                "SELECT t.data FROM tokens t JOIN grants g ON g.id=t.grant_id WHERE t.kind='subscription' AND "
                "g.person_id=? AND g.revoked_t IS NULL AND t.expires_t>?", pid, store.now())]
            if not (topic or apps):
                continue
            store.exec("UPDATE people SET nudged_t=? WHERE id=?", store.now(), pid)
            for what in (["nudge"] if topic else []) + ["wake"] * len(apps):
                log_call(store, what)
        if topic and store.on_nudge:
            store.on_nudge(topic)
        for app in apps:
            if store.on_wake:
                store.on_wake(app)
        sent += 1
    return sent


def me(store: Store, person_id: str) -> dict:
    """The person as their own assistant sees them. For each community, whether it is small; for one they own,
    how many others have joined it: a count, never names."""
    p = store.one("SELECT name, contact, about, notify FROM people WHERE id=?", person_id)
    communities = []
    for c in store.all("SELECT c.id, c.name, c.created_by=? owner FROM communities c JOIN memberships m "
                       "ON m.community_id=c.id WHERE m.person_id=? AND m.left_t IS NULL ORDER BY m.joined_t, m.rowid",
                       person_id, person_id):
        item = {"id": c["id"], "name": c["name"], "owner": bool(c["owner"]), "small": small(store, c["id"])}
        if c["owner"]:
            # Everyone who ever joined, not who is in now: a count that dropped when an owner removed someone
            # by a need told them whether its anonymous author was still a member, and one that dropped as a
            # need vanished told them its author had left (review). No count of removals: a second removal
            # that did not move it said two things had one author (rethink).
            item["joined"] = store.one("SELECT COUNT(*) n FROM memberships WHERE community_id=? AND person_id<>?",
                                       c["id"], person_id)["n"]
        communities.append(item)
    return {**dict(p), "communities": communities}


def small(store: Store, community_id: str) -> bool:
    """Fewer than SMALL people have ever joined. Every membership row ever, so it moves only at someone's first
    join there, once: leaving, removal and deletion keep their rows. Counted no further than SMALL, so it costs
    the same at any size."""
    return store.one("SELECT COUNT(*) n FROM (SELECT 1 FROM memberships WHERE community_id=? LIMIT ?)",
                     community_id, SMALL)["n"] < SMALL


def person_for_connector(store: Store, secret: str, tool: str, *, operator: str = "") -> str:
    """Whose connector URL this is, with the call logged. It never makes anyone. `operator` is whom to tell about a
    link that someone else ended."""
    with store.transaction():
        # LEFT JOIN, so a row whose person is gone refuses rather than resolving to someone who is not there.
        r = store.one("SELECT c.person_id, c.revoked_t, p.id pid, p.deleted_t FROM connectors c "
                      "LEFT JOIN people p ON p.id=c.person_id WHERE c.secret_hash=?", _hash(secret))
        if not r or not r["pid"]:
            raise Refused("this connector link is not one this server knows. Remove it from the AI's settings, then "
                          "open an invite link and add Bridge the way its page says.")
        gone = r["deleted_t"]
        # Only a link that was working when they left says so: a copy ended earlier learns nothing (review).
        if gone and (r["revoked_t"] is None or r["revoked_t"] >= gone):
            raise Refused(_DELETED)
        if r["revoked_t"] is not None:
            raise Refused("this connector link was ended from the chat (a code for a new Bridge connection was "
                          "used) and no longer works. If your person did not ask for that, someone else had their "
                          f"access: they should write to {operator or 'whoever runs this server'}.")
        store.exec("INSERT INTO calls(t, person_id, tool) VALUES (?,?,?)", store.now(), r["person_id"], tool)
    return r["person_id"]


# "Open your invite link again" read as a way back, and would have made someone new (simulation).
_DELETED = ("your person deleted everything about themselves from Bridge, so this connection no longer works. To "
            "start over as someone new, remove Bridge from the AI's settings, then add it again from an invite "
            "link.")


# -- connections: signing in (PROTOCOL.md §5) -----------------------------------------------------------------------

def _day(store: Store) -> int:
    return int(store.now() // 86400)


def _today(store: Store, k: str) -> int:
    row = store.one("SELECT n FROM daily WHERE k=? AND day=?", k, _day(store))
    return row["n"] if row else 0


def _count(store: Store, k: str) -> None:
    store.exec("INSERT INTO daily(k, day, n) VALUES (?,?,1) ON CONFLICT(k, day) DO UPDATE SET n=n+1", k, _day(store))


def register_client(store: Store, client_id: str, info: str) -> None:
    """An app registering for sign-in (RFC 7591). Anyone may, so a day's registrations are capped: each is a row
    until the sweep takes the ones that never connected."""
    with store.transaction():
        if _today(store, "apps") >= APPS_PER_DAY:
            raise Refused("too many apps registered today; try again tomorrow")
        _count(store, "apps")
        store.exec("INSERT OR REPLACE INTO clients(id, info, created_t) VALUES (?,?,?)", client_id, info, store.now())


def client(store: Store, client_id: str) -> str | None:
    row = store.one("SELECT info FROM clients WHERE id=?", client_id)
    return row["info"] if row else None


def _token(store: Store, kind: str, *, grant_id: str = "", data: dict | None = None,
           expires_t: float | None = None) -> str:
    token = secrets.token_urlsafe(32)
    store.exec("INSERT INTO tokens(hash, kind, grant_id, data, created_t, expires_t) VALUES (?,?,?,?,?,?)",
               _hash(token), kind, grant_id, json.dumps(data or {}), store.now(), expires_t)
    return token


def _live_token(store: Store, token: str, kind: str):
    """The row, while it lasts and its connection has not ended."""
    return store.one("SELECT t.*, g.client_id, g.revoked_t FROM tokens t LEFT JOIN grants g ON g.id=t.grant_id "
                     "WHERE t.hash=? AND t.kind=? AND (t.expires_t IS NULL OR t.expires_t>?) AND "
                     "(t.grant_id='' OR (g.id IS NOT NULL AND g.revoked_t IS NULL))", _hash(token), kind, store.now())


def sign_in_request(store: Store, data: dict) -> str:
    """A sign-in an app started, waiting on its person's Allow; `data` is what the authorization code will need."""
    with store.transaction():
        return _token(store, "request", data=data, expires_t=store.now() + REQUEST_S)


def sign_in_waiting(store: Store, request: str) -> dict | None:
    row = _live_token(store, request, "request")
    return json.loads(row["data"]) if row else None


def allow(store: Store, request: str, invite: str = "") -> tuple[dict, str] | None:
    """Allow pressed: a new connection, and an authorization code for its app. `invite` is the code the invite page
    left in this browser; only a community's current one is kept. It makes nobody: the connection's first tool call
    does (One door)."""
    with store.transaction():
        row = _live_token(store, request, "request")
        if not row:
            return None
        store.exec("DELETE FROM tokens WHERE hash=?", row["hash"])
        data = json.loads(row["data"])
        found = store.one("SELECT invite_code FROM communities WHERE invite_code=?", invite[:40]) if invite else None
        grant = _new_id(store, "grants", "k", 16)
        store.exec("INSERT INTO grants(id, client_id, invite, created_t) VALUES (?,?,?,?)", grant, data["client_id"],
                   found["invite_code"] if found else "", store.now())
        return data, _token(store, "code", grant_id=grant, data=data, expires_t=store.now() + AUTH_CODE_S)


def deny(store: Store, request: str) -> dict | None:
    with store.transaction():
        row = _live_token(store, request, "request")
        if row:
            store.exec("DELETE FROM tokens WHERE hash=?", row["hash"])
        return json.loads(row["data"]) if row else None


def authorization_code(store: Store, code: str) -> dict | None:
    row = _live_token(store, code, "code")
    return {**json.loads(row["data"]), "grant": row["grant_id"], "expires_t": row["expires_t"]} if row else None


def _access_token(store: Store, grant_id: str, scopes: list[str]) -> str:
    return _token(store, "access", grant_id=grant_id, data={"scopes": scopes}, expires_t=store.now() + ACCESS_S)


def exchange_code(store: Store, code: str) -> tuple[str, str] | None:
    """An authorization code for an access token and the renewal token that replaces it, once."""
    with store.transaction():
        row = _live_token(store, code, "code")
        if not row:
            return None
        store.exec("DELETE FROM tokens WHERE hash=?", row["hash"])
        scopes = json.loads(row["data"]).get("scopes") or []
        return (_access_token(store, row["grant_id"], scopes),
                _token(store, "refresh", grant_id=row["grant_id"], data={"scopes": scopes}))


def renewal(store: Store, token: str) -> dict | None:
    row = _live_token(store, token, "refresh")
    return {"grant": row["grant_id"], "client_id": row["client_id"], **json.loads(row["data"])} if row else None


def renew(store: Store, token: str) -> tuple[str, str] | None:
    """A fresh access token, and the same renewal token back. It is not replaced: an app that renews twice at once,
    or loses the answer, would then hold a dead one and sign in again, which makes someone new (PROTOCOL.md §5).
    Ending the connection ends it."""
    with store.transaction():
        row = _live_token(store, token, "refresh")
        if not row:
            return None
        return _access_token(store, row["grant_id"], json.loads(row["data"]).get("scopes") or []), token


def access(store: Store, token: str) -> dict | None:
    """The connection behind an access token."""
    row = _live_token(store, token, "access")
    if not row:
        return None
    return {"grant": row["grant_id"], "client_id": row["client_id"], "expires_t": row["expires_t"],
            **json.loads(row["data"])}


def revoke(store: Store, token: str) -> None:
    """An app giving back a token ends its connection."""
    with store.transaction():
        row = store.one("SELECT grant_id FROM tokens WHERE hash=?", _hash(token))
        if row and row["grant_id"]:
            _end_grants(store, "id=?", row["grant_id"])


def _end_grants(store: Store, where: str, *args) -> None:
    ids = [r["id"] for r in store.all(f"SELECT id FROM grants WHERE revoked_t IS NULL AND {where}", *args)]
    for grant in ids:
        store.exec("UPDATE grants SET revoked_t=? WHERE id=?", store.now(), grant)
        store.exec("DELETE FROM tokens WHERE grant_id=?", grant)


def person_for_grant(store: Store, grant_id: str, tool: str) -> str:
    """Whose connection this is, with the call logged. Its first call makes the person and joins the community of
    the invite it was allowed with, if that invite still works and the community still takes newcomers today; the
    chat's `check` then says what is missing (PROTOCOL.md §5)."""
    with store.transaction():
        # LEFT JOIN, so a connection whose person row is gone refuses rather than resolving to nobody.
        g = store.one("SELECT g.*, p.id pid, p.deleted_t FROM grants g LEFT JOIN people p ON p.id=g.person_id "
                      "WHERE g.id=? AND g.revoked_t IS NULL", grant_id)
        if not g:
            raise NotYours()
        if g["person_id"]:
            if g["pid"] is None or g["deleted_t"] is not None:
                raise Refused(_DELETED)
            person_id = g["person_id"]
        else:
            found = store.one("SELECT id FROM communities WHERE invite_code=?", g["invite"]) if g["invite"] else None
            if not found and _today(store, "uninvited") >= UNINVITED_PER_DAY:
                raise Refused("Bridge is taking no more new people without an invite today. Try again tomorrow, "
                              "or ask someone in a community for its invite link and add Bridge from its page.")
            person_id = new_person(store)
            store.exec("UPDATE grants SET person_id=? WHERE id=?", person_id, grant_id)
            if found:
                try:
                    join(store, person_id, found["id"])
                except Refused:
                    found = None                     # full for today: they join from the chat once it takes them
            if not found:
                _count(store, "uninvited")
        store.exec("INSERT INTO calls(t, person_id, tool) VALUES (?,?,?)", store.now(), person_id, tool)
    return person_id


# -- being woken: MCP Events (PROTOCOL.md §5) ---------------------------------------------------------------------

WAITING = "waiting"                    # the one event: something is waiting for the person, never what or who


def subscription_id(grant_id: str, url: str) -> str:
    """The same connection asking to be woken at the same address is the same subscription, however often it asks."""
    return "sub_" + _hash(f"{grant_id} {WAITING} {url}")[:24]


def subscription(store: Store, grant_id: str, url: str) -> dict | None:
    row = store.one("SELECT data FROM tokens WHERE hash=? AND kind='subscription' AND grant_id=? AND expires_t>?",
                    _hash(subscription_id(grant_id, url)), grant_id, store.now())
    return json.loads(row["data"]) if row else None


def subscribe(store: Store, person_id: str, grant_id: str, url: str, secret: str, days: float) -> dict:
    """An app on this connection asks to be woken at `url`, signed with `secret`, for up to WAKE_S; asked again, it
    renews. Only a connection made by signing in: the subscription ends with it. The address was verified first."""
    sub = subscription_id(grant_id, url)
    with store.transaction():
        _acting(store, person_id)
        if not grant_id or not store.one("SELECT 1 FROM grants WHERE id=? AND person_id=? AND revoked_t IS NULL",
                                         grant_id, person_id):
            raise Refused("being woken needs a connection made by signing in (Bridge's one address, then Allow)")
        expires = store.now() + min(max(days, 1 / 24), WAKE_S / 86400) * 86400
        data = {"id": sub, "url": url, "secret": secret}
        store.exec("INSERT INTO tokens(hash, kind, grant_id, data, created_t, expires_t) VALUES (?,?,?,?,?,?) "
                   "ON CONFLICT(hash) DO UPDATE SET data=excluded.data, expires_t=excluded.expires_t",
                   _hash(sub), "subscription", grant_id, json.dumps(data), store.now(), expires)
    return {**data, "expires_t": expires}


def unsubscribe(store: Store, person_id: str, grant_id: str, url: str) -> None:
    with store.transaction():
        _acting(store, person_id)
        store.exec("DELETE FROM tokens WHERE hash=? AND kind='subscription' AND grant_id=?",
                   _hash(subscription_id(grant_id, url)), grant_id)


def drop_subscription(store: Store, sub: str) -> None:
    """The app said the address is gone (410): nothing more goes there."""
    with store.transaction():
        store.exec("DELETE FROM tokens WHERE hash=? AND kind='subscription'", _hash(sub))


def holds_nothing(store: Store, person_id: str) -> bool:
    """A brand-new account, as far as anyone could lose anything by erasing it: no name, contact, notes or nudges, no
    open need, no conversation, and no community of its own."""
    me = store.one("SELECT name, contact, about, notify FROM people WHERE id=?", person_id)
    return not (me["name"] or me["contact"] or me["about"] or me["notify"]
                or store.one("SELECT 1 FROM needs WHERE author_id=? AND closed_t IS NULL AND expires_t>? LIMIT 1",
                             person_id, store.now())
                or store.one("SELECT 1 FROM conversation_people WHERE person_id=? LIMIT 1", person_id)
                or store.one("SELECT 1 FROM communities WHERE created_by=? LIMIT 1", person_id))


def _code_hash(code: str) -> str:
    return _hash("".join(ch for ch in code.lower() if ch in _ALPHABET))


def link_code(store: Store, person_id: str, *, replace: bool) -> str:
    """A code for the chat of another app, where it makes that connection this person's. With `replace`, its use ends
    every other connection of theirs. A new code of either kind ends any earlier one not yet used."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(LINK_CODE))
    with store.transaction():
        _acting(store, person_id)
        store.exec("DELETE FROM link_codes WHERE person_id=? AND used_t IS NULL", person_id)
        store.exec("INSERT INTO link_codes(hash, person_id, replace, created_t) VALUES (?,?,?,?)",
                   _code_hash(raw), person_id, int(replace), store.now())
    return "-".join(raw[i:i + 4] for i in range(0, LINK_CODE, 4))


ALREADY_LINKED, LINKED, MOVED = "already", "linked", "moved"


def use_link_code(store: Store, person_id: str, grant_id: str, code: str) -> tuple[str, str]:
    """This connection becomes the code's person, who joins whatever communities its empty account had joined; that
    account is erased. Only in a connection made by signing in, and only while its account holds nothing. Returns
    what happened, and whose the connection now is."""
    dead = Refused("that code does not work: it may be mistyped, used already, more than an hour old, or replaced by "
                   "a newer one. Ask for a fresh one in the app where Bridge already works (`setup` with "
                   "another_app).")
    with store.transaction():
        _acting(store, person_id)
        row = store.one("SELECT l.*, p.deleted_t FROM link_codes l JOIN people p ON p.id=l.person_id "
                        "WHERE l.hash=? AND l.used_t IS NULL AND l.created_t>?", _code_hash(code),
                        store.now() - LINK_CODE_S)
        if not row or row["deleted_t"] is not None:
            raise dead
        target = row["person_id"]
        if target == person_id:
            return ALREADY_LINKED, target
        if not grant_id:
            raise Refused("a code works only in a connection made by adding Bridge at its one connector address "
                          "and pressing Allow, not through a connector link of your person's own")
        if not holds_nothing(store, person_id):
            raise Refused("this connection's account already holds things of its own (a name, notes, a need, a "
                          "conversation or a community), which a code would lose. A need of its own can be closed "
                          "with `pass` first and sent again after. Otherwise keep the two apart, or, on your person's "
                          "say-so, `forget_me` here first and then use the code.")
        store.exec("UPDATE link_codes SET used_t=? WHERE hash=?", store.now(), row["hash"])
        # Moved, not copied: the owner's count of who has ever joined stays what it was.
        store.exec("UPDATE memberships SET person_id=? WHERE person_id=? AND community_id NOT IN "
                   "(SELECT community_id FROM memberships WHERE person_id=?)", target, person_id, target)
        store.exec("UPDATE grants SET person_id=? WHERE id=?", target, grant_id)
        store.exec("UPDATE people SET deleted_t=? WHERE id=?", store.now(), person_id)
        store.exec("UPDATE memberships SET left_t=COALESCE(left_t, ?) WHERE person_id=?", store.now(), person_id)
        store.exec("DELETE FROM passes WHERE person_id=?", person_id)
        store.exec("DELETE FROM calls WHERE person_id=?", person_id)
        _end_grants(store, "person_id=?", person_id)
        if row["replace"]:
            _end_grants(store, "person_id=? AND id<>?", target, grant_id)
            store.exec("UPDATE connectors SET revoked_t=? WHERE person_id=? AND revoked_t IS NULL", store.now(), target)
        return (MOVED if row["replace"] else LINKED), target


def log_call(store: Store, what: str) -> None:
    """A row in nobody's name: a Join press, a nudge, a retired tool name. A person's calls are logged only where
    their connector is looked up, in the same step: logged after it, a row could outlive their forget_me (review)."""
    with store.transaction():
        store.exec("INSERT INTO calls(t, person_id, tool) VALUES (?,'',?)", store.now(), what)


def forget_me(store: Store, person_id: str, confirm: str) -> None:
    """Their name, contact, about, nudge topic and needs are erased, every conversation they were in is over and
    emptied on both sides, and every connection of theirs ends. What a deal already handed the other
    person cannot be recalled. Their random id stays where other people's rows point at it; it no
    longer leads to anything. A second one in flight is NotYours."""
    if confirm.strip().lower() != "delete everything":
        raise Refused('pass confirm="delete everything" once your person has asked for this')
    with store.transaction():
        # A second one in flight wrote again, and moved the moment the first was made (review).
        _acting(store, person_id)
        now = store.now()
        store.exec("UPDATE people SET name='', contact='', about='', notify='', nudged_t=NULL, deleted_t=? WHERE id=?",
                   now, person_id)
        # everyone's messages: the guard looks only at its writer, so the others' may carry this one's name
        store.exec("DELETE FROM messages WHERE conversation_id IN "
                   "(SELECT conversation_id FROM conversation_people WHERE person_id=?)", person_id)
        store.exec("UPDATE needs SET text='', closed_t=COALESCE(closed_t, ?) WHERE author_id=?", now, person_id)
        store.exec("UPDATE memberships SET left_t=COALESCE(left_t, ?) WHERE person_id=?", now, person_id)
        store.exec("UPDATE connectors SET revoked_t=COALESCE(revoked_t, ?) WHERE person_id=?", now, person_id)
        _end_grants(store, "person_id=?", person_id)
        store.exec("DELETE FROM link_codes WHERE person_id=?", person_id)
        store.exec("DELETE FROM passes WHERE person_id=?", person_id)
        store.exec("UPDATE reports SET closed_t=COALESCE(closed_t, ?) WHERE reporter_id=? OR reported_id=?",
                   now, person_id, person_id)
        store.exec("DELETE FROM calls WHERE person_id=?", person_id)
    store.empty_log()


# -- communities -----------------------------------------------------------------------------------

def create_community(store: Store, by: str, name: str) -> tuple[str, str]:
    """`by` is the person who owns it, and joins it. Returns (id, invite code)."""
    name = _community_name(name)
    with store.transaction():
        cid, code = _new_id(store, "communities", "g"), _new_invite_code()
        store.exec("INSERT INTO communities(id, name, created_by, invite_code, created_t) VALUES (?,?,?,?,?)",
                   cid, name, by, code, store.now())
        join(store, by, cid)
    return cid, code


def _new_invite_code() -> str:
    """Like an id, so one read off paper or typed in any case still works."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(INVITE_CODE))


# A code, made before or since codes were lowercase: every one is at least 12 characters, so the words and the
# host around it mostly are not taken for one.
_CODE = re.compile(r"[A-Za-z0-9_-]{12,}")


def community_by_invite(store: Store, invite: str):
    """From a code or a whole link, however a chat passed it on: tracking parameters, a full stop, brackets or
    italics around it, invisible or fullwidth characters, or its case changed. A code made before codes were
    lowercase is found only in its own case, so each word is tried as written before it is folded. A link from the
    end of a sentence was refused as replaced, and the person sent back to a friend who had the same link (review).
    Cut before it is folded: a folded megabyte took seconds. Of two links, the first, not whichever SQLite
    returned (review 2)."""
    words = [(w, w.strip("_-"), w.strip("_-").lower())
             for w in _CODE.findall(guard.visible(invite[:MAX_TEXT]))]
    tried = {code for forms in words for code in forms}
    found = {c["invite_code"]: c for c in store.all(
        f"SELECT * FROM communities WHERE invite_code IN ({','.join('?' * len(tried))})", *tried)}
    return next((found[code] for forms in words for code in forms if code in found), None)


def join_by_invite(store: Store, person_id: str, invite: str):
    """Join from the chat with a code or link. Looked up and joined in one step, or a join between the two came in
    through a link replaced meanwhile (review 2). Removed, they are told only that the link does not work: "nothing
    of your person's" set a removal apart from a replaced link (review)."""
    dead = Refused("that invite link is not valid: check it was copied whole; if it was, it may have been "
                   "replaced, so ask whoever sent it for a fresh one")
    with store.transaction():
        found = community_by_invite(store, invite)
        if not found:
            raise dead
        try:
            join(store, person_id, found["id"])
        except NotYours:
            raise dead from None
    return found


def is_member(store: Store, person_id: str, community_id: str) -> bool:
    return bool(store.one("SELECT 1 FROM memberships WHERE person_id=? AND community_id=? AND left_t IS NULL",
                          person_id, community_id))


def join(store: Store, person_id: str, community_id: str) -> None:
    """The community's open needs are in front of the newcomer from this moment."""
    with store.transaction():
        _acting(store, person_id)
        if not store.one("SELECT 1 FROM communities WHERE id=?", community_id):
            raise NotYours()
        if store.one("SELECT 1 FROM memberships WHERE person_id=? AND community_id=? AND banned_t IS NOT NULL",
                     person_id, community_id):
            raise NotYours()
        if is_member(store, person_id, community_id):
            return
        # Counted for everyone's first community, however they came: counted only at a first call, an account
        # signed in with no invite could join from the chat and the limit would hold nobody.
        if not store.one("SELECT 1 FROM memberships WHERE person_id=? LIMIT 1", person_id):
            if _today(store, f"joins {community_id}") >= JOINS_PER_DAY:
                raise Refused("too many new people through this invite link today; try again tomorrow, or ask "
                              "whoever sent it")
            _count(store, f"joins {community_id}")
        store.exec("INSERT INTO memberships(person_id, community_id, joined_t) VALUES (?,?,?) "
                   "ON CONFLICT(person_id, community_id) DO UPDATE SET left_t=NULL, joined_t=excluded.joined_t",
                   person_id, community_id, store.now())


def leave(store: Store, person_id: str, community_id: str) -> bool:
    """Their needs stop showing there and its needs stop reaching them — both because a need shows only
    where its author and its reader are members, so rejoining brings their open needs back. It used to
    close them, and a person who left and rejoined two seconds later had lost them for good (swarm).
    Conversations under way carry on. Returns whether they own it."""
    community_id = _ref(community_id)
    with store.transaction():
        _acting(store, person_id)
        if not is_member(store, person_id, community_id):
            raise NotYours()
        store.exec("UPDATE memberships SET left_t=? WHERE person_id=? AND community_id=?", store.now(), person_id,
                   community_id)
        return store.one("SELECT created_by FROM communities WHERE id=?", community_id)["created_by"] == person_id


OWNER_LEFT = ("your person started this community but has left it: until they rejoin with an invite link from a "
              "member, they cannot pass on or replace its link, rename it or remove anyone, and reports there "
              "reach nobody")


def _owned(store: Store, owner_id: str, community_id: str) -> str:
    """The community, if they own it and are in it: an owner who had left still acted on it (#34). An owner who
    left, or a member who does not own it, is told so plainly; anyone else learns nothing."""
    community_id = _ref(community_id)
    _acting(store, owner_id)
    community = store.one("SELECT created_by FROM communities WHERE id=?", community_id)
    member = is_member(store, owner_id, community_id)
    if community and member and community["created_by"] == owner_id:
        return community_id
    if community and community["created_by"] == owner_id:
        raise Refused(OWNER_LEFT)
    if community and member:
        raise Refused("only whoever started this community can do that")
    raise NotYours()


def _person_behind(store: Store, owner_id: str, ref: str, community_id: str) -> str | None:
    """Who is behind a need sent to this community, a conversation of the owner's through it, or an open report
    there — the only ways an owner ever meets a member. Only through this community: a conversation from
    elsewhere let an owner test whether the anonymous person in it was a member here (review, critical). Never
    through what a deal could have named: whoever learned a name in a deal removed that person by the deal, by
    the need it was on, or by a report on either, and watched which anonymous needs went with them (rethink)."""
    need_id = conv_id = ""
    partners = False
    if ref.startswith("r-"):
        r = store.one("SELECT reporter_id, reported_id, need_id, conversation_id FROM reports WHERE id=? "
                      "AND community_id=? AND closed_t IS NULL", ref, community_id)
        if not r:
            return None
        who, need_id, conv_id = r["reported_id"], r["need_id"], r["conversation_id"]
        # A report made before its two sides dealt elsewhere stays open, and neither can report the other after
        # one; removing by it let the reporter, who knows the name, watch which needs went (review 2).
        partners = _dealt(store, r["reporter_id"], who)
    elif ref.startswith("n-"):
        need = store.one("SELECT n.author_id FROM needs n JOIN need_communities nc ON nc.need_id=n.id "
                         "WHERE n.id=? AND nc.community_id=?", ref, community_id)
        if not need:
            return None
        who, need_id = need["author_id"], ref
    else:
        conv_id, seat = _seat_ref(ref)
        conv = _conversation(store, owner_id, conv_id, or_none=True)
        if not conv:
            return None
        try:
            who = _target(store, conv, owner_id, seat)
        except NotYours:
            return None
        # Only between its starter and an author, whose shared community both are shown: two authors are joined only
        # through the starter's community with the other, which the owner never saw, and a removal that worked
        # through it would tell the owner the other was a member there (review, critical).
        if conv["starter_id"] not in (owner_id, who) or _link_via(store, conv, owner_id, who) != community_id:
            return None
    conv = store.one("SELECT * FROM conversations WHERE id=?", conv_id) if conv_id else None
    # A reported conversation on a need the owner dealt on: refused only when the reported side is that need's
    # author, the owner's deal partner. Refused whoever it reported, it told the owner their deal partner had
    # written or reported what they were shown (review).
    needs = [need_id] if need_id else [r["need_id"] for r in store.all(
        "SELECT need_id FROM conversation_needs WHERE conversation_id=? AND author_id=?", conv_id, who)] \
        if conv and ref.startswith("r-") else []
    # A report outlives a conversation the sweep deleted, and with it whether the owner dealt on its need (review 4).
    gone = conv_id and not conv
    if partners or gone or conv and conv["deal_t"] or any(_dealt_on(store, owner_id, n) for n in needs):
        # Pointing an owner at another report sent them round in a circle: the one they used was someone else's.
        if ref.startswith("r-"):
            raise Refused("this report cannot be acted on: removing someone by it could show someone who knows "
                          "them which of the anonymous needs there were theirs. `dismiss` clears it")
        raise Refused("that is a deal, or on a need your person has a deal on: removing someone through it would "
                      "show your person which of the anonymous needs there were theirs, so it cannot be done. Settle "
                      "it directly on their contact")
    return who


def _dealt(store: Store, a: str, b: str) -> bool:
    """Whether these two were in a deal the server still holds: each then knows who the other is."""
    return bool(store.one("SELECT 1 FROM conversation_people x JOIN conversation_people y ON "
                          "y.conversation_id=x.conversation_id AND y.person_id=? AND y.dealt=1 "
                          "WHERE x.person_id=? AND x.dealt=1", b, a))


def _dealt_on(store: Store, person_id: str, need_id: str) -> bool:
    """Whether this person was in a deal on that need."""
    return bool(store.one("SELECT 1 FROM conversation_needs cn JOIN conversation_people p ON "
                          "p.conversation_id=cn.conversation_id AND p.person_id=? AND p.dealt=1 WHERE cn.need_id=?",
                          person_id, need_id))


def rename(store: Store, owner_id: str, community_id: str, name: str) -> None:
    name = _community_name(name)
    with store.transaction():
        store.exec("UPDATE communities SET name=? WHERE id=?", name, _owned(store, owner_id, community_id))


def remove(store: Store, owner_id: str, ref: str, community_id: str) -> None:
    """The owner puts someone out of a community, by a need or conversation of theirs, or a report. The invite
    link no longer lets that account back in, though anyone holding it can join as someone new; their needs stop
    showing there; their conversations that came through it end as if they had walked away, and their deals are
    untouched. Nobody is told."""
    ref = _ref(ref)
    with store.transaction():
        now = store.now()                          # inside the lock, or earlier than writes it waited behind (#68)
        community_id = _owned(store, owner_id, community_id)
        who = _person_behind(store, owner_id, ref, community_id)
        if not who or who == owner_id:
            raise NotYours()
        # The same whether they are still in it or have left: an answer that differed would say which.
        store.exec("UPDATE memberships SET left_t=COALESCE(left_t, ?), banned_t=COALESCE(banned_t, ?) "
                   "WHERE person_id=? AND community_id=?", now, now, who, community_id)
        store.exec("UPDATE reports SET closed_t=COALESCE(closed_t, ?) WHERE reported_id=? AND community_id=?",
                   now, who, community_id)
        # Out of every conversation they are joined to through it, as if they had walked away.
        for conv in store.all(
                "SELECT DISTINCT c.id FROM conversations c JOIN conversation_needs cn ON cn.conversation_id=c.id "
                "WHERE cn.via=? AND c.deal_t IS NULL AND (cn.author_id=? OR c.starter_id=?)", community_id, who, who):
            store.exec("UPDATE conversation_people SET passed_t=COALESCE(passed_t, ?) WHERE conversation_id=? AND "
                       "person_id=?", now, conv["id"], who)


def invite_code(store: Store, person_id: str, community_id: str, *, new: bool = False) -> str:
    """Any member may pass the link on, as in a group chat. Only whoever started the community may
    replace it, because every link already shared stops working, and so does the code an invite page left in the
    browser of anyone whose AI has not called yet."""
    community_id = _ref(community_id)
    with store.transaction():
        _acting(store, person_id)
        c = store.one("SELECT created_by, invite_code FROM communities WHERE id=?", community_id)
        if not is_member(store, person_id, community_id):
            raise Refused(OWNER_LEFT) if c and c["created_by"] == person_id else NotYours()
        if not new:
            return c["invite_code"]
        if c["created_by"] != person_id:
            raise Refused("only whoever started this community can replace its link")
        code = _new_invite_code()
        store.exec("UPDATE communities SET invite_code=? WHERE id=?", code, community_id)
    return code


# -- the loop --------------------------------------------------------------------------------------

def go(store: Store, person_id: str, text: str, community_id: str | None = None, *, people: int = 1,
       days: float | None = None) -> str:
    """Send a need to every community they are in, or to one. `people`: how many deals it is for, 0 for
    as many as come until they close it. `days`: how long it stays up. Returns its id, and nothing about who
    it reached."""
    text = _text(text, "the need")
    if not 0 <= people <= MAX_PEOPLE:
        raise Refused(f"people is how many it is for: 1 to {MAX_PEOPLE}, or 0 for as many as come")
    if days is not None and not MIN_DAYS <= days <= MAX_DAYS:
        raise Refused(f"days is how long it stays up: from {MIN_DAYS} (about an hour) to {MAX_DAYS}")
    with store.transaction():
        _acting(store, person_id)
        if community_id:
            communities = [_ref(community_id)]
            if not is_member(store, person_id, communities[0]):
                raise NotYours()
        else:
            communities = [c["id"] for c in me(store, person_id)["communities"]]
            if not communities:
                raise Refused("not in a community yet: join one with an invite link, or start one (`community`)")
        _unidentifying(store, person_id, text)
        now = store.now()
        existing = _already_out(store, person_id, text, communities, people)
        if existing:
            return existing
        if store.one("SELECT COUNT(*) n FROM needs WHERE author_id=? AND created_t>?",
                     person_id, now - 86400)["n"] >= NEEDS_PER_DAY:
            raise Refused(f"that is {NEEDS_PER_DAY} needs in a day; the rest can wait until tomorrow")
        need_id = _new_id(store, "needs", "n")
        store.exec("INSERT INTO needs(id, author_id, text, created_t, expires_t, wants) VALUES (?,?,?,?,?,?)",
                   need_id, person_id, text, now, now + (NEED_TTL_S if days is None else days * 86400), people)
        for cid in communities:
            store.exec("INSERT INTO need_communities(need_id, community_id) VALUES (?,?)", need_id, cid)
    return need_id


def _same(text: str) -> str:
    return " ".join(text.casefold().split())


def _already_out(store: Store, person_id: str, text: str, communities: list[str], people: int) -> str | None:
    """The same need, already open. A scheduled run has no memory of the last, and one that did not read its
    own open needs sent the same need again (diary study). Sent to communities it has not reached yet — a person
    who started one after sending it — the same need goes on there, and its id comes back: a second need with
    the same words showed twice to everyone in both (review)."""
    for n in store.all("SELECT * FROM needs WHERE author_id=? AND closed_t IS NULL "
                       "AND expires_t>?", person_id, store.now()):
        if _same(n["text"]) != _same(text):
            continue
        if _full(n):
            raise Refused(f"your person already has this need out [{n['id']}], and it is full: it reaches nobody new. "
                          "To go on with one of its conversations too, `agree` there with one_more; to look for "
                          "new people, `pass` it (it closes, ending its conversations) and send it again.")
        reached = {r["community_id"] for r in store.all(
            "SELECT community_id FROM need_communities WHERE need_id=?", n["id"])}
        missing = [c for c in communities if c not in reached]
        if not missing:
            raise Refused(f"your person already has this need out [{n['id']}], still open where this would "
                          "go. To change it, `pass` that one (it closes) and send the new wording.")
        if n["wants"] != people:
            raise Refused(f"your person already has this need out [{n['id']}] with other settings; `pass` it first "
                          "to send it differently")
        for cid in missing:
            store.exec("INSERT INTO need_communities(need_id, community_id) VALUES (?,?)", n["id"], cid)
        return n["id"]
    return None


def _full(need) -> bool:
    """As many deals as it is for. It reaches nobody new, and its author says yes on it again only with one_more;
    its conversations carry on."""
    return bool(need["wants"]) and need["deals"] >= need["wants"]


# Open to someone new: not closed, expired or full. Read the same whichever it was (`_in_front`).
_TAKING = "n.closed_t IS NULL AND n.expires_t>? AND (n.wants=0 OR n.deals<n.wants)"

# A need is in front of everyone who shares one of its communities with its author, both still members.
_SHARED = ("EXISTS (SELECT 1 FROM need_communities nc "
           "JOIN memberships m ON m.community_id=nc.community_id AND m.person_id={reader} AND m.left_t IS NULL "
           "JOIN memberships a ON a.community_id=nc.community_id AND a.person_id=n.author_id AND a.left_t IS NULL "
           "WHERE nc.need_id=n.id)")


def _via(store: Store, need_id: str, reader_id: str) -> str | None:
    """The community a reader sees a need through: one it was sent to that they and its author are both
    still in. None when there is none — the need has left their view."""
    r = store.one("SELECT nc.community_id FROM need_communities nc "
                  "JOIN memberships m ON m.community_id=nc.community_id AND m.person_id=? AND m.left_t IS NULL "
                  "JOIN memberships a ON a.community_id=nc.community_id AND a.left_t IS NULL "
                  "AND a.person_id=(SELECT author_id FROM needs WHERE id=?) "
                  "WHERE nc.need_id=? ORDER BY m.joined_t, m.rowid LIMIT 1", reader_id, need_id, need_id)
    return r["community_id"] if r else None


def _sent_to_them(store: Store, need_id: str, person_id: str) -> bool:
    """Sent to a community they are in, whoever else is still there. A need that was in front of them and
    has since gone — closed, expired, or its author left — must read the same whichever it was: telling
    those apart would tell them its anonymous author had left (review)."""
    return bool(store.one(
        "SELECT 1 FROM needs n JOIN need_communities nc ON nc.need_id=n.id JOIN memberships m "
        "ON m.community_id=nc.community_id AND m.person_id=? AND m.left_t IS NULL WHERE n.id=? AND n.author_id<>?",
        person_id, need_id, person_id))


def _in_front(store: Store, need_id: str, reader_id: str, gone: str) -> tuple[sqlite3.Row, str]:
    """A need sent to the reader, and the community it reaches them through while it is still open. One that has
    gone refuses with `gone` the same whether it closed, expired or its author left: telling those apart would
    tell the reader its anonymous author had left (review)."""
    need = store.one("SELECT * FROM needs WHERE id=?", need_id)
    if not need or not _sent_to_them(store, need_id, reader_id):
        raise NotYours()
    via = _via(store, need_id, reader_id)
    # Full, it has gone for a reader with no conversation on it, as a closed one has, and is open for one with a
    # conversation on it, which carries on: either way nothing says its author made a deal. Gone for everyone, a
    # report refused while their conversation carried on told another responder the need had filled (review).
    full = _full(need) and not store.one("SELECT 1 FROM conversation_needs cn JOIN conversation_people p ON "
                                         "p.conversation_id=cn.conversation_id AND p.person_id=? WHERE cn.need_id=?",
                                         reader_id, need_id)
    if not via or need["closed_t"] or need["expires_t"] <= store.now() or full or not alive(store, need["author_id"]):
        raise Refused(gone)
    return need, via


CLEARED, MET = "cleared", "met"


def _conversation(store: Store, person_id: str, conversation_id: str, *, or_none: bool = False):
    """A conversation this person is in, or was."""
    conv = store.one("SELECT c.* FROM conversations c JOIN conversation_people p ON p.conversation_id=c.id AND "
                     "p.person_id=? WHERE c.id=?", person_id, conversation_id)
    if not conv and not or_none:
        raise NotYours()
    return conv


def _people(store: Store, conversation_id: str) -> list[sqlite3.Row]:
    return store.all("SELECT * FROM conversation_people WHERE conversation_id=? ORDER BY seat", conversation_id)


def _links(store: Store, conversation_id: str) -> list[sqlite3.Row]:
    """The needs it was opened on, in the order given: each with its author, the community its starter saw it
    through, its words and whether it has closed."""
    return store.all("SELECT cn.*, n.text, n.closed_t, n.wants, n.deals FROM conversation_needs cn JOIN needs n ON "
                     "n.id=cn.need_id WHERE cn.conversation_id=? ORDER BY cn.rowid", conversation_id)


def _in(store: Store, conv, people=None, links=None) -> list[sqlite3.Row]:
    """Who is still in it: not gone from it, not deleted, and in it as its starter or by a need of theirs still open.
    However someone went — passed, closed their need, was removed, deleted themselves — they count out the same, and
    nobody is told which (rule 2)."""
    people = _people(store, conv["id"]) if people is None else people
    links = _links(store, conv["id"]) if links is None else links
    by_open_need = {link["author_id"] for link in links if not link["closed_t"]}
    return [p for p in people if p["passed_t"] is None and alive(store, p["person_id"])
            and (p["seat"] == 1 or p["person_id"] in by_open_need)]


def _signature(inside: list) -> str:
    """Who is in it, as a yes records it: a yes given before someone went is not a yes to what is left."""
    return ",".join(str(p["seat"]) for p in inside)


def _holds_yes(person, signature: str) -> bool:
    return bool(person["yes_t"]) and person["yes_in"] == signature


_GONE_FROM = "your person is no longer in that conversation; the others carry on without them"


def _left_before_the_deal(store: Store, conv, person_id: str) -> bool:
    """Gone from a conversation the others then made a deal in: told nothing of it, as if it carried on (rule 2)."""
    return bool(conv["deal_t"]) and not store.one("SELECT dealt FROM conversation_people WHERE conversation_id=? AND "
                                                  "person_id=?", conv["id"], person_id)["dealt"]


def _over(store: Store, conv) -> bool:
    """No deal, and no longer able to become one: fewer than two still in it, or a week with nobody answering."""
    return len(_in(store, conv)) < 2 or conv["last_t"] + QUIET_TTL_S <= store.now()


def _target(store: Store, conv, person_id: str, seat: int | None) -> str:
    """Someone else in a conversation: the one other person, or, of several, the one numbered `seat`."""
    others = [p for p in _people(store, conv["id"]) if p["person_id"] != person_id]
    if seat is None and len(others) == 1:
        return others[0]["person_id"]
    if seat is None:
        raise Refused(f"[{conv['id']}] has {len(others) + 1} people in it: say which one, with their number after "
                      f"the id, as [{conv['id']}:{others[0]['seat']}]")
    found = next((p for p in others if p["seat"] == seat), None)
    if not found:
        raise NotYours()
    return found["person_id"]


def _link_via(store: Store, conv, a: str, b: str) -> str:
    """The community two people in a conversation are joined through: the one its starter saw the other's need
    through. Two authors, neither its starter, meet only through it, so this is the starter's with `b`."""
    author = b if a == conv["starter_id"] else a if b == conv["starter_id"] else b
    row = store.one("SELECT via FROM conversation_needs WHERE conversation_id=? AND author_id=? ORDER BY rowid "
                    "LIMIT 1", conv["id"], author)
    return row["via"] if row else ""


def _started_on(store: Store, person_id: str, need_ids: list[str]):
    """The conversation this person started on exactly these needs: a scheduled run with no memory of the last one
    must not open a second."""
    for conv in store.all("SELECT c.* FROM conversations c JOIN conversation_needs cn ON cn.conversation_id=c.id "
                          "WHERE c.starter_id=? AND cn.need_id=?", person_id, need_ids[0]):
        if {r["need_id"] for r in store.all("SELECT need_id FROM conversation_needs WHERE conversation_id=?",
                                            conv["id"])} == set(need_ids):
            return conv
    return None


def _open(store: Store, person_id: str, need_ids: list[str]) -> tuple[sqlite3.Row, bool]:
    """The conversation this person started on these needs, or a new one with every one of their authors in it,
    each joined to the starter through the community the starter saw their need through. Several needs may be
    pieced together, the person's own among them; whatever the assistant makes of them is its own judgment.
    Returns it, and whether it is new."""
    if not all(n.startswith("n-") for n in need_ids):
        raise Refused("several ids open one conversation only when every one is a need (n-…); to write in a "
                      "conversation, give its id alone")
    conv = _started_on(store, person_id, need_ids)
    if conv:
        return conv, False
    needs = []
    for need_id in need_ids:
        own = store.one("SELECT * FROM needs WHERE id=? AND author_id=?", need_id, person_id)
        if own and len(need_ids) > 1:
            if own["closed_t"] or own["expires_t"] <= store.now():
                raise Refused(f"your person's own need [{need_id}] has closed or expired; leave it out, or send it "
                              "again first")
            needs.append((own, ""))
        else:
            needs.append(_in_front(store, need_id, person_id, "that need is no longer open" if len(need_ids) == 1
                                   else f"the need [{need_id}] is no longer open; nothing was sent"))
    authors = list(dict.fromkeys(n["author_id"] for n, _ in needs if n["author_id"] != person_id))
    if not authors:
        raise Refused("those are all your person's own needs: a conversation needs someone else's in it")
    if len(authors) + 1 > MAX_IN:
        raise Refused(f"one conversation holds at most {MAX_IN} people, its starter included; these needs bring "
                      f"{len(authors) + 1}. Nothing was sent.")
    conv_id, now = _new_id(store, "conversations", "c"), store.now()
    store.exec("INSERT INTO conversations(id, starter_id, created_t, last_t) VALUES (?,?,?,?)", conv_id, person_id,
               now, now)
    for need, via in needs:
        store.exec("INSERT INTO conversation_needs(conversation_id, need_id, author_id, via) VALUES (?,?,?,?)",
                   conv_id, need["id"], need["author_id"], via)
    for seat, pid in enumerate([person_id, *authors], 1):
        store.exec("INSERT INTO conversation_people(conversation_id, person_id, seat) VALUES (?,?,?)", conv_id, pid,
                   seat)
    return store.one("SELECT * FROM conversations WHERE id=?", conv_id), True


def reply(store: Store, person_id: str, to: str, text: str, *, agree_too: bool = False,
          revision: int | None = None) -> tuple[str, str | None]:
    """Write to everyone else in a conversation. `to` is a need that reached them, which opens a conversation with
    its author; several needs, separated by spaces or commas, which open one conversation with all their authors;
    or a conversation they are in. `agree_too` carries their person's yes with the message, in one step — for an
    assistant working on a yes given in advance — and in a conversation already open, needs the `revision` their
    person saw. Every message clears every yes: a yes is to the conversation as it stands. A yes that completes
    everyone else's makes the deal on what all saw, and its message is not sent. Returns (conversation id, what
    `agree` said, MET for that deal, CLEARED when the message took back their own yes, or None)."""
    text = _text(text, "the message")
    refs = list(dict.fromkeys(r for r in (_seat_ref(raw)[0] for raw in re.split(r"[\s,]+", to)) if r))
    if not refs:
        raise NotYours()
    with store.transaction():
        _acting(store, person_id)
        if len(refs) > 1 or refs[0].startswith("n-"):
            conv, opened = _open(store, person_id, refs)
            if opened:
                revision = 0 if revision is None else revision
        else:
            conv = _conversation(store, person_id, refs[0])
        if _left_before_the_deal(store, conv, person_id):
            raise Refused(_GONE_FROM)
        if conv["deal_t"]:
            # Carrying messages after a deal let a deal partner message and nudge someone for months with no
            # way to stop it (audit); nobody on the live copy had written one.
            raise Refused("it's a deal: nothing more goes through Bridge. `check` shows the deal for "
                          f"{DEAL_SHOWN_S // 86400} days after it; give your person what it shows, so they can use "
                          "their contact")
        if _over(store, conv):
            raise Refused("that conversation is over")
        people, links = _people(store, conv["id"]), _links(store, conv["id"])
        inside = _in(store, conv, people, links)
        signature, mine = _signature(inside), next(p for p in people if p["person_id"] == person_id)
        others = [p for p in inside if p["person_id"] != person_id]
        if len(others) == len(inside):
            raise Refused(_GONE_FROM)
        if agree_too:
            _as_seen(store, conv, person_id, revision, "sent")
        if agree_too and all(_holds_yes(p, signature) for p in others):
            # Their yeses were to what this person saw, so they meet there, and the message, which they never saw, is
            # not sent. Sent first, it took their yes back: a yes with a reply never made a deal, and two sides each
            # replying with a yes went round for ever (review).
            _agree(store, person_id, conv["id"], revision=revision)
            outcome = MET
        else:
            # Only the conversation's own messages: a limit that counted what the others had waiting elsewhere
            # would tell the sender about their other conversations (rule 7).
            last = store.all("SELECT sender_id FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                             conv["id"], UNANSWERED)
            if len(last) == UNANSWERED and all(m["sender_id"] == person_id for m in last):
                # More work on one side bought more of the other's attention: a fourth, fifth, twentieth message
                # each nudged them, and kept a conversation they had stopped answering alive (design review).
                raise Refused(f"your person's side has written the last {UNANSWERED} messages here with no answer; "
                              "nothing more goes through until someone else answers. Nothing was sent. Keep what "
                              "you would add for when they do, or `pass` if it has gone quiet.")
            if store.one("SELECT COUNT(*) n FROM messages WHERE sender_id=? AND t>?",
                         person_id, store.now() - 86400)["n"] >= MESSAGES_PER_DAY:
                raise Refused(f"that is {MESSAGES_PER_DAY} messages in a day; the rest can wait until tomorrow")
            _unidentifying(store, person_id, text)
            store.exec("INSERT INTO messages(conversation_id, sender_id, text, t) VALUES (?,?,?,?)",
                       conv["id"], person_id, text, store.now())
            # A yes that stood through a later message was to terms the message may have changed: one side said yes,
            # the other then asked for more and said yes itself, and it was a deal (design review). And the week runs
            # from the first message still unanswered: a sender who kept writing kept a silent conversation open.
            answering = not last or last[0]["sender_id"] != person_id
            store.exec("UPDATE conversation_people SET yes_t=NULL WHERE conversation_id=?", conv["id"])
            store.exec("UPDATE conversations SET last_t=CASE WHEN ? THEN ? ELSE last_t END WHERE id=?",
                       answering, store.now(), conv["id"])
            # A yes this message clears is given again with it as it was: after `agree` with one_more on a full need,
            # a reply with agree=true, as the instructions say, was refused (review).
            outcome = (_agree(store, person_id, conv["id"], revision=_revision(store, conv["id"]),
                              one_more=_holds_yes(mine, signature)) if agree_too
                       else CLEARED if _holds_yes(mine, signature) else None)
    _nudge(store, *(p["person_id"] for p in others))
    return conv["id"], outcome


DEAL, YES, ALREADY = "deal", "yes", "already"
WITHDRAWN, NO_YES = "withdrawn", "no yes"
# A deal made before this call: answered as a deal, and nudges nobody. A repeated `agree` on a deal nudged the
# other side every ten minutes for as long as the conversation was kept (review).
_DEALT = "dealt"


def agree(store: Store, person_id: str, conversation_id: str, *, revision: int | None = None,
          one_more: bool = False) -> str:
    """Their person said yes to this one, as it stood at `revision`, which `check` shows: DEAL when it is a deal
    (made now, or before), YES when it waits on someone else, ALREADY when their yes was recorded before.
    Refused when someone else has written since. `one_more`: on their own full need, room for one more deal
    first. A deal made by this call nudges the others; nothing else here does."""
    outcome = _agree(store, person_id, conversation_id, revision=revision, one_more=one_more)
    if outcome == DEAL:
        conv = _conversation(store, person_id, _seat_ref(conversation_id)[0])
        _nudge(store, *(p["person_id"] for p in _people(store, conv["id"])
                        if p["dealt"] and p["person_id"] != person_id))
    return DEAL if outcome == _DEALT else outcome


def _revision(store: Store, conversation_id: str) -> int:
    """How many messages the conversation holds: the state a yes is given to."""
    return store.one("SELECT COUNT(*) n FROM messages WHERE conversation_id=?", conversation_id)["n"]


def _as_seen(store: Store, conv, person_id: str, revision, done: str) -> None:
    """A yes names the revision its person saw, and is refused if anyone else has written since: read, then
    asked, then agreed, a yes landed on a message nobody had shown its person (design review). Their own later
    messages do not make it stale: their own assistant wrote them."""
    if type(revision) is not int:
        raise Refused(f"a yes names the revision it was given at: `check` shows it on each conversation "
                      f"(\"revision 4\"). Pass `revision` with the number from the `check` your person's yes was "
                      f"given on. Nothing was {done}. If your tool has no `revision`, your app's list of Bridge "
                      "tools is out of date: in ChatGPT, Settings → Apps → Bridge → Refresh; in Claude, a new "
                      "chat. Never remove Bridge to refresh it: added again, it is a new account.")
    now = _revision(store, conv["id"])
    if not 0 <= revision <= now:
        raise Refused(f"that conversation has no revision {revision}: it is at {now}. Nothing was {done}.")
    if store.one("SELECT 1 FROM (SELECT sender_id FROM messages WHERE conversation_id=? ORDER BY id LIMIT -1 "
                 "OFFSET ?) WHERE sender_id<>?", conv["id"], revision, person_id):
        raise Refused(f"the other side has written since revision {revision}: `check`, show your person what they "
                      f"added, and only then say yes, at revision {now}. Nothing was {done}.")


def _agree(store: Store, person_id: str, conversation_id: str, *, revision: int | None = None,
           one_more: bool = False) -> str:
    with store.transaction():
        _acting(store, person_id)
        conv = _conversation(store, person_id, _seat_ref(conversation_id)[0])
        if _left_before_the_deal(store, conv, person_id):
            raise Refused(_GONE_FROM)
        if conv["deal_t"]:
            return _DEALT
        if _over(store, conv):
            raise Refused("that conversation is over")
        people, links = _people(store, conv["id"]), _links(store, conv["id"])
        inside = _in(store, conv, people, links)
        signature = _signature(inside)
        if person_id not in {p["person_id"] for p in inside}:
            raise Refused(_GONE_FROM)
        _as_seen(store, conv, person_id, revision, "recorded")
        mine = store.one("SELECT name, contact FROM people WHERE id=?", person_id)
        if not mine["name"] or not mine["contact"]:
            raise Refused("first set their name and how to reach them (an email or a phone number) with "
                          "`setup`: a deal hands both to the other person")
        if _holds_yes(next(p for p in people if p["person_id"] == person_id), signature):
            return ALREADY
        for link in links:
            if link["author_id"] == person_id and not link["closed_t"]:
                _no_race(store, conv, link["need_id"], one_more)
        now = store.now()
        store.exec("UPDATE conversation_people SET yes_t=?, yes_in=? WHERE conversation_id=? AND person_id=?", now,
                   signature, conv["id"], person_id)
        if not all(_holds_yes(p, signature) for p in inside if p["person_id"] != person_id):
            return YES
        dealt = [p["person_id"] for p in inside]
        store.exec("UPDATE conversations SET deal_t=? WHERE id=?", now, conv["id"])
        store.exec(f"UPDATE conversation_people SET dealt=1 WHERE conversation_id=? AND person_id IN "
                   f"({','.join('?' * len(dealt))})", conv["id"], *dealt)
        # A report kept open past a deal let its owner, or the reporter through an honest owner, remove the deal
        # partner by it and watch which anonymous needs went with them (rethink, r4_revised.py). Only this deal's
        # own: closing every report between them showed an owner, as one vanished while a need left their list, who
        # wrote that need (review 3). An older one between them is refused in `_person_behind`.
        store.exec(f"UPDATE reports SET closed_t=COALESCE(closed_t, ?) WHERE conversation_id=? OR (need_id IN "
                   f"(SELECT need_id FROM conversation_needs WHERE conversation_id=?) AND reporter_id IN "
                   f"({','.join('?' * len(dealt))}))", now, conv["id"], conv["id"], *dealt)
        # A need is full at as many deals as its author asked for: one, unless they said otherwise. A need
        # that had found its person kept taking offers, and in the simulation the next offer was the liar's; so a
        # full one reaches nobody new, and its author says yes on it again only with one_more. It no longer
        # closes: that ended its other conversations, and an introduction that came to nothing left its author
        # starting over (design review). Counted on the need: deal conversations are deleted after 90 days and a
        # need can last a year, so counting them let a need for two take a third (review). Each need whose author
        # is in the deal has had one.
        for link in links:
            if link["author_id"] in dealt and not link["closed_t"]:
                store.exec("UPDATE needs SET deals=deals+1 WHERE id=?", link["need_id"])
        return DEAL


def _no_race(store: Store, conv, need_id: str, one_more: bool = False) -> None:
    """An author's open yeses on a need may not outnumber its places left. An assistant said yes to both
    replies to a need for one sitter, and whichever answered first — the adversary — got the deal (replay).
    Only the author's own yeses are counted, so the refusal tells them nothing about anyone else. `one_more`
    gives a full need one place for this yes and changes nothing else: the need stays full, since one that came
    back into view would tell its readers it had filled, and so that its author had made a deal (rule 2); and on
    a need with places left it is nothing, so it is never a way round a race."""
    need = store.one("SELECT wants, deals, author_id FROM needs WHERE id=?", need_id)
    if not need["wants"]:
        return
    if _full(need) and not one_more:
        raise Refused(f"your person's need is full: {need['deals']} of {need['wants']} found, so a yes here would "
                      "be one more deal. Nothing was sent. Only if your person wants this one too — not on a yes in "
                      "advance — `agree` here with one_more=true first, and a `reply` with agree=true after it keeps "
                      "that yes; if they have what they wanted, `pass` the need, which closes it and ends its other "
                      "conversations.")
    held = []
    for c in store.all("SELECT c.*, p.yes_t, p.yes_in FROM conversations c JOIN conversation_needs cn ON "
                       "cn.conversation_id=c.id AND cn.need_id=? JOIN conversation_people p ON p.conversation_id=c.id "
                       "AND p.person_id=? WHERE c.id<>? AND p.yes_t IS NOT NULL AND c.deal_t IS NULL ORDER BY p.yes_t",
                       need_id, need["author_id"], conv["id"]):
        if not _over(store, c) and _holds_yes(c, _signature(_in(store, c))):
            held.append(c["id"])
    places = max(need["wants"] - need["deals"], 1 if one_more else 0)
    if len(held) >= places:
        where = ", ".join(f"[{c}]" for c in held)
        raise Refused(f"your person already said yes in {where} on this need, which is for {need['wants']}"
                      f"{' (' + str(need['deals']) + ' found)' if need['deals'] else ''}: another yes would race "
                      "it, and whichever side answered first would get the deal. Nothing was sent. If this one is "
                      "better, take that yes back first (`agree` with withdraw) or `pass` that conversation.")


REPORTED = "reported"
_AFTER_A_DEAL = ("from here it is between the two of them, on the contact each has. If they pressure or threaten "
                 "your person, stop answering and block that contact; for anything dangerous, the police")


def report(store: Store, person_id: str, ref: str) -> str:
    """Report a need that reached them, or someone in a pre-deal conversation, to the owner of the community it
    came through: for someone in a conversation, the one they are joined to it by. A scammer fishing for children's
    names could not be put out: an owner meets members only through needs and conversations of their own (diary
    study). Always answered REPORTED, however often: a report about the owner themselves, or to an owner who has
    left, is delivered to nobody. It is kept only as the reporter's own, closed and pointing at no one, so that the
    daily limit counts it too; so is a report about someone the reporter has made a deal with."""
    ref, seat = _seat_ref(ref)
    with store.transaction():
        _acting(store, person_id)
        if ref.startswith("n-"):
            need, community = _in_front(store, ref, person_id, "that need is no longer in front of your person")
            # A need for two stays open after its first deal, and a report of it made then let the one who dealt
            # watch which anonymous needs went when the owner removed its author (review).
            if _dealt_on(store, person_id, ref):
                raise Refused(f"your person has a deal on that need, which cannot be reported: {_AFTER_A_DEAL}")
            reported, need_id, conv_id, seat = need["author_id"], ref, "", 0
        else:
            conv = _conversation(store, person_id, ref)
            # One who went before the others' deal is not told of it: their report is taken, and held back as every
            # report of a conversation that became a deal is (`_reported`).
            if conv["deal_t"] and not _left_before_the_deal(store, conv, person_id):
                raise Refused(f"that one is a deal, which cannot be reported: {_AFTER_A_DEAL}")
            reported = _target(store, conv, person_id, seat)
            community = _link_via(store, conv, person_id, reported)
            seat = store.one("SELECT seat FROM conversation_people WHERE conversation_id=? AND person_id=?", ref,
                             reported)["seat"]
            need_id, conv_id = "", ref
        owner = (store.one("SELECT created_by FROM communities WHERE id=?", community) or {"created_by": ""})[
            "created_by"]
        if owner == person_id:
            raise Refused("your person owns the community this came through, so there is nobody to report it to: "
                          "`community` remove it directly if they want that person out, or `pass` it")
        if store.one("SELECT 1 FROM reports WHERE reporter_id=? AND need_id=? AND conversation_id=? AND seat=?",
                     person_id, need_id, conv_id, seat):
            return REPORTED
        if store.one("SELECT COUNT(*) n FROM reports WHERE reporter_id=? AND t>?",
                     person_id, store.now() - 86400)["n"] >= REPORTS_PER_DAY:
            raise Refused(f"that is {REPORTS_PER_DAY} reports in a day; the rest can wait until tomorrow")
        # Someone who made a deal with the reported side knows their name, and a removal by the report would show
        # them which anonymous needs were theirs (review 2).
        delivered = (owner != reported and is_member(store, owner, community)
                     and not _dealt(store, person_id, reported))
        store.exec("INSERT INTO reports(id, community_id, reporter_id, reported_id, need_id, conversation_id, t, "
                   "closed_t, seat) VALUES (?,?,?,?,?,?,?,?,?)", _new_id(store, "reports", "r"),
                   community if delivered else "", person_id, reported if delivered else "", need_id, conv_id,
                   store.now(), None if delivered else store.now(), seat)
    if delivered:
        _nudge(store, owner)
    return REPORTED


def dismiss(store: Store, owner_id: str, ref: str, community_id: str) -> None:
    """The owner clears a report without acting on it. Nobody is told."""
    ref = _ref(ref)
    with store.transaction():
        community_id = _owned(store, owner_id, community_id)
        if not store.one("SELECT 1 FROM reports WHERE id=? AND community_id=? AND closed_t IS NULL", ref, community_id):
            raise NotYours()
        store.exec("UPDATE reports SET closed_t=? WHERE id=?", store.now(), ref)


def report_community(store: Store, owner_id: str, ref: str) -> str | None:
    """The community of a report to this owner, so the owner's assistant need not name it."""
    r = store.one("SELECT r.community_id FROM reports r JOIN communities c ON c.id=r.community_id "
                  "WHERE r.id=? AND c.created_by=?", _ref(ref), owner_id)
    return r["community_id"] if r else None


def _reported(store: Store, community_id: str) -> list[dict]:
    """Open reports in a community, with what the reported side wrote before any deal: after one, their words may
    name them. A deal closes the reports on its conversation; one that older code left open is held back."""
    out = []
    # Looked up per report: a subquery over every deal scanned the whole server on each owner's check (review 2).
    for r in store.all("SELECT * FROM reports r WHERE community_id=? AND closed_t IS NULL AND NOT EXISTS (SELECT 1 "
                       "FROM conversations c WHERE c.id=r.conversation_id AND c.deal_t IS NOT NULL) ORDER BY t",
                       community_id):
        if r["conversation_id"]:
            wrote = [m["text"] for m in store.all(
                "SELECT text FROM messages WHERE conversation_id=? AND sender_id=? ORDER BY id",
                r["conversation_id"], r["reported_id"])][-MESSAGES_WAITING:]
        else:
            need = store.one("SELECT text FROM needs WHERE id=?", r["need_id"])
            wrote = [need["text"]] if need and need["text"] else []
        out.append({"id": r["id"], "kind": "conversation" if r["conversation_id"] else "need", "wrote": wrote})
    return out


def withdraw(store: Store, person_id: str, conversation_id: str) -> str:
    """Take back their person's yes before it is a deal. Nobody else was shown the yes, so nobody is shown that it
    went either."""
    with store.transaction():
        _acting(store, person_id)
        conv = _conversation(store, person_id, _seat_ref(conversation_id)[0])
        if _left_before_the_deal(store, conv, person_id):
            raise Refused(_GONE_FROM)
        if conv["deal_t"]:
            raise Refused("that one is already a deal; a deal cannot be taken back, and nothing more goes through "
                          "Bridge: your person settles it with them directly, on their contact")
        mine = store.one("SELECT yes_t FROM conversation_people WHERE conversation_id=? AND person_id=?", conv["id"],
                         person_id)
        if not mine["yes_t"]:
            return NO_YES
        if _over(store, conv):
            raise Refused("that conversation is over; there is nothing to take back")
        store.exec("UPDATE conversation_people SET yes_t=NULL WHERE conversation_id=? AND person_id=?", conv["id"],
                   person_id)
        return WITHDRAWN


def pass_on(store: Store, person_id: str, ref: str) -> str:
    """Stop seeing a need, close your own, or leave a conversation — saying which, and "already" when it
    was done before. The others in a conversation see that it ended, or only that someone is no longer in it, and
    never learn who they were talking to."""
    ref = _seat_ref(ref)[0]
    with store.transaction():
        _acting(store, person_id)
        now = store.now()
        if not ref.startswith("n-"):
            conv = _conversation(store, person_id, ref)
            if conv["deal_t"] and not _left_before_the_deal(store, conv, person_id):
                raise Refused("that one is already a deal; it is between the two of you now")
            mine = store.one("SELECT passed_t FROM conversation_people WHERE conversation_id=? AND person_id=?", ref,
                             person_id)
            if mine["passed_t"]:
                return "already left that conversation"
            store.exec("UPDATE conversation_people SET passed_t=? WHERE conversation_id=? AND person_id=?", now, ref,
                       person_id)
            return "left that conversation (still in the community)"
        own = store.one("SELECT closed_t FROM needs WHERE id=? AND author_id=?", ref, person_id)
        if own:
            if own["closed_t"]:
                return "already closed"
            store.exec("UPDATE needs SET closed_t=? WHERE id=?", now, ref)
            return "closed your need"
        if not _sent_to_them(store, ref, person_id):
            raise NotYours()
        if store.one("SELECT 1 FROM passes WHERE need_id=? AND person_id=?", ref, person_id):
            return "already passed"
        store.exec("INSERT INTO passes(need_id, person_id, t) VALUES (?,?,?)", ref, person_id, now)
        return "passed"
# -- what an assistant is shown ----------------------------------------------------------------------

def inbox(store: Store, person_id: str, *, passed: bool = False, needs_from: str | None = None) -> dict:
    """Everything waiting for this person. `passed`: the open needs they passed, instead of the rest — a
    pass was for good, and a member who later saw the lost dog could no longer find the alert (simulation).
    `needs_from`: only needs, from that one on, older ones next; the page's `next` is where the following page
    starts. Reading older needs used to mean passing newer ones: a person could not look further without saying
    no to what was in front of them (design review). A counterpart is "them" until a deal, and then the name and
    contact they chose. No id, name, contact or `about` of anyone else appears before that."""
    now = store.now()
    conversations, live_on = [], {}
    for conv in [] if needs_from else store.all(
            "SELECT c.* FROM conversations c JOIN conversation_people p ON p.conversation_id=c.id AND p.person_id=? "
            "ORDER BY c.last_t DESC", person_id):
        people, links = _people(store, conv["id"]), _links(store, conv["id"])
        mine = next(p for p in people if p["person_id"] == person_id)
        if conv["deal_t"]:
            # Someone who went before the deal was not in it, and is shown nothing of it.
            if conv["deal_t"] + DEAL_SHOWN_S <= now or not mine["dealt"]:
                continue
        elif mine["passed_t"] or conv["last_t"] + QUIET_TTL_S <= now:
            continue
        # Two people: "you" and "them", as always. More: each by their seat, the same number for everyone in it.
        group, seat_of = len(people) > 2, {p["person_id"]: p["seat"] for p in people}

        def who(pid: str, group=group, seat_of=seat_of) -> str:
            return "you" if pid == person_id else f"person {seat_of.get(pid, '?')}" if group else "them"

        messages = store.all("SELECT id, sender_id, text, t FROM messages WHERE conversation_id=? ORDER BY id",
                             conv["id"])
        revision = len(messages)
        if conv["deal_t"]:
            # A deal ends the conversation, and what each side last said before it is where the when and
            # where were: the deal view dropped them, and the side told later could say who but not when (audit).
            last = {m["sender_id"]: m["id"] for m in messages if m["t"] <= conv["deal_t"]}
            messages = [m for m in messages if m["id"] in last.values()]
        your_turn = bool(messages) and messages[-1]["sender_id"] != person_id
        keep = MESSAGES_SHOWN if your_turn else MESSAGES_WAITING
        inside = _in(store, conv, people, links)
        mine_by = [link for link in links if link["author_id"] == person_id]
        started = conv["starter_id"] == person_id

        def community_of(cid: str) -> str:
            row = store.one("SELECT name FROM communities WHERE id=?", cid)
            return row["name"] if row else ""
        # Each person is shown the community they are joined to it by: its starter, every need's; an author, only
        # their own, since the others' would tell them which communities the starter is in.
        via = links[0]["via"] if not group else "" if started or not mine_by else mine_by[0]["via"]
        item = {"id": conv["id"], "need": links[0]["text"] if links else "", "mine": bool(mine_by),
                "community": community_of(via),
                "messages": [{"from": who(m["sender_id"]), "text": m["text"]} for m in messages[-keep:]],
                "earlier": max(0, len(messages) - keep), "revision": revision,
                "deal": conv["deal_t"], "last_t": conv["last_t"],      # deal: when it became one, if it did
                # Their yes is never shown before the deal. In the simulation a liar said yes at once
                # so the other side would see it and hurry; three of four deals went to the liar.
                "you_said_yes": _holds_yes(mine, _signature(inside)),
                "your_turn": your_turn}
        if group:
            item["needs"] = [{"text": link["text"], "by": who(link["author_id"]),
                              "community": community_of(link["via"]) if started or link["author_id"] == person_id
                              else ""} for link in links]
            ins = {p["person_id"] for p in inside}
            item["people"] = [{"who": who(p["person_id"]), "started": p["seat"] == 1,
                               "in": p["person_id"] in ins} for p in people]
        if conv["deal_t"]:
            shown = []
            for p in people:
                if p["dealt"] and p["person_id"] != person_id:
                    o = store.one("SELECT name, contact, deleted_t FROM people WHERE id=?", p["person_id"])
                    shown.append(None if o["deleted_t"] else {"name": o["name"], "contact": o["contact"]}
                                 if not group else {"who": who(p["person_id"]), "name": o["name"],
                                                    "contact": o["contact"]})
            if group:
                item["everyone"] = shown
            else:
                item["them"] = shown[0] if shown else None
            # "Stops showing after 30 days" read the same on day 1 and day 29; two deals nearly went unseen
            # (diary study). So each deal says how long it has left, the way a need says its time left.
            item["shown_until"] = conv["deal_t"] + DEAL_SHOWN_S
        else:
            item["over"] = _over(store, conv)
            if mine_by:
                need = store.one("SELECT closed_t, wants, deals FROM needs WHERE id=?", mine_by[0]["need_id"])
                # "OVER — they moved on" was false when the author's own need had closed (simulation).
                item["need_closed"] = bool(need["closed_t"])
                # Only to its author: shown to anyone else, it would say a deal had been made elsewhere.
                item["need_full"] = _full(need)
            if mine_by and not item["over"]:
                # The first reply won: an author agreed to the adversary's while the real donor's waited, and a
                # deal ends the need's other conversations (simulation). So the author sees how many there are.
                need_id = mine_by[0]["need_id"]
                if need_id not in live_on:
                    live_on[need_id] = {o["id"] for o in store.all(
                        "SELECT c.* FROM conversations c JOIN conversation_needs cn ON cn.conversation_id=c.id AND "
                        "cn.need_id=? JOIN conversation_people p ON p.conversation_id=c.id AND p.person_id=? AND "
                        "p.passed_t IS NULL WHERE c.deal_t IS NULL", need_id, person_id) if not _over(store, o)}
                item["others_on_need"] = len(live_on[need_id] - {conv["id"]})
                item["deal_fills_need"] = need["wants"] - need["deals"] == 1
        conversations.append(item)
    # Only needs sent to one of the reader's own communities are even looked at (the rest of the query then decides,
    # exactly as before): read against every need on the server, `check` grew with the whole server, not with what
    # the reader could ever be shown — 65 ms at 20,000 needs, most of it deciding against needs from elsewhere.
    open_needs = ("FROM needs n JOIN people a ON a.id=n.author_id WHERE n.id IN (SELECT nc.need_id "
                  "FROM memberships r JOIN need_communities nc ON nc.community_id=r.community_id "
                  "WHERE r.person_id=? AND r.left_t IS NULL) "
                  f"AND n.author_id<>? AND {_TAKING} "
                  "AND a.deleted_t IS NULL AND " + _SHARED.format(reader="?") + " "
                  f"AND {'' if passed else 'NOT '}EXISTS "
                  "(SELECT 1 FROM passes p WHERE p.need_id=n.id AND p.person_id=?) "
                  "AND NOT EXISTS (SELECT 1 FROM conversation_needs cn JOIN conversations c ON "
                  "c.id=cn.conversation_id WHERE cn.need_id=n.id AND c.starter_id=?)")
    args: tuple = (person_id, person_id, now, person_id, person_id, person_id)
    with store.transaction():
        if needs_from:
            # Any need that was sent to them marks a place, whatever has become of it since: one refused once it
            # had gone would tell a closed need from one whose author left (`_sent_to_them`).
            at = store.one("SELECT created_t, rowid FROM needs WHERE id=?", _ref(needs_from))
            if not at or not _sent_to_them(store, _ref(needs_from), person_id):
                raise NotYours()
            open_needs += " AND (n.created_t<? OR (n.created_t=? AND n.rowid<=?))"
            args += (at["created_t"], at["created_t"], at["rowid"])
        # One moment: an author who went mid-call failed `check`, and a list and a count read apart could tell
        # "they went" from "it closed" (review).
        page = store.all(f"SELECT n.* {open_needs} ORDER BY n.created_t DESC, n.rowid DESC LIMIT ?",
                         *args, NEEDS_SHOWN + 1)
        reached = [{"id": n["id"], "text": n["text"], "expires_t": n["expires_t"], "people": n["wants"],
                    "community": store.one("SELECT name FROM communities WHERE id=?",
                                           _via(store, n["id"], person_id))["name"]}
                   for n in page[:NEEDS_SHOWN]]
        more = max(0, store.one(f"SELECT COUNT(*) n {open_needs}", *args)["n"] - NEEDS_SHOWN)
    # The count is the conversations listed above, not every one ever opened: it said "1 conversation"
    # about one its author had passed, which no longer appeared anywhere (swarm).
    mine = [] if needs_from else [{
             "id": n["id"], "text": n["text"], "expires_t": n["expires_t"], "conversations": n["conversations"],
             "people": n["wants"], "deals": n["deals"], "full": _full(n),
             "communities": [c["name"] for c in store.all(
                 "SELECT c.name FROM need_communities nc JOIN communities c ON c.id=nc.community_id "
                 "JOIN memberships m ON m.community_id=nc.community_id AND m.person_id=? AND m.left_t IS NULL "
                 "WHERE nc.need_id=? ORDER BY c.created_t, c.rowid", person_id, n["id"])]}
            for n in store.all(
        "SELECT n.*, (SELECT COUNT(*) FROM conversation_needs cn JOIN conversations c ON c.id=cn.conversation_id "
        "JOIN conversation_people p ON p.conversation_id=c.id AND p.person_id=n.author_id AND p.passed_t IS NULL "
        "WHERE cn.need_id=n.id AND c.deal_t IS NULL AND c.last_t>?) conversations FROM needs n "
        "WHERE n.author_id=? AND n.closed_t IS NULL AND n.expires_t>? ORDER BY n.created_t DESC",
        now - QUIET_TTL_S, person_id, now)]
    reports = []
    for c in [] if needs_from else store.all(
            "SELECT c.id, c.name FROM communities c JOIN memberships m ON m.community_id=c.id "
            "AND m.person_id=? AND m.left_t IS NULL WHERE c.created_by=?", person_id, person_id):
        reports += [{**r, "community": c["name"]} for r in _reported(store, c["id"])]
    return {"me": me(store, person_id), "conversations": conversations, "reached": reached, "more": more, "mine": mine,
            "passed": passed, "reports": reports, "page": bool(needs_from),
            "next": page[NEEDS_SHOWN]["id"] if len(page) > NEEDS_SHOWN else None}


def sweep(store: Store) -> None:
    """Delete what ended more than RETAIN_S ago: conversations with their messages, needs with their
    passes, and the call log. Cheap, so `check` runs it about once an hour."""
    with store.transaction():
        now = store.now()
        last = store.one("SELECT v FROM kv WHERE k='swept_t'")
        if last and float(last["v"]) > now - 3600:
            return
        store.exec("INSERT OR REPLACE INTO kv(k, v) VALUES ('swept_t', ?)", str(now))
        cutoff = now - RETAIN_S
        # Ended: a deal; fewer than two left in it, when the last but one went; or a week with nobody answering.
        ended = [r["id"] for r in store.all(
            "SELECT c.id FROM conversations c WHERE COALESCE(c.deal_t, (SELECT CASE WHEN SUM(p.passed_t IS NULL) < 2 "
            "THEN MAX(p.passed_t) END FROM conversation_people p WHERE p.conversation_id=c.id), c.last_t + ?) < ?",
            QUIET_TTL_S, cutoff)]
        for table, column in (("messages", "conversation_id"), ("conversation_needs", "conversation_id"),
                              ("conversation_people", "conversation_id"), ("conversations", "id")):
            for i in range(0, len(ended), 500):
                chunk = ended[i:i + 500]
                store.exec(f"DELETE FROM {table} WHERE {column} IN ({','.join('?' * len(chunk))})", *chunk)
        gone = "SELECT id FROM needs WHERE COALESCE(closed_t, expires_t) < ? AND NOT EXISTS " \
               "(SELECT 1 FROM conversation_needs cn WHERE cn.need_id=needs.id)"
        store.exec(f"DELETE FROM passes WHERE need_id IN ({gone})", cutoff)
        store.exec(f"DELETE FROM need_communities WHERE need_id IN ({gone})", cutoff)
        store.exec(f"DELETE FROM needs WHERE id IN ({gone})", cutoff)
        store.exec("DELETE FROM calls WHERE t < ?", cutoff)
        store.exec("DELETE FROM reports WHERE t < ?", cutoff)
        # Sign-in: expired steps, connections whose app never called within a day (they made nobody), apps
        # registered that never connected, spent codes, and counts from before yesterday.
        store.exec("DELETE FROM tokens WHERE expires_t < ?", now)
        store.exec("DELETE FROM tokens WHERE grant_id IN (SELECT id FROM grants WHERE revoked_t IS NOT NULL OR "
                   "(person_id='' AND created_t < ?))", now - 86400)
        store.exec("DELETE FROM grants WHERE revoked_t < ? OR (person_id='' AND created_t < ?)", cutoff, now - 86400)
        store.exec("DELETE FROM clients WHERE created_t < ? AND id NOT IN (SELECT client_id FROM grants)",
                   now - 86400)
        store.exec("DELETE FROM link_codes WHERE created_t < ?", now - LINK_CODE_S)
        store.exec("DELETE FROM daily WHERE day < ?", _day(store) - 1)


def stats(store: Store) -> dict:
    """For the operator: counts, never text."""
    now = store.now()
    def count(sql: str) -> int:
        return store.one(f"SELECT COUNT(*) n FROM {sql}")["n"]
    return {"people": count("people WHERE deleted_t IS NULL"), "communities": count("communities"),
            "needs": count("needs"), "conversations": count("conversations"), "messages": count("messages"),
            "deals": count("conversations WHERE deal_t IS NOT NULL"),
            # How people reach the server: connections signed in, and the connector links of their own from before.
            "connections": count("grants WHERE revoked_t IS NULL AND person_id<>''"),
            "own_links": count("connectors c JOIN people p ON p.id=c.person_id WHERE c.revoked_t IS NULL AND "
                               "p.deleted_t IS NULL"),
            # Accounts nobody's AI uses any more but whose needs are still out: someone who removed Bridge and
            # added it again without a code leaves one behind.
            "orphans": store.one("SELECT COUNT(*) n FROM people p WHERE deleted_t IS NULL AND EXISTS (SELECT 1 FROM "
                                 "needs WHERE author_id=p.id AND closed_t IS NULL AND expires_t>?) AND NOT EXISTS "
                                 "(SELECT 1 FROM calls WHERE person_id=p.id AND t>?)", now, now - 14 * 86400)["n"],
            # Nudges and the operator's alerts share ntfy.sh's 250 a day per IP (docs/OPERATIONS.md).
            "nudges_today": store.one("SELECT COUNT(*) n FROM calls WHERE tool='nudge' AND t>?", now - 86400)["n"],
            "calls": {r["tool"]: r["n"] for r in store.all("SELECT tool, COUNT(*) n FROM calls GROUP BY tool")}}
