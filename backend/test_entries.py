"""The rules added around logging a job: duplicates, skips, and corrections.

Four behaviours, and each is a rule the server holds rather than a nicety the
browser offers — so each is tested by asking the API directly, the way anything
else that talks to it would.

  * a job link is checked against the whole history before it is saved
  * a skip has to say why
  * a correction to a posting reaches everyone holding it, and only the person
    who first logged it may make one
  * withdrawing an entry takes back one profile's application and no one else's
"""
from __future__ import annotations

import io
import itertools

import pytest
from fastapi.testclient import TestClient

PASSWORD = "entrypass12345"
TEAM = [("entry-boss@entries.example.com", "Entry Boss", "admin"),
        ("entry-one@entries.example.com", "Ada One", "bd"),
        ("entry-two@entries.example.com", "Bo Two", "bd")]

_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/entries.db")
    from app.main import SessionLocal, app, engine, hash_password  # noqa: E402
    from app.models import Base, User  # noqa: E402

    Base.metadata.create_all(engine)
    db = SessionLocal()
    for email, name, role in TEAM:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, name=name, role=role,
                        password_hash=hash_password(PASSWORD)))
    db.commit()
    db.close()
    return TestClient(app)


def token(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return token(client, TEAM[0][0])


@pytest.fixture
def make_profile(client, admin):
    def build(owner_email, headline="Accounts Receivable"):
        people = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
        response = client.post("/api/profiles", headers=admin, json={
            "name": f"Entry {next(_serial)}", "headline": headline,
            "platform": "Indeed", "user_id": people[owner_email]})
        assert response.status_code == 201, response.text
        return response.json()["id"]
    return build


def open_cycle(client, admin, name="Entries"):
    response = client.post("/api/batches", headers=admin,
                           json={"name": f"{name} {next(_serial)}", "quota": 500,
                                 "mode": "cover"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def link(n: int) -> str:
    return f"https://www.upwork.com/jobs/~01{n:016x}"


def type_in(client, headers, batch_id, profile_id, numbers):
    rows = [{"url": link(n), "title": f"Role {n}", "company": f"Client {n}",
             "platform": "Indeed", "date": "2026-08-01 09:00"} for n in numbers]
    response = client.put(f"/api/batches/{batch_id}/profiles/{profile_id}/entries",
                          headers=headers, json={"rows": rows})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# The duplicate check
# --------------------------------------------------------------------------- #

def test_a_link_nobody_has_used_is_not_a_duplicate(client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    body = client.get("/api/jobs/check", headers=admin,
                      params={"url": link(910001), "profile_id": profile}).json()
    assert body["duplicate"] is False
    assert body["mine"] is None and body["others"] == []
    # Still fingerprinted, so the caller can tell "not seen" from "unusable".
    assert body["fingerprint"]


def test_a_link_this_profile_already_used_comes_back_with_its_date(
        client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    batch = open_cycle(client, admin)
    bd = token(client, TEAM[1][0])
    type_in(client, bd, batch, profile, [910100])

    # A second profile so the cycle has something to compare against.
    other = make_profile(TEAM[2][0])
    type_in(client, token(client, TEAM[2][0]), batch, other, [910200, 910201])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    body = client.get("/api/jobs/check", headers=bd,
                      params={"url": link(910100), "profile_id": profile}).json()
    assert body["duplicate"] is True
    assert body["mine"]["profile_id"] == profile
    # The date is the whole point of the warning: "you did this, and when".
    assert body["mine"]["applied_on"].startswith("2026-08-01")


def test_a_colleague_having_applied_is_reported_but_is_not_a_duplicate(
        client, admin, make_profile):
    """Two profiles on one posting is the product working, not a mistake."""
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, token(client, TEAM[1][0]), batch, mine, [910300])
    type_in(client, token(client, TEAM[2][0]), batch, theirs, [910300, 910301])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    body = client.get("/api/jobs/check", headers=admin,
                      params={"url": link(910300), "profile_id": theirs}).json()
    assert body["duplicate"] is True                       # theirs did apply
    others = {o["profile_id"] for o in body["others"]}
    assert mine in others

    # Asked about a profile that has *not* applied, the same job is only ever
    # somebody else's — reported, but not a duplicate.
    fresh = make_profile(TEAM[1][0])
    body = client.get("/api/jobs/check", headers=admin,
                      params={"url": link(910300), "profile_id": fresh}).json()
    assert body["duplicate"] is False
    assert {o["profile_id"] for o in body["others"]} >= {mine, theirs}


def test_the_same_job_through_a_tracking_link_is_still_recognised(
        client, admin, make_profile):
    """Matched on the fingerprint, so a referral parameter changes nothing."""
    profile = make_profile(TEAM[1][0])
    other = make_profile(TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, token(client, TEAM[1][0]), batch, profile, [910400])
    type_in(client, token(client, TEAM[2][0]), batch, other, [910401, 910402])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    dressed_up = link(910400) + "?utm_source=newsletter&ref=abc123"
    body = client.get("/api/jobs/check", headers=admin,
                      params={"url": dressed_up, "profile_id": profile}).json()
    assert body["duplicate"] is True


# --------------------------------------------------------------------------- #
# A skip has to say why
# --------------------------------------------------------------------------- #

def dispatched(client, headers, batch_id, profile_id):
    body = client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet",
                      headers=headers).json()
    return body["jobs"]


@pytest.fixture
def a_dispatched_job(client, admin, make_profile):
    """One profile with a job on its list that it did not find itself."""
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    batch = open_cycle(client, admin)
    base = next(_serial) * 1000 + 920000
    type_in(client, token(client, TEAM[1][0]), batch, mine, [base])
    type_in(client, token(client, TEAM[2][0]), batch, theirs, [base + 1, base + 2])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200
    jobs = dispatched(client, token(client, TEAM[1][0]), batch, mine)
    assert jobs, "the cover cycle should hand this profile what the other one found"
    return {"batch": batch, "profile": mine, "job": jobs[0]}


def test_skipping_without_a_reason_is_refused(client, a_dispatched_job):
    bd = token(client, TEAM[1][0])
    response = client.patch(f"/api/assignments/{a_dispatched_job['job']['id']}",
                            headers=bd, json={"status": "skipped"})
    assert response.status_code == 400
    assert "why" in response.json()["detail"].lower()

    # Whitespace is not a reason either.
    assert client.patch(f"/api/assignments/{a_dispatched_job['job']['id']}",
                        headers=bd, json={"status": "skipped",
                                          "reason": "   "}).status_code == 400


def test_a_skip_keeps_the_reason_and_the_manager_can_read_it(client, admin, a_dispatched_job):
    bd = token(client, TEAM[1][0])
    response = client.patch(f"/api/assignments/{a_dispatched_job['job']['id']}",
                            headers=bd, json={"status": "skipped",
                                              "reason": "On-site only, and we are remote."})
    assert response.status_code == 200
    assert response.json()["skip_reason"] == "On-site only, and we are remote."

    report = client.get(f"/api/batches/{a_dispatched_job['batch']}/report",
                        headers=admin).json()
    reasons = [row["reason"] for row in report["turned_down"]]
    assert "On-site only, and we are remote." in reasons


def test_taking_a_skip_back_clears_the_reason(client, a_dispatched_job):
    """A job returned to the list must not keep an explanation for leaving it."""
    bd = token(client, TEAM[1][0])
    assignment = a_dispatched_job["job"]["id"]
    client.patch(f"/api/assignments/{assignment}", headers=bd,
                 json={"status": "skipped", "reason": "Rate is far too low."})
    response = client.patch(f"/api/assignments/{assignment}", headers=bd,
                            json={"status": "pending"})
    assert response.status_code == 200
    assert response.json()["skip_reason"] == ""


def test_applying_needs_no_reason(client, a_dispatched_job):
    bd = token(client, TEAM[1][0])
    assert client.patch(f"/api/assignments/{a_dispatched_job['job']['id']}",
                        headers=bd, json={"status": "applied"}).status_code == 200


# --------------------------------------------------------------------------- #
# Correcting a posting, and withdrawing an entry
# --------------------------------------------------------------------------- #

@pytest.fixture
def a_shared_job(client, admin, make_profile):
    """One posting that Ada found and Bo was handed.

    The distinction the edit rule turns on. Ada typed it onto her own sheet, so
    it is hers to correct. Bo never went looking for it — the cover cycle put it
    on his list because Ada had found it — and marking it applied puts it in his
    record without making it his to rewrite.
    """
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    batch = open_cycle(client, admin)
    base = next(_serial) * 1000 + 930000
    type_in(client, token(client, TEAM[1][0]), batch, mine, [base])
    type_in(client, token(client, TEAM[2][0]), batch, theirs, [base + 1, base + 2])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    bo = token(client, TEAM[2][0])
    handed = [job for job in dispatched(client, bo, batch, theirs)
              if job["url"] == link(base)]
    assert handed, "the cover cycle should hand Ada's find to Bo"
    assert client.patch(f"/api/assignments/{handed[0]['id']}", headers=bo,
                        json={"status": "applied"}).status_code == 200

    record = client.get("/api/jobs", headers=admin, params={"q": f"Role {base}"}).json()
    assert record["rows"], "the job should be in the all-time record"
    return {"batch": batch, "mine": mine, "theirs": theirs,
            "job_id": record["rows"][0]["job_id"], "base": base}


def test_being_handed_a_job_does_not_make_it_yours_to_correct(client, a_shared_job):
    """Bo applied to it and holds it, but Ada is the one who found it."""
    bo = token(client, TEAM[2][0])
    response = client.patch(f"/api/jobs/{a_shared_job['job_id']}", headers=bo,
                            json={"title": "Something else entirely"})
    assert response.status_code == 403
    assert "logged yourself" in response.json()["detail"]


def test_both_people_who_typed_a_posting_in_may_correct_it(client, admin, make_profile):
    """Two BDs who find the same job on the same day both found it.

    Picking one of them by insert order would hand somebody the pen for a
    reason neither could explain.
    """
    ada, bo = make_profile(TEAM[1][0]), make_profile(TEAM[2][0])
    batch = open_cycle(client, admin)
    base = next(_serial) * 1000 + 935000
    type_in(client, token(client, TEAM[1][0]), batch, ada, [base])
    type_in(client, token(client, TEAM[2][0]), batch, bo, [base, base + 1])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    job_id = client.get("/api/jobs", headers=admin,
                        params={"q": f"Role {base}"}).json()["rows"][0]["job_id"]
    assert client.patch(f"/api/jobs/{job_id}", headers=token(client, TEAM[1][0]),
                        json={"platform": "Monster"}).status_code == 200
    assert client.patch(f"/api/jobs/{job_id}", headers=token(client, TEAM[2][0]),
                        json={"platform": "Dice"}).status_code == 200


def test_a_correction_reaches_every_profile_holding_the_posting(client, admin, a_shared_job):
    owner = token(client, TEAM[1][0])
    response = client.patch(f"/api/jobs/{a_shared_job['job_id']}", headers=owner,
                            json={"title": "Senior AR Specialist", "company": "Northwind"})
    assert response.status_code == 200, response.text

    # There is one job row, so the other profile's record shows the new wording
    # without anything being copied anywhere.
    record = client.get("/api/jobs", headers=admin,
                        params={"q": "Senior AR Specialist"}).json()
    holders = {row["profile_id"] for row in record["rows"]}
    assert holders >= {a_shared_job["mine"], a_shared_job["theirs"]}
    assert all(row["title"] == "Senior AR Specialist" for row in record["rows"])


def test_a_manager_may_correct_anybody_s_job(client, admin, a_shared_job):
    assert client.patch(f"/api/jobs/{a_shared_job['job_id']}", headers=admin,
                        json={"platform": "LinkedIn"}).status_code == 200


def test_a_correction_that_would_merge_two_postings_is_refused(client, admin, a_shared_job):
    """Pointing one job at another's link would silently fuse two histories."""
    owner = token(client, TEAM[1][0])
    other = client.get("/api/jobs", headers=admin,
                       params={"q": f"Role {a_shared_job['base'] + 1}"}).json()["rows"][0]
    assert other["url"], "Bo's own job, recorded separately"
    response = client.patch(f"/api/jobs/{a_shared_job['job_id']}", headers=owner,
                            json={"url": other["url"]})
    assert response.status_code == 409
    assert "already recorded separately" in response.json()["detail"]


def test_withdrawing_takes_back_one_profile_s_entry_and_no_one_else_s(
        client, admin, a_shared_job):
    owner = token(client, TEAM[1][0])
    response = client.delete(
        f"/api/jobs/{a_shared_job['job_id']}/profiles/{a_shared_job['mine']}",
        headers=owner)
    assert response.status_code == 200

    record = client.get("/api/jobs", headers=admin,
                        params={"q": f"Role {a_shared_job['base']}"}).json()
    holders = {row["profile_id"] for row in record["rows"]}
    assert a_shared_job["mine"] not in holders
    assert a_shared_job["theirs"] in holders, "the colleague keeps their own record"


def test_you_cannot_withdraw_somebody_else_s_entry(client, a_shared_job):
    stranger = token(client, TEAM[2][0])
    response = client.delete(
        f"/api/jobs/{a_shared_job['job_id']}/profiles/{a_shared_job['mine']}",
        headers=stranger)
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Handed-in counts mean the same thing everywhere
# --------------------------------------------------------------------------- #

def test_a_sheet_reports_how_many_rows_are_usable_not_how_many_lines_it_had(
        client, admin, make_profile):
    """The figure the manager reads has to be the figure the cycle acts on."""
    profile = make_profile(TEAM[1][0])
    batch = open_cycle(client, admin)
    bd = token(client, TEAM[1][0])

    # Three real jobs and two rows carrying nothing the matcher can use.
    rows = [{"url": link(940000 + n), "title": f"Role {n}", "company": f"Client {n}",
             "platform": "Indeed", "date": "2026-08-02 09:00"} for n in range(3)]
    rows += [{"url": "", "title": "", "company": "", "platform": "Indeed",
              "date": "2026-08-02 09:00"} for _ in range(2)]
    body = client.put(f"/api/batches/{batch}/profiles/{profile}/entries",
                      headers=bd, json={"rows": rows}).json()

    assert body["usable_count"] == 3
    assert body["row_count"] == 3, "blank rows are not stored as though they were work"

    listed = client.get(f"/api/batches/{batch}/profiles/{profile}/entries",
                        headers=bd).json()
    assert listed["usable_count"] == 3


def test_an_uploaded_sheet_separates_its_line_count_from_its_usable_count(
        client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    batch = open_cycle(client, admin)
    bd = token(client, TEAM[1][0])

    csv = "Job link,Job title,Company,Platform,Applied on\n"
    csv += "".join(f"{link(950000 + n)},Role {n},Client {n},Indeed,2026-08-03\n"
                   for n in range(4))
    csv += ",,,Indeed,2026-08-03\n" * 3          # three rows that identify nothing

    response = client.post(f"/api/batches/{batch}/uploads", headers=bd,
                           data={"profile_id": profile},
                           files={"file": ("sheet.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["row_count"] == 7, "the file really did have seven rows"
    assert body["usable_count"] == 4, "only four of them are a job"
