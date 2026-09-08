"""The record, the ladder, and the work that comes out of a conversation.

    pytest test_pipeline.py -v

What is pinned down here:

  * every job a profile ever applied to stays findable, all-time and by search,
    because a client's reply arrives long after the cycle that earned it closed;
  * an interview can be started from that record with no time agreed — a draft —
    and counts towards nothing until somebody puts a time on it;
  * the stage ladder, and the fact that where a conversation died is carried
    rather than flattened into one interviews-to-offers percentage;
  * assessments: set by either side, done by the developer, and late when the
    deadline has passed and nobody has submitted;
  * a profile that has handed in nothing still receives the pool when it sells
    the same skills as somebody who has.

Shares a database with the rest of the suite — pytest imports app.main once, so
whichever module runs first decides where the data lives. Every account and
profile minted here carries a name no other module uses.
"""
import datetime as dt
import io
import itertools

import pytest
from fastapi.testclient import TestClient

from app.matching import fingerprint as _fingerprint


def matching_fingerprint(url):
    return _fingerprint(url, "", "")[0]

TEAM = [("pl-boss@pipeline.example.com", "Pipe Boss", "admin"),
        ("pl-bd@pipeline.example.com", "Pia Dee", "bd"),
        ("pl-bd2@pipeline.example.com", "Fay Zann", "bd"),
        ("pl-dev@pipeline.example.com", "Dev Pipe", "dev")]

PASSWORD = "pipepass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/pipe.db")
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
    return token(client, "pl-boss@pipeline.example.com")


@pytest.fixture(scope="module")
def bd(client):
    return token(client, "pl-bd@pipeline.example.com")


@pytest.fixture(scope="module")
def other_bd(client):
    return token(client, "pl-bd2@pipeline.example.com")


@pytest.fixture(scope="module")
def dev(client):
    return token(client, "pl-dev@pipeline.example.com")


@pytest.fixture
def people(client, admin):
    return {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}


@pytest.fixture
def make_profile(client, admin, people):
    def make(bd_email="pl-bd@pipeline.example.com",
             dev_email="pl-dev@pipeline.example.com", skills="", **extra):
        body = {"name": f"Pipe{next(_serial)}", "headline": "AI Engineer",
                "platform": "Upwork", "user_id": people[bd_email],
                "dev_user_id": people[dev_email] if dev_email else None,
                "skills": skills}
        body.update(extra)
        response = client.post("/api/profiles", json=body, headers=admin)
        assert response.status_code == 201, response.text
        return response.json()
    return make


def when(days: int, clock: str) -> str:
    from app.models import working_today
    return f"{(working_today() + dt.timedelta(days=days)).isoformat()}T{clock}"


def sheet(job_ids, client_name="Northwind Digital", title="RAG Developer"):
    out = io.StringIO()
    out.write("Job Title,Company,Job URL,Job description link\n")
    for n in job_ids:
        out.write(f"{title} {n},{client_name},"
                  f"https://www.upwork.com/jobs/~03{n:016x},"
                  f"https://example.com/jd/{n}\n")
    return out.getvalue().encode()


def cycle(client, admin, name, **extra):
    body = {"name": name, "mode": "cover", "quota": 500, "auto_build_minutes": 0}
    body.update(extra)
    response = client.post("/api/batches", json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def hand_in(client, batch_id, headers, profile_id, payload):
    response = client.post(f"/api/batches/{batch_id}/uploads",
                           data={"profile_id": profile_id},
                           files={"file": ("s.csv", payload, "text/csv")}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def applied(client, admin, bd, make_profile):
    """A profile with a real application history behind it."""
    mine = make_profile()
    theirs = make_profile()
    batch = cycle(client, admin, f"Rec{next(_serial)}")
    hand_in(client, batch, bd, mine["id"], sheet(range(700, 706)))
    hand_in(client, batch, bd, theirs["id"], sheet(range(704, 710), "Sable Analytics"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)
    return {"profile": mine, "other": theirs, "batch": batch}


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #

def test_the_record_holds_everything_applied_for(client, bd, applied):
    """Not scoped to a cycle. A reply arrives three weeks after the application
    that earned it, by which time that cycle is closed and off the screens."""
    record = client.get("/api/jobs", headers=bd).json()
    assert record["total"] >= 12
    row = record["rows"][0]
    assert {"job_id", "profile", "title", "company", "url", "description_url"} <= set(row)


def test_found_by_uses_bd_names_not_profile_names(client, admin, bd, other_bd, make_profile):
    """A row should call out the people who applied, not the profile label they used."""
    # This module's own team. The emails here were copied in from
    # test_developer.py, where "dv-bd@" and "Otto Other" exist — in this module
    # they do not, so the fixture raised a KeyError before the test could run.
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")
    batch = cycle(client, admin, f"FoundBy{next(_serial)}")
    # The ranges have to differ, or there is nothing to test. Both sheets held
    # 820-825, so in cover mode each profile had already applied to everything
    # the other found and neither was dispatched a single job — `found_by` was
    # read off an empty list. Overlapping them leaves 826-829 for `mine`, all
    # of them found by the other BD.
    hand_in(client, batch, bd, mine["id"], sheet(range(820, 826)))
    hand_in(client, batch, other_bd, theirs["id"], sheet(range(823, 830), "Northwind Digital"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    jobs = client.get(f"/api/batches/{batch}/profiles/{mine['id']}/sheet", headers=bd).json()["jobs"]
    found = {name for row in jobs for name in row["found_by"]}
    assert "Fay Zann" in found, "the colleague who applied, by their own name"
    assert "Pipe" not in " ".join(found), "not the profile label they applied under"


def dated_sheet(job_ids, client_name="Northwind Digital", title="RAG Developer",
                platform="", stamp=""):
    """A sheet with the two columns the plain `sheet` helper leaves out.

    `platform` and `stamp` are written as empty cells when not given, which is
    the sheet a BD hands in having skipped those boxes — the case that stranded
    a job with no platform on it for good.
    """
    out = io.StringIO()
    out.write("Job Title,Company,Job URL,Platform,Applied on\n")
    for n in job_ids:
        out.write(f"{title} {n},{client_name},"
                  f"https://www.upwork.com/jobs/~03{n:016x},{platform},{stamp}\n")
    return out.getvalue().encode()


def test_a_platform_typed_later_reaches_a_job_that_was_built_without_one(
        client, admin, bd, make_profile):
    """A posting first built off a sheet with no platform used to keep an empty
    one for good — `build_lists` set it at creation and never again — so it read
    as "—" on the all-jobs record forever after, with the board named on a sheet
    all along."""
    mine = make_profile()
    theirs = make_profile()

    blank = cycle(client, admin, f"NoPlat{next(_serial)}")
    hand_in(client, blank, bd, mine["id"], dated_sheet(range(900, 906)))
    hand_in(client, blank, bd, theirs["id"], dated_sheet(range(904, 910), "Sable Analytics"))
    client.post(f"/api/batches/{blank}/compute", headers=admin)

    record = client.get("/api/jobs", params={"q": "RAG Developer 900"}, headers=bd).json()
    assert record["rows"], "the job was built"
    assert record["rows"][0]["platform"] == "", "nothing named a board yet"

    # The next cycle, with the column filled in this time.
    named = cycle(client, admin, f"Plat{next(_serial)}")
    hand_in(client, named, bd, mine["id"], dated_sheet(range(900, 906), platform="Indeed"))
    hand_in(client, named, bd, theirs["id"],
            dated_sheet(range(904, 910), "Sable Analytics", platform="Indeed"))
    client.post(f"/api/batches/{named}/compute", headers=admin)

    record = client.get("/api/jobs", params={"q": "RAG Developer 900"}, headers=bd).json()
    assert record["rows"][0]["platform"] == "Indeed", "the sheet's board reaches the posting"


def test_one_colleagues_platform_is_enough_for_the_shared_posting(
        client, admin, bd, make_profile):
    """Two sheets name one job and only one of them says where it came from.
    The build reads every record for a fingerprint, not just the first, so which
    sheet was read first stops deciding whether the posting has a platform."""
    mine = make_profile()
    theirs = make_profile()
    batch = cycle(client, admin, f"Share{next(_serial)}")
    hand_in(client, batch, bd, mine["id"], dated_sheet(range(930, 936)))
    hand_in(client, batch, bd, theirs["id"], dated_sheet(range(930, 936), platform="LinkedIn"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    record = client.get("/api/jobs", params={"q": "RAG Developer 930"}, headers=bd).json()
    assert record["rows"], "the job was built"
    assert {row["platform"] for row in record["rows"]} == {"LinkedIn"}


def test_a_new_job_says_when_it_was_found(client, admin, bd, other_bd, make_profile):
    """The new-jobs list carried a date column that was empty on every row: it
    read this profile's own `applied_on`, and a job is on that list precisely
    because this profile has not applied to it. What it can say is when the
    colleague who found it applied, which is how old the posting is."""
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")
    batch = cycle(client, admin, f"FoundOn{next(_serial)}")
    hand_in(client, batch, bd, mine["id"], dated_sheet(range(950, 956)))
    hand_in(client, batch, other_bd, theirs["id"],
            dated_sheet(range(953, 960), "Northwind Digital",
                        platform="Indeed", stamp="2026-08-31 16:28"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    jobs = client.get(f"/api/batches/{batch}/profiles/{mine['id']}/sheet",
                      headers=bd).json()["jobs"]
    dispatched = [job for job in jobs if job["found_by"]]
    assert dispatched, "something was dispatched off the other BD's sheet"
    assert all(job["found_on"] == "2026-08-31 16:28" for job in dispatched), (
        "the stamp off the sheet of whoever found it")
    assert all(job["applied_on"] == "" for job in dispatched), (
        "this profile has not applied to it — that is why it is on the list")


def test_a_job_nobody_dated_still_says_how_old_it_is(client, admin, bd, other_bd,
                                                     make_profile):
    """A sheet handed in with no date column leaves every application on it
    unstamped. Falling back to when the posting first entered the system beats
    a dash, because the first thing a BD wants to know is whether the link is
    three days old or three months."""
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")
    batch = cycle(client, admin, f"NoDate{next(_serial)}")
    hand_in(client, batch, bd, mine["id"], sheet(range(970, 976)))
    hand_in(client, batch, other_bd, theirs["id"], sheet(range(973, 980), "Northwind Digital"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    jobs = client.get(f"/api/batches/{batch}/profiles/{mine['id']}/sheet",
                      headers=bd).json()["jobs"]
    dispatched = [job for job in jobs if job["found_by"]]
    assert dispatched
    for job in dispatched:
        assert len(job["found_on"]) == 16 and job["found_on"][4] == "-", (
            f"a readable YYYY-MM-DD HH:MM, got {job['found_on']!r}")


def test_the_record_is_searched_by_anything_pasted_out_of_an_email(client, bd, applied):
    """A person pasting out of a client's email has no idea which field the
    thing they copied lives in, so all of them are searched."""
    # Scoped to the one profile. This fixture mints fresh profiles per test
    # against the same postings, so the workspace-wide count grows as the module
    # runs and only a scoped one is a number worth asserting on.
    mine = applied["other"]["id"]
    by_client = client.get(f"/api/jobs?q=sable&profile_id={mine}", headers=bd).json()
    # Four of its six, not all six. Jobs 704 and 705 are on both sheets — the
    # same posting found twice — and a job is one row: the first client name
    # recorded for it is the one it keeps. That is the fingerprint doing its
    # job, showing up here as two of Sable's six filed under Northwind.
    assert by_client["total"] == 4
    assert all(r["company"] == "Sable Analytics" for r in by_client["rows"])

    # Mid-value, not just leading — "Northwind" inside "The Northwind Group".
    by_title = client.get(f"/api/jobs?q=Developer+704&profile_id={mine}", headers=bd).json()
    assert by_title["total"] == 1

    assert client.get("/api/jobs?q=nothingmatchesthis", headers=bd).json()["total"] == 0


def test_the_record_stops_at_the_profiles_you_run(client, bd, other_bd, applied):
    """A BD who runs neither profile sees none of it.

    Asserted against the two profiles in question rather than against a total
    of zero. This module shares one database across its tests, so the other BD
    picks up a history of their own as the suite runs — and a test that only
    holds while a colleague has never logged anything is testing the order the
    tests happen to run in, not the scoping rule it is named for.
    """
    seen = client.get("/api/jobs", headers=other_bd).json()
    off_limits = {applied["profile"]["id"], applied["other"]["id"]}
    assert not ({row["profile_id"] for row in seen["rows"]} & off_limits)

    # The BD who does run them sees them, so the rule above is a real boundary
    # and not an empty result from some unrelated cause.
    theirs = client.get("/api/jobs", headers=bd).json()
    assert {row["profile_id"] for row in theirs["rows"]} & off_limits


def test_the_record_pages(client, bd, applied):
    mine = applied["profile"]["id"]
    first = client.get(f"/api/jobs?limit=5&profile_id={mine}", headers=bd).json()
    second = client.get(f"/api/jobs?limit=5&offset=5&profile_id={mine}", headers=bd).json()
    assert len(first["rows"]) == 5
    assert first["total"] == second["total"] == 6
    # Keyed on the pair, not the job. One posting legitimately appears twice
    # when two profiles both applied to it — they are two candidates, and the
    # record is of applications rather than of postings.
    def keys(page):
        return {(r["job_id"], r["profile_id"]) for r in page["rows"]}
    assert keys(first) & keys(second) == set()


def test_the_description_link_survives_the_sheet(client, bd, applied):
    """The apply link dies when the posting expires and takes the wording with
    it. The description link is what a BD still has three weeks later."""
    row = client.get("/api/jobs?q=sable", headers=bd).json()["rows"][0]
    assert row["description_url"].startswith("https://example.com/jd/")


# --------------------------------------------------------------------------- #
# Starting an interview from the record
# --------------------------------------------------------------------------- #

def test_an_interview_started_from_a_job_carries_the_job_across(client, bd, applied):
    """The point of the record. The title, the client and both links come over
    instead of being typed again out of an email, wrong."""
    job = client.get("/api/jobs?q=sable", headers=bd).json()["rows"][0]
    made = client.post("/api/interviews",
                       json={"profile_id": applied["other"]["id"], "job_id": job["job_id"]},
                       headers=bd)
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["status"] == "draft"
    assert row["is_draft"] is True
    assert row["client"] == "Sable Analytics"      # filled from the job
    assert row["role"] == job["title"]
    assert row["job"]["description_url"] == job["description_url"]


def test_a_draft_counts_towards_nothing_until_it_has_a_time(client, bd, applied):
    """No time agreed means no conversation yet. Counting it would put a client
    who has not answered into a rate that says they did."""
    profile = applied["profile"]["id"]
    before = client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()

    draft = client.post("/api/interviews", json={"profile_id": profile,
                                                 "client": "Ironvale"},
                        headers=bd).json()
    after = client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()

    assert after["counts"]["awaiting_time"] == before["counts"]["awaiting_time"] + 1
    assert after["counts"]["scheduled"] == before["counts"]["scheduled"]
    assert after["funnel"]["interviews"] == before["funnel"]["interviews"]
    # Its own list — a reply nobody has answered is a thing to chase.
    assert draft["id"] in {r["id"] for r in after["awaiting_time"]}
    assert draft["id"] not in {r["id"] for r in after["today"] + after["upcoming"]}


def test_putting_a_time_on_a_draft_is_what_books_it(client, bd, applied):
    """Agreeing the time *is* the confirmation. A second button to say so is a
    button somebody forgets, leaving a real interview counted nowhere."""
    profile = applied["profile"]["id"]
    draft = client.post("/api/interviews", json={"profile_id": profile,
                                                 "client": "Ironvale Systems"},
                        headers=bd).json()

    booked = client.patch(f"/api/interviews/{draft['id']}",
                          json={"scheduled_at": when(2, "14:00")}, headers=bd)
    assert booked.status_code == 200, booked.text
    assert booked.json()["status"] == "scheduled"
    assert booked.json()["when"]["time"] == "14:00"


def test_a_draft_cannot_be_reported_on(client, bd, applied):
    """It has no time on it, so it has not happened. An outcome here would be
    a call nobody had, counted in a rate."""
    draft = client.post("/api/interviews",
                        json={"profile_id": applied["profile"]["id"], "client": "Ghost Co"},
                        headers=bd).json()
    refused = client.patch(f"/api/interviews/{draft['id']}",
                           json={"outcome": "offer"}, headers=bd)
    assert refused.status_code == 400
    assert "has not happened" in refused.json()["detail"]


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #

def test_a_conversation_climbs_the_ladder(client, bd, dev, applied):
    """Where a conversation died matters more than that it died — a team losing
    everybody at technical has a different problem from one losing them at
    final, and a single percentage cannot tell those apart."""
    profile = applied["profile"]["id"]
    first = client.post("/api/interviews",
                        json={"profile_id": profile, "scheduled_at": when(-3, "10:00"),
                              "client": "Larkspur Data", "stage": "screening"},
                        headers=bd).json()
    assert first["stage"] == "screening"

    client.patch(f"/api/interviews/{first['id']}", json={"outcome": "passed"}, headers=dev)

    second = client.post("/api/interviews",
                         json={"profile_id": profile, "scheduled_at": when(-1, "10:00"),
                               "client": "Larkspur Data", "stage": "technical",
                               "job_id": first["job_id"]},
                         headers=bd).json()
    client.patch(f"/api/interviews/{second['id']}", json={"outcome": "rejected"}, headers=dev)

    stages = {row["stage"]: row for row in
              client.get(f"/api/interviews?profile_id={profile}",
                         headers=bd).json()["funnel"]["by_stage"]}
    assert stages["screening"]["cleared"] >= 1
    assert stages["technical"]["lost"] >= 1
    assert [s["stage"] for s in
            client.get(f"/api/interviews?profile_id={profile}",
                       headers=bd).json()["funnel"]["by_stage"]] == \
        ["screening", "technical", "assessment", "final", "offer"]


def test_a_stage_has_to_be_one_of_the_rungs(client, bd, applied):
    refused = client.post("/api/interviews",
                          json={"profile_id": applied["profile"]["id"],
                                "scheduled_at": when(1, "09:00"), "stage": "vibes"},
                          headers=bd)
    assert refused.status_code == 400


# --------------------------------------------------------------------------- #
# Assessments
# --------------------------------------------------------------------------- #

def test_the_bd_sets_it_and_the_developer_does_it(client, bd, dev, applied):
    """The same split as an interview: the BD has the client's email, the
    developer has the work."""
    profile = applied["profile"]["id"]
    sitting = client.post("/api/interviews",
                          json={"profile_id": profile, "scheduled_at": when(-2, "11:00"),
                                "client": "Copperline Media", "stage": "technical"},
                          headers=bd).json()

    made = client.post("/api/assessments",
                       json={"profile_id": profile, "interview_id": sitting["id"],
                             "brief": "Build a small RAG pipeline.",
                             "link": "https://example.com/take-home",
                             "due_at": when(3, "17:00")},
                       headers=bd)
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["status"] == "sent"
    assert row["client"] == "Copperline Media"     # filled from the interview
    assert row["interview"]["stage"] == "technical"
    assert row["set_by"] == "Pia Dee"

    done = client.patch(f"/api/assessments/{row['id']}",
                        json={"status": "submitted",
                              "submission_url": "https://github.com/example/take-home",
                              "notes": "Went with hybrid search. Took about four hours."},
                        headers=dev)
    assert done.status_code == 200, done.text
    assert done.json()["submitted"] is not None
    assert done.json()["is_open"] is False

    # And the BD reads it on their own screen.
    seen = client.get(f"/api/assessments?profile_id={profile}", headers=bd).json()
    mine = next(a for a in seen["rows"] if a["id"] == row["id"])
    assert mine["notes"].startswith("Went with hybrid search")
    assert mine["updated_by"] == "Dev Pipe"


def test_an_assessment_nobody_submitted_goes_overdue(client, bd, applied):
    """A deadline nobody is watching is the same as no deadline, and a missed
    take-home costs the interview that earned it."""
    profile = applied["profile"]["id"]
    late = client.post("/api/assessments",
                       json={"profile_id": profile, "title": "Late one",
                             "due_at": when(-2, "17:00")}, headers=bd).json()
    assert late["overdue"] is True

    figures = client.get(f"/api/assessments?profile_id={profile}", headers=bd).json()
    assert figures["counts"]["overdue"] >= 1
    assert late["id"] in {a["id"] for a in figures["open"]}


def test_a_submitted_assessment_is_not_late_however_late_it_was(client, bd, dev, applied):
    """Only an open one can be chased. One that went in after the deadline is a
    thing that happened, not a thing to do."""
    profile = applied["profile"]["id"]
    row = client.post("/api/assessments",
                      json={"profile_id": profile, "title": "Handed in late",
                            "due_at": when(-4, "17:00")}, headers=bd).json()
    assert row["overdue"] is True

    after = client.patch(f"/api/assessments/{row['id']}",
                         json={"status": "submitted"}, headers=dev).json()
    assert after["overdue"] is False


def test_an_assessment_with_no_deadline_is_not_late(client, bd, applied):
    """No deadline is the commonest answer after "next Friday". Inventing one
    puts a red flag on a screen nobody set."""
    row = client.post("/api/assessments",
                      json={"profile_id": applied["profile"]["id"], "title": "Open ended"},
                      headers=bd).json()
    assert row["due"] is None
    assert row["overdue"] is False
    assert row["is_open"] is True


def test_a_stranger_cannot_reach_the_assessments(client, other_bd, bd, applied):
    profile = applied["profile"]["id"]
    client.post("/api/assessments", json={"profile_id": profile, "title": "Private"},
                headers=bd)
    refused = client.get(f"/api/assessments?profile_id={profile}", headers=other_bd)
    assert refused.status_code == 403


def test_an_assessment_cannot_be_hung_on_another_profiles_interview(
        client, bd, applied, make_profile):
    elsewhere = make_profile()
    sitting = client.post("/api/interviews",
                          json={"profile_id": elsewhere["id"],
                                "scheduled_at": when(1, "10:00")}, headers=bd).json()
    refused = client.post("/api/assessments",
                          json={"profile_id": applied["profile"]["id"],
                                "interview_id": sitting["id"]}, headers=bd)
    assert refused.status_code == 400


# --------------------------------------------------------------------------- #
# Joining a cycle you handed nothing into
# --------------------------------------------------------------------------- #

def test_a_profile_selling_the_same_skills_still_gets_the_pool(
        client, admin, bd, make_profile):
    """The profile with the most spare capacity should not be the one handed no
    work just because it has not logged anything yet."""
    one = make_profile(skills="Python, RAG, LangChain")
    two = make_profile(skills="Python, PyTorch")
    idle = make_profile(skills="RAG, LLM")            # hands in nothing
    unrelated = make_profile(skills="Figma, Illustrator")

    batch = cycle(client, admin, f"Join{next(_serial)}")
    hand_in(client, batch, bd, one["id"], sheet(range(800, 806)))
    hand_in(client, batch, bd, two["id"], sheet(range(806, 812), "Verdant Labs"))
    data = client.post(f"/api/batches/{batch}/compute", headers=admin).json()

    given = {p["id"]: p["assigned"] for p in data["participants"]}
    assert given.get(idle["id"], 0) == 12, "a profile selling the same skills gets the pool"
    assert unrelated["id"] not in given, "a designer is not in an AI cycle"
    # At least the one this test made. The suite shares a database, so other
    # modules' profiles can legitimately match too — which is why every precise
    # assertion here is about a profile this test minted itself.
    assert data["report"].get("Profiles pulled in on skills") >= 1


def test_a_profile_with_no_skills_recorded_is_never_pulled_in(
        client, admin, bd, make_profile):
    """An empty field is not a match. It is a profile nobody has finished
    setting up, and handing it a stranger's pool would be a guess."""
    one = make_profile(skills="Rust, WebAssembly")
    two = make_profile(skills="Rust, Tokio")
    blank = make_profile(skills="")

    batch = cycle(client, admin, f"Blank{next(_serial)}")
    hand_in(client, batch, bd, one["id"], sheet(range(900, 904)))
    hand_in(client, batch, bd, two["id"], sheet(range(904, 908), "Talloak"))
    data = client.post(f"/api/batches/{batch}/compute", headers=admin).json()

    assert blank["id"] not in {p["id"] for p in data["participants"]}


def test_shared_tooling_is_not_the_same_market(client, admin, bd, make_profile):
    """Everybody runs Postgres in Docker on AWS. Matching on that is how a
    front-end profile lands in an AI cycle, so shared infrastructure cannot
    carry a match on its own — a shared language or framework can."""
    one = make_profile(skills="Python, RAG, LangChain, Postgres, Docker")
    two = make_profile(skills="Python, PyTorch, MLOps, Postgres")
    frontend = make_profile(skills="React, Stripe, Postgres, Docker, AWS")

    batch = cycle(client, admin, f"Infra{next(_serial)}")
    hand_in(client, batch, bd, one["id"], sheet(range(970, 974)))
    hand_in(client, batch, bd, two["id"], sheet(range(974, 978), "Larkspur"))
    data = client.post(f"/api/batches/{batch}/compute", headers=admin).json()

    joined = {p["id"] for p in data["participants"]}
    assert frontend["id"] not in joined, "Postgres and Docker in common is not a market"


def test_a_late_joiner_is_given_jobs_not_given_away(client, admin, bd, make_profile):
    """They contributed nothing to the pool, so nothing of theirs is in it —
    and their own history still blocks anything they have already applied to."""
    one = make_profile(skills="Elixir, Phoenix")
    two = make_profile(skills="Elixir, OTP")
    idle = make_profile(skills="Phoenix, Elixir")

    first = cycle(client, admin, f"Late1{next(_serial)}")
    hand_in(client, first, bd, idle["id"], sheet(range(950, 953)))
    hand_in(client, first, bd, one["id"], sheet(range(953, 956), "Harbourstone"))
    client.post(f"/api/batches/{first}/compute", headers=admin)

    second = cycle(client, admin, f"Late2{next(_serial)}")
    hand_in(client, second, bd, one["id"], sheet(range(950, 956)))
    hand_in(client, second, bd, two["id"], sheet(range(956, 960), "Orchard"))
    data = client.post(f"/api/batches/{second}/compute", headers=admin).json()

    given = {p["id"]: p["assigned"] for p in data["participants"]}
    # 950-952 are its own history and never come back; 953-959 are new to it.
    assert given[idle["id"]] == 7


# --------------------------------------------------------------------------- #
# Rounds — one conversation, several sittings
# --------------------------------------------------------------------------- #

def sat(web, headers, profile_id, days=-3, clock="10:00", **extra):
    """An interview that has already been and gone, unless days says otherwise.

    The test client is `web` here, not `client`, so that `client="Northwind"`
    stays available as what it means everywhere else in this app — the company
    on the other end of the call. Same reason as `book()` above.
    """
    body = {"profile_id": profile_id, "scheduled_at": when(days, clock),
            "client": "Larkspur Data", "role": "RAG Developer"}
    body.update(extra)
    response = web.post("/api/interviews", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Turning a job down
# --------------------------------------------------------------------------- #

def linked_sheet(rows):
    """A sheet of (url, title, company) exactly as given."""
    out = io.StringIO()
    out.write("Job Title,Company,Job URL\n")
    for url, title, company in rows:
        out.write(f"{title},{company},{url}\n")
    return out.getvalue().encode()


def test_a_skipped_job_does_not_come_back_on_a_different_link(
        client, admin, bd, other_bd, make_profile):
    """The bug BDs kept reporting: they turned a job down and a fortnight later
    it was back on the list.

    Nothing was wrong with the skip. The same posting had been handed in again
    on a different link \u2014 the apply URL rather than the listing \u2014 and a
    different link is a different fingerprint, so it arrived as a new row with
    no skip against it. A skip is a judgement about the posting, not about the
    row it came in on.
    """
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    listing = "https://careers.acme-two.example.com/jobs/48213/senior-ai-engineer"
    apply_url = listing + "/apply?src=board"
    assert (matching_fingerprint(listing) != matching_fingerprint(apply_url)), (
        "the premise: these are two rows to the matcher")

    first = cycle(client, admin, f"Skip{next(_serial)}")
    hand_in(client, first, other_bd, theirs["id"],
            linked_sheet([(listing, "Senior AI Engineer", "Acme Two"),
                          ("https://example.com/jobs/1", "Filler", "Padding Co")]))
    hand_in(client, first, bd, mine["id"], sheet(range(1200, 1206)))
    client.post(f"/api/batches/{first}/compute", headers=admin)

    jobs = client.get(f"/api/batches/{first}/profiles/{mine['id']}/sheet",
                      headers=bd).json()["jobs"]
    target = next(j for j in jobs if j["company"] == "Acme Two")
    turned = client.patch(f"/api/assignments/{target['id']}",
                          json={"status": "skipped",
                                "reason": "Wrong seniority for this profile."},
                          headers=bd)
    assert turned.status_code == 200, turned.text

    # A new round, and the colleague hands the same posting in from the apply
    # flow this time \u2014 which is what somebody who actually applied would paste.
    second = cycle(client, admin, f"Skip{next(_serial)}")
    hand_in(client, second, other_bd, theirs["id"],
            linked_sheet([(apply_url, "Senior AI Engineer", "Acme Two"),
                          ("https://example.com/jobs/1", "Filler", "Padding Co")]))
    hand_in(client, second, bd, mine["id"], sheet(range(1200, 1206)))
    client.post(f"/api/batches/{second}/compute", headers=admin)

    after = client.get(f"/api/batches/{second}/profiles/{mine['id']}/sheet",
                       headers=bd).json()["jobs"]
    assert not [j for j in after if j["company"] == "Acme Two"], (
        "the posting they turned down came back under its apply link")


def test_a_new_round_does_not_hand_back_work_already_done(
        client, admin, bd, other_bd, make_profile):
    """The other half of the same bug, reported a week after the first.

    A profile applies for a posting off its own sheet. A new round opens, a
    colleague hands the same posting in from the apply URL rather than the
    listing, and it arrives as a new row with no application against it \u2014 so
    the round hands somebody work they have already done.
    """
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    listing = "https://careers.acme-three.example.com/jobs/71400/ar-specialist"
    apply_url = listing + "/apply?src=board"

    first = cycle(client, admin, f"Done{next(_serial)}")
    hand_in(client, first, bd, mine["id"],
            linked_sheet([(listing, "AR Specialist", "Acme Three"),
                          ("https://example.com/jobs/20", "Filler", "Padding Co")]))
    hand_in(client, first, other_bd, theirs["id"], sheet(range(1300, 1306)))
    client.post(f"/api/batches/{first}/compute", headers=admin)

    record = client.get("/api/jobs", params={"q": "Acme Three", "profile_id": mine["id"]},
                        headers=bd).json()
    assert record["total"] == 1, "the profile applied for it off its own sheet"

    second = cycle(client, admin, f"Done{next(_serial)}")
    hand_in(client, second, other_bd, theirs["id"],
            linked_sheet([(apply_url, "AR Specialist", "Acme Three"),
                          ("https://example.com/jobs/21", "Filler Two", "Padding Co")]))
    hand_in(client, second, bd, mine["id"], sheet(range(1310, 1316)))
    client.post(f"/api/batches/{second}/compute", headers=admin)

    handed = client.get(f"/api/batches/{second}/profiles/{mine['id']}/sheet",
                        headers=bd).json()["jobs"]
    assert not [j for j in handed if j["company"] == "Acme Three"], (
        "handed back a posting this profile had already applied for")


def test_a_colleague_may_still_be_given_what_you_applied_for(
        client, admin, bd, other_bd, make_profile):
    """Blocked per profile, and only per profile. Two profiles are two
    candidates: one having approached a client is the reason the other should
    be offered it, not a reason to hold it back."""
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    listing = "https://careers.acme-four.example.com/jobs/71500/collections-lead"

    batch = cycle(client, admin, f"Both{next(_serial)}")
    hand_in(client, batch, bd, mine["id"],
            linked_sheet([(listing, "Collections Lead", "Acme Four"),
                          ("https://example.com/jobs/22", "Filler", "Padding Co")]))
    hand_in(client, batch, other_bd, theirs["id"], sheet(range(1320, 1326)))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    handed = client.get(f"/api/batches/{batch}/profiles/{theirs['id']}/sheet",
                        headers=other_bd).json()["jobs"]
    assert [j for j in handed if j["company"] == "Acme Four"], (
        "the colleague has never applied to it; it is exactly what they are for")


def test_turning_one_job_down_does_not_bury_the_whole_client(
        client, admin, bd, other_bd, make_profile):
    """Both halves of the key are required. A different role at the same client
    is a different job, and one skip must not take the client with it."""
    mine = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    first = cycle(client, admin, f"Bury{next(_serial)}")
    hand_in(client, first, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.corvus.example.com/p/9001", "Data Engineer", "Corvus Systems"),
        ("https://jobs.corvus.example.com/p/9002", "Platform Engineer", "Corvus Systems"),
    ]))
    hand_in(client, first, bd, mine["id"], sheet(range(1210, 1216)))
    client.post(f"/api/batches/{first}/compute", headers=admin)

    jobs = client.get(f"/api/batches/{first}/profiles/{mine['id']}/sheet",
                      headers=bd).json()["jobs"]
    data_role = next(j for j in jobs if j["title"] == "Data Engineer")
    client.patch(f"/api/assignments/{data_role['id']}",
                 json={"status": "skipped", "reason": "Not this profile."},
                 headers=bd)

    second = cycle(client, admin, f"Bury{next(_serial)}")
    hand_in(client, second, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.corvus.example.com/p/9001/apply", "Data Engineer", "Corvus Systems"),
        ("https://jobs.corvus.example.com/p/9002", "Platform Engineer", "Corvus Systems"),
    ]))
    hand_in(client, second, bd, mine["id"], sheet(range(1210, 1216)))
    client.post(f"/api/batches/{second}/compute", headers=admin)

    after = client.get(f"/api/batches/{second}/profiles/{mine['id']}/sheet",
                       headers=bd).json()["jobs"]
    titles = {j["title"] for j in after}
    assert "Data Engineer" not in titles, "the one they turned down"
    assert "Platform Engineer" in titles, (
        "a different role at the same client is a different job")


def test_one_skip_can_cover_every_profile_a_person_runs(client, admin, bd, other_bd,
                                                        make_profile):
    """The complaint behind this: a BD turns a job down and it comes round again
    the following week under the other name they apply as.

    Nothing is wrong with the skip \u2014 it is per profile, and per profile is
    right, because two profiles are two candidates in two markets. But when the
    reason is about the job rather than the fit, turning it down once per
    profile per week reads as the skip not working. So it can be said once.
    """
    one = make_profile(bd_email="pl-bd@pipeline.example.com")
    two = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    batch = cycle(client, admin, f"Every{next(_serial)}")
    hand_in(client, batch, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.ashcroft.example.com/p/5150", "Billing Coordinator", "Ashcroft Media"),
        ("https://example.com/jobs/3", "Filler", "Padding Co"),
    ]))
    hand_in(client, batch, bd, one["id"], sheet(range(1240, 1246)))
    hand_in(client, batch, bd, two["id"], sheet(range(1250, 1256), "Ironvale"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    mine = client.get(f"/api/batches/{batch}/profiles/{one['id']}/sheet",
                      headers=bd).json()["jobs"]
    target = next(j for j in mine if j["company"] == "Ashcroft Media")
    done = client.patch(f"/api/assignments/{target['id']}",
                        json={"status": "skipped", "reason": "Rate is too low.",
                              "every_profile": True},
                        headers=bd)
    assert done.status_code == 200, done.text
    assert done.json()["also_skipped"] >= 1, "the other profile they run"

    for pid in (one["id"], two["id"]):
        rows = client.get(f"/api/batches/{batch}/profiles/{pid}/sheet",
                          headers=bd).json()["jobs"]
        assert not [j for j in rows if j["company"] == "Ashcroft Media"]

    # ...and it stays gone when the round is built again.
    client.post(f"/api/batches/{batch}/compute", headers=admin)
    for pid in (one["id"], two["id"]):
        rows = client.get(f"/api/batches/{batch}/profiles/{pid}/sheet",
                          headers=bd).json()["jobs"]
        assert not [j for j in rows if j["company"] == "Ashcroft Media"]


def test_skipping_everywhere_never_overwrites_work_already_done(
        client, admin, bd, other_bd, make_profile):
    """The other profile may already have applied for it. That is work, and a
    tick box on a different screen must not rewrite it as a rejection."""
    one = make_profile(bd_email="pl-bd@pipeline.example.com")
    two = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    batch = cycle(client, admin, f"Guard{next(_serial)}")
    hand_in(client, batch, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.meridian.example.com/p/6100", "Claims Processor", "Meridian Group"),
        ("https://example.com/jobs/4", "Filler", "Padding Co"),
    ]))
    hand_in(client, batch, bd, one["id"], sheet(range(1260, 1266)))
    hand_in(client, batch, bd, two["id"], sheet(range(1270, 1276), "Ironvale"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    second = client.get(f"/api/batches/{batch}/profiles/{two['id']}/sheet",
                        headers=bd).json()["jobs"]
    already = next(j for j in second if j["company"] == "Meridian Group")
    client.patch(f"/api/assignments/{already['id']}", json={"status": "applied"},
                 headers=bd)

    first = client.get(f"/api/batches/{batch}/profiles/{one['id']}/sheet",
                       headers=bd).json()["jobs"]
    target = next(j for j in first if j["company"] == "Meridian Group")
    done = client.patch(f"/api/assignments/{target['id']}",
                        json={"status": "skipped", "reason": "On-site only.",
                              "every_profile": True},
                        headers=bd)
    assert done.status_code == 200, done.text

    # The point is not how many rows moved — this BD has profiles left over
    # from other tests in this module. It is that the one which had already
    # applied was left exactly as it was.
    record = client.get(f"/api/jobs?profile_id={two['id']}", headers=bd).json()
    assert [r for r in record["rows"] if r["company"] == "Meridian Group"], (
        "the application the other profile already sent")
    board = client.get(f"/api/dashboard/profiles/{two['id']}", headers=bd).json()
    assert board["stats"]["applied"] >= 1, "still counted as work, not as a rejection"


def test_a_job_says_when_another_of_your_profiles_turned_it_down(
        client, admin, bd, other_bd, make_profile):
    """Without this a BD sees a posting they clearly remember rejecting and
    concludes the skip is broken. It is not \u2014 it was a different candidate."""
    one = make_profile(bd_email="pl-bd@pipeline.example.com")
    two = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    batch = cycle(client, admin, f"Says{next(_serial)}")
    hand_in(client, batch, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.verdant.example.com/p/8200", "Support Associate", "Verdant Labs"),
        ("https://example.com/jobs/5", "Filler", "Padding Co"),
    ]))
    hand_in(client, batch, bd, one["id"], sheet(range(1280, 1286)))
    hand_in(client, batch, bd, two["id"], sheet(range(1290, 1296), "Ironvale"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    first = client.get(f"/api/batches/{batch}/profiles/{one['id']}/sheet",
                       headers=bd).json()["jobs"]
    target = next(j for j in first if j["company"] == "Verdant Labs")
    client.patch(f"/api/assignments/{target['id']}",
                 json={"status": "skipped", "reason": "Wrong market for this one."},
                 headers=bd)

    second = client.get(f"/api/batches/{batch}/profiles/{two['id']}/sheet",
                        headers=bd).json()["jobs"]
    still = next(j for j in second if j["company"] == "Verdant Labs")
    assert still["turned_down_by"] == [one["name"]], (
        "the row has to say which of their names already rejected it")


def test_a_skip_belongs_to_the_profile_not_the_person(client, admin, bd, other_bd,
                                                      make_profile):
    """Two profiles are two candidates. One turning a job down says nothing
    about whether the other should see it."""
    one = make_profile(bd_email="pl-bd@pipeline.example.com")
    two = make_profile(bd_email="pl-bd@pipeline.example.com")
    theirs = make_profile(bd_email="pl-bd2@pipeline.example.com")

    batch = cycle(client, admin, f"Whose{next(_serial)}")
    hand_in(client, batch, other_bd, theirs["id"], linked_sheet([
        ("https://jobs.halcyon.example.com/p/7700", "ML Engineer", "Halcyon Data"),
        ("https://example.com/jobs/2", "Filler", "Padding Co"),
    ]))
    hand_in(client, batch, bd, one["id"], sheet(range(1220, 1226)))
    # The second profile hands in too, so it is unarguably taking part and the
    # test is about the skip rather than about who was in the round.
    hand_in(client, batch, bd, two["id"], sheet(range(1230, 1236), "Ironvale"))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    first = client.get(f"/api/batches/{batch}/profiles/{one['id']}/sheet",
                       headers=bd).json()["jobs"]
    target = next(j for j in first if j["company"] == "Halcyon Data")
    client.patch(f"/api/assignments/{target['id']}",
                 json={"status": "skipped", "reason": "Not for this one."},
                 headers=bd)

    client.post(f"/api/batches/{batch}/compute", headers=admin)
    mine_again = client.get(f"/api/batches/{batch}/profiles/{one['id']}/sheet",
                            headers=bd).json()["jobs"]
    assert not [j for j in mine_again if j["company"] == "Halcyon Data"]

    others = client.get(f"/api/batches/{batch}/profiles/{two['id']}/sheet",
                        headers=bd).json()["jobs"]
    assert [j for j in others if j["company"] == "Halcyon Data"], (
        "the other profile never turned it down")


# --------------------------------------------------------------------------- #
# The client's own email
# --------------------------------------------------------------------------- #

def test_an_interview_can_keep_a_link_to_the_clients_email(client, bd, applied):
    """The meeting link is where to be at two o'clock. This is what they asked
    for, and three weeks later it is the only place their words still exist."""
    made = sat(client, bd, applied["profile"]["id"],
               email_url="https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234")
    assert made["email_url"] == "https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234"
    assert made["link"] == "", "the meeting link is a different field"


def test_the_email_link_is_optional_everywhere(client, bd, applied):
    """Plenty of replies arrive by phone or through a board's own messaging. A
    required field would be filled with rubbish rather than left alone."""
    profile = applied["profile"]["id"]
    booked = sat(client, bd, profile)
    assert booked["email_url"] == ""

    test = client.post("/api/assessments",
                       json={"profile_id": profile, "title": "Take-home"},
                       headers=bd)
    assert test.status_code == 201, test.text
    assert test.json()["email_url"] == ""


def test_a_junk_email_link_is_refused_rather_than_stored(client, bd, applied):
    """It ends up in an href on a colleague's screen, so it goes through the
    same check as every other link somebody types into a form."""
    response = client.post("/api/interviews",
                           json={"profile_id": applied["profile"]["id"],
                                 "scheduled_at": when(1, "10:00"),
                                 "email_url": "javascript:alert(1)"},
                           headers=bd)
    assert response.status_code == 400
    assert "http" in response.json()["detail"]


def test_the_email_link_can_be_added_after_the_booking(client, bd, applied):
    """A reply gets booked in ten seconds off a phone; the thread gets pasted
    in later, from a desk."""
    made = sat(client, bd, applied["profile"]["id"])
    saved = client.patch(f"/api/interviews/{made['id']}",
                         json={"email_url": "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"}, headers=bd)
    assert saved.status_code == 200, saved.text
    assert saved.json()["email_url"] == "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"


def test_the_next_round_keeps_the_same_email_thread(client, bd, applied):
    """A second round is the same conversation with the same client, so it is
    the same thread \u2014 carried across like the client and the role rather than
    looked up and retyped."""
    first = sat(client, bd, applied["profile"]["id"], email_url="https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234")
    client.patch(f"/api/interviews/{first['id']}",
                 json={"status": "done", "outcome": "passed"}, headers=bd)
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={}, headers=bd)
    assert second.status_code == 201, second.text
    assert second.json()["email_url"] == "https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234"


def test_a_second_round_on_a_new_thread_says_so(client, bd, applied):
    """Carried across is a default, not a rule. A client who moved the
    conversation to a different thread is a thing that happens."""
    first = sat(client, bd, applied["profile"]["id"], email_url="https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234")
    client.patch(f"/api/interviews/{first['id']}",
                 json={"status": "done", "outcome": "passed"}, headers=bd)
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={"email_url": "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"}, headers=bd)
    assert second.json()["email_url"] == "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"


def test_a_test_takes_the_thread_off_the_call_it_came_out_of(client, bd, applied):
    """The take-home almost always arrives on the same thread as the call that
    produced it, so that is the default rather than something to look up."""
    profile = applied["profile"]["id"]
    sitting = sat(client, bd, profile, email_url="https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234")
    made = client.post("/api/assessments",
                       json={"profile_id": profile, "interview_id": sitting["id"],
                             "title": "Take-home \u00b7 RAG pipeline"},
                       headers=bd)
    assert made.status_code == 201, made.text
    assert made.json()["email_url"] == "https://mail.google.com/mail/u/0/#inbox/FMfcgzabcd1234"

    # ...unless the client sent it from somewhere else.
    other = client.post("/api/assessments",
                        json={"profile_id": profile, "interview_id": sitting["id"],
                              "title": "Second test", "email_url": "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"},
                        headers=bd)
    assert other.json()["email_url"] == "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"


def test_the_developer_may_add_the_thread_too(client, bd, dev, applied):
    """Both halves of the row have always been writable by whoever has the
    thing in front of them. A client that emailed the developer directly is
    exactly the case this exists for."""
    made = sat(client, bd, applied["profile"]["id"])
    saved = client.patch(f"/api/interviews/{made['id']}",
                         json={"email_url": "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"}, headers=dev)
    assert saved.status_code == 200, saved.text
    assert saved.json()["email_url"] == "https://outlook.office.com/mail/id/AAQkAGI2threadtwo"


def test_booking_the_next_round_carries_the_conversation_across(client, bd, applied):
    """The gap this closes loses work.

    A screening call goes well and the second round then has to be retyped from
    memory — same client, same role, same posting — so it usually is not typed
    for a week, and the client is left waiting on a team that thinks it is
    winning. One press instead, and nothing is retyped.
    """
    profile = applied["profile"]["id"]
    record = client.get(f"/api/jobs?profile_id={profile}", headers=bd).json()["rows"][0]
    first = sat(client, bd, profile, stage="screening", job_id=record["job_id"])

    made = client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=bd)
    assert made.status_code == 201, made.text
    second = made.json()

    assert second["client"] == "Larkspur Data"
    assert second["role"] == "RAG Developer"
    assert second["job_id"] == record["job_id"]
    assert second["stage"] == "technical"          # one rung up, guessed for them
    assert second["previous_id"] == first["id"]
    # No time was agreed, so it waits rather than inventing an appointment.
    assert second["status"] == "draft"
    assert second["round"] == 2 and second["rounds"] == 2

    # And booking it is what says the round before was cleared.
    assert second["previous"]["outcome"] == "passed"
    assert second["previous"]["status"] == "done"


def test_booking_the_next_round_does_not_overwrite_a_recorded_outcome(client, bd, dev,
                                                                      applied):
    """An offer somebody recorded is theirs. A scheduling action must not
    quietly demote it to `passed`."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, stage="final")
    client.patch(f"/api/interviews/{first['id']}", json={"outcome": "offer"}, headers=dev)

    made = client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=bd)
    assert made.status_code == 201, made.text
    assert made.json()["previous"]["outcome"] == "offer"


def test_a_round_that_has_not_happened_yet_is_not_marked_done(client, bd, applied):
    """A client saying up front that there will be two rounds is not a report
    on the first one, and a call next Tuesday must not read as finished."""
    profile = applied["profile"]["id"]
    ahead = sat(client, bd, profile, days=4, clock="15:00", stage="screening")

    made = client.post(f"/api/interviews/{ahead['id']}/next-round", json={}, headers=bd)
    assert made.status_code == 201, made.text
    assert made.json()["previous"]["status"] == "scheduled"
    assert made.json()["previous"]["outcome"] == "pending"


def test_nothing_follows_a_round_that_was_a_no(client, bd, dev, applied):
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile)
    client.patch(f"/api/interviews/{first['id']}", json={"outcome": "rejected"}, headers=dev)

    refused = client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=bd)
    assert refused.status_code == 400
    assert "no" in refused.json()["detail"].lower()


def test_a_reply_with_no_time_on_it_cannot_have_a_second_round(client, bd, applied):
    """A draft has not happened. There is nothing for a next round to follow."""
    profile = applied["profile"]["id"]
    draft = client.post("/api/interviews",
                        json={"profile_id": profile, "scheduled_at": "",
                              "client": "Larkspur Data"}, headers=bd).json()
    assert draft["status"] == "draft"

    refused = client.post(f"/api/interviews/{draft['id']}/next-round", json={}, headers=bd)
    assert refused.status_code == 400


def test_a_chain_of_rounds_reads_as_one_conversation(client, bd, applied):
    """Four rounds with one client is a different fact from four clients who
    each said no after one call, and in a flat list they look identical."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, stage="screening")
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={"scheduled_at": when(-2, "11:00")}, headers=bd).json()
    third = client.post(f"/api/interviews/{second['id']}/next-round",
                        json={"scheduled_at": when(-1, "11:00")}, headers=bd).json()

    rows = {row["id"]: row for row in
            client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()["rows"]}
    assert [rows[first["id"]]["round"], rows[second["id"]]["round"],
            rows[third["id"]]["round"]] == [1, 2, 3]
    assert rows[third["id"]]["rounds"] == 3
    # Read from the middle, it still knows what came before it.
    assert rows[second["id"]]["follows"]["stage"] == "screening"
    assert rows[first["id"]]["follows"] is None


def test_a_chain_cannot_cross_two_profiles(client, bd, applied):
    """A chain of rounds is one client talking to one identity. Linking across
    two would make a stranger's conversation part of this profile's story."""
    first = sat(client, bd, applied["profile"]["id"])
    refused = client.post("/api/interviews",
                          json={"profile_id": applied["other"]["id"],
                                "scheduled_at": when(1, "09:00"),
                                "previous_id": first["id"]}, headers=bd)
    assert refused.status_code == 400


def test_a_cleared_round_with_nothing_after_it_is_called_out(client, bd, dev, applied):
    """The quietest way this product loses work: the client said yes, nobody
    booked the next round, and on every other screen it reads as a success."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, stage="screening")
    client.patch(f"/api/interviews/{first['id']}", json={"outcome": "passed"}, headers=dev)

    diary = client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()
    assert diary["counts"]["stalled"] == 1
    assert [row["id"] for row in diary["stalled"]] == [first["id"]]

    # Booking what follows is what clears it.
    client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=bd)
    after = client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()
    assert after["counts"]["stalled"] == 0


def test_a_hire_is_not_a_stalled_conversation(client, bd, dev, applied):
    """Nothing follows a hire. It is the end of the ladder, not a gap in it."""
    profile = applied["profile"]["id"]
    row = sat(client, bd, profile, stage="offer")
    client.patch(f"/api/interviews/{row['id']}", json={"outcome": "hired"}, headers=dev)
    diary = client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()
    assert diary["counts"]["stalled"] == 0


def test_removing_a_round_leaves_what_followed_it_standing(client, bd, applied):
    """The link is a convenience. Losing it costs a breadcrumb; taking a real
    second round away with a mistyped first one would cost the work."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile)
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={"scheduled_at": when(-1, "12:00")}, headers=bd).json()

    assert client.delete(f"/api/interviews/{first['id']}", headers=bd).status_code == 200

    rows = {row["id"]: row for row in
            client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()["rows"]}
    assert second["id"] in rows
    assert rows[second["id"]]["previous_id"] is None
    assert rows[second["id"]]["round"] == 1


def test_the_developer_can_book_the_next_round_too(client, bd, dev, applied):
    """They are usually the first to know it is wanted — the client said so in
    the room — and making them ask somebody else to type it in loses a week."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile)
    made = client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=dev)
    assert made.status_code == 201, made.text
    assert made.json()["previous_id"] == first["id"]


def test_a_stranger_cannot_book_a_round_onto_someone_elses_conversation(
        client, bd, other_bd, applied):
    first = sat(client, bd, applied["profile"]["id"])
    refused = client.post(f"/api/interviews/{first['id']}/next-round", json={},
                          headers=other_bd)
    assert refused.status_code == 403


# --------------------------------------------------------------------------- #
# Take-homes, everywhere they have to be seen
# --------------------------------------------------------------------------- #

def test_a_take_home_shows_on_the_interview_it_came_out_of(client, bd, applied):
    """When a client has sent a test, the test *is* the state of that
    conversation. A diary that cannot say so sends people to a second screen to
    find out whether they are waiting on the client or on their own developer.
    """
    profile = applied["profile"]["id"]
    sitting = sat(client, bd, profile, stage="technical")
    client.post("/api/assessments",
                json={"profile_id": profile, "interview_id": sitting["id"],
                      "title": "Small RAG pipeline", "due_at": when(2, "17:00")},
                headers=bd)

    rows = {row["id"]: row for row in
            client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()["rows"]}
    attached = rows[sitting["id"]]["assessments"]
    assert [a["title"] for a in attached] == ["Small RAG pipeline"]


def test_an_overdue_take_home_reaches_every_dashboard(client, admin, bd, dev, applied):
    """A missed deadline is the one thing here that goes wrong silently. Every
    other figure understates itself when nobody touches it; this one changes
    nothing on any screen until the client's next email — so it has to be on
    all of them.
    """
    profile = applied["profile"]["id"]
    client.post("/api/assessments",
                json={"profile_id": profile, "title": "Late take-home",
                      "due_at": when(-2, "17:00")},
                headers=bd)

    mine = client.get("/api/dashboard/me", headers=bd).json()
    assert mine["assessments"]["counts"]["overdue"] >= 1

    org = client.get("/api/dashboard/overview", headers=admin).json()
    assert org["assessments"]["counts"]["overdue"] >= 1

    desk = client.get("/api/dashboard/dev", headers=dev).json()
    assert desk["assessments"]["counts"]["overdue"] >= 1

    detail = client.get(f"/api/dashboard/profiles/{profile}", headers=bd).json()
    assert detail["assessments"]["counts"]["overdue"] == 1

    # And on the profile's own row, so a board about how much went out cannot
    # stay silent about the test that could lose it.
    row = next(p for p in mine["profiles"] if p["profile_id"] == profile)
    assert row["assessments_open"] == 1
    assert row["assessments_overdue"] == 1


def test_the_developer_board_says_who_owes_a_take_home(client, admin, bd, applied):
    """Free on Thursday is not free when a test is due Friday, and a manager
    reading availability off the diary alone books straight over it."""
    profile = applied["profile"]["id"]
    client.post("/api/assessments",
                json={"profile_id": profile, "title": "Weekend eater",
                      "due_at": when(1, "17:00")},
                headers=bd)

    board = client.get("/api/dashboard/overview", headers=admin).json()["developers"]
    mine = next(row for row in board if row["name"] == "Dev Pipe")
    assert mine["assessments_open"] >= 1


def test_the_pipeline_downloads_as_a_spreadsheet(client, bd, dev, applied):
    """Everything downloadable until now counted what went out, and a team can
    improve all of that without winning a single piece of work. This is the
    other half — the part somebody is asked about at the end of a quarter."""
    from openpyxl import load_workbook

    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, stage="screening")
    client.post(f"/api/interviews/{first['id']}/next-round",
                json={"scheduled_at": when(-1, "10:00")}, headers=bd)
    client.post("/api/assessments",
                json={"profile_id": profile, "title": "Small RAG pipeline",
                      "due_at": when(-1, "17:00")},
                headers=bd)

    got = client.get(f"/api/pipeline.xlsx?profile_id={profile}", headers=bd)
    assert got.status_code == 200, got.text
    book = load_workbook(io.BytesIO(got.content))
    assert book.sheetnames == ["Conversations", "Take-homes"]

    talks = [[c.value for c in row] for row in book["Conversations"].iter_rows(min_row=2)]
    assert any("2 of 2" in (row[5] or "") for row in talks)     # the chain is legible

    tests = [[c.value for c in row] for row in book["Take-homes"].iter_rows(min_row=2)]
    # Said in words: a file outlives the screen that would explain a status.
    assert any("overdue" in (row[5] or "") for row in tests)


def test_a_stranger_cannot_download_someone_elses_pipeline(client, bd, other_bd, applied):
    sat(client, bd, applied["profile"]["id"])
    refused = client.get(f"/api/pipeline.xlsx?profile_id={applied['profile']['id']}",
                         headers=other_bd)
    assert refused.status_code == 403


def test_the_dispatched_sheet_keeps_who_found_each_job(client, admin, bd, applied):
    """The download is what somebody works through on a train, and it should
    not be a worse document than the screen it came from."""
    from openpyxl import load_workbook

    got = client.get(f"/api/batches/{applied['batch']}/profiles/"
                     f"{applied['profile']['id']}/sheet.xlsx", headers=bd)
    assert got.status_code == 200, got.text
    sheet = load_workbook(io.BytesIO(got.content)).worksheets[0]
    headers = [cell.value for cell in sheet[1]]
    assert "Found by" in headers and "Description link" in headers

    column = headers.index("Found by")
    rows = [[c.value for c in row] for row in sheet.iter_rows(min_row=2)]
    assert any(row[column] for row in rows), "nothing said who found these"


def test_nothing_follows_a_round_that_was_called_off(client, bd, applied):
    """A cancelled call never happened, so it cleared nothing. Marking it
    passed on the way to booking a second round would invent a conversation."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile)
    client.patch(f"/api/interviews/{first['id']}", json={"status": "cancelled"}, headers=bd)

    refused = client.post(f"/api/interviews/{first['id']}/next-round", json={}, headers=bd)
    assert refused.status_code == 400
    assert "called off" in refused.json()["detail"]

    # And it is still a cancellation afterwards, not a pass.
    rows = {row["id"]: row for row in
            client.get(f"/api/interviews?profile_id={profile}", headers=bd).json()["rows"]}
    assert rows[first["id"]]["status"] == "cancelled"
    assert rows[first["id"]]["outcome"] == "pending"


def test_the_whole_posting_travels_onto_the_interview(client, bd, applied):
    """Six things, and a BD reading a client's reply three weeks later wants
    all of them. Going back to the record for the platform or the day it went
    out is exactly the retyping the record exists to stop."""
    profile = applied["profile"]["id"]
    record = next(r for r in
                  client.get(f"/api/jobs?profile_id={profile}", headers=bd).json()["rows"]
                  if r["url"] and r["description_url"])

    made = client.post("/api/interviews",
                       json={"profile_id": profile, "scheduled_at": "",
                             "job_id": record["job_id"]}, headers=bd)
    assert made.status_code == 201, made.text
    job = made.json()["job"]

    assert job["title"] == record["title"]
    assert job["company"] == record["company"]
    assert job["url"] == record["url"]
    assert job["description_url"] == record["description_url"]
    assert job["platform"] == record["platform"]
    # The date the BD wrote on their sheet, not the day the cycle was built.
    assert job["applied_on"] == record["applied_on"]

    # And it is still all there on the list the waiting-on-a-time table reads.
    waiting = client.get(f"/api/interviews?profile_id={profile}",
                         headers=bd).json()["awaiting_time"]
    row = next(r for r in waiting if r["id"] == made.json()["id"])
    assert row["job"]["applied_on"] == record["applied_on"]
    assert row["job"]["platform"] == record["platform"]


def test_the_applied_date_shown_is_this_profiles_own(client, bd, applied):
    """Two identities can have applied to one posting on different days, and
    showing one of them under the other is worse than showing nothing."""
    mine, theirs = applied["profile"]["id"], applied["other"]["id"]
    shared = [r for r in
              client.get(f"/api/jobs?profile_id={mine}", headers=bd).json()["rows"]]
    others = {r["job_id"]: r for r in
              client.get(f"/api/jobs?profile_id={theirs}", headers=bd).json()["rows"]}
    overlap = next((r for r in shared if r["job_id"] in others), None)
    assert overlap, "the fixture is meant to share postings between the two profiles"

    for profile_id, expected in ((mine, overlap), (theirs, others[overlap["job_id"]])):
        row = client.post("/api/interviews",
                          json={"profile_id": profile_id, "scheduled_at": "",
                                "job_id": overlap["job_id"]}, headers=bd).json()
        assert row["job"]["applied_on"] == expected["applied_on"]


def test_a_take_home_carries_the_whole_posting_too(client, bd, applied):
    """A take-home and the call that produced it describe one conversation.
    Two screens disagreeing about which board it came off, or when the
    application went out, is worse than neither of them saying."""
    profile = applied["profile"]["id"]
    record = next(r for r in
                  client.get(f"/api/jobs?profile_id={profile}", headers=bd).json()["rows"]
                  if r["url"] and r["description_url"])

    made = client.post("/api/assessments",
                       json={"profile_id": profile, "job_id": record["job_id"],
                             "title": "Small RAG pipeline"}, headers=bd)
    assert made.status_code == 201, made.text
    job = made.json()["job"]

    for field in ("title", "company", "url", "description_url", "platform", "applied_on"):
        assert job[field] == record[field], field

    # And still whole on the list every screen reads.
    rows = client.get(f"/api/assessments?profile_id={profile}", headers=bd).json()["rows"]
    row = next(r for r in rows if r["id"] == made.json()["id"])
    assert row["job"]["platform"] == record["platform"]
    assert row["job"]["applied_on"] == record["applied_on"]


def test_a_take_home_set_from_a_call_inherits_that_calls_posting(client, bd, applied):
    """Naming the interview is enough. The call already knows which posting it
    came out of, and asking for it twice is the retyping this all exists to
    stop."""
    profile = applied["profile"]["id"]
    record = next(r for r in
                  client.get(f"/api/jobs?profile_id={profile}", headers=bd).json()["rows"]
                  if r["url"])
    sitting = sat(client, bd, profile, stage="technical", job_id=record["job_id"])

    made = client.post("/api/assessments",
                       json={"profile_id": profile, "interview_id": sitting["id"],
                             "title": "Take-home"}, headers=bd)
    assert made.status_code == 201, made.text
    assert made.json()["job"]["url"] == record["url"]
    assert made.json()["job"]["applied_on"] == record["applied_on"]


def test_the_take_home_applied_date_is_this_profiles_own(client, bd, applied):
    """Same rule as the diary: two identities can have applied on different
    days, and showing one under the other invents a fact."""
    mine, theirs = applied["profile"]["id"], applied["other"]["id"]
    ours = client.get(f"/api/jobs?profile_id={mine}", headers=bd).json()["rows"]
    others = {r["job_id"]: r for r in
              client.get(f"/api/jobs?profile_id={theirs}", headers=bd).json()["rows"]}
    overlap = next((r for r in ours if r["job_id"] in others), None)
    assert overlap, "the fixture is meant to share postings between the two profiles"

    for profile_id, expected in ((mine, overlap), (theirs, others[overlap["job_id"]])):
        row = client.post("/api/assessments",
                          json={"profile_id": profile_id, "job_id": overlap["job_id"],
                                "title": "Shared posting"}, headers=bd).json()
        assert row["job"]["applied_on"] == expected["applied_on"]


# --------------------------------------------------------------------------- #
# The range report — what somebody did between two dates
# --------------------------------------------------------------------------- #

def today_iso():
    from app.models import working_today
    return working_today().isoformat()


def days_ago(n):
    import datetime as _dt
    from app.models import working_today
    return (working_today() - _dt.timedelta(days=n)).isoformat()


def test_no_dates_means_no_report(client, bd, applied):
    """The report answers a question about dates. Inventing a default window
    would put a figure on screen nobody asked the question behind."""
    assert client.get("/api/dashboard/me", headers=bd).json()["report"] is None


def test_the_report_splits_what_you_found_from_what_you_were_handed(
        client, admin, bd, applied):
    """The number a BD is actually asked for at the end of a week: of
    everything that went out, how much did I find myself.

    An application against a posting off this profile's own sheet is one it
    found; one against a posting a colleague found and the cycle handed over is
    not. The split is exact — a logged job has a batch_applications row and a
    dispatched one does not — rather than a guess.
    """
    profile = applied["profile"]["id"]
    report = client.get(
        f"/api/dashboard/me?date_from={days_ago(30)}&date_to={today_iso()}",
        headers=bd).json()["report"]

    assert report is not None
    sent = report["applied"]
    # The fixture hands in six postings on this profile's own sheet.
    assert sent["own_found"] >= 6

    # Scoped to the profile the split is about. `/dashboard/me` covers every
    # profile this BD runs, so an absolute zero there is a claim about whatever
    # else happened to run first in this module rather than about this split.
    stats = client.get(f"/api/dashboard/profiles/{profile}?batch_id={applied['batch']}",
                       headers=bd).json()["stats"]
    assert stats["own_found"] >= 6
    assert stats["from_others"] == 0, (
        "nothing off this profile's dispatched list has been marked applied")
    assert sent["total"] == sent["own_found"] + sent["from_others"]

    # Now work one job off the list somebody else found.
    sheets = client.get(f"/api/batches/{applied['batch']}/my-sheets",
                        headers=bd).json()["profiles"]
    mine = next(p for p in sheets if p["id"] == profile)
    assert mine["jobs"], "the fixture is meant to dispatch something here"
    client.patch(f"/api/assignments/{mine['jobs'][0]['id']}",
                 json={"status": "applied"}, headers=bd)

    after = client.get(
        f"/api/dashboard/me?date_from={days_ago(30)}&date_to={today_iso()}",
        headers=bd).json()["report"]["applied"]
    # One more than before, measured rather than assumed — the person-wide
    # report covers every profile this BD runs.
    assert after["from_others"] == sent["from_others"] + 1
    assert after["total"] == after["own_found"] + after["from_others"]


def test_the_report_counts_what_was_turned_down(client, bd, applied):
    """Measured as the change, not as an absolute.

    The report covers every profile this BD runs, so an exact total is a
    statement about whatever else happened to run first in the module. One skip
    should move it by exactly one, and that is true whatever else is there.
    """
    window = f"date_from={days_ago(30)}&date_to={today_iso()}"
    before = client.get(f"/api/dashboard/me?{window}",
                        headers=bd).json()["report"]["applied"]["skipped"]

    profile = applied["profile"]["id"]
    sheets = client.get(f"/api/batches/{applied['batch']}/my-sheets",
                        headers=bd).json()["profiles"]
    mine = next(p for p in sheets if p["id"] == profile)
    client.patch(f"/api/assignments/{mine['jobs'][0]['id']}",
                 json={"status": "skipped", "reason": "Wrong seniority."}, headers=bd)

    after = client.get(f"/api/dashboard/me?{window}",
                       headers=bd).json()["report"]["applied"]["skipped"]
    assert after == before + 1


def test_the_report_averages_over_the_window_asked_for(client, bd, applied):
    """Per-day is over the days requested, not the days worked — a fortnight
    with one busy Tuesday averages low, and that is the honest answer."""
    report = client.get(
        f"/api/dashboard/me?date_from={days_ago(9)}&date_to={today_iso()}",
        headers=bd).json()["report"]
    assert report["days"] == 10
    assert report["applied"]["per_day"] == round(report["applied"]["total"] / 10, 1)
    assert report["applied"]["active_days"] >= 1
    assert report["applied"]["busiest"]["count"] >= 1


def test_a_window_before_any_work_is_empty_rather_than_missing(client, bd, applied):
    report = client.get(
        f"/api/dashboard/me?date_from={days_ago(400)}&date_to={days_ago(380)}",
        headers=bd).json()["report"]
    assert report["applied"]["total"] == 0
    assert report["heard_back"]["conversations"] == 0
    assert report["interviews"]["sittings"] == 0


def test_how_far_counts_conversations_not_sittings(client, bd, dev, applied):
    """"How many clients did I reach a second round with" is a question about
    clients. A chain of three sittings is one answer to it, not three —
    counting rows would say a team that ran one long process beat a team that
    reached four clients once each."""
    profile = applied["profile"]["id"]

    # One client, three rounds.
    first = sat(client, bd, profile, days=-4, stage="screening", client="Longhaul Ltd")
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={"scheduled_at": when(-3, "10:00")}, headers=bd).json()
    client.post(f"/api/interviews/{second['id']}/next-round",
                json={"scheduled_at": when(-2, "10:00")}, headers=bd)

    # Two clients, one round each.
    sat(client, bd, profile, days=-4, clock="12:00", client="Oneshot A")
    sat(client, bd, profile, days=-4, clock="13:00", client="Oneshot B")

    report = client.get(
        f"/api/dashboard/profiles/{profile}?date_from={days_ago(10)}"
        f"&date_to={today_iso()}", headers=bd).json()["report"]["interviews"]

    assert report["sittings"] == 5            # five calls happened
    assert report["conversations"] == 3       # with three clients
    assert report["one_round"] == 2           # two never went past the first
    assert report["two_plus"] == 1            # one did
    assert report["three_plus"] == 1
    assert report["furthest"] == 3


def test_a_chain_starting_before_the_window_is_still_one_conversation(
        client, bd, applied):
    """A report on this week must not turn last week's screening call into a
    second client."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, days=-20, stage="screening", client="Carryover Co")
    client.post(f"/api/interviews/{first['id']}/next-round",
                json={"scheduled_at": when(-2, "11:00")}, headers=bd)

    # A window that contains only the second round.
    report = client.get(
        f"/api/dashboard/profiles/{profile}?date_from={days_ago(5)}"
        f"&date_to={today_iso()}", headers=bd).json()["report"]["interviews"]
    assert report["sittings"] == 1
    assert report["conversations"] == 1
    assert report["two_plus"] == 1            # the chain is two long, not one
    assert report["one_round"] == 0


def test_the_report_names_the_clients_that_came_back(client, bd, applied):
    """One row per conversation. A client who ran three rounds replied once."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, days=-3, client="Northwind Digital")
    client.post(f"/api/interviews/{first['id']}/next-round",
                json={"scheduled_at": when(-2, "14:00")}, headers=bd)

    heard = client.get(
        f"/api/dashboard/profiles/{profile}?date_from={days_ago(10)}"
        f"&date_to={today_iso()}", headers=bd).json()["report"]["heard_back"]

    named = [row["client"] for row in heard["clients"]]
    assert named.count("Northwind Digital") == 1
    assert heard["conversations"] == len(heard["clients"])
    assert 0 <= heard["rate"] <= 100


def test_a_developer_gets_the_same_report_for_their_own_identities(
        client, dev, bd, applied):
    profile = applied["profile"]["id"]
    sat(client, bd, profile, days=-2, client="Their Client")

    report = client.get(
        f"/api/dashboard/dev?date_from={days_ago(10)}&date_to={today_iso()}",
        headers=dev).json()["report"]
    assert report is not None
    assert report["interviews"]["sittings"] >= 1
    assert report["interviews"]["conversations"] >= 1


def test_a_backwards_range_is_refused(client, bd):
    refused = client.get(
        f"/api/dashboard/me?date_from={today_iso()}&date_to={days_ago(5)}",
        headers=bd)
    assert refused.status_code == 400


def test_the_diary_narrows_to_the_range_and_drops_the_usual_lists(
        client, bd, applied):
    """A date range replaces "today / next fortnight" rather than sitting
    beside it — the question was about those dates, not about this week."""
    profile = applied["profile"]["id"]
    sat(client, bd, profile, days=-3, client="In Range")
    sat(client, bd, profile, days=3, clock="09:00", client="Out Of Range")

    ranged = client.get(
        f"/api/interviews?profile_id={profile}&date_from={days_ago(10)}"
        f"&date_to={today_iso()}", headers=bd).json()

    assert ranged["today"] == [] and ranged["upcoming"] == []
    named = {row["client"] for row in ranged["recent"]}
    assert "In Range" in named
    assert "Out Of Range" not in named


def test_a_chain_ending_after_the_window_still_counts_as_two_rounds(
        client, bd, applied):
    """The mirror of the test above, and the one that catches a chain walked in
    only one direction. A screening call this week that already has a technical
    round booked for next month reached a second round — saying "one round
    only" because the second is outside the window would be the report
    contradicting the diary."""
    profile = applied["profile"]["id"]
    first = sat(client, bd, profile, days=-1, stage="screening", client="Ahead Ltd")
    client.post(f"/api/interviews/{first['id']}/next-round",
                json={"scheduled_at": when(20, "11:00")}, headers=bd)

    # A window holding only the first round.
    report = client.get(
        f"/api/dashboard/profiles/{profile}?date_from={days_ago(3)}"
        f"&date_to={today_iso()}", headers=bd).json()["report"]["interviews"]
    assert report["sittings"] == 1
    assert report["conversations"] == 1
    assert report["two_plus"] == 1
    assert report["one_round"] == 0
    assert report["furthest"] == 2
