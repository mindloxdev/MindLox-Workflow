"""Dashboards, and who may see whose figures.

    pytest test_dashboard.py -v

Two gates, and they are not the same gate:

  * a person's OWN dashboard is shut until the manager opens it for them
    individually. A manager can see anybody's at any time, and what they see
    is the same payload that person would get.
  * the TEAM BOARD — everyone side by side — is a second, workspace-wide
    switch, and it only reaches people who already have a dashboard.

Both are enforced on the server. Hiding a tab is not refusing a request.

Also pinned down: a BD's dashboard shows their own profiles and nobody else's,
a profile can be taken off the shared board, and the numbers mean what the
labels say after real work goes through.

Written to share a database with the rest of the suite: pytest imports app.main
once, so whichever test module runs first decides where the data lives. Nothing
here asserts on a workspace-wide total it did not create, and every account and
profile it makes carries a name no other module uses.
"""
import io
import itertools

import pytest
from fastapi.testclient import TestClient

TEAM = [("dash-boss@dashboard.example.com", "Dash Boss", "admin"),
        ("dash-one@dashboard.example.com", "Dana One", "bd"),
        ("dash-two@dashboard.example.com", "Dev Two", "bd")]

PASSWORD = "dashpass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/dash.db")
    from app.main import SessionLocal, app, engine, hash_password  # noqa: E402
    from app.models import Base, User  # noqa: E402

    Base.metadata.create_all(engine)
    db = SessionLocal()
    for email, name, role in TEAM:
        if not db.query(User).filter(User.email == email).first():
            # Opened here so the figure tests are not all about permission. The
            # gate itself is exercised by the tests that close it again.
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
    return token(client, "dash-boss@dashboard.example.com")


@pytest.fixture(scope="module")
def dana(client):
    return token(client, "dash-one@dashboard.example.com")


@pytest.fixture(scope="module")
def devtwo(client):
    return token(client, "dash-two@dashboard.example.com")


@pytest.fixture
def make_profile(client, admin):
    """A profile no other test has touched, run by the named account."""
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}

    def make(email, share=True):
        response = client.post("/api/profiles",
                               json={"name": f"Board{next(_serial)}",
                                     "headline": "AI Engineer", "platform": "Upwork",
                                     "user_id": users[email], "share_progress": share},
                               headers=admin)
        assert response.status_code == 201, response.text
        return response.json()
    return make


def sheet(job_ids):
    out = io.StringIO()
    out.write("Job Title,Company,Job URL\n")
    for n in job_ids:
        out.write(f"Role {n},Client {n % 7} Ltd,https://www.upwork.com/jobs/~01{n:016x}\n")
    return out.getvalue().encode()


def open_cycle(client, admin, name):
    response = client.post("/api/batches",
                           json={"name": name, "mode": "cover", "quota": 500,
                                 "one_per_client": False, "auto_build_minutes": 0},
                           headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def hand_in(client, batch_id, headers, profile_id, job_ids):
    response = client.post(f"/api/batches/{batch_id}/uploads",
                           data={"profile_id": profile_id},
                           files={"file": ("s.csv", sheet(job_ids), "text/csv")},
                           headers=headers)
    assert response.status_code == 201, response.text


def set_dashboard(client, admin, email, visible):
    """Open or close one person's own dashboard."""
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    response = client.patch(f"/api/users/{users[email]}",
                            json={"dashboard_visible": visible}, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def set_board(client, admin, visible):
    response = client.patch("/api/settings", json={"team_board_visible": visible},
                            headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def worked_cycle(client, admin, dana, devtwo, make_profile):
    """A built cycle with two profiles that share ten of their logged jobs."""
    first = make_profile("dash-one@dashboard.example.com")
    second = make_profile("dash-two@dashboard.example.com")
    batch_id = open_cycle(client, admin, f"Dash {next(_serial)}")
    # Ranges 0-29 and 20-49 overlap on exactly ten postings.
    hand_in(client, batch_id, dana, first["id"], range(0, 30))
    hand_in(client, batch_id, devtwo, second["id"], range(20, 50))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200
    return {"batch_id": batch_id, "first": first, "second": second}


def _backdate_sheet(batch_id, profile_id, days):
    """Age the Upload row without touching a single job on it."""
    import datetime as dt
    from app.main import SessionLocal
    from app.models import Upload
    db = SessionLocal()
    row = db.query(Upload).filter(Upload.batch_id == batch_id,
                                  Upload.profile_id == profile_id).one()
    row.created_at = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                      - dt.timedelta(days=days))
    db.commit()
    db.close()


def _backdate_applications(profile_id, days):
    """Age the record of the jobs themselves — they were logged another day."""
    import datetime as dt
    from app.main import SessionLocal
    from app.models import Application
    db = SessionLocal()
    when = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=days)
    for row in db.query(Application).filter(Application.profile_id == profile_id):
        row.created_at = when
    db.commit()
    db.close()


def _today_row(client, admin, batch_id, name):
    from app.models import working_today
    day = working_today().isoformat()
    data = client.get(f"/api/dashboard/overview?batch_id={batch_id}"
                      f"&date_from={day}&date_to={day}", headers=admin).json()
    return next(row for row in data["profiles"] if row["name"] == name)


# --------------------------------------------------------------------------- #
# Today, on the manager's screen
#
# A sheet is a living document: a BD opens one and keeps typing into it all
# week. Dating the jobs on it by when the *sheet* was started made the Today
# column all-or-nothing and wrong in both directions at once.
# --------------------------------------------------------------------------- #

def test_todays_jobs_count_today_on_a_sheet_started_days_ago(client, admin, worked_cycle):
    """The row of zeros the manager reported: thirty jobs logged this morning,
    on a sheet opened last week, reading as nothing at all."""
    first = worked_cycle["first"]
    _backdate_sheet(worked_cycle["batch_id"], first["id"], days=3)

    row = _today_row(client, admin, worked_cycle["batch_id"], first["name"])
    assert row["logged"] == 30, "jobs logged today must not inherit the sheet's own age"
    assert row["last_logged"], "and the count must agree with the 'last worked' beside it"


def test_jobs_logged_on_an_earlier_day_are_not_todays(client, admin, worked_cycle):
    """The other half, and the reason the figures read as inexact: a sheet that
    happened to be started today handed the whole cycle's jobs to today."""
    second = worked_cycle["second"]
    _backdate_applications(second["id"], days=2)

    row = _today_row(client, admin, worked_cycle["batch_id"], second["name"])
    assert row["logged"] == 0, "work done on Monday is not work done today"


def test_a_sheets_own_applied_on_date_decides_the_day(client, admin, dana, make_profile):
    """A BD typing up Monday's applications on Wednesday did that work on
    Monday, and their own date column is what says so."""
    from app.models import working_today
    first = make_profile("dash-one@dashboard.example.com")
    second = make_profile("dash-two@dashboard.example.com")
    batch_id = open_cycle(client, admin, f"Dated {next(_serial)}")

    client.put(f"/api/batches/{batch_id}/profiles/{first['id']}/entries", json={"rows": [
        {"url": f"https://www.upwork.com/jobs/~01{n:016x}", "title": f"Back {n}",
         "company": f"Client {n} Ltd", "date": "2020-03-02"} for n in range(900, 904)]},
        headers=dana)
    hand_in(client, batch_id, admin, second["id"], range(910, 914))
    assert client.post(f"/api/batches/{batch_id}/compute", headers=admin).status_code == 200

    day = working_today().isoformat()
    today = client.get(f"/api/dashboard/overview?batch_id={batch_id}"
                       f"&date_from={day}&date_to={day}", headers=admin).json()
    row = next(r for r in today["profiles"] if r["name"] == first["name"])
    assert row["logged"] == 0, "work the sheet dates to 2020 is not work done today"

    back_then = client.get(f"/api/dashboard/overview?batch_id={batch_id}"
                           f"&date_from=2020-03-02&date_to=2020-03-02", headers=admin).json()
    row = next(r for r in back_then["profiles"] if r["name"] == first["name"])
    assert row["logged"] == 4, "it counts on the day the sheet says it happened"


def test_the_team_row_and_the_persons_own_screen_agree(client, admin, dana, worked_cycle):
    """What the manager did to find the truth: open the person. Unscoped, the
    two views are the same numbers."""
    first = worked_cycle["first"]
    data = client.get(f"/api/dashboard/overview?batch_id={worked_cycle['batch_id']}",
                      headers=admin).json()
    team = next(row for row in data["profiles"] if row["name"] == first["name"])
    theirs = client.get(f"/api/dashboard/profiles/{first['id']}"
                        f"?batch_id={worked_cycle['batch_id']}", headers=dana).json()
    for key in ("logged", "assigned", "applied", "skipped", "pending", "duplicates"):
        assert team[key] == theirs["stats"][key], key


# --------------------------------------------------------------------------- #
# A BD's own dashboard
# --------------------------------------------------------------------------- #

def test_a_bd_sees_only_their_own_profiles(client, dana, worked_cycle):
    data = client.get(f"/api/dashboard/me?batch_id={worked_cycle['batch_id']}",
                      headers=dana).json()
    names = {row["name"] for row in data["profiles"]}
    assert worked_cycle["first"]["name"] in names
    assert worked_cycle["second"]["name"] not in names


def test_the_numbers_say_what_the_labels_say(client, dana, worked_cycle):
    """Dana logged 30 jobs, ten of which Dev also found. The pool is 50, so the
    20 Dana has never tried come back."""
    data = client.get(f"/api/dashboard/me?batch_id={worked_cycle['batch_id']}",
                      headers=dana).json()
    mine = next(r for r in data["profiles"] if r["name"] == worked_cycle["first"]["name"])
    assert mine["logged"] == 30
    assert mine["duplicates"] == 10
    assert mine["assigned"] == 20
    assert mine["pending"] == 20 and mine["applied"] == 0
    assert mine["done_pct"] == 0


def test_marking_a_job_applied_moves_the_dashboard(client, dana, worked_cycle):
    batch_id = worked_cycle["batch_id"]
    profile_id = worked_cycle["first"]["id"]
    jobs = client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet",
                      headers=dana).json()["jobs"]
    assert client.patch(f"/api/assignments/{jobs[0]['id']}", json={"status": "applied"},
                        headers=dana).status_code == 200
    assert client.patch(f"/api/assignments/{jobs[1]['id']}",
                        json={"status": "skipped", "reason": "Rate too low."},
                        headers=dana).status_code == 200

    data = client.get(f"/api/dashboard/me?batch_id={batch_id}", headers=dana).json()
    mine = next(r for r in data["profiles"] if r["profile_id"] == profile_id)
    assert mine["applied"] == 1 and mine["skipped"] == 1 and mine["pending"] == 18
    assert mine["done_pct"] == 10          # two of twenty


def test_the_activity_strip_is_a_fixed_width(client, dana):
    data = client.get("/api/dashboard/me", headers=dana).json()
    assert len(data["activity"]) == 14
    assert all(set(day) == {"day", "count"} for day in data["activity"])
    assert data["streak"] >= 1             # this suite just logged jobs today


def test_a_dashboard_survives_having_no_cycle_at_all(client, admin):
    """A brand new workspace opens on this screen before anything exists."""
    from app.dashboard import for_person
    from app.main import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "dash-boss@dashboard.example.com").first()
        data = for_person(db, user, None, team_visible=True)
        assert data["batch"] is None
        assert data["totals"]["assigned"] == 0
        assert len(data["activity"]) == 14
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Whether a person may see their own dashboard at all
# --------------------------------------------------------------------------- #

DANA = "dash-one@dashboard.example.com"


def test_a_bd_has_no_dashboard_until_the_manager_opens_it(client, admin, dana):
    set_dashboard(client, admin, DANA, False)
    assert client.get("/api/dashboard/me", headers=dana).status_code == 403

    set_dashboard(client, admin, DANA, True)
    assert client.get("/api/dashboard/me", headers=dana).status_code == 200

    set_dashboard(client, admin, DANA, False)
    assert client.get("/api/dashboard/me", headers=dana).status_code == 403
    set_dashboard(client, admin, DANA, True)


def test_the_closed_state_reaches_the_browser_at_sign_in(client, admin, dana):
    """The app hides the tab from this flag, so it has to be honest."""
    set_dashboard(client, admin, DANA, False)
    assert client.get("/api/auth/me", headers=dana).json()["dashboard_visible"] is False
    set_dashboard(client, admin, DANA, True)
    assert client.get("/api/auth/me", headers=dana).json()["dashboard_visible"] is True


def test_a_manager_never_needs_their_own_dashboard_opened(client, admin):
    assert client.get("/api/auth/me", headers=admin).json()["dashboard_visible"] is True
    assert client.get("/api/dashboard/me", headers=admin).status_code == 200


def test_a_closed_dashboard_does_not_touch_the_work(client, admin, dana, worked_cycle):
    """Closing the screen of figures must not take away the list or the sheet."""
    set_dashboard(client, admin, DANA, False)
    batch_id, profile_id = worked_cycle["batch_id"], worked_cycle["first"]["id"]
    assert client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/sheet",
                      headers=dana).status_code == 200
    assert client.get(f"/api/batches/{batch_id}/my-sheets", headers=dana).status_code == 200
    assert client.get(f"/api/batches/{batch_id}/profiles/{profile_id}/entries",
                      headers=dana).status_code == 200
    set_dashboard(client, admin, DANA, True)


def test_a_closed_dashboard_closes_the_rest_of_it_too(client, admin, dana, worked_cycle):
    set_dashboard(client, admin, DANA, False)
    assert client.get("/api/dashboard/team", headers=dana).status_code == 403
    assert client.get(f"/api/dashboard/profiles/{worked_cycle['first']['id']}",
                      headers=dana).status_code == 403
    set_dashboard(client, admin, DANA, True)


def test_a_bd_cannot_open_their_own_dashboard(client, admin, dana):
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    assert client.patch(f"/api/users/{users[DANA]}", json={"dashboard_visible": True},
                        headers=dana).status_code == 403


# --------------------------------------------------------------------------- #
# The manager looking at one person
# --------------------------------------------------------------------------- #

def test_the_manager_sees_exactly_what_that_person_would_see(client, admin, dana, worked_cycle):
    """Same payload, so checking before you open it is not an approximation."""
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    batch_id = worked_cycle["batch_id"]

    theirs = client.get(f"/api/dashboard/me?batch_id={batch_id}", headers=dana).json()
    mine = client.get(f"/api/dashboard/people/{users[DANA]}?batch_id={batch_id}",
                      headers=admin).json()
    assert mine["totals"] == theirs["totals"]
    assert [r["profile_id"] for r in mine["profiles"]] == \
           [r["profile_id"] for r in theirs["profiles"]]
    assert mine["person"]["email"] == DANA


def test_the_manager_can_look_while_it_is_still_closed(client, admin, dana):
    """The whole point of the switch: see it first, then decide."""
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    set_dashboard(client, admin, DANA, False)
    response = client.get(f"/api/dashboard/people/{users[DANA]}", headers=admin)
    assert response.status_code == 200
    assert response.json()["person"]["dashboard_visible"] is False
    assert client.get("/api/dashboard/me", headers=dana).status_code == 403
    set_dashboard(client, admin, DANA, True)


def test_a_bd_cannot_look_at_a_colleagues_dashboard(client, admin, dana):
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    other = users["dash-two@dashboard.example.com"]
    assert client.get(f"/api/dashboard/people/{other}", headers=dana).status_code == 403


def test_looking_at_nobody(client, admin):
    assert client.get("/api/dashboard/people/999999", headers=admin).status_code == 404


def test_a_new_person_starts_with_no_dashboard(client, admin):
    made = client.post("/api/users", json={"email": "quiet@dashboard.example.com",
                                           "name": "Quiet One", "password": "quietpass123",
                                           "role": "bd"}, headers=admin)
    assert made.status_code == 201, made.text
    assert made.json()["dashboard_visible"] is False


# --------------------------------------------------------------------------- #
# The team board, and who may open it
# --------------------------------------------------------------------------- #

def test_the_board_is_shut_to_a_bd_until_the_manager_opens_it(client, admin, dana):
    set_board(client, admin, False)
    assert client.get("/api/dashboard/team", headers=dana).status_code == 403
    assert client.get("/api/dashboard/me", headers=dana).json()["team_visible"] is False

    set_board(client, admin, True)
    assert client.get("/api/dashboard/team", headers=dana).status_code == 200
    assert client.get("/api/dashboard/me", headers=dana).json()["team_visible"] is True

    set_board(client, admin, False)
    assert client.get("/api/dashboard/team", headers=dana).status_code == 403


def test_the_manager_never_needs_the_switch(client, admin):
    set_board(client, admin, False)
    assert client.get("/api/dashboard/team", headers=admin).status_code == 200


def test_a_bd_cannot_flip_the_switch(client, dana):
    assert client.patch("/api/settings", json={"team_board_visible": True},
                        headers=dana).status_code == 403


def test_a_profile_can_be_taken_off_the_board(client, admin, dana, make_profile):
    """Off the board for colleagues, still on the manager's screen."""
    set_board(client, admin, True)
    private = make_profile("dash-two@dashboard.example.com", share=False)

    theirs = client.get("/api/dashboard/team", headers=dana).json()
    assert private["name"] not in {row["name"] for row in theirs["rows"]}
    assert theirs["hidden"] >= 1

    mine = client.get("/api/dashboard/team", headers=admin).json()
    assert private["name"] in {row["name"] for row in mine["rows"]}
    assert mine["hidden"] == 0


def test_a_profile_can_be_put_back_on_the_board(client, admin, dana, make_profile):
    set_board(client, admin, True)
    private = make_profile("dash-two@dashboard.example.com", share=False)
    assert client.patch(f"/api/profiles/{private['id']}", json={"share_progress": True},
                        headers=admin).json()["share_progress"] is True
    rows = client.get("/api/dashboard/team", headers=dana).json()["rows"]
    assert private["name"] in {row["name"] for row in rows}


def test_the_board_is_ranked(client, admin, worked_cycle):
    rows = client.get(f"/api/dashboard/team?batch_id={worked_cycle['batch_id']}",
                      headers=admin).json()["rows"]
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
    applied = [row["applied"] for row in rows]
    assert applied == sorted(applied, reverse=True)


# --------------------------------------------------------------------------- #
# The manager's screen
# --------------------------------------------------------------------------- #

def test_the_overview_rolls_profiles_up_to_the_person(client, admin, dana, worked_cycle):
    """One person may run several profiles, so the person row is the sum of
    theirs — that is the only view that answers 'how is Dana doing'."""
    # A profile belonging to somebody else, to prove the roll-up separates
    # people rather than summing the workspace. It used to be created with
    # `user_id: None`, which the API refuses — a profile must have a BD, and
    # that rule is deliberate — so the test was failing before it reached a
    # single assertion about the thing it is named for.
    people = {u["email"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    extra = client.post("/api/profiles",
                        json={"name": f"Board{next(_serial)}", "headline": "AI Engineer",
                              "user_id": people["dash-two@dashboard.example.com"]},
                        headers=admin)
    assert extra.status_code == 201, extra.text

    data = client.get(f"/api/dashboard/overview?batch_id={worked_cycle['batch_id']}",
                      headers=admin).json()
    person = next(p for p in data["people"] if p["email"] == "dash-one@dashboard.example.com")
    mine = [r for r in data["profiles"] if r["user_id"] == person["user_id"]]
    assert person["runs"] == len(mine)
    assert person["logged"] == sum(r["logged"] for r in mine)
    assert person["applied"] == sum(r["applied"] for r in mine)
    assert extra.json()["id"] not in {r["profile_id"] for r in mine},         "somebody else's profile does not count towards this person"


def test_the_overview_names_who_has_not_handed_in(client, admin, make_profile):
    quiet = make_profile("dash-two@dashboard.example.com")
    batch_id = open_cycle(client, admin, f"Quiet {next(_serial)}")
    data = client.get(f"/api/dashboard/overview?batch_id={batch_id}", headers=admin).json()
    assert quiet["name"] in {row["name"] for row in data["missing"]}
    assert data["org"]["handed_in"] == 0


def test_a_built_cycle_lands_in_the_history(client, admin, worked_cycle):
    data = client.get(f"/api/dashboard/overview?batch_id={worked_cycle['batch_id']}",
                      headers=admin).json()
    entry = next(row for row in data["history"] if row["id"] == worked_cycle["batch_id"])
    assert entry["rows_read"] == 60 and entry["unique_jobs"] == 50
    assert entry["duplicates"] == 10
    assert entry["duplicate_pct"] == 17          # ten of sixty rows typed twice


def test_a_bd_cannot_open_the_overview(client, dana):
    assert client.get("/api/dashboard/overview", headers=dana).status_code == 403


# --------------------------------------------------------------------------- #
# Drilling into one profile
# --------------------------------------------------------------------------- #

def test_the_manager_can_open_any_profile(client, admin, worked_cycle):
    data = client.get(f"/api/dashboard/profiles/{worked_cycle['first']['id']}"
                      f"?batch_id={worked_cycle['batch_id']}", headers=admin).json()
    assert data["profile"]["name"] == worked_cycle["first"]["name"]
    assert data["stats"]["logged"] == 30
    assert len(data["recent"]) == 20                 # capped at the newest twenty
    assert data["recent"][0]["title"].startswith("Role ")
    assert any(cycle["id"] == worked_cycle["batch_id"] for cycle in data["cycles"])


def test_a_bd_can_open_their_own_profile(client, dana, worked_cycle):
    response = client.get(f"/api/dashboard/profiles/{worked_cycle['first']['id']}",
                          headers=dana)
    assert response.status_code == 200


def test_a_bd_cannot_open_a_colleagues_profile(client, admin, dana, worked_cycle):
    """Even with the board open. Totals are shared; somebody else's diary is not."""
    set_board(client, admin, True)
    response = client.get(f"/api/dashboard/profiles/{worked_cycle['second']['id']}",
                          headers=dana)
    assert response.status_code == 403


def test_dashboards_need_a_sign_in(client):
    for path in ("/api/dashboard/me", "/api/dashboard/team", "/api/dashboard/overview",
                 "/api/dashboard/people/1", "/api/settings"):
        assert client.get(path).status_code == 401, path
