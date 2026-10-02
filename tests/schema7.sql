-- Schema version 7, as the live database had it before 8 (conversations of several) and 9 (locks).

-- `name` and `contact` are shown to one person only: the other side of a deal. `about` is never shown
-- to anyone; it is the person's own assistant's notes, read back to it and nothing else.
-- `notify`: the ntfy.sh topic the server made for their nudges, if they asked for one; `nudged_t`: the last sent.
CREATE TABLE people (
  id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
  about TEXT NOT NULL DEFAULT '', created_t REAL NOT NULL, deleted_t REAL,
  notify TEXT NOT NULL DEFAULT '', nudged_t REAL
);
-- The secret in a person's own connector URL, hashed: how people connected before sign-in (PROTOCOL.md §5).
-- Nothing makes a new one but the operator's and the simulations' own tools.
CREATE TABLE connectors (
  secret_hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, created_t REAL NOT NULL, revoked_t REAL
);
CREATE INDEX connectors_by_person ON connectors(person_id, revoked_t);
-- `created_by` owns the community: only they replace the invite link or remove someone. The code is
-- readable on purpose: any member may pass the link on.
CREATE TABLE communities (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_by TEXT NOT NULL, invite_code TEXT NOT NULL UNIQUE,
  created_t REAL NOT NULL
);
-- `banned_t`: removed by the owner; the invite link no longer lets them back in.
CREATE TABLE memberships (
  person_id TEXT NOT NULL, community_id TEXT NOT NULL, joined_t REAL NOT NULL, left_t REAL, banned_t REAL,
  PRIMARY KEY (person_id, community_id)
);
CREATE INDEX memberships_by_community ON memberships(community_id, left_t);
-- What someone's assistant sent out. Its author is shown to nobody. `wants`: how many deals fill it; 0 means none do. A
-- full need reaches nobody new and stays open, conversations and all, until its author closes it or it expires.
-- `deals`: how many it has had, kept here because the conversations themselves are deleted long before a
-- year-long need ends.
CREATE TABLE needs (
  id TEXT PRIMARY KEY, author_id TEXT NOT NULL, text TEXT NOT NULL,
  created_t REAL NOT NULL, expires_t REAL NOT NULL, closed_t REAL,
  wants INTEGER NOT NULL DEFAULT 1, deals INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX needs_by_author ON needs(author_id, created_t);
CREATE TABLE need_communities (
  need_id TEXT NOT NULL, community_id TEXT NOT NULL, PRIMARY KEY (need_id, community_id)
);
CREATE INDEX need_communities_by_community ON need_communities(community_id);
-- Every member's assistant sees every open need in their communities. A pass says "not for us": it
-- hides the need from that one assistant and is reported to nobody.
CREATE TABLE passes (
  need_id TEXT NOT NULL, person_id TEXT NOT NULL, t REAL NOT NULL, PRIMARY KEY (need_id, person_id)
);
-- Two people, neither named to the other, whose assistants are talking about one need. `via`: the
-- community the responder saw the need through, fixed when the conversation opens. Both sides are shown
-- it, and an owner can act on the conversation only in that community. `last_t`: when one side last answered
-- the other; a second message before an answer does not move it, so a week unanswered ends it. A yes is to the
-- conversation as it stands: any message clears both.
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, need_id TEXT NOT NULL, author_id TEXT NOT NULL, responder_id TEXT NOT NULL,
  via TEXT NOT NULL DEFAULT '', created_t REAL NOT NULL, last_t REAL NOT NULL,
  author_yes_t REAL, responder_yes_t REAL, deal_t REAL, author_passed_t REAL, responder_passed_t REAL,
  UNIQUE (need_id, responder_id)
);
CREATE INDEX conversations_by_author ON conversations(author_id, last_t);
CREATE INDEX conversations_by_responder ON conversations(responder_id, last_t);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, sender_id TEXT NOT NULL, text TEXT NOT NULL,
  t REAL NOT NULL
);
CREATE INDEX messages_by_conversation ON messages(conversation_id, id);
CREATE INDEX messages_by_sender ON messages(sender_id, t);
-- A member reporting a need, or the other side of a conversation, to the owner of the community it came
-- through. The owner is shown what the reported side wrote, never who either of them is.
CREATE TABLE reports (
  id TEXT PRIMARY KEY, community_id TEXT NOT NULL, reporter_id TEXT NOT NULL, reported_id TEXT NOT NULL,
  need_id TEXT NOT NULL DEFAULT '', conversation_id TEXT NOT NULL DEFAULT '', t REAL NOT NULL, closed_t REAL
);
CREATE INDEX reports_by_community ON reports(community_id, closed_t);
CREATE INDEX reports_by_reporter ON reports(reporter_id, t);
-- One row per tool call: who, which tool, when. No arguments, no text. And one per Join press on an invite
-- page: person '', tool "join-page <ai> <community id>".
CREATE TABLE calls (t REAL NOT NULL, person_id TEXT NOT NULL, tool TEXT NOT NULL);
CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);

-- One per connection: an app its person signed in from. `person_id` is '' until the app's first tool call, which
-- makes the person. `invite`: the invite code the Allow page was opened with, joined at that call.
CREATE TABLE grants (
  id TEXT PRIMARY KEY, client_id TEXT NOT NULL, person_id TEXT NOT NULL DEFAULT '', invite TEXT NOT NULL DEFAULT '',
  created_t REAL NOT NULL, revoked_t REAL
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
CREATE TABLE link_codes (
  hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, replace INTEGER NOT NULL, created_t REAL NOT NULL, used_t REAL
);
-- Counts per day: people whose first community this is (`joins g-…`), people made with no invite (`uninvited`).
CREATE TABLE daily (k TEXT NOT NULL, day INTEGER NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (k, day));
PRAGMA user_version=7;
