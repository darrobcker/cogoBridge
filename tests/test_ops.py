"""The operator's scripts, run as the operator runs them but against a scratch home: never ~/.bridge,
never launchctl. The environment is built from nothing, so a variable the scripts forget to honour falls back
to the scratch home and not to the real one.

Untested: a deploy failing because /health never names the new commit. It waits a minute before it says so.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from bridge import net
from bridge.store import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DAY = 86400


def _uv_dir(what: str) -> str:
    return subprocess.run(["uv", what, "dir"], capture_output=True, text=True, check=True).stdout.strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def uv_env() -> dict:
    """uv's own cache and interpreters, offline: a deploy under test builds from what is already here."""
    return {"UV_CACHE_DIR": _uv_dir("cache"), "UV_PYTHON_INSTALL_DIR": _uv_dir("python"), "UV_OFFLINE": "1",
            "UV_PYTHON_DOWNLOADS": "never"}


@pytest.fixture
def home(tmp_path, uv_env):
    """A scratch home with a real database in it, and the environment the scripts run in."""
    h = tmp_path / "home"
    env = {"PATH": os.environ["PATH"], "HOME": str(h), "BRIDGE_HOME": str(h / ".bridge"),
           "BRIDGE_BACKUPS": str(h / "backups"), "BRIDGE_LIVE": str(h / "live"),
           "BRIDGE_RESTART": "false", "BRIDGE_PORT": str(free_port()),
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", **uv_env}
    (h / ".bridge").mkdir(parents=True)
    store = net.open_store(h / ".bridge" / "bridge.db")
    net.create_community(store, net.new_person(store), "Friends")
    store.db.close()
    return h, env


def run(env: dict, *args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], env=env, cwd=cwd, capture_output=True, text=True, timeout=600)


def backups(h: Path) -> list[Path]:
    """Only the names scripts/backup writes."""
    return sorted((h / "backups").glob("bridge-" + "[0-9]" * 8 + "T" + "[0-9]" * 6 + "Z.db"))


def age(path: Path, seconds: float) -> None:
    os.utime(path, (time.time() - seconds, time.time() - seconds))


# -- backup ---------------------------------------------------------------------------------------------

def test_backup_is_a_private_checked_copy_including_what_is_still_in_the_wal_and_keeps_two_weeks(home):
    """Rotation deleted every old bridge-*.db under the backups directory, subdirectories included, so a
    copy the operator made by hand before a migration went with the rest. Then its pattern still took any name
    of a loose backup-like shape, such as a backup kept under a suffix. It keeps to its own exact names now, and
    takes the half-made copy a killed backup leaves, which is people's data too."""
    h, env = home
    store = net.open_store(h / ".bridge" / "bridge.db")    # the server, up and holding the WAL
    store.db.execute("PRAGMA wal_autocheckpoint=0")
    net.create_community(store, net.new_person(store), "Written after the last checkpoint")
    (h / "backups" / "keep").mkdir(parents=True)
    old, recent = h / "backups/bridge-20260101T000000Z.db", h / "backups/bridge-20260102T000000Z.db"
    half = h / "backups/bridge-20260101T000001Z.db.4242.partial"
    kept = [h / "backups/x", h / "backups/bridge-before-migration.db",
            h / "backups/keep/bridge-20260101T000000Z.db", h / "backups/bridge-20260101T000000Z.db.keep",
            h / "backups/bridge-1-before-T1Z.db"]
    for path, days in ((old, 15), (half, 15), (recent, 13), *((k, 30) for k in kept)):
        path.write_text("")
        age(path, days * DAY)
    done = run(env, SCRIPTS / "backup")
    assert done.returncode == 0, done.stderr
    new = Path(done.stdout.strip())
    names = {r[0] for r in sqlite3.connect(new).execute("SELECT name FROM communities")}
    assert names == {"Friends", "Written after the last checkpoint"}
    assert stat.S_IMODE(new.stat().st_mode) == 0o600 and stat.S_IMODE((h / "backups").stat().st_mode) == 0o700
    assert not old.exists() and not half.exists() and recent.exists() and all(k.exists() for k in kept)
    assert backups(h) == sorted([new, recent])


def test_what_forget_me_erased_is_in_neither_the_file_nor_a_later_backup(home):
    """forget_me deleted the rows, but sqlite left their bytes in the file's free pages, and a backup copies whole
    pages: a backup made weeks later still held the person's name and contact, against the consent page's 15
    days (review)."""
    h, env = home
    store = net.open_store(h / ".bridge" / "bridge.db")
    owner = store.one("SELECT id FROM people")["id"]
    community = store.one("SELECT id FROM communities")["id"]
    pid = net.new_person(store)
    net.join(store, pid, community)
    net.setup(store, pid, name="Zelda Quixote", contact="zelda.quixote@example.com", about="likes XYZZY")
    net.reply(store, owner, net.go(store, pid, "a lift PLUGHWORD", community), "I can drive")
    net.forget_me(store, pid, "delete everything")
    store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    store.db.close()
    done = run(env, SCRIPTS / "backup")
    assert done.returncode == 0, done.stderr
    for f in (h / ".bridge" / "bridge.db", *backups(h)):
        data = f.read_bytes()
        assert not any(w in data for w in (b"Zelda", b"zelda.quixote", b"XYZZY", b"PLUGHWORD")), f


def test_backup_fails_loudly_and_leaves_nothing_when_the_copy_is_not_intact(home):
    h, env = home
    db = h / ".bridge" / "bridge.db"
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE filler (x TEXT)")
    raw.execute("CREATE INDEX filler_x ON filler(x)")
    raw.executemany("INSERT INTO filler VALUES (?)", [(f"row{i:05d}",) for i in range(2000)])
    raw.commit()
    raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw.close()
    data = bytearray(db.read_bytes())
    at = data.rfind(b"row01999")
    data[at:at + 8] = b"zzzzzzzz"              # the table and its index now disagree
    db.write_bytes(bytes(data))
    done = run(env, SCRIPTS / "backup")
    assert done.returncode != 0 and "BACKUP FAILED" in done.stderr and "index" in done.stderr
    assert list((h / "backups").iterdir()) == []


def test_two_backups_at_once_never_certify_an_empty_copy(home):
    """Two backups in the same second shared one partial file. The one that lost the lock deleted it on exit,
    and the other then checked a path that was gone: sqlite3 created an empty database there, answered 'ok',
    and an empty file with no tables was kept as a backup and printed as one."""
    h, env = home
    raw = sqlite3.connect(h / ".bridge" / "bridge.db")
    raw.execute("CREATE TABLE filler (x TEXT)")
    raw.executemany("INSERT INTO filler VALUES (?)", [("x" * 1000,) for _ in range(5000)])
    raw.commit()
    raw.close()
    for _ in range(3):
        runs = [subprocess.Popen([SCRIPTS / "backup"], env=env, stdout=subprocess.PIPE, text=True)
                for _ in range(2)]
        for printed in (p.communicate(timeout=120)[0].split() for p in runs):
            for path in printed:
                assert sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
                    "SELECT count(*) FROM communities").fetchone() == (1,)
        assert backups(h) and all(b.stat().st_size > 0 for b in backups(h))


def test_backup_without_a_database_fails_rather_than_saving_an_empty_one(home):
    h, env = home
    (h / ".bridge" / "bridge.db").unlink()
    done = run(env, SCRIPTS / "backup")
    assert done.returncode != 0 and "no database" in done.stderr
    assert not (h / ".bridge" / "bridge.db").exists()


# -- tick -----------------------------------------------------------------------------------------------

def tick(env: dict) -> subprocess.CompletedProcess:
    done = run(env, sys.executable, SCRIPTS / "tick")
    assert done.returncode == 0, done.stderr
    return done


def test_tick_trims_big_logs_in_place_and_backs_up_once_a_day(home):
    """A copy made by hand under a backup-like name counted as the newest backup, and stopped the daily one.
    And only a backup that succeeded deleted old ones, so a backup outlived the bound the consent page states
    by up to a day, and forever while backups failed: tick now deletes them every time it runs."""
    h, env = home
    log, small = h / ".bridge" / "server.log", h / ".bridge" / "tunnel.log"
    lines = [f"line {i:07d} ".ljust(99, "x") + "\n" for i in range(60_000)]      # 6 MB
    log.write_text("".join(lines))
    small.write_text("a short log\n")
    inode = log.stat().st_ino
    tick(env)
    kept = log.read_text()
    assert log.stat().st_ino == inode and 900_000 < len(kept) <= 1 << 20
    assert kept.endswith(lines[-1]) and kept.startswith("line ")
    assert small.read_text() == "a short log\n"
    assert len(backups(h)) == 1 and not (h / ".bridge" / "tick.json").exists()   # no alerts asked for
    tick(env)
    assert len(backups(h)) == 1
    yesterday = backups(h)[0].rename(h / "backups" / "bridge-20000101T000000Z.db")
    age(yesterday, DAY + 60)
    (h / "backups" / "bridge-1-before-T1Z.db").write_text("")    # not one of backup's, so not the newest
    tick(env)
    assert len(backups(h)) == 2
    stale = [h / "backups/bridge-19991201T000000Z.db", h / "backups/bridge-19991201T000000Z.db.7.partial"]

    def made_stale():
        for path in stale:
            path.write_text("")
            age(path, 14.9 * DAY)
    made_stale()
    tick(env)                                                   # no backup due
    assert not any(p.exists() for p in stale) and len(backups(h)) == 2
    for path in backups(h):
        age(path, 2 * DAY)
    made_stale()
    (h / ".bridge" / "bridge.db").unlink()          # a backup due, and failing
    assert run(env, sys.executable, SCRIPTS / "tick").returncode != 0
    assert not any(p.exists() for p in stale) and len(backups(h)) == 2


class Watched(http.server.BaseHTTPRequestHandler):
    """The public URL and the operator's ntfy topic, both on one local port. Like Cloudflare in front of the
    public URL, it bans urllib's default User-Agent."""
    up = False
    told: list[str] = []
    kept: dict[str, bytes] = {}         # the off-site container: upload-only, so a name once written stays
    put_fails = False

    def banned(self) -> bool:
        if not self.headers.get("User-Agent", "").startswith("Python-urllib"):
            return False
        self.send_response(403)
        self.end_headers()
        self.wfile.write(b"error code: 1010")
        return True

    def do_GET(self):
        if self.banned():
            return
        self.send_response(200 if Watched.up else 502)
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode() if Watched.up else b"bad gateway")

    def do_POST(self):
        if self.banned():
            return
        Watched.told.append(self.rfile.read(int(self.headers["Content-Length"])).decode())
        self.send_response(200)
        self.end_headers()

    def do_PUT(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        name = self.path.split("?")[0]
        status, code = (500, "") if Watched.put_fails else (403, "UnauthorizedBlobOverwrite") if name in Watched.kept \
            else (201, "")                                       # what Azure answers an upload-only signature
        if self.banned() or self.headers.get("x-ms-blob-type") != "BlockBlob" or not self.path.endswith("?sig=s3cret"):
            status, code = 403, "AuthenticationFailed"
        if status == 201:
            Watched.kept[name] = body
        self.send_response(status)
        if code:
            self.send_header("x-ms-error-code", code)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def watched():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Watched)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Watched.up, Watched.told, Watched.kept, Watched.put_fails = False, [], {}, False
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_tick_tells_the_operator_after_two_failures_at_most_hourly_and_once_when_it_is_back(home, watched):
    """Cloudflare answers urllib's default User-Agent with 403 (error 1010), so against the real public URL the
    check never passed: the operator would have been told it was down every hour while it was up, and never
    that it was back. The test server did not look at the User-Agent, so this passed."""
    h, env = home
    base = watched                                          # the public URL; its ntfy topic is on it too
    env = {**env, "BRIDGE_BASE_URL": base, "BRIDGE_OPERATOR_NOTIFY": f"{base}/topic"}
    state = h / ".bridge" / "tick.json"
    tick(env)
    assert Watched.told == []                              # once can be the tunnel reconnecting
    tick(env)
    assert len(Watched.told) == 1 and "down" in Watched.told[0] and base in Watched.told[0]
    tick(env)
    assert len(Watched.told) == 1
    saved = json.loads(state.read_text())
    state.write_text(json.dumps({**saved, "alerted_t": saved["alerted_t"] - 3600}))
    tick(env)
    assert len(Watched.told) == 2 and "down" in Watched.told[1]
    Watched.up = True
    tick(env)
    tick(env)
    assert len(Watched.told) == 3 and "back up" in Watched.told[2]
    Watched.up = False
    tick(env)
    assert len(Watched.told) == 3


def test_tick_tells_the_operator_when_the_backup_fails_and_calls_nothing_down_without_a_url_to_check(
        home, watched):
    """A failed scheduled backup was only a traceback in tick.log, repeated every ten minutes, which nobody
    reads. And with a notify URL but no base URL, tick fetched '/health', which cannot succeed, and counted a
    server that was up as down."""
    h, env = home
    env = {**env, "BRIDGE_OPERATOR_NOTIFY": f"{watched}/topic"}
    (h / ".bridge" / "bridge.db").unlink()
    for _ in range(3):
        done = run(env, sys.executable, SCRIPTS / "tick")
        assert done.returncode != 0 and "BACKUP FAILED" in done.stderr
    assert Watched.told == ["Bridge backup failed: see tick.log"]
    assert "fails" not in json.loads((h / ".bridge" / "tick.json").read_text())


def test_each_new_backup_is_copied_off_the_machine_once_and_a_failed_copy_is_retried_and_told(home, watched):
    """The backups sat on the server's own disk, so losing the machine lost them too. Each new one goes to a container
    that takes uploads only; a copy that fails is tried again next time, the operator is told at most hourly, and the
    address, which carries the signature, is never printed."""
    h, env = home
    env = {**env, "BRIDGE_OPERATOR_NOTIFY": f"{watched}/topic", "BRIDGE_BACKUP_COPY": f"{watched}/box?sig=s3cret"}
    tick(env)
    (first,) = backups(h)
    assert Watched.kept == {f"/box/{first.name}": first.read_bytes()}
    tick(env)
    assert len(Watched.kept) == 1                                       # once
    first.rename(h / "backups" / "bridge-20000101T000000Z.db")
    age(h / "backups" / "bridge-20000101T000000Z.db", DAY + 60)
    time.sleep(1.1)                                     # a backup's name is its second: the next must differ
    Watched.put_fails = True
    for _ in range(2):
        done = run(env, sys.executable, SCRIPTS / "tick")
        assert done.returncode != 0 and "BACKUP COPY FAILED" in done.stderr and "s3cret" not in done.stderr
    assert Watched.told == ["Bridge's backup could not be copied off the machine: see tick.log"]
    Watched.put_fails = False
    tick(env)
    assert len(Watched.kept) == 2 and len(backups(h)) == 2
    state = h / ".bridge" / "tick.json"
    state.write_text(json.dumps({k: v for k, v in json.loads(state.read_text()).items() if k != "copied"}))
    tick(env)                                                           # its answer lost: already there is copied
    assert len(Watched.kept) == 2 and len(Watched.told) == 1


# -- deploy ---------------------------------------------------------------------------------------------

def git(repo: Path, env: dict, *args) -> str:
    done = run(env, "git", "-C", repo, *args)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def repo(home, tmp_path):
    """This code in a throwaway repository, its suite cut to one test so a deploy under test is quick: a
    commit that passes, a child that fails, its fix, and a side commit that never reached origin/main."""
    h, env = home
    r = tmp_path / "repo"
    listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.split("\n")
    for name in filter(None, listed):
        if (ROOT / name).is_file() and not name.startswith("tests/"):
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, r / name)
    (r / "tests").mkdir()
    (r / "tests" / "test_ok.py").write_text("def test_ok():\n    pass\n")
    git(r.parent, env, "init", "-q", "-b", "main", r)
    git(r, env, "add", "-A")
    git(r, env, "commit", "-q", "-m", "passes")
    good = git(r, env, "rev-parse", "HEAD")
    (r / "tests" / "test_fails.py").write_text("def test_fails():\n    assert 1 + 1 == 3\n")
    git(r, env, "add", "-A")
    git(r, env, "commit", "-q", "-m", "fails")
    bad = git(r, env, "rev-parse", "HEAD")
    git(r, env, "rm", "-q", "tests/test_fails.py")
    git(r, env, "commit", "-q", "-m", "fixed")
    fixed = git(r, env, "rev-parse", "HEAD")
    git(r, env, "update-ref", "refs/remotes/origin/main", fixed)
    side = git(r, env, "commit-tree", f"{good}^{{tree}}", "-p", good, "-m", "never pushed")
    return r, {"good": good, "bad": bad, "fixed": fixed, "side": side}


def deploy(env: dict, r: Path, *args) -> subprocess.CompletedProcess:
    return run(env, SCRIPTS / "deploy", *args, cwd=r)


def test_deploy_refuses_what_it_should_and_force_skips_only_the_refusals(home, repo):
    """With no database at BRIDGE_HOME, deploy said there was nothing to rehearse, moved the live tree, and
    only then died in the backup: new code on disk, not running, never rehearsed and nothing backed up, for the
    next restart to open the real file with. And a live path that was a plain directory inside a checkout had
    git detach, and with --force wipe, that checkout. With BRIDGE_HOME exported at a dev home, deploy
    rehearsed and backed up that file while the server, which sets no BRIDGE_HOME, opened ~/.bridge.
    And a failed restart said only a line number, not that the live tree had already moved."""
    h, env = home
    r, c = repo
    done = deploy(env, r, c["side"])
    assert done.returncode != 0 and "not on origin/main" in done.stderr
    (r / "sub").mkdir()
    done = deploy({**env, "BRIDGE_LIVE": str(r / "sub")}, r, "--force", c["good"])
    assert done.returncode != 0 and "not a git worktree of its own" in done.stderr
    assert git(r, env, "symbolic-ref", "--short", "HEAD") == "main"
    (r / "README.md").write_text("an edit nobody committed\n")
    done = deploy(env, r, c["good"])
    assert done.returncode != 0 and "uncommitted changes" in done.stderr
    db = h / ".bridge" / "bridge.db"
    dev = h / "dev"
    dev.mkdir()
    elsewhere = db.rename(dev / db.name)
    done = deploy({**env, "BRIDGE_HOME": str(dev)}, r, "--force", c["good"])
    assert done.returncode != 0 and "no database" in done.stderr
    assert not (h / "live").exists() and not backups(h)

    elsewhere.rename(db)
    done = deploy(env, r, "--force", c["side"])                    # the stub restart is where it stops
    assert done.returncode != 0 and "Restarting" in done.stdout and "not running it" in done.stderr
    assert git(h / "live", env, "rev-parse", "HEAD") == c["side"] and len(backups(h)) == 1


def test_deploy_moves_nothing_when_the_new_code_cannot_open_the_database_or_the_backup_fails(home, repo, tmp_path):
    """Only a step header pinned the migration rehearsal, so its abort could break unnoticed. And the backup ran
    after the live tree had moved: when it failed, the old server went on running beside the new commit's files,
    serving its templates, and was never restarted."""
    h, env = home
    r, c = repo
    restarted = tmp_path / "restarted"
    env = {**env, "BRIDGE_RESTART": f'touch "{restarted}"'}
    raw = sqlite3.connect(h / ".bridge" / "bridge.db")
    raw.execute("PRAGMA user_version=99")
    done = deploy(env, r, c["good"])
    assert done.returncode != 0 and "could not open a copy of the live database" in done.stderr
    assert "schema version 99" in done.stderr
    assert not (h / "live").exists() and not backups(h) and not restarted.exists()

    raw.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    raw.close()
    (h / "backups").write_text("")                                 # where the directory should be
    done = deploy(env, r, c["good"])
    assert done.returncode != 0 and "backup failed; nothing has moved" in done.stderr
    assert not (h / "live").exists() and not restarted.exists()


def test_deploy_puts_a_tested_commit_live_keeps_it_when_the_next_fails_and_moves_on_to_a_fix(home, repo, tmp_path):
    h, env = home
    r, c = repo
    pid = tmp_path / "server.pid"
    # Stands in for `launchctl kickstart -k`: stops the running server, and starts the deployed code the way
    # the LaunchAgent would.
    env = {**env, "BRIDGE_RESTART": f'if [ -f "{pid}" ]; then old=$(cat "{pid}"); kill $old; '
                                          f'while kill -0 $old 2>/dev/null; do sleep 0.1; done; fi; '
                                          f'cd "$BRIDGE_LIVE"; .venv/bin/bridge serve --port '
                                          f'{env["BRIDGE_PORT"]} >>"$BRIDGE_HOME/server.log" 2>&1 '
                                          f'</dev/null & echo $! >"{pid}"'}
    try:
        done = deploy(env, r, c["good"])
        assert done.returncode == 0, done.stdout + done.stderr
        short = git(r, env, "rev-parse", "--short", c["good"])
        assert f"Live: {short}" in done.stdout and "Rehearsing the migration" in done.stdout
        assert "Tests, run 5 of 5" in done.stdout
        assert git(h / "live", env, "rev-parse", "HEAD") == c["good"] and len(backups(h)) == 1
        assert git(r, env, "worktree", "list").count("\n") == 1          # the build worktree is gone

        (h / "live" / "README.md").write_text("a hand edit on the live tree\n")
        done = deploy(env, r, c["good"])
        assert done.returncode != 0 and str(h / "live") in done.stderr and "uncommitted" in done.stderr
        git(h / "live", env, "checkout", "--", "README.md")

        done = deploy(env, r, c["bad"])
        assert done.returncode != 0 and "tests failed on run 1" in done.stderr
        assert git(h / "live", env, "rev-parse", "HEAD") == c["good"] and len(backups(h)) == 1

        backups(h)[0].rename(h / "backups" / "bridge-20000101T000000Z.db")      # made within this second
        done = deploy(env, r, c["fixed"])
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"Live: {git(r, env, 'rev-parse', '--short', c['fixed'])}" in done.stdout
        assert git(h / "live", env, "rev-parse", "HEAD") == c["fixed"] and len(backups(h)) == 2
    finally:
        if pid.exists():
            os.kill(int(pid.read_text()), signal.SIGTERM)
