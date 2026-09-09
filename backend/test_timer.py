"""The cycle clock — the manager's window, and what it caught.

    pytest test_timer.py -v

What is pinned down here:

  * a cycle starts with no clock, and no screen shows one;
  * setting a budget starts it from now, adding to a running one leaves the
    time already spent spent, and a budget of zero takes the clock away;
  * every BD reads the same countdown and only a manager can move it;
  * running out of time changes nothing — the cycle keeps its window so the
    figures still have one to report on;
  * the figures count what happened *inside* the window, dated by when
    somebody marked it, with work finished after the whistle counted as late
    rather than quietly folded in with the rest.

Shares a database with the rest of the suite — every account and profile minted
here carries a name no other module uses.
"""
import datetime as dt
import io, itertools, os, csv
import pytest
from fastapi.testclient import TestClient

_serial = itertools.count(1)

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path_factory.mktemp('db')}/clock.db"
    from app.main import SessionLocal, app, engine, hash_password
    from app.models import Base, User
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(email="a@clock.example.com", name="Clock Boss", password_hash=hash_password("admin12345"), role="admin"))
    db.add(User(email="ali@clock.example.com", name="Cal Ock", password_hash=hash_password("bdpass12345"), role="bd"))
    db.add(User(email="sara@clock.example.com", name="Tess Timer", password_hash=hash_password("bdpass12345"), role="bd"))
    db.commit(); db.close()
    return TestClient(app)

def token(client, email, pw="bdpass12345"):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'email': email, 'password': pw}).json()['token']}"}

@pytest.fixture(scope="module")
def admin(client): return token(client, "a@clock.example.com", "admin12345")

def mkprofile(client, admin, email):
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    return client.post("/api/profiles", json={"name": f"Clock{next(_serial)}", "headline": "AI Engineer",
                       "platform": "Upwork", "user_id": users[email]}, headers=admin).json()["id"]

def rows_csv(rows):
    out = io.StringIO(); w = csv.writer(out); w.writerow(["Job Title","Company","Job URL"])
    for r in rows: w.writerow(r)
    return out.getvalue().encode()

def cycle(client, admin, name="W1"):
    return client.post("/api/batches", json={"name": name, "mode": "cover", "quota": 500,
                       "one_per_client": False, "auto_build_minutes": 0}, headers=admin).json()["id"]


def test_a_cycle_starts_with_no_clock(client, admin):
    c = cycle(client, admin, "No clock")
    b = client.get(f"/api/batches/{c}", headers=admin).json()
    assert b["timer_minutes"] == 0 and b["timer_seconds_left"] == 0
    assert b["timer_running"] is False
    assert client.get(f"/api/batches/{c}/timer-report", headers=admin).status_code == 404


def test_setting_moving_and_clearing(client, admin):
    c = cycle(client, admin, "Clock")
    r = client.put(f"/api/batches/{c}/timer", json={"minutes": 120}, headers=admin)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["timer_minutes"] == 120 and b["timer_running"]
    assert 7150 < b["timer_seconds_left"] <= 7200, b["timer_seconds_left"]

    added = client.put(f"/api/batches/{c}/timer", json={"add_minutes": 15}, headers=admin).json()
    assert added["timer_minutes"] == 135
    assert added["timer_started_at"] == b["timer_started_at"], "adding time must not restart"
    assert 8050 < added["timer_seconds_left"] <= 8100

    taken = client.put(f"/api/batches/{c}/timer", json={"add_minutes": -15}, headers=admin).json()
    assert taken["timer_minutes"] == 120

    gone = client.put(f"/api/batches/{c}/timer", json={"minutes": 0}, headers=admin).json()
    assert gone["timer_minutes"] == 0 and gone["timer_started_at"] is None

    assert client.put(f"/api/batches/{c}/timer", json={"minutes": 99999},
                      headers=admin).status_code == 400
    assert client.put(f"/api/batches/{c}/timer", json={}, headers=admin).status_code == 400


def test_a_bd_sees_the_clock_and_a_manager_only_sets_it(client, admin):
    c = cycle(client, admin, "Seen")
    client.put(f"/api/batches/{c}/timer", json={"minutes": 60}, headers=admin)
    ali = token(client, "ali@clock.example.com")
    seen = [b for b in client.get("/api/batches", headers=ali).json() if b["id"] == c][0]
    assert seen["timer_running"] and seen["timer_seconds_left"] > 3500
    assert client.put(f"/api/batches/{c}/timer", json={"minutes": 30},
                      headers=ali).status_code == 403
    assert client.get(f"/api/batches/{c}/timer-report", headers=ali).status_code == 403


def test_an_expired_clock_reads_as_no_time_left_but_keeps_its_window(client, admin):
    from app.main import SessionLocal
    from app.models import Batch
    c = cycle(client, admin, "Expired")
    client.put(f"/api/batches/{c}/timer", json={"minutes": 30}, headers=admin)
    db = SessionLocal()
    row = db.get(Batch, c)
    row.timer_started_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=2)
    db.commit(); db.close()

    b = client.get(f"/api/batches/{c}", headers=admin).json()
    assert b["timer_seconds_left"] == 0 and b["timer_running"] is False
    assert b["timer_minutes"] == 30, "the window is kept so the figures still have one"
    assert client.get(f"/api/batches/{c}/timer-report", headers=admin).status_code == 200


def test_the_figures_count_only_what_happened_inside_the_window(client, admin):
    from app.main import SessionLocal
    from app.models import Assignment, Batch
    ali_p = mkprofile(client, admin, "ali@clock.example.com"); sara_p = mkprofile(client, admin, "sara@clock.example.com")
    ali = token(client, "ali@clock.example.com"); sara = token(client, "sara@clock.example.com")
    c = cycle(client, admin, "Figures")
    for hdr, pid, lo in ((ali, ali_p, 100), (sara, sara_p, 200)):
        client.post(f"/api/batches/{c}/uploads", data={"profile_id": pid},
                    files={"file": ("s.csv", rows_csv([(f"R{n}", f"C{n} Ltd",
                          f"https://www.upwork.com/jobs/~01{n:016x}") for n in range(lo, lo+5)]),
                          "text/csv")}, headers=hdr)
    client.post(f"/api/batches/{c}/compute", headers=admin)
    client.put(f"/api/batches/{c}/timer", json={"minutes": 120}, headers=admin)

    mine = client.get(f"/api/batches/{c}/profiles/{ali_p}/sheet", headers=ali).json()["jobs"]
    assert len(mine) == 5
    client.patch(f"/api/assignments/{mine[0]['id']}", json={"status": "applied"}, headers=ali)
    client.patch(f"/api/assignments/{mine[1]['id']}",
                 json={"status": "skipped", "reason": "Rate too low."}, headers=ali)

    # ...and one marked long after the whistle.
    db = SessionLocal()
    late = db.get(Assignment, mine[2]["id"])
    late.status = "applied"
    late.status_changed_at = (db.get(Batch, c).timer_started_at + dt.timedelta(hours=5))
    db.commit(); db.close()

    figures = client.get(f"/api/batches/{c}/timer-report", headers=admin).json()
    row = [r for r in figures["profiles"] if r["id"] == ali_p][0]
    assert row["applied"] == 1 and row["skipped"] == 1
    assert row["late"] == 1, "work finished after time was up is counted as late"
    assert row["given"] == 5
    assert row["left"] == 3, "two untouched, plus the one done late"
    assert row["done"] == 2 and row["done_pct"] == 40


def test_own_jobs_logged_inside_the_window_are_counted(client, admin):
    ali_p = mkprofile(client, admin, "ali@clock.example.com"); sara_p = mkprofile(client, admin, "sara@clock.example.com")
    ali = token(client, "ali@clock.example.com"); sara = token(client, "sara@clock.example.com")
    c = cycle(client, admin, "Own jobs")
    for hdr, pid, lo in ((ali, ali_p, 300), (sara, sara_p, 400)):
        client.post(f"/api/batches/{c}/uploads", data={"profile_id": pid},
                    files={"file": ("s.csv", rows_csv([(f"R{n}", f"C{n} Ltd",
                          f"https://www.upwork.com/jobs/~01{n:016x}") for n in range(lo, lo+3)]),
                          "text/csv")}, headers=hdr)
    client.post(f"/api/batches/{c}/compute", headers=admin)
    client.put(f"/api/batches/{c}/timer", json={"minutes": 120}, headers=admin)

    # Ali types three more of his own into the open cycle while the clock runs.
    more = client.put(f"/api/batches/{c}/profiles/{ali_p}/entries", json={"rows": [
        {"url": f"https://www.upwork.com/jobs/~01{n:016x}", "title": f"R{n}",
         "company": f"C{n} Ltd"} for n in range(300, 306)]}, headers=ali)
    assert more.status_code == 200, more.text
    client.post(f"/api/batches/{c}/compute", headers=admin)

    row = [r for r in client.get(f"/api/batches/{c}/timer-report", headers=admin).json()["profiles"]
           if r["id"] == ali_p][0]
    assert row["own_jobs"] == 3, "the three he added after the clock started"


def test_others_jobs_marked_applied_are_not_counted_twice(client, admin):
    """A job off somebody else's sheet writes an application row too. It is
    others' work, and must show up once, under others' jobs."""
    ali_p = mkprofile(client, admin, "ali@clock.example.com"); sara_p = mkprofile(client, admin, "sara@clock.example.com")
    ali = token(client, "ali@clock.example.com"); sara = token(client, "sara@clock.example.com")
    c = cycle(client, admin, "No double count")
    for hdr, pid, lo in ((ali, ali_p, 500), (sara, sara_p, 600)):
        client.post(f"/api/batches/{c}/uploads", data={"profile_id": pid},
                    files={"file": ("s.csv", rows_csv([(f"R{n}", f"C{n} Ltd",
                          f"https://www.upwork.com/jobs/~01{n:016x}") for n in range(lo, lo+4)]),
                          "text/csv")}, headers=hdr)
    client.post(f"/api/batches/{c}/compute", headers=admin)
    client.put(f"/api/batches/{c}/timer", json={"minutes": 120}, headers=admin)

    mine = client.get(f"/api/batches/{c}/profiles/{ali_p}/sheet", headers=ali).json()["jobs"]
    client.patch(f"/api/assignments/{mine[0]['id']}", json={"status": "applied"}, headers=ali)

    row = [r for r in client.get(f"/api/batches/{c}/timer-report", headers=admin).json()["profiles"]
           if r["id"] == ali_p][0]
    assert row["applied"] == 1 and row["own_jobs"] == 0
