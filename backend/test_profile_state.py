"""The three lists a profile can be on, and handing an account to a new person.

A profile is on, disabled, or deleted. Only the first is a working list; the
other two exist so a manager can find what they switched off and put it back.
None of the three ever removes a row, because `interviews` and `assessments`
cascade on delete and `applications` and `assignments` carry every figure any
report counts.

Two things here would look fine on screen and be false. A profile whose name is
held by a row on no screen — the 409 that started this, naming a profile the
manager could not find. And a BD's seat handed to a new hire by making a second
account, which leaves the work split between a name that has gone and a name
that has just arrived.

Run with:  pytest test_profile_state.py -v
"""
import itertools

import pytest
from fastapi.testclient import TestClient

TEAM = [("state-boss@s.example.com", "Ray Boss", "admin"),
        ("state-boss2@s.example.com", "Moe Boss", "admin"),
        ("state-bd@s.example.com", "Bee Dee", "bd"),
        ("state-dev@s.example.com", "Dee Veloper", "dev")]

PASSWORD = "statepass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/state.db")
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


def token(client, email, password=PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return token(client, "state-boss@s.example.com")


@pytest.fixture(scope="module")
def bd(client):
    return token(client, "state-bd@s.example.com")


def person_id(client, admin, email):
    people = client.get("/api/users", headers=admin).json()
    return next(p["id"] for p in people if p["email"] == email)


@pytest.fixture(scope="module")
def bd_id(client, admin):
    return person_id(client, admin, "state-bd@s.example.com")


def make_profile(client, admin, bd_id, name=None):
    name = name or f"State Case {next(_serial)}"
    response = client.post("/api/profiles", json={"name": name, "user_id": bd_id},
                           headers=admin)
    assert response.status_code == 201, response.text
    return response.json()


def ids_on(client, admin, state):
    return [p["id"] for p in
            client.get(f"/api/profiles?state={state}", headers=admin).json()]


# --------------------------------------------------------------------------- #
# Disable and enable
# --------------------------------------------------------------------------- #

def test_disabled_profile_leaves_the_list_but_keeps_its_name(client, admin, bd_id):
    """The bug that started this: blocked by a row you cannot see.

    The working list filters on `is_active`; the clash check counts every row.
    Both are right on their own, and together they used to send a manager
    hunting a profile that was not on the screen.
    """
    profile = make_profile(client, admin, bd_id, "Fahad Hassan AR")
    assert client.post(f"/api/profiles/{profile['id']}/disable",
                       headers=admin).status_code == 200

    assert profile["id"] not in ids_on(client, admin, "on")

    again = client.post("/api/profiles", json={"name": "Fahad Hassan AR", "user_id": bd_id},
                        headers=admin)
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert "disabled" in detail.lower(), detail
    assert "enable" in detail.lower(), detail


def test_case_and_spacing_do_not_get_a_second_profile_in(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id, "Case Disabled")
    client.post(f"/api/profiles/{profile['id']}/disable", headers=admin)
    clash = client.post("/api/profiles", json={"name": "  case disabled  ", "user_id": bd_id},
                        headers=admin)
    assert clash.status_code == 409, clash.text


def test_the_three_lists_never_overlap(client, admin, bd_id):
    live = make_profile(client, admin, bd_id)
    off = make_profile(client, admin, bd_id)
    gone = make_profile(client, admin, bd_id)
    client.post(f"/api/profiles/{off['id']}/disable", headers=admin)
    client.delete(f"/api/profiles/{gone['id']}", headers=admin)

    on, disabled, deleted = (set(ids_on(client, admin, s))
                             for s in ("on", "disabled", "deleted"))
    assert live["id"] in on and off["id"] in disabled and gone["id"] in deleted
    assert not on & disabled and not on & deleted and not disabled & deleted


def test_enable_puts_a_disabled_profile_back(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    client.post(f"/api/profiles/{profile['id']}/disable", headers=admin)

    back = client.post(f"/api/profiles/{profile['id']}/enable", headers=admin)
    assert back.status_code == 200, back.text
    assert back.json()["is_active"] is True
    assert profile["id"] in ids_on(client, admin, "on")
    assert profile["id"] not in ids_on(client, admin, "disabled")


def test_enable_keeps_the_identity_it_had(client, admin, bd_id):
    """Same id, same owner, same name — so the duplicate guard still recognises
    everything this profile has already applied to."""
    profile = make_profile(client, admin, bd_id)
    client.post(f"/api/profiles/{profile['id']}/disable", headers=admin)
    back = client.post(f"/api/profiles/{profile['id']}/enable", headers=admin).json()
    assert back["id"] == profile["id"]
    assert back["name"] == profile["name"]
    assert back["user_id"] == bd_id


def test_enabling_a_live_profile_changes_nothing(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    back = client.post(f"/api/profiles/{profile['id']}/enable", headers=admin)
    assert back.status_code == 200
    assert back.json()["is_active"] is True


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

def test_delete_keeps_every_record_the_profile_left(client, admin, bd_id):
    """The whole point of deleting this way.

    `interviews` and `assessments` are ON DELETE CASCADE. If deleting removed
    the row, the diary and the outstanding take-home tests would go with it and
    nobody would be told.
    """
    from app.main import SessionLocal
    from app.models import Assessment, Profile

    profile = make_profile(client, admin, bd_id)
    db = SessionLocal()
    db.add(Assessment(profile_id=profile["id"], title="Take-home"))
    db.commit()
    db.close()

    assert client.delete(f"/api/profiles/{profile['id']}", headers=admin).status_code == 200

    db = SessionLocal()
    assert db.get(Profile, profile["id"]) is not None
    kept = db.query(Assessment).filter(Assessment.profile_id == profile["id"]).count()
    db.close()
    assert kept == 1


def test_deleted_profile_keeps_its_name(client, admin, bd_id):
    """Chosen deliberately: the old records still carry the name, and a second
    profile under it would split them across two ids."""
    profile = make_profile(client, admin, bd_id, "Gone For Good")
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)

    again = client.post("/api/profiles", json={"name": "Gone For Good", "user_id": bd_id},
                        headers=admin)
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert "deleted" in detail.lower(), detail
    assert "enable" in detail.lower(), detail


def test_a_deleted_profile_is_off_every_working_screen(client, admin, bd, bd_id):
    """Deleting sets `is_active` false as well as stamping the date, so the many
    queries written before deleting existed keep excluding it."""
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    assert profile["id"] not in [p["id"] for p in
                                 client.get("/api/profiles", headers=bd).json()]
    assert profile["id"] not in ids_on(client, admin, "on")


def test_delete_can_be_undone(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    assert profile["id"] in ids_on(client, admin, "deleted")

    back = client.post(f"/api/profiles/{profile['id']}/enable", headers=admin)
    assert back.status_code == 200, back.text
    assert profile["id"] in ids_on(client, admin, "on")
    assert profile["id"] not in ids_on(client, admin, "deleted")


def test_disabling_a_deleted_profile_leaves_it_deleted(client, admin, bd_id):
    """One way back from both states, and it is the same one."""
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    client.post(f"/api/profiles/{profile['id']}/disable", headers=admin)
    assert profile["id"] in ids_on(client, admin, "deleted")
    assert profile["id"] not in ids_on(client, admin, "disabled")


def test_deleting_twice_keeps_the_first_date(client, admin, bd_id):
    from app.main import SessionLocal
    from app.models import Profile

    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    db = SessionLocal()
    first = db.get(Profile, profile["id"]).deleted_at
    db.close()

    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    db = SessionLocal()
    assert db.get(Profile, profile["id"]).deleted_at == first
    db.close()


# --------------------------------------------------------------------------- #
# Who may do any of it
# --------------------------------------------------------------------------- #

def test_only_a_manager_may_see_the_off_lists(client, bd):
    assert client.get("/api/profiles?state=disabled", headers=bd).status_code == 403
    assert client.get("/api/profiles?state=deleted", headers=bd).status_code == 403


def test_a_nonsense_state_is_refused(client, admin):
    assert client.get("/api/profiles?state=sideways", headers=admin).status_code == 400


def test_a_bd_cannot_disable_delete_or_enable(client, admin, bd, bd_id):
    profile = make_profile(client, admin, bd_id)
    assert client.post(f"/api/profiles/{profile['id']}/disable", headers=bd).status_code == 403
    assert client.delete(f"/api/profiles/{profile['id']}", headers=bd).status_code == 403
    assert client.post(f"/api/profiles/{profile['id']}/enable", headers=bd).status_code == 403


def test_acting_on_nothing_is_a_404(client, admin):
    assert client.post("/api/profiles/999999/enable", headers=admin).status_code == 404
    assert client.post("/api/profiles/999999/disable", headers=admin).status_code == 404
    assert client.delete("/api/profiles/999999", headers=admin).status_code == 404


def test_rename_onto_a_held_name_says_where_it_went(client, admin, bd_id):
    held = make_profile(client, admin, bd_id, "Held Name")
    client.post(f"/api/profiles/{held['id']}/disable", headers=admin)

    other = make_profile(client, admin, bd_id)
    clash = client.patch(f"/api/profiles/{other['id']}", json={"name": "Held Name"},
                         headers=admin)
    assert clash.status_code == 409, clash.text
    assert "disabled" in clash.json()["detail"].lower()


def test_enable_refuses_to_make_a_second_live_profile_under_one_name(client, admin, bd_id):
    """The gap between the unique index and the clash check.

    `ix_profiles_name` is unique but case-sensitive; the clash check is the
    other way round. The API can never let a case variant in, but a hand-edit or
    an importer writing straight to the table can — and if it does so while a
    row is off the lists, enabling that row would put two live profiles on the
    board under one name spelled two ways.
    """
    from app.main import SessionLocal
    from app.models import Profile

    first = make_profile(client, admin, bd_id, "Twice Over")
    client.post(f"/api/profiles/{first['id']}/disable", headers=admin)

    assert client.post("/api/profiles", json={"name": "twice over", "user_id": bd_id},
                       headers=admin).status_code == 409
    db = SessionLocal()
    db.add(Profile(name="twice over", user_id=bd_id))
    db.commit()
    db.close()

    blocked = client.post(f"/api/profiles/{first['id']}/enable", headers=admin)
    assert blocked.status_code == 409, blocked.text
    assert "rename" in blocked.json()["detail"].lower()
    assert first["id"] not in ids_on(client, admin, "on")


# --------------------------------------------------------------------------- #
# People: disable, enable, and handing a seat to somebody new
# --------------------------------------------------------------------------- #

def new_person(client, admin, role="bd", name=None, email=None):
    n = next(_serial)
    body = {"name": name or f"Person {n}", "email": email or f"state-p{n}@s.example.com",
            "password": PASSWORD, "role": role}
    response = client.post("/api/users", json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()


def test_disable_and_enable_a_person(client, admin):
    person = new_person(client, admin)
    off = client.post(f"/api/users/{person['id']}/disable", headers=admin)
    assert off.status_code == 200, off.text
    assert off.json()["is_active"] is False

    on = client.post(f"/api/users/{person['id']}/enable", headers=admin)
    assert on.status_code == 200, on.text
    assert on.json()["is_active"] is True


def test_a_manager_cannot_disable_themselves(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    blocked = client.post(f"/api/users/{me['id']}/disable", headers=admin)
    assert blocked.status_code == 400


def test_handing_a_seat_over_carries_the_profiles_with_it(client, admin):
    """Faria leaves, somebody new takes the seat.

    Editing the account moves the whole desk at once. Making a second account
    and reassigning would leave the work split between a name that has gone and
    a name that has just arrived — and every figure counted under either would
    be half the story.
    """
    leaver = new_person(client, admin, name="Faria", email="state-faria@s.example.com")
    theirs = make_profile(client, admin, leaver["id"])

    handover = client.patch(f"/api/users/{leaver['id']}",
                            json={"name": "New Starter",
                                  "email": "state-newstarter@s.example.com",
                                  "password": "brandnewpass123"},
                            headers=admin)
    assert handover.status_code == 200, handover.text
    assert handover.json()["name"] == "New Starter"

    # Same account, so the profile came with it without being reassigned.
    still = client.get(f"/api/profiles/{theirs['id']}", headers=admin).json()
    assert still["user_id"] == leaver["id"]
    assert still["owner"] == "New Starter"

    # And the person who left cannot sign in as the person who replaced them.
    assert client.post("/api/auth/login",
                       json={"email": "state-faria@s.example.com",
                             "password": PASSWORD}).status_code == 401
    assert token(client, "state-newstarter@s.example.com", "brandnewpass123")


def test_an_email_already_in_use_is_refused(client, admin):
    first = new_person(client, admin)
    second = new_person(client, admin)
    clash = client.patch(f"/api/users/{second['id']}", json={"email": first["email"]},
                         headers=admin)
    assert clash.status_code == 409, clash.text


def test_a_blank_name_or_email_is_refused(client, admin):
    person = new_person(client, admin)
    assert client.patch(f"/api/users/{person['id']}", json={"name": "   "},
                        headers=admin).status_code == 400
    assert client.patch(f"/api/users/{person['id']}", json={"email": "  "},
                        headers=admin).status_code == 400


def test_a_short_password_is_refused(client, admin):
    person = new_person(client, admin)
    assert client.patch(f"/api/users/{person['id']}", json={"password": "short"},
                        headers=admin).status_code == 400


def test_a_developer_behind_a_profile_cannot_quietly_stop_being_one(client, admin):
    """A profile may only name a developer as its developer. Moving somebody out
    of the role would leave the profile pointing at somebody the rules say
    cannot be there — and the client still meets them."""
    dev = new_person(client, admin, role="dev")
    profile = make_profile(client, admin, person_id(client, admin, "state-bd@s.example.com"))
    assert client.patch(f"/api/profiles/{profile['id']}", json={"dev_user_id": dev["id"]},
                        headers=admin).status_code == 200

    blocked = client.patch(f"/api/users/{dev['id']}", json={"role": "bd"}, headers=admin)
    assert blocked.status_code == 400, blocked.text
    assert profile["name"] in blocked.json()["detail"]

    # Deleting the profile settles it, and then the move is allowed.
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    assert client.patch(f"/api/users/{dev['id']}", json={"role": "bd"},
                        headers=admin).status_code == 200


def test_a_manager_cannot_change_their_own_role(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    blocked = client.patch(f"/api/users/{me['id']}", json={"role": "bd"}, headers=admin)
    assert blocked.status_code == 400


def test_a_bd_cannot_edit_anybody(client, bd, admin):
    person = new_person(client, admin)
    assert client.patch(f"/api/users/{person['id']}", json={"name": "Hijacked"},
                        headers=bd).status_code == 403
    assert client.post(f"/api/users/{person['id']}/disable", headers=bd).status_code == 403
    assert client.post(f"/api/users/{person['id']}/enable", headers=bd).status_code == 403
