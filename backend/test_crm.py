"""The client screen: what would be wrong quietly.

Every assertion here is a thing that would look fine on screen and be false. A
status that reads *In conversation* three months after a client said no, two
companies' histories fused because their names looked alike, a cancelled call
counted as a rejection, a note that vanished with the last posting — none of
those raise an error anywhere. They just make the screen lie.

Run with:  pytest test_crm.py -v
"""
import datetime as dt
import io
import itertools

import pytest
from fastapi.testclient import TestClient

from app.matching import client_key

TEAM = [("crm-boss@crm.example.com", "Cee Boss", "admin"),
        ("crm-bd@crm.example.com", "Cass Dee", "bd"),
        ("crm-bd2@crm.example.com", "Dev Otto", "bd"),
        ("crm-dev@crm.example.com", "Del Oper", "dev")]

PASSWORD = "crmpass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/crm.db")
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
    return token(client, "crm-boss@crm.example.com")


@pytest.fixture(scope="module")
def bd(client):
    return token(client, "crm-bd@crm.example.com")


@pytest.fixture(scope="module")
def other_bd(client):
    return token(client, "crm-bd2@crm.example.com")


@pytest.fixture(scope="module")
def dev(client):
    return token(client, "crm-dev@crm.example.com")


@pytest.fixture(scope="module")
def people(client, admin):
    return {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}


@pytest.fixture
def make_profile(client, admin, people):
    def make(bd_email="crm-bd@crm.example.com", headline="Accounts Receivable"):
        body = {"name": f"Crm{next(_serial)}", "headline": headline,
                "user_id": people[bd_email], "dev_user_id": people["crm-dev@crm.example.com"],
                "skills": "billing, collections, support"}
        response = client.post("/api/profiles", json=body, headers=admin)
        assert response.status_code == 201, response.text
        return response.json()
    return make


def when(days: int, clock: str) -> str:
    from app.models import working_today
    return f"{(working_today() + dt.timedelta(days=days)).isoformat()}T{clock}"


def sheet(rows):
    out = io.StringIO()
    out.write("Job Title,Company,Job URL\n")
    for url, title, company in rows:
        out.write(f"{title},{company},{url}\n")
    return out.getvalue().encode()


def cycle(client, admin, name):
    response = client.post("/api/batches", json={"name": name, "mode": "cover",
                                                 "quota": 500, "auto_build_minutes": 0},
                           headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def hand_in(client, batch_id, headers, profile_id, payload):
    response = client.post(f"/api/batches/{batch_id}/uploads",
                           data={"profile_id": profile_id},
                           files={"file": ("s.csv", payload, "text/csv")}, headers=headers)
    assert response.status_code == 201, response.text


def clients_of(client, admin, **params):
    response = client.get("/api/crm/clients", params=params, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def find(payload, name):
    key = client_key(name)
    return next((row for row in payload["clients"] if row["client_key"] == key), None)


def one_client(client, admin, name, url, title="AR Specialist", profile=None,
               bd_headers=None, other=None, other_headers=None):
    """A cycle with this posting on it, built, so applications exist."""
    batch = cycle(client, admin, f"Crm{next(_serial)}")
    hand_in(client, batch, bd_headers, profile["id"],
            sheet([(url, title, name), ("https://x.example.com/pad1", "Pad", "Padding Co")]))
    hand_in(client, batch, other_headers, other["id"],
            sheet([("https://x.example.com/pad2", "Pad Two", "Padding Co"),
                   ("https://x.example.com/pad3", "Pad Three", "Padding Co")]))
    client.post(f"/api/batches/{batch}/compute", headers=admin)
    return batch


# --------------------------------------------------------------------------- #
# The client key
# --------------------------------------------------------------------------- #

def test_one_company_spelled_two_ways_is_one_client():
    """The whole screen groups on this. Get it wrong and a manager reads half a
    client's history and concludes they have never been approached."""
    assert client_key("Northwind Health, Inc.") == client_key("northwind health")
    assert client_key("ACME Solutions Pvt Ltd") == client_key("Acme Solutions")


def test_two_companies_with_similar_names_stay_two_clients():
    """Not fuzzy, on purpose. Fusing two clients' histories on a screen a
    manager reads before an account call is the worst thing this could do."""
    assert client_key("Northwind Health") != client_key("Northwind Digital")
    assert client_key("Larkspur Data") != client_key("Larkspur Media")


# --------------------------------------------------------------------------- #
# Status, which is derived and never typed
# --------------------------------------------------------------------------- #

def test_applications_with_no_reply_read_as_approached(client, admin, bd, other_bd,
                                                       make_profile):
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Quietvale Health",
               "https://careers.quietvale.example.com/jobs/100/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    row = find(clients_of(client, admin), "Quietvale Health")
    assert row is not None, "a client we applied to has to appear"
    assert row["status"] == "approached"
    assert row["applications"] == 1
    assert row["own_jobs"] + row["others_jobs"] == row["applications"]


def test_a_reply_with_no_time_is_its_own_state(client, admin, bd, other_bd,
                                               make_profile):
    """A draft is in no rate and no count of what is coming. Nobody has agreed
    a time, so there is no conversation yet to have a rate about."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Halfway Systems",
               "https://careers.halfway.example.com/jobs/200/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    made = client.post("/api/interviews", json={"profile_id": mine["id"],
                                                "client": "Halfway Systems"},
                       headers=bd)
    assert made.status_code == 201, made.text

    row = find(clients_of(client, admin), "Halfway Systems")
    assert row["status"] == "replied"
    assert row["next_up"] is None, "nothing to turn up to without a time"
    assert row["furthest"] == "", "a draft has not reached a rung"


def test_a_cleared_round_with_nothing_after_reads_as_stalled(client, admin, bd,
                                                             other_bd, dev,
                                                             make_profile):
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Driftwood Labs",
               "https://careers.driftwood.example.com/jobs/300/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    made = client.post("/api/interviews",
                       json={"profile_id": mine["id"], "client": "Driftwood Labs",
                             "scheduled_at": when(-3, "10:00")}, headers=bd).json()
    client.patch(f"/api/interviews/{made['id']}",
                 json={"status": "done", "outcome": "passed"}, headers=dev)

    row = find(clients_of(client, admin), "Driftwood Labs")
    assert row["status"] == "stalled"


def test_a_hire_never_lands_in_stalled(client, admin, bd, other_bd, dev, make_profile):
    """A hire clears a round and has nothing booked after it, which is what
    stalled looks for. It is the one case where that is the point."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Summit Freight",
               "https://careers.summit.example.com/jobs/400/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    made = client.post("/api/interviews",
                       json={"profile_id": mine["id"], "client": "Summit Freight",
                             "scheduled_at": when(-4, "10:00")}, headers=bd).json()
    client.patch(f"/api/interviews/{made['id']}",
                 json={"status": "done", "outcome": "hired"}, headers=dev)

    row = find(clients_of(client, admin), "Summit Freight")
    assert row["status"] == "hired"


def test_an_open_test_outranks_the_interview(client, admin, bd, other_bd, dev,
                                             make_profile):
    """A test out is waiting on somebody here. In conversation is not."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Ledgerworks",
               "https://careers.ledgerworks.example.com/jobs/500/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    sitting = client.post("/api/interviews",
                          json={"profile_id": mine["id"], "client": "Ledgerworks",
                                "scheduled_at": when(2, "10:00")}, headers=bd).json()
    assert find(clients_of(client, admin), "Ledgerworks")["status"] == "in_conversation"

    made = client.post("/api/assessments",
                       json={"profile_id": mine["id"], "client": "Ledgerworks",
                             "interview_id": sitting["id"], "title": "Take-home"},
                       headers=bd)
    assert made.status_code == 201, made.text

    row = find(clients_of(client, admin), "Ledgerworks")
    assert row["status"] == "test_out"
    assert row["open_tests"] == 1


def test_a_cancelled_interview_is_not_a_rejection(client, admin, bd, other_bd,
                                                  make_profile):
    """A client who pulled out before the call did not reject anybody, and
    filing them under Closed would make a quiet week look like a bad one."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Ashvale Group",
               "https://careers.ashvale.example.com/jobs/600/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    made = client.post("/api/interviews",
                       json={"profile_id": mine["id"], "client": "Ashvale Group",
                             "scheduled_at": when(1, "10:00")}, headers=bd).json()
    client.patch(f"/api/interviews/{made['id']}", json={"status": "cancelled"},
                 headers=bd)

    row = find(clients_of(client, admin), "Ashvale Group")
    assert row["status"] != "closed"
    assert row["status"] == "approached", "back to what it was before the reply"


# --------------------------------------------------------------------------- #
# The window, the arithmetic, and found twice
# --------------------------------------------------------------------------- #

def test_the_date_window_reads_when_the_work_happened(client, admin, bd, other_bd,
                                                      make_profile):
    """Dated by the day the work happened, never by which cycle it belonged to.
    A window before any of it shows nothing rather than everything."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Timeworn Freight",
               "https://careers.timeworn.example.com/jobs/700/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    long_ago = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    older = (dt.date.today() - dt.timedelta(days=380)).isoformat()
    assert find(clients_of(client, admin, date_from=long_ago, date_to=older),
                "Timeworn Freight") is None

    today = dt.date.today().isoformat()
    assert find(clients_of(client, admin, date_from=today, date_to=today),
                "Timeworn Freight") is not None


def test_the_columns_add_up(client, admin, bd, other_bd, make_profile):
    """Applications sent is own jobs plus others' jobs, at every client, always.
    Two columns that do not add to the third is the defect a manager notices
    first and trusts the screen less for ever after."""
    payload = clients_of(client, admin, per_page=200)
    assert payload["clients"], "the fixtures put something here"
    for row in payload["clients"]:
        assert row["own_jobs"] + row["others_jobs"] == row["applications"], row["client"]


def test_one_posting_two_profiles_is_found_twice_once(client, admin, bd, other_bd,
                                                      make_profile):
    """Two profiles finding one job is one piece of duplicated effort. Counting
    it once per finder turns a figure meant to be acted on into one nobody
    trusts."""
    mine = make_profile()
    theirs = make_profile("crm-bd2@crm.example.com")
    url = "https://careers.doubled.example.com/jobs/800/ar-specialist"

    batch = cycle(client, admin, f"Crm{next(_serial)}")
    hand_in(client, batch, bd, mine["id"],
            sheet([(url, "AR Specialist", "Doubled Up Ltd")]))
    hand_in(client, batch, other_bd, theirs["id"],
            sheet([(url, "AR Specialist", "Doubled Up Ltd")]))
    client.post(f"/api/batches/{batch}/compute", headers=admin)

    row = find(clients_of(client, admin, per_page=200), "Doubled Up Ltd")
    assert row["applications"] == 2, "two profiles applied"
    assert row["found_twice"] == 1, "one posting, found twice"

    detail = client.get(f"/api/crm/clients/{row['client_key']}", headers=admin).json()
    assert len(detail["found_twice"]) == 1


# --------------------------------------------------------------------------- #
# Permission, and the note
# --------------------------------------------------------------------------- #

def test_only_a_manager_may_read_any_of_it(client, bd, dev, make_profile):
    """Hidden tabs are a courtesy. This is the control."""
    mine = make_profile()
    for headers in (bd, dev):
        assert client.get("/api/crm/clients", headers=headers).status_code == 403
        assert client.get("/api/crm/clients/anything", headers=headers).status_code == 403
        assert client.put("/api/crm/clients/anything/note", json={"note": "x"},
                          headers=headers).status_code == 403
        assert client.get("/api/crm/export.xlsx", headers=headers).status_code == 403


def test_a_note_outlives_every_posting_at_that_client(client, admin, bd, other_bd,
                                                      make_profile):
    """The moment a manager most wants to read "we approached them in March and
    they went quiet" is after the postings are gone."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Vanishing Point Ltd",
               "https://careers.vanishing.example.com/jobs/900/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    row = find(clients_of(client, admin, per_page=200), "Vanishing Point Ltd")
    key = row["client_key"]
    saved = client.put(f"/api/crm/clients/{key}/note",
                       json={"priority": True, "being_worked": True,
                             "note": "Approached in March, went quiet."},
                       headers=admin)
    assert saved.status_code == 200, saved.text
    assert saved.json()["priority"] is True
    assert saved.json()["updated_by"] == "Cee Boss"

    record = client.get("/api/jobs", params={"q": "Vanishing Point"},
                        headers=admin).json()
    for entry in record["rows"]:
        client.delete(f"/api/jobs/{entry['job_id']}",
                      params={"profile_id": entry["profile_id"]}, headers=admin)

    after = client.get(f"/api/crm/clients/{key}", headers=admin)
    assert after.status_code == 200, "the note is the client now"
    assert after.json()["note"]["note"] == "Approached in March, went quiet."
    assert after.json()["client"]["client"] == "Vanishing Point Ltd", (
        "the spelling a person recognises, not the slug")


def test_the_being_worked_flag_reaches_the_bd_as_a_notice(client, admin, bd,
                                                          other_bd, make_profile):
    """Advisory, and surfaced where a BD is certainly reading: the dialog that
    already fires as a link is typed. It never blocks the row."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Flagged Holdings",
               "https://careers.flagged.example.com/jobs/1000/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    key = client_key("Flagged Holdings")
    client.put(f"/api/crm/clients/{key}/note",
               json={"being_worked": True, "note": "Head office is on this one."},
               headers=admin)

    answer = client.get("/api/jobs/check", params={
        "url": "https://careers.flagged.example.com/jobs/1001/collections-lead",
        "title": "Collections Lead", "company": "Flagged Holdings",
        "profile_id": mine["id"]}, headers=bd).json()
    assert answer["being_worked"], "a different posting at a flagged client"
    assert answer["being_worked"]["by"] == "Cee Boss"
    assert answer["duplicate"] is False, "advisory, not a duplicate"


def test_an_unflagged_client_says_nothing(client, bd, admin, other_bd, make_profile):
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Unremarkable Co",
               "https://careers.unremarkable.example.com/jobs/1100/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)
    answer = client.get("/api/jobs/check", params={
        "url": "https://careers.unremarkable.example.com/jobs/1101/x",
        "title": "x", "company": "Unremarkable Co"}, headers=bd).json()
    assert answer["being_worked"] is None


# --------------------------------------------------------------------------- #
# The rest of the screen
# --------------------------------------------------------------------------- #

def test_the_drawer_reads_one_conversation_not_four_rows(client, admin, bd,
                                                         other_bd, dev, make_profile):
    """A client who ran three rounds is one story. Three rows look like three
    clients who each said no once."""
    mine, theirs = make_profile(), make_profile("crm-bd2@crm.example.com")
    one_client(client, admin, "Longhaul Partners",
               "https://careers.longhaul.example.com/jobs/1200/ar-specialist",
               profile=mine, bd_headers=bd, other=theirs, other_headers=other_bd)

    first = client.post("/api/interviews",
                        json={"profile_id": mine["id"], "client": "Longhaul Partners",
                              "scheduled_at": when(-6, "10:00")}, headers=bd).json()
    client.patch(f"/api/interviews/{first['id']}",
                 json={"status": "done", "outcome": "passed"}, headers=dev)
    second = client.post(f"/api/interviews/{first['id']}/next-round",
                         json={"scheduled_at": when(-2, "10:00")}, headers=bd).json()
    client.patch(f"/api/interviews/{second['id']}",
                 json={"status": "done", "outcome": "passed"}, headers=dev)

    key = client_key("Longhaul Partners")
    detail = client.get(f"/api/crm/clients/{key}", headers=admin).json()
    assert len(detail["conversations"]) == 1, "one chain, not two rows"
    assert len(detail["conversations"][0]["rounds"]) == 2
    assert detail["conversations"][0]["rounds"][1]["round"] == 2


def test_the_list_paginates_and_counts_before_it_cuts(client, admin):
    """The totals describe the whole answer, not the page. A column header that
    counts only what fits on screen is a number nobody can use."""
    payload = clients_of(client, admin, per_page=2, page=1)
    assert len(payload["clients"]) <= 2
    assert payload["page"]["per_page"] == 2
    assert payload["totals"]["clients"] > 2
    assert sum(payload["totals"]["by_status"].values()) == payload["totals"]["clients"]


def test_the_export_carries_three_sheets(client, admin):
    from openpyxl import load_workbook
    response = client.get("/api/crm/export.xlsx", headers=admin)
    assert response.status_code == 200, response.text
    book = load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Clients", "Conversations", "Tests"]
    assert "Client email" in [c.value for c in book["Conversations"][1]]
