from __future__ import annotations

import secrets

import pytest

from bridge import net, vault

T0 = 1_790_000_000.0
# The suite makes hundreds of communities and codes, each a scrypt derivation: the work factor is what it would wait
# on, not the scheme, which test_vault checks at the real one.
vault.SCRYPT_N = 2 ** 8


class Clock:
    def __init__(self, t: float = T0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t


@pytest.fixture(autouse=True)
def keys():
    """Every key a test makes, for any of its threads: a call made through a connection holds only its own."""
    vault._SHARED = {}
    yield vault._SHARED
    vault._SHARED = None


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock):
    s = net.open_store()
    s.set_clock(clock)
    return s


def own_link(store, person_id: str) -> str:
    """A connector URL secret of a person's own, as the server gave everyone before sign-in: nothing makes one now,
    and the ones handed out still work (PROTOCOL.md §5)."""
    secret = secrets.token_urlsafe(24)
    private = vault.key_or_none(person_id)
    store.exec("INSERT INTO connectors(secret_hash, person_id, created_t, person_key) VALUES (?,?,?,?)",
               net._hash(secret), person_id, store.now(),
               vault.lock(vault.from_secret(secret, "connector"), private, "person key") if private else "")
    return secret


def seen(store, conversation: str) -> int:
    """The revision someone who has just read the conversation saw."""
    return net._revision(store, net._ref(conversation))


def agree(store, person: str, conversation: str, **kwargs) -> str:
    """`net.agree` as an assistant calls it straight after reading the conversation."""
    kwargs.setdefault("revision", seen(store, conversation))
    return net.agree(store, person, conversation, **kwargs)


class World:
    """One community and whoever is added to it, each set up the way their assistant would."""

    def __init__(self, store):
        self.store = store
        self.owner = net.new_person(store)
        self.community, self.invite = net.create_community(store, self.owner, "Friends")
        self.p: dict[str, str] = {}

    def add(self, key: str, name: str, contact: str, about: str = "", community: str | None = None) -> str:
        pid = net.new_person(self.store)
        net.join(self.store, pid, community or self.community)
        net.setup(self.store, pid, name=name, contact=contact, about=about or None)
        self.p[key] = pid
        return pid

    def pair(self) -> tuple[str, str]:
        return (self.add("ola", "Ola Mensah", "ola@example.com", "sourdough baking, running"),
                self.add("rae", "Rae Iwuchukwu", "+44 7700 900123", "rust, climbing, board games"))

    def go(self, key: str, text: str) -> str:
        return net.go(self.store, self.p[key], text)

    def reply(self, key: str, to: str, text: str) -> str:
        return net.reply(self.store, self.p[key], to, text)[0]

    def inbox(self, key: str) -> dict:
        return net.inbox(self.store, self.p[key])

    def deal(self, asker: str, answerer: str, text: str = "a climbing partner") -> str:
        conversation = self.reply(answerer, self.go(asker, text), "keen")
        agree(self.store, self.p[asker], conversation)
        agree(self.store, self.p[answerer], conversation)
        return conversation


@pytest.fixture
def world(store) -> World:
    return World(store)


def recode(store, community: str, code: str) -> None:
    """A community's invite code set by hand, as one made before codes were lowercase: locked as the server keeps it."""
    owner = store.one("SELECT created_by FROM communities WHERE id=?", community)["created_by"]
    key = net._community_key(store, owner, community)
    store.exec("UPDATE communities SET invite_hash=?, invite_code=?, link_key=? WHERE id=?", vault.code_hash(code),
               vault.lock_text(key, code, "invite code"), vault.lock(net._link_key(code), key, "community key"),
               community)
