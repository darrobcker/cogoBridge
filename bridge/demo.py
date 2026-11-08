"""`bridge demo`: a scratch server full of made-up people, for working on the web client.

Everything goes through `net`, as their assistants would have done it, over four days ending now: three
communities, needs and conversations in each state a person meets (new, their turn, waiting on the other side, a
yes waiting for them to confirm, a deal, a conversation of several, a need passed, a report for an owner). Then each
person gets a web client connection, its secret written beside the database for `bridge serve --dev` alone. It
refuses any home that already has a database, so it can never touch a real one.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import net, vault

DAY = 86400
# Who they are; the first is the one a demo is usually seen as.
PEOPLE = {
    "Avery": ("Avery Lin", "avery.lin@example.com"),
    "Ben": ("Ben Okafor", "+1 650 555 0134"),
    "Chloe": ("Chloe Park", "chloe.park@example.com"),
    "Dev": ("Dev Raman", "dev.raman@example.com"),
    "Ema": ("Ema Novak", "+1 650 555 0177"),
    "Felix": ("Felix Brandt", "felix.b@example.com"),
    "Gus": ("Gus Hale", "gus.hale@example.com"),
}


class _Clock:
    """Four days ago, moving forward as things happen, and ending at the real time."""

    def __init__(self, start: float):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def later(self, seconds: float) -> None:
        self.t += seconds


def seed(home: Path) -> dict[str, str]:
    """Fill a new database at `home`; returns each person's web client secret by first name."""
    db = home / "bridge.db"
    if db.exists():
        raise SystemExit(f"{db} already exists: bridge demo only fills a new home")
    home.mkdir(parents=True, exist_ok=True)
    store = net.open_store(db)
    clock = _Clock(time.time() - 4 * DAY)
    store.set_clock(clock)
    store.on_nudge = lambda topic: None
    # A process of its own, outside any server: what each made is held for the rest of it, as tests do.
    vault._SHARED = {}
    p = {}
    for first, (name, contact) in PEOPLE.items():
        p[first] = net.new_person(store)
        net.setup(store, p[first], name=name, contact=contact)

    def go(who: str, text: str, community: str | None = None, **kw) -> str:
        clock.later(1800)
        return net.go(store, p[who], text, community, **kw)

    def reply(who: str, to: str, text: str) -> str:
        clock.later(2400)
        return net.reply(store, p[who], to, text)[0]

    def yes(who: str, conversation: str, confirm: bool = True) -> None:
        clock.later(600)
        net.agree(store, p[who], conversation, revision=net._revision(store, net._ref(conversation)))
        if confirm:
            net.confirmYes(store, net.yesLink(store, p[who]), net.waitingYes(store, p[who], conversation))

    neighbours, invite = net.create_community(store, p["Avery"], "Palo Alto neighbours")
    climbing, _ = net.create_community(store, p["Ben"], "Stanford climbing")
    books, _ = net.create_community(store, p["Chloe"], "Book swap")
    for who in ("Ben", "Chloe", "Dev", "Ema", "Felix", "Gus"):
        net.join(store, p[who], neighbours)
    for who in ("Avery", "Chloe", "Dev"):
        net.join(store, p[who], climbing)
    for who in ("Avery", "Ema"):
        net.join(store, p[who], books)

    # Avery's ladder: two answers; a deal with one, the other still going (a full need reaches nobody new).
    ladder = go("Avery", "Anyone have a ladder I could borrow this weekend? Just need it for an afternoon to clear "
                         "the gutters.", neighbours)
    with_chloe = reply("Chloe", ladder, "I have a 6 ft step ladder you're welcome to.")
    reply("Avery", with_chloe, "That would be perfect. Could I pick it up Saturday morning?")
    reply("Chloe", with_chloe, "Saturday at 10 works. I'll leave it by the garage.")
    reply("Dev", ladder, "I can lend one too if that falls through, an extension ladder.")
    yes("Avery", with_chloe)
    yes("Chloe", with_chloe)

    # Ben's climbing partner: Avery answered, and it's Avery's turn.
    clock.later(DAY / 2)
    partner = go("Ben", "Looking for a climbing partner for Tuesday evenings at the campus gym. I lead 5.10s and "
                        "am happy to belay.", climbing)
    with_ben = reply("Avery", partner, "I'm keen. I mostly top rope around 5.9 but want to start leading.")
    reply("Ben", with_ben, "Great. This Tuesday at 7? I can show you the lead test.")

    # Dev's running group, for as many as come: Avery wrote last, so it waits on Dev.
    clock.later(DAY / 2)
    running = go("Dev", "Starting a Sunday morning running group, easy 5k pace, all welcome.", neighbours, people=0)
    reply("Avery", running, "I'm in. Which park do you start from?")

    # One conversation of several: a ride for Felix, with Ema driving that way.
    ride = go("Felix", "Need a ride to SFO on Friday morning, flight at 10.", neighbours, days=3.2)
    driving = go("Ema", "Driving up to the city Friday around 7, room for one or two.", neighbours, days=3.5)
    reply("Avery", f"{ride}, {driving}", "You two should share: one is driving past SFO on Friday morning.")

    # Needs that reach Avery and wait: new ones, and one Avery passes.
    clock.later(DAY / 2)
    go("Ema", "Giving away a desk lamp, works fine, just don't need it.", neighbours)
    trade = go("Chloe", "Trading: The Overstory for any Le Guin novel.", books)
    net.pass_on(store, p["Avery"], trade)
    go("Chloe", "Anyone want to split a CSA vegetable box? Weekly pickup.", neighbours, people=2)
    go("Dev", "Belay partner for the bouldering comp warm-up on Saturday?", climbing)

    # Gus posts a scam in Avery's community, and Ben reports it: a report for its owner.
    scam = go("Gus", "Earn $500 a day from home, no experience, act fast before spots fill.", neighbours)
    clock.later(3600)
    net.report(store, p["Ben"], scam)

    # Lately: Avery's yes waits for Avery to confirm it (a yes waits three days), and a need with nothing yet.
    clock.later(1.5 * DAY)
    spanish = go("Avery", "Looking for someone to practise Spanish with, an hour a week over coffee. I can help "
                          "with English or maths in return.")
    with_ema = reply("Ema", spanish, "Me encantaría. Thursdays after work suit me.")
    reply("Avery", with_ema, "Thursdays work. The café on University Ave at 6?")
    reply("Ema", with_ema, "Perfect, see you there.")
    yes("Avery", with_ema, confirm=False)

    go("Avery", "Does anyone have a bike pump with a Presta valve head?", neighbours, days=3)

    store.set_clock(time.time)
    sessions = {}
    for first, pid in p.items():
        sessions[first] = net.site_sign_in(store, net.link_code(store, pid, replace=False))
    vault._SHARED = None
    path = home / "demo-sessions.json"
    path.write_text(json.dumps(sessions, indent=1))
    os.chmod(path, 0o600)
    (home / "invite.txt").write_text(invite)
    return sessions
