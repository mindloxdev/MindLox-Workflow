"""Full round trip through the API, no running server needed.

    python seed.py --samples
    pytest test_e2e.py -v -s

The scenario throughout is the one the product exists for: two profiles with
the same skills, run by two different people. Khuram logged 30 jobs, Zahid 50,
ten of them the same posting found twice. Khuram gets back the 40 it has never
seen, Zahid the 20 it has never seen — and either may receive a job the other
has already used, because they are two candidates, not one person applying
twice.

Note on isolation: every test mints its own profiles. A profile's history and
its open lists both follow it across cycles, so tests that shared profiles would
block each other's dispatch.
"""
import io
import itertools
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SHEETS = Path(__file__).parent / "sample_sheets"

PEOPLE = [("ali@example.com", "Ali Raza"),
          ("sara@example.com", "Sara Khan"),
          ("hina@example.com", "Hina Malik")]

SEEDED = [("Khuram", "AI Engineer", "ali@example.com", "khuram-applied.csv"),
          ("Zahid", "AI Engineer", "sara@example.com", "zahid-applied.csv"),
          ("Nadia", "Full Stack Engineer", "hina@example.com", "nadia-applied.csv")]

_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path_factory.mktemp('db')}/test.db"
    from app.main import SessionLocal, app, engine, hash_password  # noqa: E402
    from app.models import Base, Profile, User  # noqa: E402

    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(email="admin@example.com", name="Manager",
                password_hash=hash_password("admin12345"), role="admin"))
    for email, name in PEOPLE:
        db.add(User(email=email, name=name,
                    password_hash=hash_password("bdpass12345"), role="bd"))
    db.commit()
    owners = {u.email: u.id for u in db.query(User).all()}
    for name, headline, email, _ in SEEDED:
        db.add(Profile(name=name, headline=headline, platform="Upwork",
                       user_id=owners[email]))
    db.commit()
    db.close()
    return TestClient(app)


def token(client, email, password="bdpass12345"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return token(client, "admin@example.com", "admin12345")


@pytest.fixture(scope="module")
def seeded(client, admin):
    return {p["name"]: p["id"] for p in client.get("/api/profiles", headers=admin).json()}


@pytest.fixture
def new_profile(client, admin):
    """Mint a profile nothing else in the suite has touched."""
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}

    def make(email, headline="AI Engineer"):
        name = f"Ident{next(_serial)}"
        response = client.post("/api/profiles",
                               json={"name": name, "headline": headline,
                                     "platform": "Upwork", "user_id": users[email]},
                               headers=admin)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return make


def sheet(job_ids, tracking=False):
    """A CSV of Upwork postings, optionally with a referral tail on every link."""
    out = io.StringIO()
    out.write("Job Title,Company,Job URL\n")
    for n in job_ids:
        url = f"https://www.upwork.com/jobs/~01{n:016x}"
        if tracking:
            url += "?utm_source=email&referrer=digest"
        out.write(f"Role {n},Client {n % 12} Ltd,{url}\n")
    return out.getvalue().encode()


def open_cycle(client, admin, name, mode="cover", quota=500, one_per_client=False,
               auto_build_minutes=0):
    """Cycles default to no timer here so tests build when they mean to."""
    response = client.post("/api/batches", json={"name": name, "mode": mode, "quota": quota,
                                                 "one_per_client": one_per_client,
                                                 "auto_build_minutes": auto_build_minutes},
                           headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def hand_in(client, batch_id, headers, profile_id, payload, filename="s.csv"):
    response = client.post(f"/api/batches/{batch_id}/uploads",
                           data={"profile_id": profile_id},
                           files={"file": (filename, payload, "text/csv")}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def listing(client, batch_id, profile_id, headers):
    """What the profile sees on screen — skipped rows are not on it."""
    return client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet",
                      headers=headers).json()["jobs"]


def stored_born(assignment_ids):
    """When each of these assignment rows was created.

    The point of asserting on this rather than on the id alone: SQLite hands a
    deleted rowid straight back out, so a row destroyed and minted again comes
    back wearing the same number and the id proves nothing here. `created_at`
    is stamped per insert, so it tells the two apart on any database — which is
    what makes this test mean on SQLite what it means on Postgres.
    """
    from app.main import SessionLocal
    from app.models import Assignment
    db = SessionLocal()
    try:
        return {aid: (db.get(Assignment, aid).created_at if db.get(Assignment, aid) else None)
                for aid in assignment_ids}
    finally:
        db.close()


def stored_status(batch_id, profile_id, assignment_id):
    """One assignment's status straight from the store.

    The screen hides skipped rows, deliberately — there is nothing left to do
    about one. But "the skip survived the rebuild" is exactly the thing that
    stops the job coming back, so it still has to be checked somewhere, and
    the only honest place left is the row itself.
    """
    from app.main import SessionLocal
    from app.models import Assignment
    db = SessionLocal()
    try:
        row = db.get(Assignment, assignment_id)
        return row.status if row else None
    finally:
        db.close()


# --------------------------------------------------------------------------- #

def test_the_headline_scenario(client, admin, seeded):
    """Khuram logged 30, Zahid logged 50, ten shared. 40 back and 20 back."""
    if not (SHEETS / "khuram-applied.csv").exists():
        pytest.skip("Run `python seed.py --samples` first.")

    batch_id = open_cycle(client, admin, "Week 32")
    for name, _, email, filename in SEEDED[:2]:
        body = hand_in(client, batch_id, token(client, email), seeded[name],
                       (SHEETS / filename).read_bytes(), filename)
        assert body["mapping"]["url"], f"auto-mapper missed the link column in {filename}"
        print(f"  {name:8s} {body['row_count']:3d} rows  mapped -> {body['mapping']}")

    data = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()

    print("\n  Report:")
    for key, value in data["report"].items():
        print(f"    {key:38s} {value}")
    print("\n  New lists:")
    for person in data["participants"]:
        print(f"    {person['name']:8s} {person['headline']:22s} "
              f"{person['person']:12s} {person['assigned']:4d} jobs")

    handed = {p["name"]: p["assigned"] for p in data["participants"]}
    assert handed == {"Khuram": 40, "Zahid": 20}
    assert data["report"]["Jobs two profiles both applied to"] == 10

    xlsx = client.get(f"/api/batches/{batch_id}/profiles/{seeded['Khuram']}/sheet.xlsx",
                      headers=token(client, "ali@example.com"))
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    workbook = client.get(f"/api/batches/{batch_id}/report.xlsx", headers=admin)
    assert workbook.status_code == 200 and workbook.content[:2] == b"PK"
    print("  Excel downloads OK.")


def test_a_messy_sheet_still_maps(client, admin, seeded):
    """Nadia's sheet has different column names, blank links and shouty titles."""
    if not (SHEETS / "nadia-applied.csv").exists():
        pytest.skip("Run `python seed.py --samples` first.")
    batch_id = open_cycle(client, admin, "Messy")
    body = hand_in(client, batch_id, token(client, "hina@example.com"), seeded["Nadia"],
                   (SHEETS / "nadia-applied.csv").read_bytes(), "nadia-applied.csv")
    assert body["mapping"] == {"url": "Post Link", "title": "Position Applied",
                               "company": "Client Name", "platform": "Job Portal",
                               "date": "Apply Date",
                               # Nadia's sheet has no description column, and an
                               # empty string is the mapper saying so rather
                               # than guessing at one of the other five.
                               "description_url": "",
                               # Headline is a canonical field like the rest, so
                               # auto_map reports on it too. No sheet carries a
                               # column for it — it comes off the profile.
                               "headline": ""}


def test_two_profiles_may_receive_the_same_job(client, admin, new_profile):
    """The behaviour the whole redesign is for: one posting, two candidates."""
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    # The same headline as the other two. Cover mode only offers a job to
    # profiles sharing a headline with whoever applied to it, so a scout billed
    # as a Full Stack Engineer — which is what this said before the headline
    # gate existed — could never hand anything to two AI Engineers, and the
    # test was asserting on an empty list.
    scout = new_profile("hina@example.com")

    batch_id = open_cycle(client, admin, "Shared")
    hand_in(client, batch_id, token(client, "hina@example.com"), scout, sheet(range(2000, 2010)))
    hand_in(client, batch_id, token(client, "ali@example.com"), khuram, sheet(range(2100, 2105)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(2200, 2205)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    a = {j["url"] for j in listing(client, batch_id, khuram, token(client, "ali@example.com"))}
    b = {j["url"] for j in listing(client, batch_id, zahid, token(client, "sara@example.com"))}
    assert len(a & b) == 10, "both should be offered the ten jobs neither has touched"

    # And the gate itself: a profile selling something else is not offered them.
    outsider = new_profile("hina@example.com", "Full Stack Engineer")
    hand_in(client, batch_id, token(client, "hina@example.com"), outsider,
            sheet(range(2300, 2305)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200
    theirs = {j["url"] for j in listing(client, batch_id, outsider,
                                        token(client, "hina@example.com"))}
    assert not (theirs & a), "a different headline is a different market"


def test_rebuilding_gives_the_same_answer(client, admin, new_profile):
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, "Rebuild")
    hand_in(client, batch_id, token(client, "ali@example.com"), khuram, sheet(range(1000, 1020)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(1010, 1040)))

    first = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()
    second = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()
    assert second["report"] == first["report"], "rebuilding changed the outcome"
    assert ([p["assigned"] for p in second["participants"]]
            == [p["assigned"] for p in first["participants"]])


def test_unworked_jobs_stay_on_the_cycle_that_dispatched_them(client, admin, new_profile):
    """A cycle's list is what that cycle's sheets held.

    Untouched jobs used to be dragged forward into whatever cycle opened next.
    Two cycles open at once turned that into the complaint behind this test: a
    BD's "others' jobs" was mostly last fortnight's leftovers, and with both
    cycles rebuilding on the same timer the same job moved between them every
    five minutes. Nothing is lost by leaving it out — the row stays where it
    was, and so does the cycle it is on.
    """
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    ali, sara = token(client, "ali@example.com"), token(client, "sara@example.com")

    first = open_cycle(client, admin, "Carry 1")
    hand_in(client, first, ali, khuram, sheet(range(3000, 3010)))
    hand_in(client, first, sara, zahid, sheet(range(3010, 3020)))
    client.post(f"/api/batches/{first}/compute", headers=admin)

    mine = listing(client, first, khuram, ali)
    assert len(mine) == 10, "the ten Zahid found and Khuram has not tried"
    client.patch(f"/api/assignments/{mine[0]['id']}", json={"status": "applied"}, headers=ali)
    client.patch(f"/api/assignments/{mine[1]['id']}",
                 json={"status": "skipped", "reason": "On-site only."}, headers=ali)

    # Skipping it takes it off the screen at once. There is nothing further to
    # do about a job this profile has turned down, and it never returns.
    assert len(listing(client, first, khuram, ali)) == 9
    assert mine[1]["id"] not in {job["id"] for job in listing(client, first, khuram, ali)}

    # The same sheets again, so the second cycle gathers nothing the first did
    # not. Every one of those postings is either Khuram's own, or already
    # waiting on his first list.
    second = open_cycle(client, admin, "Carry 2")
    hand_in(client, second, ali, khuram, sheet(range(3000, 3010)))
    hand_in(client, second, sara, zahid, sheet(range(3010, 3020)))
    data = client.post(f"/api/batches/{second}/compute", headers=admin).json()

    handed = {p["id"]: p["assigned"] for p in data["participants"]}
    assert handed[khuram] == 0, "nothing carries forward, and nothing is handed out twice"

    # Still there, on the cycle that gave them to him: the eight he has not got
    # to, and the one he applied for. The skip is gone from the screen and has
    # to stay gone.
    kept = listing(client, first, khuram, ali)
    assert len(kept) == 9
    assert mine[0]["id"] in {job["id"] for job in kept}, "the one he applied for"
    assert mine[1]["id"] not in {job["id"] for job in kept}, "the one he turned down"
    assert stored_status(first, khuram, mine[1]["id"]) == "skipped", \
        "the skip has to survive, or the job comes back next cycle"


def test_split_mode_still_gives_each_job_to_one_profile(client, admin, new_profile):
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, "Split", mode="split")
    hand_in(client, batch_id, token(client, "ali@example.com"), khuram, sheet(range(4000, 4020)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(4020, 4040)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    seen = set()
    for profile_id, email in ((khuram, "ali@example.com"), (zahid, "sara@example.com")):
        for job in listing(client, batch_id, profile_id, token(client, email)):
            assert job["url"] not in seen, f"{job['url']} went to two profiles in a split cycle"
            seen.add(job["url"])
    assert seen, "a split cycle should still dispatch something"


def test_one_person_can_run_two_profiles_independently(client, admin, new_profile):
    """What one identity has applied to must not restrict the other, even when
    the same person runs both."""
    first = new_profile("ali@example.com")
    second = new_profile("ali@example.com")
    ali = token(client, "ali@example.com")

    mine = {p["id"] for p in client.get("/api/profiles", headers=ali).json()}
    assert {first, second} <= mine

    batch_id = open_cycle(client, admin, "Two hats")
    hand_in(client, batch_id, ali, first, sheet(range(5000, 5010)))
    hand_in(client, batch_id, ali, second, sheet(range(5010, 5020)))
    data = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()

    handed = {p["id"]: p["assigned"] for p in data["participants"]}
    assert handed[first] == 10 and handed[second] == 10, \
        "each identity is judged on its own history, not its operator's"

    sheets = client.get(f"/api/batches/{batch_id}/my-sheets", headers=ali).json()
    assert {p["id"] for p in sheets["profiles"]} >= {first, second}


def test_jobs_can_be_typed_in_instead_of_uploaded(client, admin, new_profile):
    """A BD with no spreadsheet types rows on screen; they must reach the cycle
    exactly as an uploaded sheet would."""
    typed = new_profile("ali@example.com")
    other = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")

    batch_id = open_cycle(client, admin, "Typed")
    empty = client.get(f"/api/batches/{batch_id}/profiles/{typed}/entries", headers=ali)
    assert empty.status_code == 200 and empty.json()["rows"] == []

    rows = [{"url": f"https://www.upwork.com/jobs/~01{n:016x}",
             "title": f"Role {n}", "company": f"Client {n}",
             "platform": "Upwork", "date": "2026-08-01"} for n in range(9000, 9006)]
    rows.append({"url": "", "title": "", "company": "", "platform": "", "date": ""})
    saved = client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries",
                       json={"rows": rows}, headers=ali)
    assert saved.status_code == 200, saved.text
    assert saved.json()["row_count"] == 6, "the blank row should not be stored"

    # It reads back, and the manager sees it as a handed-in sheet.
    back = client.get(f"/api/batches/{batch_id}/profiles/{typed}/entries", headers=ali).json()
    assert len(back["rows"]) == 6 and back["typed"] is True
    handed = client.get(f"/api/batches/{batch_id}", headers=admin).json()["uploads"]
    assert any(u["profile_id"] == typed and u["row_count"] == 6 for u in handed)

    # And it dispatches like any other sheet.
    hand_in(client, batch_id, token(client, "sara@example.com"), other, sheet(range(9100, 9110)))
    data = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()
    handed = {p["id"]: p["assigned"] for p in data["participants"]}
    assert handed[typed] == 10, "the typed profile gets the ten it has not tried"
    assert handed[other] == 6, "the other profile gets the six that were typed in"


def test_opening_the_entry_screen_does_not_hand_anything_in(client, admin, new_profile):
    """Clicking into the table and away must not leave an empty sheet behind —
    the manager would read that as a profile having reported in."""
    typed = new_profile("ali@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Typed empty")

    blank = client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries",
                       json={"rows": [{"url": "", "title": "", "company": ""}]}, headers=ali)
    assert blank.status_code == 200 and blank.json()["row_count"] == 0
    assert client.get(f"/api/batches/{batch_id}", headers=admin).json()["uploads"] == []

    # Every new row arrives pre-stamped with the time, so a row carrying only a
    # timestamp is still an empty row.
    stamped = client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries", headers=ali,
                         json={"rows": [{"url": "", "title": "", "company": "",
                                         "platform": "Upwork", "date": "2026-08-18 11:45"}]})
    assert stamped.status_code == 200 and stamped.json()["row_count"] == 0, \
        "a row with only a stamp and a platform is not a job"
    assert client.get(f"/api/batches/{batch_id}", headers=admin).json()["uploads"] == []

    # And clearing a real sheet takes it back out again.
    client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries",
               json={"rows": [{"url": "https://www.upwork.com/jobs/~01000000000000beef"}]},
               headers=ali)
    assert len(client.get(f"/api/batches/{batch_id}", headers=admin).json()["uploads"]) == 1
    client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries", json={"rows": []}, headers=ali)
    assert client.get(f"/api/batches/{batch_id}", headers=admin).json()["uploads"] == []


def test_the_applied_date_is_kept(client, admin, new_profile):
    """The date column used to be read off the sheet and thrown away. It should
    reach the history row, and marking a job applied should stamp it."""
    from sqlalchemy import select as sa_select

    from app.main import SessionLocal
    from app.models import Application

    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")

    batch_id = open_cycle(client, admin, "Dates")
    client.put(f"/api/batches/{batch_id}/profiles/{one}/entries", headers=ali, json={"rows": [
        {"url": "https://www.upwork.com/jobs/~01000000000000d1d1", "title": "Dated",
         "company": "Acme", "platform": "Upwork", "date": "2026-08-17 09:15"}]})
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(9400, 9405)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)

    db = SessionLocal()
    try:
        typed = db.scalar(sa_select(Application).where(Application.profile_id == one))
        assert typed.applied_on == "2026-08-17 09:15", "the typed date should be stored verbatim"

        # Marking something applied stamps the moment it happened.
        job = client.get(f"/api/batches/{batch_id}/profiles/{one}/sheet", headers=ali).json()["jobs"][0]
        client.patch(f"/api/assignments/{job['id']}", json={"status": "applied"}, headers=ali)
        db.expire_all()
        marked = db.scalars(sa_select(Application).where(Application.profile_id == one)).all()
        stamps = [a.applied_on for a in marked if a.applied_on]
        assert len(stamps) == 2 and any(s != "2026-08-17 09:15" for s in stamps)
    finally:
        db.close()


def test_typed_entries_reject_a_dangerous_link(client, admin, new_profile):
    typed = new_profile("ali@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Typed hostile")
    client.put(f"/api/batches/{batch_id}/profiles/{typed}/entries",
               json={"rows": [{"url": "javascript:alert(1)", "title": "X", "company": "Y"}]},
               headers=ali)
    back = client.get(f"/api/batches/{batch_id}/profiles/{typed}/entries", headers=ali).json()
    assert back["rows"][0]["url"] == "", "a javascript: link must not survive being typed in"


def test_a_bd_cannot_type_into_someone_elses_profile(client, admin, seeded):
    batch_id = open_cycle(client, admin, "Typed boundary")
    denied = client.put(f"/api/batches/{batch_id}/profiles/{seeded['Zahid']}/entries",
                        json={"rows": [{"url": "https://x.com/jobs/1234567"}]},
                        headers=token(client, "ali@example.com"))
    assert denied.status_code == 403


def test_building_keeps_the_cycle_open_but_closing_shuts_it(client, admin, new_profile):
    """Lists are rebuilt on a timer while a cycle runs, so a build must not lock
    anyone out. Only closing the cycle does that."""
    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Still open")
    hand_in(client, batch_id, ali, one, sheet(range(9200, 9205)))
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(9205, 9210)))
    built = client.post(f"/api/batches/{batch_id}/compute", headers=admin).json()
    assert built["status"] == "open" and built["last_built_at"]

    more = client.put(f"/api/batches/{batch_id}/profiles/{one}/entries",
                      json={"rows": [{"url": "https://www.upwork.com/jobs/~01000000000000abcd",
                                      "title": "Late one", "company": "Acme"}]},
                      headers=ali)
    assert more.status_code == 200, "an open cycle keeps taking jobs after a build"

    assert client.post(f"/api/batches/{batch_id}/close", headers=admin).json()["status"] == "computed"
    late = client.put(f"/api/batches/{batch_id}/profiles/{one}/entries",
                      json={"rows": [{"url": "https://www.upwork.com/jobs/~01000000000000abce"}]},
                      headers=ali)
    assert late.status_code == 400


def test_a_rebuild_keeps_work_people_have_marked(client, admin, new_profile):
    """The timer rebuilds behind people's backs. A job someone marked applied
    is their record of this cycle and must survive that."""
    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Marks survive")
    hand_in(client, batch_id, ali, one, sheet(range(9500, 9510)))
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(9510, 9520)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)

    mine = listing(client, batch_id, one, ali)
    assert len(mine) == 10
    client.patch(f"/api/assignments/{mine[0]['id']}", json={"status": "applied"}, headers=ali)
    client.patch(f"/api/assignments/{mine[1]['id']}",
                 json={"status": "skipped", "reason": "On-site only."}, headers=ali)

    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    after = listing(client, batch_id, one, ali)
    marks = {job["id"]: job["status"] for job in after}
    assert marks.get(mine[0]["id"]) == "applied", "an applied job disappeared on rebuild"
    # Off the screen, still in the store. Both halves matter: gone from the
    # list because there is nothing to do, kept underneath because that row
    # is what stops the job being dispatched again.
    assert mine[1]["id"] not in marks, "a skipped job should not be back on the list"
    assert stored_status(batch_id, one, mine[1]["id"]) == "skipped", \
        "a skipped job disappeared on rebuild"
    assert len(after) == 9, "the skipped one is gone; the other nine are unchanged"


def test_the_timer_builds_an_open_cycle_on_its_own(client, admin, new_profile):
    """No manager, no button — run_due_builds is what the background loop calls."""
    from app.main import run_due_builds

    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Hands off", auto_build_minutes=10)
    hand_in(client, batch_id, ali, one, sheet(range(9600, 9610)))
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(9610, 9620)))

    assert listing(client, batch_id, one, ali) == [], "nothing built yet"
    assert batch_id in run_due_builds(), "a never-built open cycle is due immediately"
    assert len(listing(client, batch_id, one, ali)) == 10

    # Just built, so the timer leaves it alone until the interval is up.
    assert batch_id not in run_due_builds()

    # And it stops entirely once the cycle is closed.
    client.post(f"/api/batches/{batch_id}/close", headers=admin)
    from app.main import SessionLocal
    from app.models import Batch
    db = SessionLocal()
    try:
        batch = db.get(Batch, batch_id)
        batch.last_built_at = None
        db.commit()
    finally:
        db.close()
    assert batch_id not in run_due_builds(), "a closed cycle must not be rebuilt"


def test_turning_the_timer_off_leaves_it_to_the_manager(client, admin, new_profile):
    from app.main import run_due_builds

    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    ali = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, "Manual only", auto_build_minutes=0)
    hand_in(client, batch_id, ali, one, sheet(range(9700, 9710)))
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(9710, 9720)))

    assert batch_id not in run_due_builds()
    assert listing(client, batch_id, one, ali) == []
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    assert len(listing(client, batch_id, one, ali)) == 10


def test_profile_names_must_be_unique(client, admin):
    clash = client.post("/api/profiles", json={"name": "khuram", "headline": "AI"},
                        headers=admin)
    assert clash.status_code == 409


def test_a_bd_cannot_act_as_someone_elses_profile(client, admin, seeded):
    batch_id = open_cycle(client, admin, "Boundary")
    denied = client.post(f"/api/batches/{batch_id}/uploads",
                         data={"profile_id": seeded["Zahid"]},
                         files={"file": ("s.csv", sheet(range(10)), "text/csv")},
                         headers=token(client, "ali@example.com"))
    assert denied.status_code == 403


def test_uploaded_links_cannot_carry_a_script(client, admin, new_profile):
    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, "Hostile")
    evil = ("Job Title,Company,Job URL\n"
            "Designer,Acme,javascript:alert(document.domain)\n").encode()
    hand_in(client, batch_id, token(client, "ali@example.com"), one, evil)
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(6000, 6005)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    for profile_id, email in ((one, "ali@example.com"), (two, "sara@example.com")):
        jobs = listing(client, batch_id, profile_id, token(client, email))
        assert not any((j["url"] or "").lower().startswith("javascript:") for j in jobs)


def test_exported_cells_cannot_be_formulas(client, admin, new_profile):
    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, "Formula")
    nasty = ("Job Title,Company,Job URL\n"
             "\"=cmd|'/c calc'!A1\",Acme,https://www.upwork.com/jobs/~01000000000000f1f1\n").encode()
    hand_in(client, batch_id, token(client, "ali@example.com"), one, nasty)
    hand_in(client, batch_id, token(client, "sara@example.com"), two, sheet(range(7000, 7005)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    from io import BytesIO

    from openpyxl import load_workbook
    for profile_id, email in ((one, "ali@example.com"), (two, "sara@example.com")):
        response = client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet.xlsx",
                              headers=token(client, email))
        if response.status_code != 200:
            continue
        book = load_workbook(BytesIO(response.content))
        for page in book.worksheets:
            for row in page.iter_rows(min_row=2, values_only=True):
                for value in row:
                    assert not (isinstance(value, str)
                                and value.startswith(("=", "+", "@"))), value


def test_report_counts_only_its_own_cycle(client, admin, new_profile):
    one = new_profile("ali@example.com")
    two = new_profile("sara@example.com")

    first = open_cycle(client, admin, "Scoped A")
    hand_in(client, first, token(client, "ali@example.com"), one, sheet(range(8000, 8010)))
    hand_in(client, first, token(client, "sara@example.com"), two, sheet(range(8005, 8015)))
    computed = client.post(f"/api/batches/{first}/compute", headers=admin).json()
    before = client.get(f"/api/batches/{first}/report", headers=admin).json()

    later = open_cycle(client, admin, "Scoped B")
    hand_in(client, later, token(client, "ali@example.com"), one, sheet(range(8100, 8110)))
    hand_in(client, later, token(client, "sara@example.com"), two, sheet(range(8105, 8115)))
    client.post(f"/api/batches/{later}/compute", headers=admin)

    after = client.get(f"/api/batches/{first}/report", headers=admin).json()
    assert after["matrix"] == before["matrix"], "a later cycle changed an earlier report"
    assert after["matrix"]["rows"] == computed["matrix"]["rows"]


def test_bd_cannot_compute(client):
    headers = token(client, "ali@example.com")
    assert client.post("/api/batches", json={"name": "x"}, headers=headers).status_code == 403


def test_anonymous_is_blocked(client):
    assert client.get("/api/batches").status_code == 401



def test_one_skip_covers_every_profile_in_a_split_cycle(client, admin, new_profile):
    """Skipping for every profile you run has to work in a split cycle too.

    It did not. The extra rows were minted carrying the `exclusive` flag copied
    from the row being skipped, and in a split cycle that flag is what the
    partial unique index uses to hold "this job went to exactly one profile" —
    so the second row collided with the first, the request failed, and the BD's
    decision was simply lost.
    """
    one = new_profile("ali@example.com")
    two = new_profile("ali@example.com")          # same person, second name
    theirs = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, f"SplitSkip{next(_serial)}", mode="split")
    for pid, span in ((one, range(7100, 7120)), (two, range(7120, 7140))):
        hand_in(client, batch_id, token(client, "ali@example.com"), pid, sheet(span))
    hand_in(client, batch_id, token(client, "sara@example.com"), theirs,
            sheet(range(7140, 7160)))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    bd = token(client, "ali@example.com")
    rows = listing(client, batch_id, one, bd)
    assert rows
    done = client.patch(f"/api/assignments/{rows[0]['id']}",
                        json={"status": "skipped", "reason": "Rate is too low.",
                              "every_profile": True}, headers=bd)
    assert done.status_code == 200, done.text
    assert stored_status(batch_id, one, rows[0]["id"]) == "skipped"


# --------------------------------------------------------------------------- #
# Editing a cycle that is already running
#
# These used to be answerable only when the cycle was opened — the moment a
# manager knows least, because not one sheet is in yet. Getting the cap wrong
# meant closing the cycle and starting another, losing the work logged against
# it.
# --------------------------------------------------------------------------- #

def test_the_cap_can_be_raised_while_the_cycle_runs(client, admin, new_profile):
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    batch_id = open_cycle(client, admin, f"Editable{next(_serial)}", quota=5)
    hand_in(client, batch_id, token(client, "ali@example.com"), khuram, sheet(range(8000, 8030)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(8030, 8060)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    assert len(listing(client, batch_id, khuram, token(client, "ali@example.com"))) == 5

    saved = client.patch(f"/api/batches/{batch_id}", json={"quota": 25}, headers=admin)
    assert saved.status_code == 200, saved.text
    assert saved.json()["quota"] == 25

    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    assert len(listing(client, batch_id, khuram, token(client, "ali@example.com"))) == 25


def test_lowering_the_cap_never_takes_back_work_already_done(client, admin, new_profile):
    """The whole reason this is safe to hand a manager."""
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    bd = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, f"Shrink{next(_serial)}", quota=20)
    hand_in(client, batch_id, bd, khuram, sheet(range(8100, 8130)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(8130, 8160)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)

    rows = listing(client, batch_id, khuram, bd)
    assert len(rows) == 20
    for row in rows[:12]:
        assert client.patch(f"/api/assignments/{row['id']}", json={"status": "applied"},
                            headers=bd).status_code == 200

    assert client.patch(f"/api/batches/{batch_id}", json={"quota": 2},
                        headers=admin).status_code == 200
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)

    for row in rows[:12]:
        assert stored_status(batch_id, khuram, row["id"]) == "applied", \
            "a job already applied for must survive the cap being cut"


def test_a_patch_only_changes_what_it_names(client, admin):
    batch_id = open_cycle(client, admin, f"Narrow{next(_serial)}", mode="split",
                          quota=7, one_per_client=True)
    body = client.patch(f"/api/batches/{batch_id}", json={"quota": 9}, headers=admin).json()
    assert body["quota"] == 9
    assert body["mode"] == "split" and body["one_per_client"] is True


def test_a_closed_cycle_says_so_rather_than_changing(client, admin):
    batch_id = open_cycle(client, admin, f"Shut{next(_serial)}", quota=7)
    client.post(f"/api/batches/{batch_id}/close", headers=admin)
    refused = client.patch(f"/api/batches/{batch_id}", json={"quota": 9}, headers=admin)
    assert refused.status_code == 400
    assert "Reopen" in refused.json()["detail"]


def test_a_bd_cannot_change_the_cycle(client, admin):
    batch_id = open_cycle(client, admin, f"Locked{next(_serial)}", quota=7)
    refused = client.patch(f"/api/batches/{batch_id}", json={"quota": 900},
                           headers=token(client, "ali@example.com"))
    assert refused.status_code in (401, 403)


def test_a_nonsense_setting_is_refused(client, admin):
    batch_id = open_cycle(client, admin, f"Silly{next(_serial)}", quota=7)
    assert client.patch(f"/api/batches/{batch_id}", json={"mode": "sideways"},
                        headers=admin).status_code == 400
    assert client.patch(f"/api/batches/{batch_id}", json={"name": "   "},
                        headers=admin).status_code == 400
    assert client.patch(f"/api/batches/{batch_id}", json={"quota": 0},
                        headers=admin).json()["quota"] == 1



def test_a_rebuild_keeps_the_ids_the_bd_screen_is_holding(client, admin, new_profile):
    """Pressing Applied has to work on a list read a minute ago.

    The lists rebuild on a timer and the BD's screen re-reads them every sixty
    seconds, so for up to a minute after each rebuild the ids on screen are the
    ones from before it. Rebuilding used to delete every untouched assignment
    and insert it again, which on Postgres gives it a number the sequence has
    never issued before — so every one of those presses came back "No such job
    on your sheet" and the decision was lost. SQLite hands deleted rowids
    straight back out, which is why this has to be asserted on the rows rather
    than by watching a request fail here.
    """
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    bd = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, f"Stable{next(_serial)}", quota=10)
    hand_in(client, batch_id, bd, khuram, sheet(range(9000, 9020)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(9020, 9040)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)

    before = {row["id"]: row["url"] for row in listing(client, batch_id, khuram, bd)}
    assert before
    born = stored_born(before)
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)     # the timer's rebuild
    after = {row["id"]: row["url"] for row in listing(client, batch_id, khuram, bd)}

    assert after == before, "an untouched job kept on the list must keep its id"
    assert stored_born(before) == born,         "the row was destroyed and minted again — on Postgres that is a new id"

    # ...and the press that was aimed at the old list still lands.
    stale = next(iter(before))
    got = client.patch(f"/api/assignments/{stale}", json={"status": "applied"}, headers=bd)
    assert got.status_code == 200, got.text
    assert stored_status(batch_id, khuram, stale) == "applied"


def test_a_job_that_leaves_the_list_still_goes(client, admin, new_profile):
    """Keeping ids must not turn into keeping jobs the cap has pushed out."""
    khuram = new_profile("ali@example.com")
    zahid = new_profile("sara@example.com")
    bd = token(client, "ali@example.com")
    batch_id = open_cycle(client, admin, f"Trim{next(_serial)}", quota=20)
    hand_in(client, batch_id, bd, khuram, sheet(range(9100, 9140)))
    hand_in(client, batch_id, token(client, "sara@example.com"), zahid, sheet(range(9140, 9180)))
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    assert len(listing(client, batch_id, khuram, bd)) == 20

    client.patch(f"/api/batches/{batch_id}", json={"quota": 6}, headers=admin)
    client.post(f"/api/batches/{batch_id}/compute", headers=admin)
    assert len(listing(client, batch_id, khuram, bd)) == 6
