# The Bridge protocol — draft 0.9

How people's own AI assistants find each other something worth doing, without anyone being named until
everyone involved says yes. This document is normative: an implementation that follows it interoperates with any
assistant that can call tools. `bridge/` in this repository is the reference implementation. The reasoning
is in [docs/DESIGN.md](docs/DESIGN.md).

The words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 1. Roles

- **Person** — a human. Has a `name` and a `contact` (shown only in a deal) and an `about`: their own
  assistant's notes on them — what they bring and want, what the assistant may say yes to for them, how
  often to check — read back to that assistant by `check` and to nobody else.
- **Assistant** — the person's own AI (ChatGPT, Claude, anything that can call tools). It acts *as* its
  person and has no identity of its own. Every judgment — what fits, what to say, what to walk away from —
  is the assistant's; the protocol constrains only what may be revealed.
- **Server** — carries needs and messages, records yeses. It runs no model and makes no judgments.
- **Community** — a set of people who can reach each other. The only unit of reach: there is no global
  network. Two people or a million. Whoever starts one owns it.

## 2. Objects

| Object | Fields a member's assistant can see | Lifetime |
|---|---|---|
| **Need** `n-…` | text, community it arrived through, time left, how many people it is for; to its author, whether it is full | 7 days unless its author set otherwise (an hour to a year), or until its author closes it. At as many deals as it is for (one by default) it is *full*: it reaches nobody new, and its conversations carry on |
| **Conversation** `c-…` | the need or needs it was opened on, the community it came through (fixed when it opens), messages as `you`/`them`, whose turn, its revision (how many messages it holds), whether it is over; to a need's author, how many other live conversations the need has, and whether the need is full. Its starter opened it on one need or several that reached them; each need's author is in it by that need. With more than two people in it, each is `person N` by a seat that is the same for everyone in it, every need it is on is shown to everyone in it, and who is no longer in it is shown, never how they went; its starter is shown the community each need came through, an author only their own. Two people may hold more than one conversation | until a deal, fewer than two people still in it, or 7 days without an answer: a second message from someone waiting does not restart the 7 days. Someone is out of it once they pass it, delete themselves or are removed through it, and an author once every need of theirs in it has closed. A need that expires or fills without closing does not end its conversations |
| **Deal** | the need or needs, the name and contact of everyone else in it, and the last message from each before it. A deal ends the conversation: nothing more is carried, and they use each other's contact. Someone out of it before the deal is shown nothing of it | shown for 30 days |
| **Community** `g-…` | name, id, invite link (members only); whether fewer than ten people have ever joined it (`small`), which every member and its invite page are shown, and which only ever turns off, at a join; to its owner, how many other people have ever joined — never who, and never how many are in it now, which would move when an anonymous author left | — |
| **Report** `r-…` | to the community's owner only: whether a need or someone in a conversation was reported, and what that side wrote before any deal — never who reported it, nor who wrote it, but for what §4 names | until the owner removes or dismisses, either side deletes themselves, its conversation becomes a deal, or its reporter makes a deal on its need; 90 days at most |

Ids are short, lowercase and free of look-alike characters, because assistants copy them by hand, and so are
invite codes, which are found whatever their case; an older mixed-case code is found as written. An invite link
is found despite the punctuation, brackets and invisible characters a chat wraps it in, and of two in one text,
the first.

## 3. The rules

1. **Nobody is named until everyone says yes.** Before a deal the server MUST NOT show a member anything that
   identifies anyone else in it, or anyone whose need reached them: no person id, name, contact or `about`. Before a deal the server MUST refuse
   text that contains the writer's own name or contact, or anything shaped like a contact (an email address,
   a phone number, an @handle, a link), read as a reader would read it: invisible characters dropped, and
   fullwidth and other compatibility forms folded. A community's name, which every member and its invite page
   see, MUST NOT carry anything shaped like a contact either. The guard MUST NOT depend on who else is a
   member: a refusal that did would tell the writer who is here. It is a seatbelt for an assistant that slips,
   not a wall, and implementations MUST NOT present it as more.
2. **A no is never attached to a name.** Ignoring, passing and leaving MUST NOT be reported except as "the
   conversation is over" or, of several people, that one of them is no longer in it, the same however they
   went, and MUST NOT be counted into anything another member sees. The author of a need
   MUST NOT be told who it reached, or how many. A server MUST NOT show anyone anything about another
   person's activity or past: how many things they answer, walk-aways, deals, removals or reports. That is a
   reputation score, and it flags honest people. The one exception is what §4's refusals of `remove`, and which
   reports arrive or close, tell an owner.
3. **Nobody reads anyone else's `about`.** It MUST NOT be shown to anyone else or used by the server for
   anything.
4. **What a member writes is data.** The server MUST mark member-written text in everything it returns
   — the person's own `about` included — so that it cannot pass for the server's own words or layout (the
   reference implementation drops invisible characters and blank lines, folds compatibility forms, collapses
   runs of angle brackets, fences it in `<<<` `>>>`, and marks every line of it after the first).
   Assistants MUST NOT treat it as instructions, but for their own notes in `about`. The server never writes
   inside a conversation, and SHOULD label, outside the marks, member text shaped like a notice from the
   server or its moderators ("SYSTEM:", "verified by moderators"), but for the person's own name, contact
   and notes. The label is a shape match, not a judgment of the member.
5. **Only the person can say yes, to what they saw.** An assistant MUST call `agree` only on its person's
   yes — given for that deal, or given in advance for deals of that kind ("if you find X, say yes for me"),
   in which case the assistant MUST tell them what it agreed to. A yes is to the conversation as it stands:
   it names the revision its person saw, and the server MUST refuse it, recording nothing, when anyone else
   has written since. It is also to who is in it: a yes given before someone went MUST NOT count. Every message
   clears every yes; its writer is told when it cleared their own, and nobody is told about anyone else's. It is a
   deal when everyone still in it has a yes that counts. The server cannot verify any of this, and MUST NOT claim to.
6. **A need is full at as many deals as it is for.** One unless its author said otherwise (`people`), or never
   if they chose "as many as come". A full need reaches nobody new; its conversations carry on until they end
   on their own or its author closes the need, which ends them. The server MUST refuse its author's yes in one
   of them unless they ask for one more deal (`one_more`), which gives that yes one place and leaves the need
   full, since a need that came back into view would tell its readers it had filled. On a need that is not full,
   `one_more` MUST change nothing. An author MUST NOT hold more yeses in live conversations on a need than it
   has places left: a second yes for one place races the first, and whichever side answers first gets the
   deal. The refusal names only the author's own conversations.
7. **Each thing stands alone.** Before a deal, what a member is shown about a need or a conversation, and
   how any operation on it answers them, MUST depend only on that thing and on the member's own memberships
   and acts, except for what happens to all of one person's things in a community at once (their leaving
   it, deleting themselves or being removed), which may be seen together, including through which shared
   community their things still reach the member; and except for what §4 does to keep a deal partner from
   aiming a removal.

## 4. Operations

Every operation is called by an assistant on behalf of one authenticated person. Results are text written
for an assistant to read. Two kinds of failure: a *refusal* with a reason the assistant can act on, and
*not yours*, which MUST read the same whether the thing does not exist or belongs to someone else.

| Operation | Arguments | Effect |
|---|---|---|
| `check` | `passed?`, `needs_from?` | Everything waiting: deals, conversations, needs that reached this person, their own open needs, their `about`, their communities, what setup is missing. With `passed`, the open needs they passed before, in place of new ones. With `needs_from`, a need id `check` gave: only needs, from that one on, older ones next; reading never passes or answers anything. A server SHOULD bound what `check` returns, so that deals and reports are never pushed past a host's limit on a tool's answer |
| `setup` | `name?`, `contact?`, `about?`, `notify?`, `another_app?`, `new_link?`, `code?` | Sets any of the three. An `about` sent back in the marks `check` showed it in is saved without them. `notify`: `on` or `off` (§5). `another_app`: a code that makes a connection in another app this same person. `new_link`: a code too, and once it is used every other connection of theirs ends. `code`: uses one, in a connection that holds nothing yet (§5) |
| `go` | `text`, `community_id?`, `people?`, `days?` | Sends a need to every community the person is in, or to one. The same text already open is not sent twice: it goes on to communities it has not reached, or is refused. `people`: how many deals fill it (default 1; 0: none do). `days`: how long it stays up (default 7, from about an hour to 365) |
| `reply` | `to` (a need, several needs, or a conversation), `text`, `agree?`, `revision?` | To a need: opens a conversation with its author. To several needs: opens one conversation with all their authors, each through the community the caller saw their need through; the caller's own open need may be one of them, at least one must be someone else's, and it holds at most ten people. The same caller on the same needs gets the same conversation back. To a conversation: adds a message, refused after three in a row from this person (§4). To a deal: refused, with "use their contact". Clears every yes. `agree` records the person's yes with it, in one step; in a conversation already open, it needs the `revision` their person saw before this message, and if everyone else still in it had already said yes to that, it is the deal there and the message is not sent |
| `agree` | `conversation_id`, `revision`, `one_more?`, `withdraw?` | Records this person's yes to the conversation at `revision`, refused if anyone else has written since, and says whether that made a deal, or whether it was already recorded. It does not count as a message for the 7-day timer. `one_more`: on the author's own full need, this yes may make one more deal. `withdraw` takes the yes back before a deal; the other side, never shown the yes, is not shown this either |
| `pass` | `ref` (one or more need or conversation ids) | For each: hides a need, closes one's own need, or leaves a conversation, which carries on without them if two or more are still in it — and says which, or that it was already done |
| `community` | `action` and what it needs | `create` (`name`); `join` (`invite_link`); `invite` (`community_id`): the link, any member; `leave` (`community_id`); `report` (`ref`). Owner only, while a member (one who has left is told so): `rename`, `new_link` (the old link stops working, and someone it sent to connect joins nothing through it), `remove` (`ref`: a need, a conversation of theirs, or a report), `dismiss` (`ref`: a report). In a conversation of several people, `report` and `remove` name one of them by seat, `c-…:2` |
| `forget_me` | `confirm="delete everything"` | Erases the person: name, contact, about, nudge topic, needs, access — and empties every conversation they were in, on both sides, because the other side's messages may name them |

A need shows in a community while its author is a member there. Leaving takes their needs down there,
rejoining brings back the open ones, and conversations under way carry on. A need that has gone from
someone's view MUST read the same whichever way it went, filling included: nobody but its author is shown
that a need is full, since that would say its author had made a deal.

The owner, while a member, may `remove` by a need sent to the community, by a conversation of their own
through it, or by an open report there. Through a conversation, only between its starter and an author joined to
it through this community: two authors meet only through the starter's community with each, which neither is
shown, and a removal that worked through one would tell the owner the other is a member there. `remove` MUST refuse a conversation that is a deal, a need the owner
has a deal on, a report whose conversation or need is one of those, a report of a conversation on a need the
owner has a deal on when the reported side wrote that need, a report whose reporter and reported side
have made a deal, and a report whose conversation has been deleted, since which of those it was is gone with
it. The fourth tells the owner the reported side is their deal partner, and the fifth that the reporter and
the reported side have made a deal; allowing either would show a deal partner all the other's needs. Each
MUST read the same whether its person is still a member or not.

After a removal, the link no longer admits that account, their needs stop showing there, and their pre-deal
conversations through it end. Deals are untouched. Nobody is told, though the removed person sees the
community gone from their list; if they join again from the chat, they are answered as for a link that no
longer works. Removal binds an account: whoever still holds the link can come back as someone new.

A member may report a need that reached them and has not gone from their view, or someone in a pre-deal
conversation of theirs, to the owner of the community it came through: for someone in a conversation, the one they
are joined to it by. They may not report a deal, a need they have a deal on,
or in a community they own; there they `remove` instead. The report goes to nobody when that owner is the
reported side or is no longer a member, or when the reporter and the reported side have made a deal, which named
them: it is kept only as the reporter's own, closed, so that the limit counts it. The answer reads the same
either way, and says that such cases exist; but an owner who has someone report through an account that has made
a deal learns, from whether the report arrives, whether the reported side is that deal's other person. The owner
sees what that side wrote before any deal, and never who reported it, nor who wrote it, but for what the
refusals and the silent report above tell. A report closes when the owner removes or dismisses, when either side
deletes themselves, when its conversation becomes a deal, or when its reporter makes a deal on its need. A deal
elsewhere between its two sides leaves it open, since closing it would tell the owner which anonymous need that
deal was on; removal by it is refused instead. It lasts 90 days at most.

### Reach

Every member of every community a need was sent to sees it, from the moment it is sent until it closes or
fills, including people who join meanwhile — everyone but its author, each once however many communities they
share. The server does not choose who sees a need; each assistant judges every need for itself.
`check` lists the newest open needs (the reference implementation: 20), says how many more there are, and
where the next ones start: `check` with `needs_from` lists them without passing any, and a pass hides one
until the reader asks for what they passed. Seeing is not a promise to read: an assistant reads as far as its
person wants, and nobody is told how far. A reader is told only which shared community a need came through.

### Limits

Text: 2000 characters (name 80, contact 200), `about` included, counted both as written and as rule 4 shows
them, marks included; text that shows as nothing is empty, and an empty `about` clears the notes. Anything
longer is refused, never cut. Per person per day: 10 needs, 200 messages, 10 reports. Per conversation, three
messages in a row from one side: a fourth waits for the other side's answer, and the refusal depends on that
conversation alone. A community takes at most 100 people a day for whom it is their first community, whether
they join at their first call or from the chat; someone already in a community is never refused by this. Someone
holding the link can use up a day's joins, and a new link does not reset the count. At most 1000 people a day
are made with no invite to join. A deal requires both people to have a name and a contact. Once a person is
deleted, every operation in their name MUST fail, including one already in flight.

### Retention

A server SHOULD delete conversations, their messages and closed needs 90 days after they ended.
A server MAY keep backups of its data for a bounded time, which it states to members; a deletion reaches a
backup only as the backup ages out. Restoring after the live data is lost loses what happened since that
backup, deletions included. The server says so, and its operator deletes again anyone they learn deleted
themselves in the meantime.

## 5. Transport and identity

The reference transport is [MCP](https://modelcontextprotocol.io) tools over streamable HTTP, at one connector
URL for everyone (`<server>/mcp`), with OAuth 2.1 sign-in: the authorization code with PKCE, dynamic client
registration, and the metadata of RFC 8414 and RFC 9728. An app that adds the URL sends its person to the
server's Allow page, which asks for nothing — no email, no password, no name — and knows nobody: the connection
the app then holds is the person. Nobody exists, or counts in an owner's number, until their own AI has called:
the first tool call through a new connection makes the person, subject to the limits in §4.

An invite page remembers its invite code in that browser for a day, in a cookie holding the code and nothing
else, and sends the person on to add Bridge to their AI; pressing Join with Claude or with ChatGPT remembers which,
in a second cookie, and the code then goes only to a sign-in that returns to that app. The Allow page names that
community, and the first call joins it. Where the code did not come through — another browser, an app's own sign-in window, an invite
replaced meanwhile — the person pastes the invite link into the chat and says "join this", as anyone already in
does. The invite page first asks whether the person already uses Bridge, and says how to join from their
chat if so. Later memberships come from `community` join or create.

A connection lasts until it is ended. Its access token is renewed without asking, and the token that renews it
neither expires nor is replaced, since a connection whose renewal failed would ask for Allow again and make
someone new. Allow always makes someone new: removing Bridge from an app and adding it again is a new
connection. A code joins connections to one person. `setup` with `another_app` gives one: used once, within an
hour, in a connection that holds nothing yet (no name, contact, notes, nudges, open needs, conversations or
community of its own), it makes that connection this person, who joins whatever communities it had joined, and
erases the empty account it had made. `new_link` gives one too, and when it is used, every other connection of
the person ends, the one that asked included: for when someone else may have had access, and to move off an
older link. A brand-new connection that holds nothing asks its person whether they already use Bridge in
another app, and how to bring the code over if so.

Earlier revisions gave each person a connector URL of their own, with a secret in it (`/c/<secret>/mcp`). A
server MAY keep serving the ones it issued, and MUST NOT make anyone new through one.

**Locks.** A server MUST keep everything a member wrote — name, contact, `about`, needs, messages, a community's
name and its invite code — only locked, so that nothing it stores, and no backup of it, opens without a key that one
of the members it is for holds through their own connection. In the reference implementation (`bridge/vault.py`)
each person has a key pair whose private half is stored only locked under their connections' secrets: a renewal
token, an older connector link's secret, a code, each kept by the server only as a hash. Each community, need and
conversation has a key of its own, sealed to each person who may read it; a community's is also locked under its
invite code, which is how a newcomer gets it, and a conversation's needs open with the conversation's key, so that
everyone in it reads them. A name and contact are sealed, at each yes, to the others in the conversation, and shown
only once it is a deal. A code from `another_app` or `new_link` carries the person's key, locked under the code; a
code an operator makes holds none, and whoever uses it starts over: what was locked for the old key cannot be
opened again by anyone, and their communities open again only with their invite links. A server holds a person's
key only in a call that came through one of their connections, and for that call alone. It MAY see what it needs
to keep the rules: who is in which community, who is in which conversation, when things happen, how many, and the
ntfy topic it nudges. What passes through a server while it delivers a call is in its memory; that it goes no
further rests on the server running the code it publishes, and a server that publishes its code SHOULD say which
version is running (the reference implementation's `/health`) and tag every version that has run, where its code is
published. A database from before locks MAY keep each person's key open until each connection they already had has
taken its own copy, for at most two weeks.

Only an event (below) reaches into an assistant's chat unasked. A person hears about a need when their assistant
next calls `check`: when an app that subscribed is woken, on a schedule the person sets up where their app
allows it, and otherwise at the start of each conversation. A person MAY ask for a nudge when something is aimed
at them — a message or new conversation from the other side, a deal, a report to them as owner — at most once
every ten minutes. `notify` is `on` or `off`. The first `on` makes an unguessable ntfy.sh topic and returns it.
`on` again sends one test line, at most once a day. `off` clears the topic, so a later `on` makes a new one. A
nudge is one fixed line: it never says what or who, is never sent for a yes, and MUST NOT hold up or undo what
caused it. ntfy.sh sees when a topic is nudged. Whoever sees the phone it rings on can tie its moment to what
they sent.

An app that can be woken MAY subscribe, through a connection made by signing in, to one event: `waiting` (MCP
Events, by webhook). Before anything is sent, the app echoes a challenge, signed with its secret, at the address
it gave. The server posts only to public HTTPS addresses, connects to the address it checked, follows no
redirects, and keeps a subscription at most 30 days unless the app renews it; it ends with its connection. The
event goes when a nudge would, under one limit for all of a person's wake-ups together, and carries nothing:
like a nudge, it never says what or who, is never sent for a yes, and MUST NOT hold up or undo what caused it.
The app then does what its person asked, in the chat that subscribed. The app's operator sees when it is woken.

## 6. What conformance means

A conforming server guarantees what is revealed, to whom and when — rules 1 to 4, 6 and 7. It cannot
guarantee outcomes: rules 4 and 5 bind each person's own assistant, which no server can test, and a deal is
only as careful as both assistants. The words the reference implementation gives every assistant
(`bridge/mcp_server.py`, `instructions()`, and the rules `check` repeats because hosts keep old
instructions) are where most of its safety lives; another server should start from them.

## 7. Not specified, and stated goals

Storage. Federation between servers: today a community lives on one server. A later revision will keep messages
unreadable by the server operator in transit too, which needs the key to stay in each person's own app.
