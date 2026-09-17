"""Bring an existing database up to the current shape.

There is no migration framework here on purpose — one file of plain SQLAlchemy
is easier to read, and to distrust, than a chain of generated revisions.

Version 1 keyed everything on the person who uploaded a sheet. Version 2 keys it
on the profile the job was applied under, because a person may run several and a
profile may be handed between people. That is not a column you can bolt on: the
old `applications` table carries UNIQUE(job_id, user_id), which forbids exactly
the case v2 exists to support — one person's two profiles both applying to the
same job. So the affected tables are rebuilt rather than altered.

Version 2.2 added the developer behind a profile, and interviews. Both are
purely additive: `interviews` is a new table create_all makes on its own, and
the profile columns go on below with LATER_COLUMNS. Nothing is rebuilt and
nothing is lost, so upgrading to it is only ever a restart.

Version 2.3 split an interview in two along the line of who knows: the BD books
it, the developer says how it went. That is three more optional columns on
`interviews` and no change to any row already there — an interview from before
the split keeps its brief and simply has no debrief, which is the truth.

Version 2.4 added the stage ladder, the description link on a job, and
assessments. `assessments` is a new table create_all makes on its own; the two
columns go on below. Additive again, so upgrading is a restart. Every interview
already recorded lands on `screening`, which is what most first conversations
were, and can be moved.

Version 2.5 linked an interview to the round it followed on from, so a client
who ran four rounds reads as one story rather than four unrelated rows. One
nullable column on `interviews`; every interview already recorded has no
predecessor, which is exactly what an empty column says.

Version 2.6 asked a BD why they were skipping a job, and made "handed in" mean
the same number everywhere. `assignments.skip_reason` is empty on every row
already there, which is the truth — nobody was asked at the time.
`uploads.usable_count` is the one column here that is not left at its default:
0 would read as "handed in nothing" on the manager's screen, so it is filled in
from the sheets themselves on the first start after upgrading.

Version 2.9 gave a cycle a clock. Two nullable-or-defaulted columns on
`batches`; a cycle that predates them has `timer_minutes` 0, which is exactly
what "nobody set a clock on this one" means, and no screen shows anything.

Version 3.1 let a BD back-load the months of applying they did before this app
existed, and take one decision over a whole list at once. `history_imports` is a
new table create_all makes on its own and nothing else moved: the applications
an import writes are ordinary applications, and the new workspace switch is a
row in `settings`, which has never needed a migration for a new switch. So
upgrading to it is a restart.

Everything below is idempotent. A brand new database skips it entirely.
"""
from __future__ import annotations

from sqlalchemy import Engine, MetaData, Table, inspect, insert, or_, select, text

from .models import Base

# Tables whose primary key changed meaning between v1 and v2.
REKEYED = ("uploads", "applications", "batch_applications", "assignments")


# Columns added after a table first shipped. create_all only ever creates
# missing tables, never missing columns, so these are added by hand. Additive
# and idempotent: a fresh database already has them and nothing happens.
LATER_COLUMNS = {
    "batches": [
        ("auto_build_minutes", "INTEGER DEFAULT 10"),
        ("last_built_at", "TIMESTAMP"),
        ("building_since", "TIMESTAMP"),
        # v2.9 — the manager's clock. 0 on every cycle that predates it, which
        # reads as "no clock was set", and no screen shows one.
        ("timer_minutes", "INTEGER DEFAULT 0"),
        ("timer_started_at", "TIMESTAMP"),
    ],
    # TRUE rather than 1, because Postgres will not cast an integer to boolean
    # in a column default and SQLite understands both. ADD COLUMN with a DEFAULT
    # fills the existing rows, so profiles that predate the team board are on it.
    "profiles": [
        ("share_progress", "BOOLEAN DEFAULT TRUE"),
        # v3.0 — deleting a profile without losing what it did. NULL on every
        # existing row, which reads correctly: nothing has been deleted yet.
        ("deleted_at", "TIMESTAMP"),
        # v2.2 — the developer behind the identity, and what a client is handed
        # when it applies. Every one is optional and empty by default, so a
        # workspace that upgrades and never fills any of them in behaves
        # exactly as it did: the screens show nothing rather than something
        # wrong. Empty strings rather than NULLs so the app never has to ask
        # which kind of nothing it is looking at.
        ("dev_user_id", "INTEGER"),
        ("email", "VARCHAR(255) DEFAULT ''"),
        ("resume_url", "TEXT DEFAULT ''"),
        ("skills", "VARCHAR(400) DEFAULT ''"),
        ("timezone", "VARCHAR(64) DEFAULT ''"),
        ("rate", "VARCHAR(40) DEFAULT ''"),
        ("availability", "VARCHAR(16) DEFAULT 'open'"),
        ("bio", "TEXT DEFAULT ''"),
    ],
    # v2.3 — the developer's half of an interview. `notes` was always the BD's
    # brief; these are what the person who sat the call says afterwards, and
    # who said it. Empty on every existing row, which reads correctly: nobody
    # has debriefed an interview that happened before the field existed.
    #
    # v2.4 — the rung on the ladder. 'screening' rather than NULL for every
    # existing row: an interview logged before stages existed was somebody's
    # first conversation with that client far more often than not, and a
    # default that is usually right beats a blank on every historical row.
    #
    # v2.5 — the round this one followed on from. NULL on every existing row,
    # which is the truth: nothing recorded before the column existed was booked
    # out of anything.
    "interviews": [
        ("debrief", "TEXT DEFAULT ''"),
        ("reported_by", "INTEGER"),
        ("reported_at", "TIMESTAMP"),
        ("stage", "VARCHAR(16) DEFAULT 'screening'"),
        ("previous_id", "INTEGER"),
        # v2.7 — the client's own email thread, kept beside the meeting link
        # rather than inside it. Empty on everything already booked, which is
        # the truth: nobody was asked for it at the time.
        ("email_url", "TEXT DEFAULT ''"),
    ],
    "assessments": [
        ("email_url", "TEXT DEFAULT ''"),
    ],
    # v2.4 — where the posting is written out, when that is not the apply link.
    # Empty on every job already recorded, which is the truth: nobody was asked
    # for it at the time.
    "jobs": [
        ("description_url", "TEXT DEFAULT ''"),
    ],
    # FALSE, so an upgrade does not hand every existing person a dashboard
    # nobody chose to open. The manager turns them on one at a time.
    "users": [
        ("dashboard_visible", "BOOLEAN DEFAULT FALSE"),
    ],
    # v2.6 — why a job was turned down. Empty on every row already recorded,
    # which is the truth: nobody was asked at the time.
    "assignments": [
        ("status_changed_at", "TIMESTAMP"),
        ("skip_reason", "TEXT DEFAULT ''"),
    ],
    # v2.6 — how many rows of a sheet the matcher can use, as against how many
    # rows the file had. Backfilled below rather than left at 0, because a 0
    # here reads as "handed in nothing" on the manager's screen, which is worse
    # than the mismatch it is fixing.
    "uploads": [
        ("usable_count", "INTEGER DEFAULT 0"),
    ],
}


# v2.8 adds `client_notes`, which `create_all` makes on its own — a new table
# needs nothing here. It is listed for the same reason the others are: somebody
# reading this file wants to know what a restart will do, and "nothing" is an
# answer worth writing down.


def bring_up_to_date(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "uploads" not in tables:
        return                                   # fresh database; create_all did it all
    if "profile_id" not in {c["name"] for c in inspector.get_columns("uploads")}:
        _upgrade_from_v1(engine)
    _add_later_columns(engine)
    _backfill_blank_platforms(engine)


def _add_later_columns(engine: Engine) -> None:
    for table, columns in LATER_COLUMNS.items():
        if table not in set(inspect(engine).get_table_names()):
            continue
        present = {c["name"] for c in inspect(engine).get_columns(table)}
        missing = [(name, ddl) for name, ddl in columns if name not in present]
        if not missing:
            continue
        with engine.begin() as conn:
            for name, ddl in missing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        # A cycle that predates automatic building has been built at least once
        # if it was ever marked computed, so say so rather than leaving the
        # timer to treat it as brand new.
        if table == "batches" and any(n == "last_built_at" for n, _ in missing):
            with engine.begin() as conn:
                conn.execute(text("UPDATE batches SET last_built_at = computed_at "
                                  "WHERE last_built_at IS NULL AND computed_at IS NOT NULL"))
        if table == "uploads" and any(n == "usable_count" for n, _ in missing):
            _backfill_usable_counts(engine)


def _backfill_usable_counts(engine: Engine) -> None:
    """Count the usable rows of every sheet already handed in.

    Done in Python rather than SQL because "usable" is a rule in ingest.py — a
    link, or a client and a title, after the sheet's own column mapping has
    been applied — and there is no second copy of that rule to drift from this
    one. Sheets are per profile per cycle, so this is tens of rows, not
    millions.
    """
    from . import ingest                      # here: schema.py imports at startup
    uploads = Base.metadata.tables["uploads"]
    with engine.begin() as conn:
        rows = conn.execute(select(uploads.c.id, uploads.c.rows,
                                   uploads.c.mapping, uploads.c.row_count)).all()
        for upload_id, raw, mapping, row_count in rows:
            try:
                usable = len(ingest.apply_mapping(raw or [], mapping or {}))
            except Exception:
                usable = row_count or 0        # unreadable sheet: say what it said
            conn.execute(text("UPDATE uploads SET usable_count = :n WHERE id = :i"),
                         {"n": usable, "i": upload_id})


def _backfill_blank_platforms(engine: Engine) -> None:
    """Fill in the platform of every posting that has one on a sheet already.

    `build_lists` used to set a job's platform only at the moment it created
    the row, and never afterwards. So a job first built from a sheet whose
    Platform column had not been mapped yet — or from the one colleague who
    left the cell blank — kept an empty platform for good, and read as "—" on
    the all-jobs record and the new-jobs list even though the sheet behind it
    named the board all along. The build now fills the gap on every pass, but
    only for the cycle being built; the jobs already stranded are repaired
    here, once.

    Only blanks are touched, so this can never overwrite a correction somebody
    made by hand, and running it twice does nothing the second time.
    """
    from . import ingest, matching             # here: schema.py imports at startup
    tables = set(inspect(engine).get_table_names())
    if not {"jobs", "uploads"} <= tables:
        return
    jobs = Base.metadata.tables["jobs"]
    uploads = Base.metadata.tables["uploads"]
    with engine.begin() as conn:
        blank = conn.execute(
            select(jobs.c.id, jobs.c.fingerprint)
            .where(or_(jobs.c.platform.is_(None), jobs.c.platform == ""))).all()
        if not blank:
            return

        # One pass over every sheet ever handed in, keeping the first platform
        # each fingerprint is named with. Sheets are per profile per cycle, so
        # this is thousands of rows at the outside, not millions.
        named: dict[str, str] = {}
        for raw, mapping in conn.execute(select(uploads.c.rows, uploads.c.mapping)).all():
            try:
                records = ingest.apply_mapping(raw or [], mapping or {})
            except Exception:
                continue                       # an unreadable sheet repairs nothing
            for record in records:
                platform = (record.get("platform") or "").strip()
                if not platform:
                    continue
                fingerprint, _ = matching.fingerprint(
                    record["url"], record["title"], record["company"])
                if fingerprint:
                    named.setdefault(fingerprint, platform[:120])

        for job_id, fingerprint in blank:
            platform = named.get(fingerprint)
            if platform:
                conn.execute(text("UPDATE jobs SET platform = :p WHERE id = :i"),
                             {"p": platform, "i": job_id})


def _upgrade_from_v1(engine: Engine) -> None:
    profile_of = _give_everyone_a_profile(engine)

    with engine.begin() as conn:
        if "mode" not in {c["name"] for c in inspect(conn).get_columns("batches")}:
            conn.execute(text("ALTER TABLE batches ADD COLUMN mode VARCHAR(16)"))
        # Every cycle computed under v1 split the pool, so label them honestly
        # rather than letting them inherit the new default.
        conn.execute(text("UPDATE batches SET mode = 'split' WHERE mode IS NULL"))

        for table in REKEYED:
            # An index follows its table through a rename and keeps its old
            # name, so create_all would then collide with it. These are about
            # to be thrown away with the table anyway.
            for index in inspect(conn).get_indexes(table):
                conn.execute(text(f"DROP INDEX {index['name']}"))
            conn.execute(text(f"ALTER TABLE {table} RENAME TO {table}_v1"))

    Base.metadata.create_all(engine)              # recreate them in the v2 shape

    old = MetaData()
    with engine.begin() as conn:
        for table in REKEYED:
            source = Table(f"{table}_v1", old, autoload_with=conn)
            target = Base.metadata.tables[table]
            rows = [_translate(table, dict(row), profile_of, target)
                    for row in conn.execute(select(source)).mappings()]
            rows = [row for row in rows if row is not None]
            if rows:
                conn.execute(insert(target), rows)
            conn.execute(text(f"DROP TABLE {table}_v1"))


def _give_everyone_a_profile(engine: Engine) -> dict[int, int]:
    """One profile per existing person, inheriting that person's whole history.

    Names have to be unique, and two colleagues can share a first name, so a
    clash gets the person's id appended rather than silently merging two
    people's application history into one identity.
    """
    profiles = Base.metadata.tables["profiles"]
    with engine.begin() as conn:
        taken = {name.lower() for (name,) in conn.execute(select(profiles.c.name))}
        mapping = dict(conn.execute(
            select(profiles.c.user_id, profiles.c.id)
            .where(profiles.c.user_id.is_not(None))).all())

        for user_id, name in conn.execute(text("SELECT id, name FROM users")).all():
            if user_id in mapping:
                continue
            candidate = name.strip() or f"Profile {user_id}"
            if candidate.lower() in taken:
                candidate = f"{candidate} ({user_id})"
            taken.add(candidate.lower())
            result = conn.execute(insert(profiles).values(
                name=candidate, headline="", platform="",
                user_id=user_id, is_active=True))
            mapping[user_id] = result.inserted_primary_key[0]
    return mapping


def _translate(table: str, row: dict, profile_of: dict[int, int], target: Table):
    """Rewrite one v1 row into its v2 form, or None to drop it."""
    user_id = row.get("user_id")
    profile_id = profile_of.get(user_id)
    if profile_id is None and table in ("uploads", "applications",
                                        "batch_applications", "assignments"):
        return None                               # orphaned row, nothing to attach it to

    row["profile_id"] = profile_id
    if table == "assignments":
        # v1 dispatched a job to exactly one person, always.
        row["exclusive"] = True
        row.setdefault("status", "pending")
    if table == "batch_applications":
        row.pop("user_id", None)

    return {column: row.get(column) for column in target.columns.keys()
            if column != "id" or row.get("id") is not None}
