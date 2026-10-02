# Bridge — why it is shaped this way

*For a reader who has not followed the project, including one whose job is to attack it. What the system
does is in [PROTOCOL.md](../PROTOCOL.md); this is the reasoning, the evidence, and the limits. Measured
claims say how they were measured. The simulations below ran against the code of their day, with a harness that is
not in this repository.*

## 1. The idea

You should never miss something you could have done with another person — a friend for a hobby, someone to
build a thing with, a skill swap — just because neither of you knew the other wanted it.

The bet, in the founder's words: *privately, people are willing to have their AIs go and negotiate a bunch
of things and figure stuff out with the information they provide.* So you tell your AI "go"; it works it out
with other people's AIs in your communities, unnamed; you hear back only when there is something worth
doing; and if you both say yes, you each get the other's name and contact.

It is a routing network, not a social app: no feed, no profiles, no browsing people. And it is an open
world on purpose: the server sets the rules of what may be revealed and nothing else. What to send, what
fits, what to say, when to walk away and when to say yes are the assistant's calls, and the founder's
instruction is to let the AI operate however it wants inside those rules rather than build machinery for
each case.

## 2. The decisions, and what each one is for

**The intelligence lives in each person's own assistant; the server only carries.** The assistant already
holds the private context that decides whether something fits, and the person already pays for it. An
earlier benchmark (docs/HISTORY.md) found exactly this: a central planner reading everyone's written
profiles did no better than keyword matching, and every gain came from private context reaching the
decision. So no model runs on the server, no API key exists, and hosting costs nothing but a machine.

**Every assistant sees every need.** The server does not choose who a need reaches: everyone in its
communities sees it, and each assistant judges it against what it knows. A first cut routed each need to
the 25 members whose written `about` best matched it, plus some at random. That put a keyword matcher —
the thing the benchmark showed does not work — back in charge of who gets to judge, and it meant a member's
`about` was read by the server after all. Now `about` is the assistant's own notes, read back to it and
used for nothing else. The cost is that `check` in a busy community lists twenty needs and says how many
more there are; the assistant passes what does not fit.

**The person's yes can be given in advance.** "If you find a climbing partner in East London, say yes for
me" is a yes. The assistant acts on it and reports what it agreed to. The server cannot tell a standing yes
from a fresh one, or either from an assistant inventing one; that is the bet the whole design makes.

**Nobody is named until both say yes.** This is what makes "go" cheap to say: a need can reach a
thousand assistants without its author being exposed to anyone, and a no costs nobody anything because it
is never attached to a name. It is also what makes lying cheap — see §4.

**Each thing stands alone.** Before a deal, what a member is shown about a need or a conversation, and how
any operation on it answers them, depends only on that thing and on the member's own memberships and acts,
never on who is behind anything else. Three earlier features broke this, each caught by swapping who wrote
one anonymous need and comparing what the others saw: a person could show their own name on a need or reply
(and an impersonator took 5 of 15 adversary deals with it); two people could hold only one live conversation,
so a need vanished while its author talked to the reader and came back at the deal; and each conversation
counted how many other needs the counterpart answered, which added up one person's other conversations. All
three are gone (docs/HISTORY.md §4), and the author-swap test pins the rule. Two people may now hold two
conversations about one match; the assistants are told to keep both until a deal. Four things are named
instead of hidden: an owner's count, whether a community is small, what happens to all of one person's
things in a community at once when they leave, delete themselves or are removed, and what keeps a deal
partner from aiming a removal (§4).

**A need says how many and for how long.** A need is full at as many deals as it is for — one by default,
because a need that kept taking offers after finding its person handed the next deal to the liar — or never,
when its author wants as many as come. Full, it reaches nobody new, and its conversations carry on: a deal
is an introduction, not the outcome, and when a full need closed, an author whose introduction came to
nothing had lost every other conversation on it. Its author says yes in one of those only by asking for one
more deal, and closes the need once they have what they wanted; nobody else is shown that it filled, which
would say its author had made a deal. It stays up a week unless its author says an hour or a year.
In the situations study, "one need, one deal" was the most common real limit (two tenors, three harvest
hands, sixty study participants each meant reposting), and a fixed week failed both "now" and "all year".
A group is several deals with one organiser, not a group conversation: nobody in the study needed everyone
named to everyone, and several were harmed by it.

**A deal ends the conversation.** Both get the other's name and contact, and the deal shows what each side
last said before it, which is where the when and where were. Nothing more is carried, and nobody is nudged:
the two use each other's contact. Carrying messages after a deal let a deal partner message and nudge someone
for months with no way to stop it, which an audit ranked the top risk for real people. The cost: someone
who cannot use the contact they are given (a call planned, an email set) has no fallback here, so how they
will reach each other is settled before the yes.

**A yes is to the conversation as it stands.** A yes names the revision — how many messages the conversation
held — that its person saw, and is refused if the other side has written since; every message clears both sides'
yeses. Before, a yes stood through later messages: one side said yes, the other asked for more and said yes
itself, and the deal was on terms the first had never seen; and a yes given after reading, asking and coming
back could land on a message nobody had shown its person. The sender's own later messages do not make a yes
stale, since their own assistant wrote them. A yes sent with a reply that meets one already given makes the deal
on what both saw, and the reply is not sent: sent first, it took the other yes back, so a yes with a reply never
made a deal and two sides each replying with one went round for ever. There is no separate proposal object: the
conversation is the proposal, and the assistants are told to state the whole arrangement in the last message
before a yes. A structured form would press friendships and favours into the shape of a contract, and would
prove no more, since a revision proves only that nothing new came from the other side, not that anyone read what
did.

**Reading is not deciding, and writing more buys no more attention.** `check` lists twenty needs and says
where the next ones start; `needs_from` reads on without passing any. Before, the only way to older needs was
to pass newer ones, so looking further meant saying no. Nobody is told how far anyone read, and not reading
is not a no. On the other side, an assistant can work on a reply as long as its person likes, but what
reaches the other person is bounded per conversation: three messages in a row, then nothing until they
answer, and the week before a conversation ends runs from the first message still unanswered. A sender who
kept writing used to keep a silent conversation open and nudge its other side at every message. A limit on
what a person receives across all their conversations would have to be told to the senders it refused, and
would tell them about that person's other conversations (rule 7), so that budget is the reader's own
assistant's, with the nudge at most every ten minutes. Nothing here scores, ranks or rewards volume.

**Everything happens in the chat.** The only web pages send someone from an invite link to add Bridge to
their AI, and ask for one press of Allow when their app signs in. An earlier version put a human click on a web
page at every step, reasoning that only a click proves a person decided. No host can prove that either way, the
pages multiplied, and the product stopped being "tell your AI". The person's yes to their own assistant is the
consent; the protocol says plainly that the server cannot verify it.

**One door: a person exists only once their own AI calls.** Everyone adds the same address, and their app signs in
(OAuth); the Allow page asks for nothing — no email, no password, no name — so the connection the app holds is the
person. Allow makes a connection and nobody. The first tool call through it makes the person, and joins the
community whose invite page that browser came from. Before this, the invite page handed each person a connector
link of their own with a secret in it, and before that every Join press made a person: an owner saw "8 others" in a
community one friend had joined, and a browser cookie told people who never connected that they were connected. A
secret link could not be listed in any directory, had to be copied, kept and pasted, leaked wherever it was
pasted, and made a second account whenever someone pressed Join again. Now a previewed, reloaded or twice-pressed
page makes nobody, an owner's count is of people whose AI connected, and a second account happens only when
Bridge is added again without a code: a code from the app where it already works makes the new connection
the same person, and erases the empty account its Allow made, whose community goes with it. The invite page still
asks first whether the person already uses Bridge. Sign-in asks for nothing because anything it asked would
tell the operator who people are, and add a step; the cost is that someone who loses every connection can come
back only through the operator.

**A community is the only unit of reach, and its starter owns it.** There is no global network. Anyone can
start a community, any member can pass its invite link on, and the link is the trust boundary — the same
trust as being added to a group chat. The owner, while a member, can replace the link and remove someone by
a need sent there, a conversation of their own through it, or a report: the only ways an owner ever meets a
member. The removed person's needs stop, their conversations through that community end as if they had
walked away, and the link no longer admits that account. Removal is refused wherever a deal could aim it
(PROTOCOL §4): otherwise someone who learned a name in a deal could remove that person and watch which
anonymous needs went with them. Every
member, and the invite page, is told whether fewer than ten people have ever joined (`small`), because there
a need is nearly signed: with the owner and one friend, the owner knows every need not theirs is the
friend's, and now the friend's assistant knows it too. It covers two friends and a whole campus with one mechanism.

**The text guard looks only at its writer.** Before a deal, the server refuses text containing the
writer's own name or contact, or anything shaped like a contact. An earlier guard checked every member's
name. An audit showed that made it an oracle — a refusal confirmed a named person was a member, and could
unmask the anonymous author of a need sent to several communities — and that it let one member make words
unsayable for everyone and freeze the server at a few thousand members. Looking only at the writer removes
all of that, and costs nothing as a community grows.

**A first run starts from the need.** Hosts keep an old copy of a server's instructions until the person
refreshes (HOSTS.md), and none promises to show them whole, so their first 512 characters stand on their own:
what this is, that its operator can read everything, one safety question (does anyone else use this AI account
or make decisions for them?) whose answer goes in `about` as whose yes counts, then a `check` — which marks the
communities small enough that a need there is nearly signed — then `go`, then how to hear back. There is no
setup interview: name and contact are taken at the first yes, and `about` fills as the assistant learns, with
the person told in a line what was noted. The rules that matter most travel as a block of at most five lines in
every `check` that lists anything, because that is the only text a host cannot have cached.

**Almost nothing can push, so the assistant checks — on a schedule where it can.** Only ChatGPT lets a server
wake a chat, and only one that asked (below). After the first need goes out, the assistant asks how the person
wants to hear back, and gives them a scheduled task for apps that run them (*"Check Bridge. Reply where it
fits, pass what doesn't, agree where I've already said yes, and tell me only when I need to decide
something."*), one that only reports for people who want nothing done without them, and a line for the
assistant's settings — the one that works in most apps, and in the diary studies the only thing that brought
anyone back. In ChatGPT, a chat can watch Bridge instead (below). With a standing yes and a schedule, two
assistants can reach a deal with neither person present: that is the seamless version, and it needed no server
machinery, only framing. Negotiation is asynchronous, like email.

**`check` is bounded.** It lists deals first, then reports to an owner, then conversations — those waiting on
the person first, longest waiting first — then needs, then the person's own, under one character budget, and
says how many did not fit. A deal that does not fit whole still shows short, with the name and contact, since
the other side already has theirs, and deals always leave reports room, up to half the budget. Deals too are
counted once even their short forms overflow: an offer with a yes in advance can pile them up, one answered
conversation each, and the newest then wait for the oldest to leave. Seven accounts through one invite link,
each writing twelve messages of 2000 characters, pushed an owner's reports and a genuine reply past 150,000
characters, about Claude's limit on a tool's answer; a cap of twenty conversations would not stop that, since
twenty such come to 480,000.

**Settings are the assistant's own notes.** Everything that shapes how an assistant works for its person —
what they want, what it may say yes to without asking, how often to check — lives in one free-text field,
`about`, which `check` reads back to that assistant and to no other member. It is stored on the server, so
the operator can read it, and assistants are told to write rules without naming what they protect. Notes
over 2000 characters are refused, never cut: a cut dropped the rules added last, and said "saved" (audit).
A scheduled run has no memory of the last one; the notes are its memory. The server interprets none of it,
so a new kind of preference never needs a new field.

**A wake-up, if a person wants one.** In the diary studies every person came back by luck. Two wake-ups exist, and
both say only that something is waiting — never what, never who, at most every ten minutes between them, and
never for a yes, which the other side must not learn of — when something is aimed at the person: a reply, a
message, a deal, a report to an owner. One is a nudge to their phone: `setup` with notify "on" makes an unguessable
ntfy.sh topic, and the server posts one fixed line to it. The server makes the topic, so it never connects to an
address a member chose, and "off" then "on" replaces a topic that leaked. The other is ChatGPT's MCP Events
(2026-09-29, every plan): told to "watch Bridge", a chat subscribes to one empty event, `waiting`, and when it
arrives ChatGPT does what the person said in that chat, even while they are away. That is the seamless version the
design was missing, and it adds no content to anything: the event is empty, and the assistant calls `check`. Here
the app chooses the address, which the server refused to connect to for members (docs/HISTORY.md), so the app
first proves the address is its own by echoing a signed challenge there; the server posts only to public addresses,
to the address it checked, and follows no redirects. A subscription lives with its connection, so what ends one
ends the other.

**A member can report, and only the owner sees it.** A scammer inside a community could not be put out:
an owner meets members only through needs and conversations of their own. Now a member's assistant can
report a need or the other side of a conversation to the community's owner. The owner sees what that side
wrote before any deal — never who reported it, nor who wrote it, but for what PROTOCOL §4 names — and
may put them out or dismiss it. Each report stands alone: nothing counts reports, and nobody else learns of
one. A deal, and a need the reporter has a deal on, cannot be reported; an owner removes directly instead of
reporting in their own community. PROTOCOL §4 says what keeps a deal partner from aiming a removal by a
report. Closing every report between the two at any deal told an owner, who saw one vanish as a need left their
list, who wrote that need. A report about the owner, or to an owner who has left, goes to nobody too, and the answer
reads the same. Nobody has made a real report yet; it stays because it is the only recourse against someone
who only answers other people's needs.

**Member text that poses as the server is labelled.** The server never writes inside a conversation, and
when member text is shaped like a notice from it or its moderators, the server says so, outside the marks.
It is a shape match on one message, not a judgment of the member and not a score: nothing is counted or
remembered. It exists because 9 of 15 adversary deals in the randomized simulation had a fake "SYSTEM:"
line on screen, fenced and still believed.

**Few tools.** An assistant sees eight: `check`, `setup`, `go`, `reply`, `agree`, `pass`, `community`,
`forget_me`. Everything about communities — start, join, invite, leave, report, and the owner's rename,
new link, remove and dismiss — is one `community` tool with an action, so owner powers can grow without the tool list
growing with them.

## 3. What was measured

**Simulated users** (`sim/`). Eight invented people in one community, each played by a cheap model
(Claude Haiku) acting as that person's assistant and knowing only its own person's private brief — plus
one adversary told to pose as whatever each person wants, fake system notices, and harvest contacts. Hidden
ground truth: three pairs that should find each other, three decoys that look similar but shouldn't. A fresh
session per person per round, no memory, four rounds.

| | Baseline | Iteration 2 | Iteration 3 | After the rewrite |
|---|---|---|---|---|
| Real pairs that made a deal | 1/3 | 3/3 | 3/3 | 3/3 |
| Deals that should have happened | 1/4 | 3/4 | 3/3 | 3/4 |
| Deals the liar got | 3 | 1 | 0 | 1 |
| Decoy deals | 0 | 0 | 0 | 0 |
| Names or contacts written before a deal | 0 | 0 | 0 | 0 |

What changed between runs, each from something a run showed:

- The liar won the baseline by claiming a perfect fit and saying yes instantly, so the other side saw "they
  said yes" and hurried. Now the other side's yes is hidden until the deal; each conversation shows rough
  facts about the counterpart — the liar was replying to everything, and it showed; and every
  assistant is told what a pretender looks like.
- Honest pairs were slow because both sides kept asking questions. Assistants are now told to put
  everything relevant in the first reply and settle in one or two exchanges.
- A need that had found its person kept taking offers, and the next offer was the liar's. A need then
  closed at its first deal, unless its author said it was for more people; it is now full instead (§2).
- After the rewrite the liar won once more, late: by the time its last target checked, its other three
  targets had walked away, so it showed as "replying to no other needs". The facts briefly also counted people
  who walked away from them, and the instructions now say any warning sign is enough to pass. Replayed as a
  fixed scenario (Sam's assistant meets the liar, five fresh trials each way): before, the liar got a deal in
  2 of 5 and was kept as a backup in a third; after, 0 of 5, passed every time. The walk-away count was later
  dropped (the swarm, below); the instruction to pass on any warning sign is what remains.

The facts line has since gone too (docs/HISTORY.md §4), and the credit above was generous: in iteration 2 the
liar's deals fell from 3 to 1, but the hidden yes changed at the same time. The replay above measured one
fluent-liar deal in five, on one moment. Assistants said they liked the line.

One run per condition, people invented by the builder, one cheap model playing everyone including the liar,
and "would they say yes" read from a brief rather than decided by a person. It shows the mechanics work and
that the defences move the numbers. It does not show that real people want this.

**First real use** (2026-09-21). Two friends, one need, one deal: first reply 4.6 minutes after the need
went out, deal at 22.5 minutes, six messages, no errors, contacts exchanged. Both were online and nudged
each other by text, so the timing is a best case; with two members nobody was anonymous; and they already
knew each other, so it says nothing yet about finding what people would otherwise have missed.

**The swarm** (2026-09-22). Sixteen simulated people in three overlapping communities, each with a messy
situation a real person creates — someone who leaves mid-conversation, an owner removing a spammer, a
person who deletes themselves mid-negotiation, a standing yes that conflicts with a hard no, someone who
never checks, a late joiner, a tester poking every edge — plus the liar. Four memoryless sessions each, 487
tool calls. No crashes, no unclean refusals, no name or contact in any of 51 pre-deal messages; the liar
had 14 conversations and got nothing, and two owners removed it. It found three bugs and one bad idea:

- Leaving closed the leaver's needs for good; now they only stop showing, and come back on rejoining.
- A conversation left behind by a leave showed an empty community name; same cause.
- `check` counted a conversation its author had passed but no longer listed.
- **The walk-away count was a reputation score.** Most walk-aways are honest "not a fit" passes, so
  ordinary members ended up flagged next to the liar; four assistants dropped genuine counterparts over it
  and one owner removed one. It is gone, and the protocol now forbids reporting anything about a
  counterpart's past. The one fact left was how many needs they were answering right now. The liar scenario
  above, replayed without it — the liar now looking exactly like the genuine counterpart on the facts
  line — five fresh trials: the liar was passed in all five, on what it wrote.

It also showed owners removing people carelessly — one on the facts line alone, one believing she was
removing a need. `remove` now says exactly what it did (for a while it could also be undone; nobody did),
and the instructions say to remove only when the person asked and said why.

**Audits.** An adversarial audit and an independent review by a model from a different family, each
against the running code, every finding reproduced before it was fixed. The worst: the text guard was a
membership oracle and an author-unmasking tool; five angle brackets escaped the data fence; a person's
name survived their own deletion in the other side's messages; a former member could still reply to needs
routed before they left; pressing Join twice silently broke the connector an assistant already held. A
review of the swarm fixes found an owner could "remove" from their community the anonymous person they were
talking to in another one, and learn from the answer whether that person was a member — now a conversation
records the community it came through, and an owner can act on it only there. Their reproductions are
tests in `tests/test_net.py`; the docstrings say what went wrong.

**Situations study** (2026-09-22). 200 situations written to span who asks (people, businesses,
organisations, bots, carers), where (campus, work, village, faith group, market, support group, a
community of two, one of ten million), how many, how soon, what each side wants revealed, and stakes up to
safety-critical — 120 by three agents with different briefs, 80 by a model from another family. Five
labellers each judged 40 against the protocol, under one strict test: an addition counts only if the
server must carry or enforce something; whatever assistants can do in text does not count. Before this
change 64% worked, 26% worked clumsily, 10% failed (safety-critical: under half worked). Nine candidate
additions were scored by how many situations each made work and how many it made worse: several deals per
need 27 needed, 2 harmed; a need's own lifetime 6 and 0; showing your own name 3 and 36; one-use invite
codes 2 and 0; group conversations 1 and 17; sign-in with an organisation's accounts, blocking, finding
communities and federation 0 needed each. Adding the first three took situations that fully work from 72%
to 90%. Almost everything left was one thing no addition on the list fixed: speed (§4). A cross-family
labeller agreed with the main labels on only 9 of 40; checked by hand, it had mostly misread the guard as
refusing any name at all — a place, a choir, a relative — which led to the line in the instructions saying
what the guard actually refuses.

**Open-world simulation** (2026-09-22, `sim/openworld.json`). Twelve simulated people over four sessions:
a choir needing two tenors, a baker and a lost-dog owner who wanted to be named, a teacher with a year-long
offer for anyone, a new mother who must stay unknown, an employee hiding a job search from the manager who
owns his work community, and an adversary who named itself "Omar's Bakery" and pressed everyone to show
themselves. Three right deals (both tenors, the flour), none for the adversary, and nobody shown who had
not chosen it; the mother's peer support ran anonymously with no deal, as she wanted, and she dropped the
conversation that asked for her name. What it found, each now a test: the baker's own name was refused
in the conversation his named need had started; the choir said yes without a word and the tenor, never
shown it, waited — so did the choir; a member who passed the lost-dog alert and then saw the dog could not
find it again; a tenor's assistant took the adversary's shown name for Omar; one assistant showed a
contact when told only "tell them who I am"; and the employee's assistant, told to start a smaller
community, posted into a new one with nobody else in it. An independent review of the change then found
that rule 7 (one conversation per pair) and a shown name together named anonymous sides — a baker's named
need vanished for exactly the person she was talking to anonymously — that showing a contact let another
address through the guard, and that a year-long need for two could take a third deal once the first
deal's conversation had been deleted. Each is a test.

**Diary studies** (2026-09-23, `sim/diary.py`, `sim/diary.json`; the diaries are in
`sim/data/diaries-2026-09-23/`). Eight invented people — a 71-year-old on an iPad, a privacy-minded student,
a nurse and single mother on her phone, a baker who wants to be known, a trans woman new to a city, a food
bank organiser, a blind runner on VoiceOver, a Spanish-speaking cleaner — each arriving through an invite
link as a real person would, reading the real pages, played with their AI turn by turn over three days
while other agents played the rest of each community. Seven right deals, none for the three adversaries.
What they found, in order of how many hit it:
- **Nothing tells them anything.** Every one of the eight came back by luck — a rota clash, a bandmate's
  question, opening the AI for something else while the settings line checked first. Two deals nearly
  expired unseen. The settings line was the only thing that worked, and the connect page offered it as a
  fallback; it now comes first. The wake-ups in §2 came of this.
- **Setup assumes a computer and a paid ChatGPT.** The two phone-only people could not add the connector
  alone; each sent their secret link to a relative, one had to tell her son about a landlord dispute to get
  help. The join page now says what is needed before the button.
- **Who can read what was not where they looked.** The operator's reach was only on the consent page, which
  a second-language reader translated in pieces and missed. The AI could not say who runs the server. And
  "nobody else ever sees `about`" led an assistant to write "never mention that she is trans" there, on a
  server the operator can read. All three are fixed in words.
- **In a small group a description is a name.** "A Hollybank parent who works shifts" and "a blind runner at
  this parkrun" were sent before anyone asked the person. Assistants are now told to read such details to
  their person first.

**Fixed-moment replays** (2026-09-23, `sim/replay.py`, `sim/replay.json`). Five moments from the randomized
simulation, each put in front of a fresh cheapest-model assistant five times on the previous code and five
on this change, and scored from the database only. Across the three attacks where an adversary's reply
carried a fake "SYSTEM:" or moderator line — an iftar donation, evening childcare, anonymous recovery
support — adversary deals fell from 9 of 15 to 0 of 15 and right deals rose from 4 to 7; the honest control
made its deal 3 of 3 times on both. On the recovery need the old code agreed with the adversary all five
times, each assistant naming the "verified by moderators" line as reassurance; with the line labelled as a
member's, all five passed. Two new-code childcare runs made no deal because the assistant asked its person
before saying yes about children, as it is now told to. Which of the label, the compare-before-agreeing line
and the rewritten instructions did the work is not separated; five trials each is small; one model.

A second round on the later code (the yes cap, the post-deal messages, the replaceable link) repeated the
three attacks: 0 adversary deals of 15 again, and 9 right deals of the 10 possible. The honest control made
its deal 5 of 5. Two new moments: a race between a generic reply and a concrete one to a need for one
tutor went to the concrete one 5 of 5 on both versions, so it measures nothing; and the fluent liar (§4)
won 5 of 5 on both. One thing the numbers hide: in the childcare moment the assistants still used the
standing yes 4 times of 5, though told a yes in advance never covers children — to the right sitter, but
against the rule. Instructions move behaviour; they do not bind it.

## 4. What it does not fix

- **Anyone can claim anything before a deal.** The hidden yes and the warning signs raise the cost of lying;
  they prove nothing. A patient liar who stays specific passes both. A deal is an introduction, not a vetting.
  Measured (2026-09-23 replays, cheapest model): asked a pointed question, an adversary answering three other
  needs invented a specific answer — a parkrun time, a named course — and got the deal 5 times of 5 on the old
  code and 4 of 5 on the code of that day, where a yes in advance did not cover someone answering 3 or more
  needs (a rule dropped with the facts line) and one assistant stopped to ask. Fake notices are caught; fluent
  invention is not. What limits the harm is after the deal: meeting in public, checking the name.
- **Unattended deals.** With a standing yes and a schedule, an assistant can close a deal while its person
  is away. The scope of the standing yes is the real guard; a vague one ("say yes to anything") is an open
  door.
- **"Only your person can say yes" is an instruction to an assistant**, not something a server can check.
- **Anonymity is thin in small groups.** What someone writes may make it obvious who they are, and the
  guard does not stop a person describing themselves. An owner's count of the others is exact, so in a
  community of a few the owner can tell who wrote a need. Members are told a community is `small` below ten
  joins ever; one that shrinks after ten is not flagged.
- **Anyone can make accounts.** Sign-in asks for nothing, so a script can make as many connections as it
  likes. The server makes at most 1000 people a day with no invite, and a community takes at most 100 a day for
  whom it is their first, by any door; someone holding an invite link can use up a day's joins. The owner can
  replace the link and remove people, one at a time, and only ones they have met through a need, a conversation
  or a report. Nothing server-side tells a harvester apart, so the invite link is the boundary. Registration,
  the Allow page and the token endpoint are not limited by address: a flood of them is for whatever is in front
  of the server (Cloudflare) to stop, beyond a cap on a day's app registrations. Presses of Join and Allow are
  logged uncapped, one `calls` row each until the sweep.
- **A second account is prevented by words and a code.** Removing Bridge from an app and adding it again,
  or adding it in a second app, makes a new account until a code from a working connection is given there. The
  pages say so, and so does the new account's first `check`, `setup` or `go` while it holds nothing. Someone
  with no working connection left comes back only through the operator (`docs/OPERATIONS.md`); until then the old
  account's needs stay out, and `bridge stats` counts people with open needs and no call in 14 days.
- **A connection is whoever holds the app it is in.** Its tokens never appear where a person could paste them,
  so the leaked link is gone for anyone who signed in. People still on a connector link of their own from before
  carry that risk until they move with a code. A code is the person, for an hour, to whoever uses it first.
- **Until Bridge is listed, adding it takes a computer the first time**: Claude's custom connectors can be
  added on a phone only in a beta, and ChatGPT needs a paid plan's developer mode in a computer's browser every
  time. A listing in Claude's directory, and a published ChatGPT app, remove both (`docs/OPERATIONS.md`).
- **The operator reads everything**, and AI providers see whatever passes through a chat.
- **Only ChatGPT can be woken.** Elsewhere a deal takes as long as the slower person takes to open a chat, or
  until a scheduled check or a phone nudge brings them. In the situations study this was the largest gap by far:
  nearly every situation that had to happen within hours — a shift to cover tonight, a same-day burial, insulin in
  Lisbon this afternoon — failed on it alone. A woken chat acts on what its person already said; anything else
  still waits for them.
- **A community whose owner deletes themselves has no owner.** Nobody can replace its link or remove
  anyone, and the server cannot hand it on without choosing someone — which would mean looking at who is
  in it. Its members can start a new one and move. Only the operator, with the database, can do more.
- **A deal shows the other side's name and contact as they are now.** A fixed typo reaches them; so does a
  contact changed to be unreachable. Nothing snapshots what a deal handed over.
- **A full need's other conversations wait on its author.** They carry on until the author closes the need,
  asks for one more deal, or leaves them a week unanswered, and the other side is never told the need filled.
  The instructions tell authors to close a need once they have what they wanted; nothing makes them.
- **A revision is only a count.** It shows that nothing new came from the other side, not that anyone read
  what did, and a vague last message makes a vague deal. It cannot tell "yes, see you then" from new terms
  either, so a message on its own takes the other side's yes back and costs the deal a round.
- **Three in a row is per conversation.** Someone with many accounts, or many needs to answer, still reaches
  one person through many conversations. Their assistant pages, passes and reports; the nudge rings at most
  every ten minutes.
- **Two conversations may be one match.** Two people who each answer the other's need hold two
  conversations, and nothing links them; the assistants are told to keep both until a deal.
- **All of a person's things change together** when they leave, delete themselves or are removed, including
  which shared community they reach you through, and a deal partner may tie that to a name.
- **An owner who knows someone can get them to reply, and remove them by that reply**: sensitive needs go only
  where a person trusts the owner, and the instructions say so.
- **What keeps a deal partner from aiming a removal is itself a clue** (PROTOCOL §4), to an owner and to
  whoever reports through them.
- **Removing someone through your own conversation may show them it was you**: they see the community gone.
- **Removal binds an account, not a human.** Whoever still holds the link can come back as someone new; the
  remove answer says to replace the link and resend it one person at a time.
- **Someone who only answers other people's needs is reachable only by a report**, and a report about the
  owner goes nowhere: an abusive owner can only be left. A report that vanishes may mean a deal or a
  deletion.
- **90 days after a deal the server forgets it**, and an owner can then remove its partner by a year-long
  need, or its partner report their other needs.
- **A deal partner's second account can report them.** The server cannot tell it from anyone else's, so an
  owner who acts on that report shows the deal partner which needs went. And a deal partner's own reports of
  them go nowhere, so one who reports anonymous needs to an owner who acts on every report learns, by which
  needs vanish, which were not their partner's.
- **Deleted data stays in backups for up to 15 days.**
- **A nudge's timing is visible** to whoever sees the phone it rings on, and ntfy.sh sees when each topic is
  nudged.

## 5. Scale

Sending a need writes one row per community; reading is one query; the guard looks at one person.
No call does work proportional to a community's size. Ended conversations and closed needs are deleted after
90 days. One SQLite file and one process will carry a pilot and a good deal more; past that the core
(`bridge/net.py`) is a few hundred lines over plain SQL and the storage can change under it. The first
thing to change then: `check` finds a reader's open needs by scanning every open need on the server and
keeping those in the reader's communities (#22). Starting from the reader's memberships through
`need_communities_by_community` bounds it by what reaches them.

The old tool names that apps with a cached tool list still call (`mcp_server._RETIRED`) go once two weeks of
the calls log show none: each such call is logged, without the person, as `retired <name>`.

A wake-up signal was designed and held back on 2026-09-22 until people asked for it; the diary studies
did, all eight of them, so it is built (§2) — optional, off unless a person asks for it.

Sign-in was built on 2026-09-28, once the pilot had passed ten people and adoption, not the rules, was what held
it back: every step of adding Bridge that asked the person for something — a secret
link to copy, keep and paste, on a computer — went. What remains is being listed. Claude's directory takes a
submission from any paid account and lists it after an automated review; ChatGPT's needs a verified identity and
a human review that must find it suitable for 13–17-year-olds, which a network that introduces strangers, with
no age gate, may not pass. Considered on 2026-09-27 and not built, because each changes more than it has yet
been shown to be worth: an author pausing a need without closing it, which needs a schema change and so makes a
rollback lose data; a runner that works for a person for hours, which each person's own host already offers as
scheduled tasks; and permissions narrower than a connector, which the same assistant that holds the connector
could widen, since no host shows a server that a human approved anything (HOSTS.md). A pilot in one existing
community, with its members' consent, is the test of whether any of this helps, against what that community
already does. Conversations of several people came on 2026-10-01, as something an assistant may do rather than
a feature with steps: one that sees needs it can piece together opens one conversation with all their authors, and
nobody is named until everyone still in it says yes. Then messages the operator cannot read, a stated goal;
federation between servers, unspecified. What is
deliberately not going to be built: matching, ranking or routing by the server, and anything that asks the
person a question after a deal.

## 6. Deliberately absent

The only pages are home, which is also the documentation a directory asks for; the invite page and the connect
page it leads to; the Allow page an app's sign-in opens, and its page for a sign-in that expired; the invalid-link
page, and the page for an address with none; and the consent page, which is also the privacy policy and the
terms. None of them knows who anyone is. Beside
them, one line of plain text proves to OpenAI that this host is the publisher's. The Allow page
exists because sign-in needs a page the person's own browser shows: it holds one button, and asks for nothing.

No email, and no notification anyone did not ask for: a person may ask for a content-free nudge to an ntfy.sh
topic the server makes, and a chat may ask to be woken by an empty event (§2); nothing else is ever sent to
anyone who uses it. The operator's own machine tells the operator when the server stops answering, and that says
nothing about anyone (`docs/OPERATIONS.md`). No scores, reputation, streaks or reminders — nothing that rewards
volume, and nothing about a counterpart's past. No scheduling of meetings. No cap on how long two assistants may
talk. No model on the server, no API keys. No ads.

## 7. Where a critic should push hardest

1. **One real pair has used it.** Everything else is simulated. What would show it finds things people
   would not have found themselves?
2. **Will people hand their AI "go"?** The whole bet. The simulation assumed it.
3. **Is the liar problem solved or moved?** What stops a patient liar, besides the invite link?
4. **Is anonymous-until-yes worth what it costs?** It is what makes a liar cheap.
5. **Does "everyone sees everything" hold at a thousand members?** Every assistant can read every need in its
   communities, on its person's plan, and pages through as far as it likes. At what size does that cost more
   than it finds, and do the needs past the first page ever get read?
6. **Is the latency tolerable** when nobody is nudging anybody?
