# What was tried before, and why it was dropped

Three earlier designs, their studies and 27 decision documents came before this repository, which starts from
the design they led to. This page is what is worth knowing of them.

## 1. The board and the planner (September 16–19)

Members wrote profiles ("sheets"). A nightly planner — a model on the server, paid for by the operator —
read them all and invented multi-party arrangements, revealed in two phases and agreed by signature.

What killed it, each measured (`studies/bench`, `studies/stress` under the tag):

- **A central planner reading written profiles did no better than keyword matching** (all parties would do
  it: 1 of 5 proposals for matching, 0 of 6 for the planner). Only conditions where *private context
  reached the decision* did well: a per-person private screen (2 of 2) and an oracle with everyone's full
  context (6 of 6). This is the finding the current design is built on: the judgment belongs where the
  private context is, in each person's own assistant.
- **Hiding names behind descriptions hid nothing**: given the profiles, a model identified who a description
  meant in 50 of 50 cases, at group sizes from 7 to 60. Descriptions identify people.
- **Proposed time slots did not fit** (63% fell outside someone's stated hours), and **signatures did not
  bind** better than a click.

## 2. The relay (September 19–21)

One person asks one to three others, chosen from descriptions; the asker is named, the answerer is not; both
act by clicking buttons on a web page; failure is announced on a date fixed in advance so its timing says
nothing. Carefully built and audited four times, and a drift from the idea: a human click at every step, a
website holding it together, word matching as the only intelligence, and caps because every ask landed on a
person rather than on their assistant. It was never used by anyone. What survived it: the fencing of
member-written text, "a no is never reported", and the habit of turning every audit finding into a test.

## 3. The network, first cut (September 21)

The current design, with two things since removed:

- **An append-only event log with projections.** Every write was an event plus a handler; nothing ever
  replayed the log; deleting a person meant scanning it. It doubled the write path for an audit trail
  nobody read. Plain tables replaced it.
- **A guard that checked text against every member's name.** See docs/DESIGN.md §2 — it was an oracle, a
  way to unmask authors, a way to poison a community's vocabulary, and O(members) inside the global lock.
- **Facts about a counterpart's past.** For a day each conversation showed how many people had walked away
  from the other side this month, added after the liar looked clean once its earlier targets had left. The
  swarm showed it flagged honest people: most walk-aways are ordinary "not a fit" passes. Removed; the
  protocol now forbids anything about a counterpart's past.
- **Routing.** A need reached at most 25 members, chosen by matching its words against their `about`. That
  put a keyword matcher in charge of who got to judge — the benchmark's losing condition — and had the
  server read `about` after all. Now everyone sees every need and each assistant judges for itself.

## 4. Dropped 2026-09

- **Cookie identity.** Pressing Join made a person, their membership and a connector at once, and a signed
  cookie remembered the person so a second Join in the same browser added a membership instead of an account.
  Every press that never connected still made a person: a real owner saw "8 others" in a community one friend
  had joined, and the cookie told people who never connected that they were connected. It guarded only a
  second Join in the same browser. Now a person exists only at their AI's first call (DESIGN §2, "One
  door"). Trigger to bring a browser-side guard back: `bridge stats` orphans (people with open needs and
  no call in 14 days) rising while people report pressing Join when they already used Bridge.
- **Messages after a deal.** A deal's conversation went on carrying messages, and nudges, for as long as either
  side wrote. Nobody on the live copy had written one, and an audit ranked it the top risk for real people: a
  deal partner could message and nudge someone for months with no way to stop it. A deal now ends its
  conversation and shows each side's last message before it. Trigger: people who made a deal asking to go on
  through Bridge because the contact they were given did not work.
- **Showing yourself (`show`).** A person could put their own name, or name and contact, on one need or
  reply. Nobody used it live. In the situations study 3 of 200 situations needed it and 36 were made worse;
  assistants set it wrongly 59 times in 150; the impersonator took 5 of 15 adversary deals with it; and a
  shown name next to anything anonymous of the same person named that too, so the pair rule and the guard
  each needed an exception for it. A business can still put its public name in its need, unless that name
  shares a word with its writer's own setup name. Trigger: real needs refused, more than once, for a name
  their writer wanted known.
- **One live conversation per pair (a revival, then dropped).** The first cut let two people hold two
  conversations and told the assistants to drop one; each side dropped a different one and the match was
  lost. The rule that replaced it refused a second conversation and hid a need from someone its author was
  already talking with. Both tied two anonymous things to one author, and the hidden need came back at the
  deal (the rethink's author-swap scripts). Now both conversations stay and the assistants are told to keep
  both until a deal, which cannot lose the match that way; at worst the two make a second deal. Trigger: a
  real pair who lost a match by dropping both of two conversations.
- **The facts line.** Each conversation said how many other needs the counterpart was answering: no, 1-2,
  3 or more. Iteration 2 credited it, but the hidden yes changed at the same time; the simulated voices
  triaged it "no change needed"; the replays measured one fluent-liar deal in five, on one moment. It added
  up one person's other conversations, which rule 7 now forbids, and linked two anonymous things of one
  person once a counterpart walked away. Trigger: a real report about someone who fit every need.
- **Undoing a removal (`restore`), and the owner's count of removals.** Never used. Both told an owner
  whether two things had one author: a second removal of someone already removed did not move the count,
  and restore answered only for someone removed. Someone removed by mistake joins again as someone new.
  Trigger: an owner asks to undo a removal.
- **Nudges to an address the person chose.** (An app's address came back on 2026-09-29, for MCP Events, verified by
  a signed challenge first: DESIGN §2.) Any https link would do, so the server connected to addresses
  members chose, behind DNS and private-address checks and no redirects, and still with gaps (#25, #26, #36,
  #43). Live used only ntfy.sh. Now the server makes the ntfy.sh topic; one a member chose there before is kept
  until they turn nudges off. Trigger: someone who needs nudges somewhere ntfy.sh cannot reach.
- **A deal closing its need.** At as many deals as it was for, a need closed, and every other conversation on
  it ended. It kept the next offer after a match from going to the liar (simulation), which a full need still
  does, but it made the first introduction the end: an author whose deal came to nothing had lost the other
  conversations and started over (design review, 2026-09-27). Now a full need reaches nobody new and keeps its
  conversations until its author closes it. Trigger: authors leaving full needs open while the other side
  waits, often enough that someone says so.
- **Every message restarting the week.** A conversation ended after 7 days without a message from either
  side, so a side that kept writing kept a silent one open, nudging the other at every message. Now the week
  runs from the first message still unanswered, and one side sends at most three in a row. Trigger: real
  conversations lost to the week while one side was away for a known reason.
- **Communities owned by the operator.** A community started from the command line had no member to own it,
  so the operator handled its reports from the command line and every owner check had a bypass for it. The
  live one had members and nobody who could act on it. Now every community has a person as its owner; a
  fresh server's first one is made from the command line with a new owner, and the code that makes it theirs.
  Trigger: an operator who must moderate a community they are not in.

- **A connector link of each person's own (2026-09-28).** The invite page handed each person a URL with a secret
  in it, made into the person at its first call. It could not be listed in any directory, which only takes one
  address for everyone; it had to be copied, kept and pasted on a computer; it leaked wherever it was pasted; and
  pressing Join again made a second account. Replaced by sign-in with nothing to fill in (DESIGN §2, "One door").
  The links already handed out still work, and move to sign-in with a code. Trigger: none — a host that could not
  sign in would get a link from the operator.

## 5. The name

It began as demand, became peoplerouter (2026-09-21), then opporouter (2026-09-25, since DINQ already ships an MCP
called "openpeoplerouter"), and is Bridge, from Cohesive Good, Co. (2026-09-29), code and all. Assistants that
saved older instructions may still use the old names, and the fake-notice label matches all three.

## Host constraints

What ChatGPT, Claude and Gemini allow a connector to do was last checked against primary documentation on
2026-09-29 and is in [HOSTS.md](HOSTS.md). The facts the design leans on: only ChatGPT lets a server wake a
chat, and only one that subscribed; no host proves to a server that a human approved anything; inference runs on
the user's own plan.