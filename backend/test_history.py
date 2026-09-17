"""Back-loading old spreadsheets, and taking one decision over a whole list.

Two features, tested together because they arrived together and for the same
person: a BD with three months of applying in a file and nothing in the system
to show for it, who then has several hundred postings on their list where the
answer to every one is the same.

What is asserted here is the half that is easy to get wrong and impossible to
notice:

  * an import writes history, not this week's work
  * handing in the same file twice adds only what was missing — the whole
    promise the feature rests on
  * a run that stops part way resumes, and nothing is counted or written twice
  * rows nothing can be read from are reported rather than silently dropped
  * shared imports reach colleagues' lists and unshared ones do not, and the
    importer is never handed their own back
  * a whole selection obeys every rule a single row obeys, including having to
    say why it was skipped
  * the manager's switch is a rule the API keeps, not a button the browser hides
"""
from __future__ import annotations

import io
import itertools

import pytest
from fastapi.testclient import TestClient

PASSWORD = "historypass12345"
TEAM = [("hist-boss@history.example.com", "Hist Boss", "admin"),
        ("hist-one@history.example.com", "Ada Past", "bd"),
        ("hist-two@history.example.com", "Bo Present", "bd")]

_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/history.db")
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


@pytest.fixture(autouse=True)
def switches_on(client, admin):
    """Every test starts from the shipped defaults, whatever the last one did."""
    client.patch("/api/settings", headers=admin,
                 json={"bulk_actions_enabled": True, "team_board_visible": False})
    yield


@pytest.fixture
def make_profile(client, admin):
    def build(owner_email, headline="Accounts Receivable"):
        people = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
        response = client.post("/api/profiles", headers=admin, json={
            "name": f"History {next(_serial)}", "headline": headline,
            "platform": "Indeed", "user_id": people[owner_email]})
        assert response.status_code == 201, response.text
        return response.json()["id"]
    return build


def open_cycle(client, admin, quota=500):
    response = client.post("/api/batches", headers=admin,
                           json={"name": f"History {next(_serial)}", "quota": quota,
                                 "mode": "cover"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def link(n: int) -> str:
    return f"https://www.upwork.com/jobs/~01{n:016x}"


def sheet(numbers, *, extra_rows=()) -> bytes:
    """An old apply sheet, in the shape a BD's own spreadsheet is really in."""
    lines = ["Date,Portal,Client,Link,Job Title"]
    for n in numbers:
        lines.append(f"07/14/2026,Indeed.,Client {n},{link(n)},Role {n}")
    lines.extend(extra_rows)
    return ("\n".join(lines) + "\n").encode()


def upload_history(client, headers, profile_id, body, *, share=True,
                   filename="old-sheet.csv"):
    response = client.post(
        "/api/history/imports", headers=headers,
        data={"profile_id": str(profile_id), "share_with_team": str(share).lower()},
        files={"file": (filename, io.BytesIO(body), "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()


def run_to_the_end(client, headers, import_id):
    """Press run until it says it is finished, the way the browser does."""
    for _ in range(200):
        response = client.post(f"/api/history/imports/{import_id}/run", headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        if result["done"]:
            return result
    raise AssertionError("the import never finished")


def type_in(client, headers, batch_id, profile_id, numbers):
    rows = [{"url": link(n), "title": f"Role {n}", "company": f"Client {n}",
             "platform": "Indeed", "date": "2026-08-01 09:00"} for n in numbers]
    response = client.put(f"/api/batches/{batch_id}/profiles/{profile_id}/entries",
                          headers=headers, json={"rows": rows})
    assert response.status_code == 200, response.text


def dispatched(client, headers, batch_id, profile_id):
    body = client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet",
                      headers=headers).json()
    return {row["url"] for row in body["jobs"]}


# --------------------------------------------------------------------------- #
# What an import writes
# --------------------------------------------------------------------------- #

def test_an_import_files_history_and_not_this_weeks_work(client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])

    started = upload_history(client, bd, profile, sheet(range(9000, 9030)))
    assert started["row_count"] == 30 and started["usable_count"] == 30
    assert started["cursor"] == 0, "nothing is written until the run is asked for"

    result = run_to_the_end(client, bd, started["id"])
    assert result["added"] == 30 and result["already"] == 0

    # In the profile's all-time record...
    record = client.get("/api/jobs", headers=bd,
                        params={"profile_id": profile, "limit": 100}).json()
    assert record["total"] == 30

    # ...and carrying no cycle, because months-old work is not this week's.
    from app.main import SessionLocal
    from app.models import Application
    db = SessionLocal()
    stamps = db.query(Application.batch_id, Application.applied_on).filter(
        Application.profile_id == profile).all()
    db.close()
    assert {batch_id for batch_id, _ in stamps} == {None}
    # The date the BD typed, normalised — the same shape whatever the sheet said.
    assert {stamp for _, stamp in stamps} == {"2026-07-14"}


def test_rows_nothing_can_be_read_from_are_reported_not_dropped(
        client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])

    # Three real rows, two that carry no link, no client and no title at all.
    body = sheet(range(9100, 9103), extra_rows=[",,,,", "07/14/2026,Indeed,,,"])
    started = upload_history(client, bd, profile, body)
    assert started["row_count"] == 5 and started["usable_count"] == 3

    result = run_to_the_end(client, bd, started["id"])
    assert (result["added"], result["unusable"]) == (3, 2)


# --------------------------------------------------------------------------- #
# The promise the whole feature rests on
# --------------------------------------------------------------------------- #

def test_handing_in_the_same_file_again_adds_only_what_was_missing(
        client, admin, make_profile):
    """The 3,000-row story: 2,750 landed, 250 did not, and the fix is the file.

    The first import stands in for the one that was interrupted — it carries the
    rows that made it. The second is the same complete sheet handed in again,
    and it must add the missing 250 and touch nothing else.
    """
    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])

    landed = list(range(9200, 9475))                 # 275 rows that got in
    missing = list(range(9475, 9500))                # 25 that never did
    first = run_to_the_end(client, bd,
                           upload_history(client, bd, profile, sheet(landed))["id"])
    assert first["added"] == 275

    whole = upload_history(client, bd, profile, sheet(landed + missing))
    assert whole["row_count"] == 300
    second = run_to_the_end(client, bd, whole["id"])

    assert second["added"] == 25, "only the rows that never landed"
    assert second["already"] == 275, "and the rest recognised, not rewritten"

    record = client.get("/api/jobs", headers=bd,
                        params={"profile_id": profile, "limit": 1}).json()
    assert record["total"] == 300, "no row is on record twice"


def test_a_run_that_stops_part_way_carries_on_from_where_it_stopped(
        client, admin, make_profile, monkeypatch):
    """A closed laptop costs progress, never data."""
    from app import history

    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])
    started = upload_history(client, bd, profile, sheet(range(9600, 9700)))

    # A small chunk, so one press cannot finish it — which is what the real
    # thing looks like on a sheet of three thousand.
    monkeypatch.setattr(history, "CHUNK", 30)

    first = client.post(f"/api/history/imports/{started['id']}/run", headers=bd).json()
    assert first["done"] is False and first["cursor"] == 30 and first["added"] == 30

    # ...and now nobody presses anything for a while. The import remembers.
    listed = client.get("/api/history/imports", headers=bd,
                        params={"profile_id": profile}).json()["imports"]
    waiting = next(r for r in listed if r["id"] == started["id"])
    assert waiting["status"] == "running" and waiting["cursor"] == 30

    monkeypatch.undo()
    finished = run_to_the_end(client, bd, started["id"])
    assert finished["added"] == 100, "the other 70, and the first 30 not again"
    assert finished["already"] == 0

    record = client.get("/api/jobs", headers=bd,
                        params={"profile_id": profile, "limit": 1}).json()
    assert record["total"] == 100


def test_the_columns_stop_being_editable_once_rows_are_written(
        client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])
    started = upload_history(client, bd, profile, sheet(range(9800, 9810)))

    # Before: fine, and the count is taken again through the new columns.
    fixed = client.patch(f"/api/history/imports/{started['id']}", headers=bd,
                         json={"mapping": {**started["mapping"], "url": ""}})
    assert fixed.status_code == 200 and fixed.json()["usable_count"] == 10

    run_to_the_end(client, bd, started["id"])
    refused = client.patch(f"/api/history/imports/{started['id']}", headers=bd,
                           json={"mapping": started["mapping"]})
    assert refused.status_code == 400
    assert "again" in refused.json()["detail"]


def test_an_import_belongs_to_the_person_who_runs_the_profile(
        client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    stranger = token(client, TEAM[2][0])
    refused = client.post(
        "/api/history/imports", headers=stranger,
        data={"profile_id": str(profile)},
        files={"file": ("x.csv", io.BytesIO(sheet([9900])), "text/csv")})
    assert refused.status_code == 403


# --------------------------------------------------------------------------- #
# Who the back-loaded postings reach
# --------------------------------------------------------------------------- #

def test_shared_history_reaches_colleagues_and_never_the_importer(
        client, admin, make_profile):
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    me, them = token(client, TEAM[1][0]), token(client, TEAM[2][0])
    batch = open_cycle(client, admin)

    # Both hand in a sheet, so the cycle has something to compare.
    type_in(client, me, batch, mine, [9010])
    type_in(client, them, batch, theirs, [9011])

    old = list(range(9020, 9040))
    run_to_the_end(client, me, upload_history(client, me, mine, sheet(old))["id"])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    reached = dispatched(client, them, batch, theirs)
    assert {link(n) for n in old} <= reached, "the colleague is offered all of it"

    back = dispatched(client, me, batch, mine)
    assert not ({link(n) for n in old} & back), \
        "and the importer is never handed back their own history"


def test_a_back_load_never_crowds_out_this_weeks_postings(client, admin, make_profile):
    """The reason `defer` exists.

    Three months of old postings and a cap of five. Without the deferral the
    back-load — which is bigger, and placed first whenever it happens to be
    scarcer — would spend the whole cap on June before the list reached a single
    thing found this week, which is worse than never importing at all.
    """
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    me, them = token(client, TEAM[1][0]), token(client, TEAM[2][0])
    batch = open_cycle(client, admin, quota=5)

    this_week = list(range(8500, 8505))
    type_in(client, me, batch, mine, this_week)
    type_in(client, them, batch, theirs, [8600])

    old_work = list(range(8700, 8760))       # twelve times as much history
    run_to_the_end(client, me,
                   upload_history(client, me, mine, sheet(old_work))["id"])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    reached = dispatched(client, them, batch, theirs)
    assert len(reached) == 5, "the cap held"
    assert reached == {link(n) for n in this_week},         "and every place went to what the cycle itself gathered"


def test_history_kept_private_reaches_nobody(client, admin, make_profile):
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    me, them = token(client, TEAM[1][0]), token(client, TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, me, batch, mine, [9050])
    type_in(client, them, batch, theirs, [9051])

    old = list(range(9060, 9070))
    run_to_the_end(client, me,
                   upload_history(client, me, mine, sheet(old), share=False)["id"])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    assert not ({link(n) for n in old} & dispatched(client, them, batch, theirs))


def test_the_manager_can_switch_an_import_off_after_the_fact(
        client, admin, make_profile):
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    me, them = token(client, TEAM[1][0]), token(client, TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, me, batch, mine, [9080])
    type_in(client, them, batch, theirs, [9081])

    old = list(range(9085, 9095))
    record = upload_history(client, me, mine, sheet(old))
    run_to_the_end(client, me, record["id"])

    turned_off = client.patch(f"/api/history/imports/{record['id']}", headers=admin,
                              json={"share_with_team": False})
    assert turned_off.status_code == 200
    assert turned_off.json()["share_with_team"] is False

    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200
    assert not ({link(n) for n in old} & dispatched(client, them, batch, theirs))


def test_forgetting_a_sheet_keeps_the_work_it_filed(client, admin, make_profile):
    profile = make_profile(TEAM[1][0])
    bd = token(client, TEAM[1][0])
    record = upload_history(client, bd, profile, sheet(range(9300, 9310)))
    run_to_the_end(client, bd, record["id"])

    assert client.delete(f"/api/history/imports/{record['id']}",
                         headers=bd).status_code == 200
    assert not [r for r in client.get("/api/history/imports", headers=bd,
                                      params={"profile_id": profile}).json()["imports"]]

    # The applications are the profile's record of work really done, and stay.
    assert client.get("/api/jobs", headers=bd,
                      params={"profile_id": profile, "limit": 1}).json()["total"] == 10


# --------------------------------------------------------------------------- #
# One decision over a whole selection
# --------------------------------------------------------------------------- #

@pytest.fixture
def a_list(client, admin, make_profile):
    """A profile with a list of others' jobs on it, and its BD's headers."""
    mine = make_profile(TEAM[1][0])
    theirs = make_profile(TEAM[2][0])
    me, them = token(client, TEAM[1][0]), token(client, TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, me, batch, mine, [7000, 7001])
    type_in(client, them, batch, theirs, list(range(7100, 7120)))
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    rows = client.get(f"/api/batches/{batch}/profiles/{mine}/sheet",
                      headers=me).json()["jobs"]
    assert len(rows) >= 20
    return {"batch": batch, "profile": mine, "bd": me, "rows": rows}


def test_a_whole_selection_can_be_marked_applied_in_one_press(client, a_list):
    ids = [row["id"] for row in a_list["rows"]]
    done = client.post("/api/assignments/bulk", headers=a_list["bd"],
                       json={"ids": ids, "status": "applied"})
    assert done.status_code == 200, done.text
    assert done.json()["updated"] == len(ids)

    # Marked applied is the profile's history from now on, exactly as it is
    # when the dropdown on one row is used.
    record = client.get("/api/jobs", headers=a_list["bd"],
                        params={"profile_id": a_list["profile"], "limit": 1}).json()
    assert record["total"] >= len(ids)


def test_a_selection_cannot_be_skipped_without_saying_why(client, a_list):
    ids = [row["id"] for row in a_list["rows"][:5]]
    refused = client.post("/api/assignments/bulk", headers=a_list["bd"],
                          json={"ids": ids, "status": "skipped"})
    assert refused.status_code == 400
    assert "why" in refused.json()["detail"].lower()

    ok = client.post("/api/assignments/bulk", headers=a_list["bd"],
                     json={"ids": ids, "status": "skipped",
                           "reason": "Client we stopped working in June."})
    assert ok.status_code == 200 and ok.json()["updated"] == 5

    # The one reason goes on every row, which is what the manager reads back.
    turned_down = client.get(f"/api/batches/{a_list['batch']}/skipped",
                             headers=a_list["bd"],
                             params={"profile_id": a_list["profile"]}).json()
    assert len(turned_down["rows"]) == 5
    assert {r["reason"] for r in turned_down["rows"]} == {
        "Client we stopped working in June."}


def test_a_selection_reaching_somebody_elses_profile_is_refused_whole(
        client, admin, a_list, make_profile):
    theirs = make_profile(TEAM[2][0])
    them = token(client, TEAM[2][0])
    batch = open_cycle(client, admin)
    type_in(client, a_list["bd"], batch, a_list["profile"], [7200])
    type_in(client, them, batch, theirs, [7300, 7301])
    assert client.post(f"/api/batches/{batch}/compute", headers=admin).status_code == 200

    not_mine = [row["id"] for row in client.get(
        f"/api/batches/{batch}/profiles/{theirs}/sheet", headers=them).json()["jobs"]]
    mixed = [a_list["rows"][0]["id"], *not_mine[:2]]

    refused = client.post("/api/assignments/bulk", headers=a_list["bd"],
                          json={"ids": mixed, "status": "applied"})
    assert refused.status_code == 403

    # Whole, not half: the row this person does own is untouched too.
    still_there = client.get(f"/api/batches/{a_list['batch']}/profiles/"
                             f"{a_list['profile']}/sheet",
                             headers=a_list["bd"]).json()["jobs"]
    assert next(r for r in still_there
                if r["id"] == a_list["rows"][0]["id"])["status"] == "pending"


def test_the_manager_can_take_the_whole_press_away(client, admin, a_list):
    off = client.patch("/api/settings", headers=admin,
                       json={"bulk_actions_enabled": False})
    assert off.status_code == 200 and off.json()["bulk_actions_enabled"] is False

    # Every screen can read it, which is how the button knows to be absent.
    assert client.get("/api/settings",
                      headers=a_list["bd"]).json()["bulk_actions_enabled"] is False

    refused = client.post("/api/assignments/bulk", headers=a_list["bd"],
                          json={"ids": [a_list["rows"][0]["id"]], "status": "applied"})
    assert refused.status_code == 403, "the rule is the server's, not the browser's"

    # One at a time still works. Turning the press off is not turning the
    # screen off.
    single = client.patch(f"/api/assignments/{a_list['rows'][0]['id']}",
                          headers=a_list["bd"], json={"status": "applied"})
    assert single.status_code == 200


def test_a_bd_cannot_touch_the_switch(client, a_list):
    refused = client.patch("/api/settings", headers=a_list["bd"],
                           json={"bulk_actions_enabled": False})
    assert refused.status_code == 403


def test_one_press_is_capped(client, a_list):
    from app.main import BULK_MAX
    refused = client.post("/api/assignments/bulk", headers=a_list["bd"],
                          json={"ids": list(range(1, BULK_MAX + 2)), "status": "applied"})
    assert refused.status_code == 400
    assert str(BULK_MAX) in refused.json()["detail"]
