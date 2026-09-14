"""Retiring a profile, and getting it back.

Retirement only switches `is_active` off. The row keeps its name and its whole
application history, which is the point — bring it back and the duplicate guard
still knows every posting it has already gone for. But it also means the name
stays taken while the row is filtered out of every list, and for a long time
there was no way back at all: the confirmation dialog promised "if you bring it
back" over an endpoint nobody had written. A manager hit a 409 naming a profile
that was nowhere on the screen.

Run with:  pytest test_profile_restore.py -v
"""
import itertools

import pytest
from fastapi.testclient import TestClient

TEAM = [("restore-boss@r.example.com", "Ray Boss", "admin"),
        ("restore-bd@r.example.com", "Bee Dee", "bd")]

PASSWORD = "restorepass12345"
_serial = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ.setdefault("DATABASE_URL",
                          f"sqlite:///{tmp_path_factory.mktemp('db')}/restore.db")
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
    return token(client, "restore-boss@r.example.com")


@pytest.fixture(scope="module")
def bd(client):
    return token(client, "restore-bd@r.example.com")


@pytest.fixture(scope="module")
def bd_id(client, admin):
    people = client.get("/api/users", headers=admin).json()
    return next(p["id"] for p in people if p["email"] == "restore-bd@r.example.com")


def make_profile(client, admin, bd_id, name=None):
    name = name or f"Restore Case {next(_serial)}"
    response = client.post("/api/profiles", json={"name": name, "user_id": bd_id},
                           headers=admin)
    assert response.status_code == 201, response.text
    return response.json()


def test_retired_profile_leaves_the_list_but_keeps_its_name(client, admin, bd_id):
    """The bug that started this: blocked by a row you cannot see.

    The list filters on `is_active`; the clash check counts every row. Both are
    right on their own, and together they used to send a manager hunting a
    profile that was not on the screen.
    """
    profile = make_profile(client, admin, bd_id, "Fahad Hassan AR")
    assert client.delete(f"/api/profiles/{profile['id']}", headers=admin).status_code == 200

    live = client.get("/api/profiles", headers=admin).json()
    assert profile["id"] not in [p["id"] for p in live]

    again = client.post("/api/profiles", json={"name": "Fahad Hassan AR", "user_id": bd_id},
                        headers=admin)
    assert again.status_code == 409
    # The name is still held — and the message has to say where it went, or it
    # is describing a row the manager has no way to find.
    detail = again.json()["detail"]
    assert "retired" in detail.lower(), detail
    assert "restore" in detail.lower(), detail


def test_case_and_spacing_do_not_get_a_second_profile_in(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id, "Case Retired")
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    clash = client.post("/api/profiles", json={"name": "  case retired  ", "user_id": bd_id},
                        headers=admin)
    assert clash.status_code == 409, clash.text


def test_retired_list_is_where_the_row_went(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    gone = client.get("/api/profiles?retired=true", headers=admin).json()
    assert profile["id"] in [p["id"] for p in gone]
    # And the two lists never overlap, or the screen would show a row twice.
    live = {p["id"] for p in client.get("/api/profiles", headers=admin).json()}
    assert not live & {p["id"] for p in gone}


def test_only_a_manager_may_see_the_retired_list(client, bd):
    assert client.get("/api/profiles?retired=true", headers=bd).status_code == 403


def test_restore_puts_it_back_on_the_list(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)

    back = client.post(f"/api/profiles/{profile['id']}/restore", headers=admin)
    assert back.status_code == 200, back.text
    assert back.json()["is_active"] is True

    live = client.get("/api/profiles", headers=admin).json()
    assert profile["id"] in [p["id"] for p in live]
    assert profile["id"] not in [
        p["id"] for p in client.get("/api/profiles?retired=true", headers=admin).json()]


def test_restore_keeps_the_identity_it_had(client, admin, bd_id):
    """What retiring promised: the history comes back with it.

    Same id, same owner, same name — so the duplicate guard still recognises
    everything this profile has already applied to.
    """
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    back = client.post(f"/api/profiles/{profile['id']}/restore", headers=admin).json()
    assert back["id"] == profile["id"]
    assert back["name"] == profile["name"]
    assert back["user_id"] == bd_id


def test_restoring_a_live_profile_changes_nothing(client, admin, bd_id):
    profile = make_profile(client, admin, bd_id)
    back = client.post(f"/api/profiles/{profile['id']}/restore", headers=admin)
    assert back.status_code == 200
    assert back.json()["is_active"] is True


def test_a_bd_cannot_restore(client, admin, bd, bd_id):
    profile = make_profile(client, admin, bd_id)
    client.delete(f"/api/profiles/{profile['id']}", headers=admin)
    assert client.post(f"/api/profiles/{profile['id']}/restore", headers=bd).status_code == 403


def test_restoring_nothing_is_a_404(client, admin):
    assert client.post("/api/profiles/999999/restore", headers=admin).status_code == 404


def test_rename_onto_a_retired_name_says_where_it_went(client, admin, bd_id):
    held = make_profile(client, admin, bd_id, "Held Name")
    client.delete(f"/api/profiles/{held['id']}", headers=admin)

    other = make_profile(client, admin, bd_id)
    clash = client.patch(f"/api/profiles/{other['id']}", json={"name": "Held Name"},
                         headers=admin)
    assert clash.status_code == 409, clash.text
    assert "retired" in clash.json()["detail"].lower()


def test_restore_refuses_to_make_a_second_live_profile_under_one_name(client, admin, bd_id):
    """The gap between the unique index and the clash check.

    `ix_profiles_name` is unique but case-sensitive; the clash check is the
    other way round. So the API can never let a case variant in, but a
    hand-edit or an importer writing straight to the table can — and if it does
    so while a row is retired, restoring that row would put two live profiles
    on the board under one name spelled two ways.
    """
    from app.main import SessionLocal
    from app.models import Profile

    first = make_profile(client, admin, bd_id, "Twice Over")
    client.delete(f"/api/profiles/{first['id']}", headers=admin)

    # Straight to the table, the way an importer would: the API refuses this.
    assert client.post("/api/profiles", json={"name": "twice over", "user_id": bd_id},
                       headers=admin).status_code == 409
    db = SessionLocal()
    db.add(Profile(name="twice over", user_id=bd_id))
    db.commit()
    db.close()

    blocked = client.post(f"/api/profiles/{first['id']}/restore", headers=admin)
    assert blocked.status_code == 409, blocked.text
    assert "rename" in blocked.json()["detail"].lower()

    # And it really did stay off the lists rather than half-restoring.
    live = client.get("/api/profiles", headers=admin).json()
    assert first["id"] not in [p["id"] for p in live]
