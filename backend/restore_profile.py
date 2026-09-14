"""Bring a retired profile back from the command line.

The Restore button on the People screen is the normal way to do this. This is
for the case that button cannot reach: a profile retired before the button
existed, on a database the app is already pointed at, when you would rather not
wait for a deploy.

It does exactly what the endpoint does — flips `is_active` back on, touching
nothing else — so the profile returns with its whole application history and the
duplicate guard still knows every posting it has already gone for.

    python restore_profile.py --list
    python restore_profile.py "Fahad Hassan AR"
    python restore_profile.py "Fahad Hassan AR" --apply

Without --apply it only says what it would do. DATABASE_URL is read the same way
the app reads it, so this hits whatever database the app itself would.
"""
import argparse
import sys
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.main import DATABASE_URL, SessionLocal
from app.models import Profile, User


def retired(db):
    return list(db.scalars(select(Profile).where(Profile.is_active == False)  # noqa: E712
                           .order_by(Profile.name)))


def where_am_i(url: str) -> str:
    """Which database, without the password.

    Worth printing — this script is for the case where the answer is the live
    workspace — but `DATABASE_URL` carries credentials, and this output gets
    pasted into chats and tickets.
    """
    split = urlsplit(url)
    if not split.hostname:
        return url.split("?", 1)[0]
    host = split.hostname + (f":{split.port}" if split.port else "")
    who = f"{split.username}@" if split.username else ""
    return f"{split.scheme}://{who}{host}{split.path}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="the retired profile to bring back")
    parser.add_argument("--list", action="store_true", help="show retired profiles and stop")
    parser.add_argument("--apply", action="store_true", help="actually write the change")
    args = parser.parse_args()

    print(f"database: {where_am_i(DATABASE_URL)}\n")
    db = SessionLocal()
    try:
        gone = retired(db)
        if args.list or not args.name:
            if not gone:
                print("No retired profiles.")
                return 0
            owners = {u.id: u.name for u in db.scalars(select(User))}
            print("Retired profiles:")
            for p in gone:
                print(f"  {p.id:>5}  {p.name}  (was run by {owners.get(p.user_id) or 'nobody'})")
            if not args.name:
                print("\nPass one of these names to restore it.")
            return 0

        profile = db.scalar(select(Profile).where(
            func.lower(Profile.name) == args.name.strip().lower()))
        if not profile:
            print(f"No profile called {args.name!r}. Run --list to see what is retired.")
            return 1
        if profile.is_active:
            print(f"{profile.name} (id {profile.id}) is already active. Nothing to do.")
            return 0

        # The same guard the endpoint uses: the unique index on `name` is
        # case-sensitive and the clash checks are not, so a case variant can
        # exist and restoring into it would put two live profiles on the board
        # under one name.
        clash = db.scalar(select(Profile).where(
            func.lower(Profile.name) == profile.name.lower(), Profile.id != profile.id))
        if clash:
            print(f"A profile called {clash.name} (id {clash.id}) already holds this name. "
                  "Rename one of them first.")
            return 1

        if not args.apply:
            print(f"Would restore {profile.name} (id {profile.id}). "
                  "Re-run with --apply to do it.")
            return 0

        profile.is_active = True
        db.commit()
        print(f"Restored {profile.name} (id {profile.id}). It is back on the lists.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
