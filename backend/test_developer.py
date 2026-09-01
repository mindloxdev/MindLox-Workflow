"""The developer behind a profile, and what the applications turned into.

    pytest test_developer.py -v

A profile is an identity a client is sold. Behind it are two people who are not
the same person: the BD who runs the account and does the applying, and the
developer who sits the interview and writes the code. Everything here is about
keeping those two straight.

What is pinned down:

  * a developer sees the identities they are sold under and nothing else, and
    cannot work a list or hand in a sheet under any of them;
  * they keep their own resume, address and availability current, and cannot
    rename the identity or hand it to somebody else;
  * a time typed on the team's clock is the same time everybody reads back,
    whatever timezone the machine running this is set to;
  * one developer sold under two identities cannot be quietly double-booked;
  * an outcome is what moves the funnel, and a cancelled interview never counts
    as a rejection.

Shares a database with the rest of the suite — pytest imports app.main once, so
whichever module runs first decides where the data lives. Nothing here asserts
on a workspace-wide total it did not create, and every account and profile it
makes carries a name no other module uses.
"""
import datetime as dt
import io
import itertools

import pytest
from fastapi.testclient import TestClient

TEAM = [("dv-boss@developer.example.com", "Dev Boss", "admin"),
        ("dv-bd@developer.example.com", "Bea Dee", "bd"),
        ("dv-other@developer.example.com", "Otto Other", "bd"),
        ("dv-one@developer.example.com", "Dev One", "dev"),
        ("dv-two@developer.example.com", "Dev Two", "dev")]

PASSWORD = "devpass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/dev.db")
    from app.main import SessionLocal, app, engine, hash_password  # noqa: E402
    from app.models import Base, User  # noqa: E402

    Base.metadata.create_all(engine)
    db = SessionLocal()
    for email, name, role in TEAM:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, name=name, dashboard_visible=True,
                        password_hash=hash_password(PASSWORD), role=role))
    db.commit()
    db.close()
    return TestClient(app)


def token(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return token(client, "dv-boss@developer.example.com")


@pytest.fixture(scope="module")
def bd(client):
    return token(client, "dv-bd@developer.example.com")


@pytest.fixture(scope="module")
def other_bd(client):
    return token(client, "dv-other@developer.example.com")


@pytest.fixture(scope="module")
def one(client):
    return token(client, "dv-one@developer.example.com")


@pytest.fixture(scope="module")
def two(client):
    return token(client, "dv-two@developer.example.com")


@pytest.fixture
def people(client, admin):
    return {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}


@pytest.fixture
def make_profile(client, admin, people):
    """A profile no other test has touched, with a named BD and developer."""
    def make(bd_email="dv-bd@developer.example.com",
             dev_email="dv-one@developer.example.com", **extra):
        # "Behind", because that is what a developer is to a profile — and
        # because no other module in this suite mints a name starting with it.
        body = {"name": f"Behind{next(_serial)}", "headline": "AI Engineer",
                "platform": "Upwork", "user_id": people[bd_email],
                "dev_user_id": people[dev_email] if dev_email else None}
        body.update(extra)
        response = client.post("/api/profiles", json=body, headers=admin)
        assert response.status_code == 201, response.text
        return response.json()
    return make


def when(days: int, clock: str) -> str:
    """A datetime-local string, that many days from the team's today.

    Built from the team's calendar rather than the machine's, so a test does
    not fall on the wrong side of midnight when the suite runs from a timezone
    a long way east of New York.
    """
    from app.models import working_today
    return f"{(working_today() + dt.timedelta(days=days)).isoformat()}T{clock}"


def book(web, headers, profile_id, days=1, clock="14:00", **extra):
    """Log an interview. The test client is `web` here, not `client`, so that
    `client="Northwind"` stays available as what it means everywhere else in
    this app — the company on the other end of the call."""
    body = {"profile_id": profile_id, "scheduled_at": when(days, clock),
            "client": "Northwind Digital", "role": "RAG Developer"}
    body.update(extra)
    response = web.post("/api/interviews", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def sheet(job_ids):
    out = io.StringIO()
    out.write("Job Title,Company,Job URL\n")
    for n in job_ids:
        out.write(f"Role {n},Client {n % 5} Ltd,https://www.upwork.com/jobs/~02{n:016x}\n")
    return out.getvalue().encode()


# --------------------------------------------------------------------------- #
# Who sees what
# --------------------------------------------------------------------------- #

def test_a_developer_sees_the_identities_they_are_sold_under(client, one, make_profile):
    """And nobody else's. A BD's /profiles answers "what do I run"; a
    developer's answers "what am I", and they are different questions."""
    mine = make_profile(dev_email="dv-one@developer.example.com")
    theirs = make_profile(dev_email="dv-two@developer.example.com")

    names = {p["name"] for p in client.get("/api/profiles", headers=one).json()}
    assert mine["name"] in names
    assert theirs["name"] not in names


def test_a_developer_cannot_work_a_list_under_their_own_identity(client, one, admin,
                                                                 make_profile):
    """The wider door is for the interview and the resume, not for the work.

    Letting a developer mark jobs applied would put work into a BD's record
    that the BD did not do — and worse, retire a job from the rotation on the
    strength of somebody who never applied for it.
    """
    profile = make_profile()
    cycle = client.post("/api/batches",
                        json={"name": f"DevCycle{next(_serial)}", "mode": "cover",
                              "quota": 100, "auto_build_minutes": 0},
                        headers=admin).json()["id"]

    refused = client.post(f"/api/batches/{cycle}/uploads",
                          data={"profile_id": profile["id"]},
                          files={"file": ("s.csv", sheet(range(3)), "text/csv")},
                          headers=one)
    assert refused.status_code == 403
    assert "someone else" in refused.json()["detail"]


def test_a_profile_requires_a_bd_assignment(client, admin):
    """Managers can give a profile to any developer, but a BD must still own it."""
    response = client.post("/api/profiles",
                           json={"name": "NoOwner", "headline": "AI Engineer"},
                           headers=admin)
    assert response.status_code == 400
    assert "BD" in response.json()["detail"]


def test_a_bd_can_assign_a_profile_to_a_selected_dev(client, admin, bd, make_profile):
    """When a profile has no developer yet, the BD may pick one on the booking form."""
    profile = make_profile(dev_email=None)
    developers = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()
                  if u["role"] == "dev"}
    chosen = developers["dv-one@developer.example.com"]

    interview = client.post("/api/interviews",
                            json={"profile_id": profile["id"],
                                  "scheduled_at": when(0, "17:00"),
                                  "client": "Northwind Digital",
                                  "role": "RAG Developer",
                                  "dev_user_id": chosen},
                            headers=bd)
    assert interview.status_code == 201, interview.text
    assert interview.json()["developer_id"] == chosen

    updated = client.get(f"/api/profiles/{profile['id']}", headers=bd).json()
    assert updated["dev_user_id"] == chosen

    assessment = client.post("/api/assessments",
                             json={"profile_id": profile["id"],
                                   "title": "Take-home · RAG",
                                   "dev_user_id": chosen},
                             headers=bd)
    assert assessment.status_code == 201, assessment.text
    assert assessment.json()["developer_id"] == chosen


def test_a_stranger_cannot_reach_the_diary(client, other_bd, bd, make_profile):
    """A BD who runs neither the profile nor anybody on it gets nothing."""
    profile = make_profile()
    booked = book(client, bd, profile["id"])

    refused = client.get(f"/api/interviews?profile_id={profile['id']}", headers=other_bd)
    assert refused.status_code == 403

    moved = client.patch(f"/api/interviews/{booked['id']}",
                         json={"status": "cancelled"}, headers=other_bd)
    assert moved.status_code == 403

    # And it is absent from their own diary, not merely unreachable by id.
    theirs = client.get("/api/interviews", headers=other_bd).json()
    assert booked["id"] not in {row["id"] for row in theirs["rows"]}


# --------------------------------------------------------------------------- #
# Booking
# --------------------------------------------------------------------------- #

def test_the_bd_books_it_and_the_developer_sees_it_today(client, bd, one, make_profile):
    """Nothing is emailed and nobody is told. It is simply on their screen."""
    profile = make_profile()
    book(client, bd, profile["id"], days=0, clock="15:00", client="Sable Analytics")

    desk = client.get("/api/dashboard/dev", headers=one).json()
    today = [row for row in desk["today"] if row["profile"] == profile["name"]]
    assert len(today) == 1
    assert today[0]["client"] == "Sable Analytics"
    assert today[0]["is_today"] is True
    assert desk["counts"]["today"] >= 1


def test_the_time_typed_is_the_time_read_back(client, bd, make_profile):
    """Half past two means half past two in New York, wherever you typed it.

    The clock is the one thing on this feature that cannot be approximately
    right: two people reading one row as two different hours is a missed
    interview, and nobody finds out until the client says so.
    """
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=3, clock="14:30")
    assert booked["when"]["time"] == "14:30"
    assert booked["when"]["input"].endswith("T14:30")
    assert booked["when"]["day"] == when(3, "14:30")[:10]

    # And it survives the round trip an edit form makes it do.
    again = client.patch(f"/api/interviews/{booked['id']}",
                         json={"scheduled_at": booked["when"]["input"]}, headers=bd)
    assert again.status_code == 200, again.text
    assert again.json()["when"]["time"] == "14:30"


def test_one_developer_under_two_identities_cannot_be_quietly_double_booked(
        client, bd, admin, people, make_profile):
    """Two profiles are two candidates to a client. They are one person's
    Tuesday afternoon, and that is where the double-booking hides."""
    first = make_profile(dev_email="dv-two@developer.example.com")
    second = make_profile(dev_email="dv-two@developer.example.com")

    book(client, bd, first["id"], days=5, clock="11:00", duration_minutes=60)
    overlapping = book(client, bd, second["id"], days=5, clock="11:30")

    assert overlapping["clash"] is not None
    assert overlapping["clash"]["profile"] == first["name"]
    # Reported, never refused — a reschedule legitimately overlaps the slot it
    # is moving out of, and an app that argues gets worked around.
    assert overlapping["id"] > 0


def test_two_profiles_with_different_developers_do_not_clash(client, bd, make_profile):
    """Two different people are free to be busy at the same time."""
    first = make_profile(dev_email="dv-one@developer.example.com")
    second = make_profile(dev_email="dv-two@developer.example.com")

    book(client, bd, first["id"], days=6, clock="09:00", duration_minutes=60)
    fine = book(client, bd, second["id"], days=6, clock="09:15")
    assert fine["clash"] is None


# --------------------------------------------------------------------------- #
# The developer's own details
# --------------------------------------------------------------------------- #

def test_a_developer_keeps_their_own_details_current(client, one, make_profile):
    """Which resume goes out, which address a client replies to, whether they
    can start next week. Routing that through a manager is how it goes stale."""
    profile = make_profile()
    response = client.patch(f"/api/profiles/{profile['id']}", headers=one, json={
        "email": "dev.one@example.com",
        "resume_url": "https://example.com/cv/one.pdf",
        "skills": "Python, RAG, AWS",
        "availability": "booked",
        "rate": "$50/hr",
    })
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["email"] == "dev.one@example.com"
    assert saved["availability"] == "booked"
    assert saved["skills"] == "Python, RAG, AWS"


def test_a_developer_cannot_rename_the_identity_or_hand_it_on(client, one, people,
                                                              make_profile):
    """The name and the owner decide what other people see, so they stay with
    the manager. The refusal says which field, because a 403 with no subject is
    just a wall."""
    profile = make_profile()

    renamed = client.patch(f"/api/profiles/{profile['id']}",
                           json={"name": "Something Else"}, headers=one)
    assert renamed.status_code == 403
    assert "name" in renamed.json()["detail"]

    handed = client.patch(f"/api/profiles/{profile['id']}",
                          json={"user_id": people["dv-other@developer.example.com"]},
                          headers=one)
    assert handed.status_code == 403


def test_a_developer_cannot_edit_an_identity_that_is_not_theirs(client, two,
                                                                make_profile):
    profile = make_profile(dev_email="dv-one@developer.example.com")
    refused = client.patch(f"/api/profiles/{profile['id']}",
                           json={"email": "hijack@example.com"}, headers=two)
    assert refused.status_code == 403


def test_a_resume_link_has_to_be_a_link(client, one, make_profile):
    """It ends up in an href on a colleague's screen."""
    profile = make_profile()
    refused = client.patch(f"/api/profiles/{profile['id']}",
                           json={"resume_url": "javascript:alert(1)"}, headers=one)
    assert refused.status_code == 400
    assert "http" in refused.json()["detail"]


# --------------------------------------------------------------------------- #
# Outcomes, and the funnel
# --------------------------------------------------------------------------- #

def test_an_outcome_closes_the_interview_and_moves_the_funnel(client, bd, one,
                                                              make_profile):
    """Nobody records how an interview went before it happens, so saying it was
    an offer is also saying it happened."""
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=2, clock="10:00")
    assert booked["status"] == "scheduled"

    before = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert before["funnel"]["offers"] == 0

    saved = client.patch(f"/api/interviews/{booked['id']}",
                         json={"outcome": "offer"}, headers=one).json()
    assert saved["status"] == "done"
    assert saved["outcome"] == "offer"

    after = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert after["funnel"]["offers"] == 1
    assert after["funnel"]["passed"] == 1        # an offer cleared the round too
    assert after["funnel"]["hired"] == 0


# --------------------------------------------------------------------------- #
# Who books, and who reports back
# --------------------------------------------------------------------------- #

def test_either_side_of_a_profile_may_book(client, bd, one, make_profile):
    """The BD runs the account most replies arrive at; the developer is who a
    client that found them directly will email. Both find out first often
    enough that the one who knows should not have to ask somebody else."""
    profile = make_profile()
    theirs = book(client, one, profile["id"], days=1, clock="10:00")
    assert theirs["status"] == "scheduled"

    ours = book(client, bd, profile["id"], days=1, clock="13:00")
    assert ours["status"] == "scheduled"

    # And each side sees what the other logged, on the same row.
    seen = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert {row["id"] for row in seen["upcoming"]} >= {theirs["id"], ours["id"]}


def test_one_reply_logged_twice_is_caught_rather_than_forbidden(client, bd, one,
                                                                make_profile):
    """What stops a reply becoming two rows is the clash check, not a
    permission — and it reports rather than refuses, because a reschedule
    legitimately overlaps the slot it is leaving."""
    profile = make_profile()
    first = book(client, bd, profile["id"], days=5, clock="11:00", duration_minutes=60)
    again = book(client, one, profile["id"], days=5, clock="11:30")

    assert again["clash"] is not None
    assert again["clash"]["id"] == first["id"]
    assert again["clash"]["profile"] == profile["name"]


def test_a_developer_may_move_what_they_are_sitting(client, bd, one, make_profile):
    """Both sides own the whole row now. The two prose fields stay split by who
    can answer them, which is a division of labour rather than a permission."""
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=3, clock="11:00")

    moved = client.patch(f"/api/interviews/{booked['id']}",
                         json={"scheduled_at": when(4, "16:00")}, headers=one)
    assert moved.status_code == 200, moved.text
    assert moved.json()["when"]["time"] == "16:00"


def test_the_developer_reports_back_and_the_bd_reads_it(client, bd, one, make_profile):
    """The half of the row the developer owns. They were in the room; nobody
    else can answer it first-hand, and the BD holds the record."""
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=-1, clock="09:00",
                  notes="Wants to hear about the RAG project.")

    saved = client.patch(f"/api/interviews/{booked['id']}",
                         json={"outcome": "passed",
                               "debrief": "Went well. They are sending a take-home."},
                         headers=one)
    assert saved.status_code == 200, saved.text

    row = client.get(f"/api/interviews?profile_id={profile['id']}",
                     headers=bd).json()["recent"][0]
    assert row["debrief"] == "Went well. They are sending a take-home."
    assert row["reported_by"] == "Dev One"       # whose word it is
    assert row["reported_at"]                    # and how fresh
    assert row["awaiting_outcome"] is False
    # The BD's brief is a different field and survives the debrief written over
    # the top of it — there is no other copy of it anywhere.
    assert row["notes"] == "Wants to hear about the RAG project."


def test_a_developer_reports_only_on_the_identities_they_are_sold_under(
        client, bd, two, make_profile):
    """Somebody else's diary is refused on the server, not merely absent from
    the screen."""
    profile = make_profile(dev_email="dv-one@developer.example.com")
    booked = book(client, bd, profile["id"], days=-1, clock="15:00")
    refused = client.patch(f"/api/interviews/{booked['id']}",
                           json={"outcome": "offer"}, headers=two)
    assert refused.status_code == 403


def test_a_developer_opens_one_identity_at_a_time(client, bd, one, make_profile):
    """A developer may be sold under several profiles, and the question they
    ask is usually about one of them: what has Khuram got today."""
    first = make_profile()
    second = make_profile()
    book(client, bd, first["id"], days=0, clock="09:15", client="Sable Analytics")
    book(client, bd, second["id"], days=0, clock="16:15", client="Verdant Labs")

    just_one = client.get(f"/api/interviews?profile_id={first['id']}", headers=one).json()
    assert [row["client"] for row in just_one["today"]] == ["Sable Analytics"]

    both = client.get("/api/interviews", headers=one).json()
    clients = {row["client"] for row in both["today"]}
    assert {"Sable Analytics", "Verdant Labs"} <= clients


def test_a_cancelled_interview_is_not_a_rejection(client, bd, make_profile):
    """A client who pulled out before the call did not turn anybody down, and
    counting it as a rejection makes a quiet week look like a bad one."""
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=4, clock="12:00")
    client.patch(f"/api/interviews/{booked['id']}", json={"status": "cancelled"},
                 headers=bd)

    figures = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert figures["funnel"]["interviews"] == 0
    assert figures["funnel"]["rejected"] == 0
    assert figures["funnel"]["cancelled"] == 1


def test_an_interview_that_has_been_and_gone_counts_as_unreported(client, bd,
                                                                  make_profile):
    """The number worth putting on a screen: it happened, and nobody has said
    how. Every rate is understated until somebody does."""
    profile = make_profile()
    book(client, bd, profile["id"], days=-2, clock="11:00")

    figures = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert figures["counts"]["awaiting_outcome"] == 1
    assert figures["recent"][0]["awaiting_outcome"] is True
    assert figures["recent"][0]["is_past"] is True


def test_a_cancellation_ahead_is_shown_rather_than_hidden(client, bd, make_profile):
    """It stays in the list, greyed, because a slot that vanished silently is
    the same to a reader as a slot that was never booked."""
    profile = make_profile()
    booked = book(client, bd, profile["id"], days=7, clock="13:00")
    client.patch(f"/api/interviews/{booked['id']}", json={"status": "cancelled"},
                 headers=bd)

    figures = client.get(f"/api/interviews?profile_id={profile['id']}", headers=bd).json()
    assert booked["id"] in {row["id"] for row in figures["upcoming"]}
    assert figures["counts"]["scheduled"] == 0


# --------------------------------------------------------------------------- #
# The manager
# --------------------------------------------------------------------------- #

def test_the_manager_sees_a_developers_screen_as_they_see_it(client, admin, bd,
                                                             people, make_profile):
    profile = make_profile(dev_email="dv-one@developer.example.com")
    book(client, bd, profile["id"], days=0, clock="16:45", client="Verdant Labs")

    seen = client.get(f"/api/dashboard/devs/{people['dv-one@developer.example.com']}",
                      headers=admin)
    assert seen.status_code == 200, seen.text
    payload = seen.json()
    assert payload["developer"]["name"] == "Dev One"
    assert any(row["client"] == "Verdant Labs" for row in payload["today"])


def test_the_manager_sees_who_is_free(client, admin, one, make_profile):
    """One developer, two identities, and the busier answer wins — a BD needs
    the harder truth, not the more convenient one."""
    profile = make_profile(dev_email="dv-one@developer.example.com")
    client.patch(f"/api/profiles/{profile['id']}", json={"availability": "booked"},
                 headers=one)

    overview = client.get("/api/dashboard/overview", headers=admin).json()
    rows = {row["name"]: row for row in overview["developers"]}
    assert "Dev One" in rows
    assert rows["Dev One"]["availability"] == "booked"
    assert rows["Dev One"]["runs"] >= 1


def test_a_bd_cannot_open_the_developer_screen(client, bd):
    refused = client.get("/api/dashboard/dev", headers=bd)
    assert refused.status_code == 403


def test_a_developer_needs_no_switch_thrown_to_see_their_own_desk(client, admin,
                                                                  people):
    """The dashboard switch exists so nobody is measured without somebody
    deciding to measure them. A calendar is not a measurement, and withholding
    it only means nobody turns up."""
    shut = client.patch(f"/api/users/{people['dv-one@developer.example.com']}",
                        json={"dashboard_visible": False}, headers=admin)
    assert shut.status_code == 200

    desk = client.get("/api/dashboard/dev", headers=token(client, "dv-one@developer.example.com"))
    assert desk.status_code == 200
    assert desk.json()["profiles"]


def test_a_developer_with_nobody_behind_it_is_still_bookable(client, bd, make_profile):
    """The interview is real whether or not the workspace has caught up with
    who is sitting it. Refusing would lose the appointment to a data-entry gap.
    """
    profile = make_profile(dev_email=None)
    booked = book(client, bd, profile["id"], days=1, clock="09:30")
    assert booked["developer"] is None
    assert booked["clash"] is None
