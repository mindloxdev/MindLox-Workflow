"""Progress figures for the dashboards.

Reads only. Nothing here writes, so opening a dashboard can never disturb a
cycle that is mid-rebuild — which matters, because the lists rebuild on a timer
while people are looking at them.

Three words that look alike and are not:

  sheet rows  what a profile physically handed in — the raw line count.
  logged      distinct jobs that sheet turned into, counted after
              fingerprinting, so one posting listed twice under two different
              links counts once.
  assigned    what this cycle put on that profile's list. What it has been
              handed, not what it has done.

Work done is `applied`. Work declined is `skipped`. Everything still waiting is
`pending` — and only `pending` rows are thrown away and rebuilt by the timer,
which is why nothing here measures the age of an assignment. That number would
reset every ten minutes and mean nothing.

Queries are grouped over a whole cycle rather than filtered to a list of
profiles: one query answers for everybody, the caller keeps the rows it wants,
and there is no IN (...) to outgrow SQLite's bound-parameter limit.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import assessments, interviews
from .models import (Application, Assignment, Batch, BatchApplication, Job,
                     Profile, Upload, User, to_working, working_label,
                     working_today)

ACTIVITY_DAYS = 14        # the strip on a BD's own dashboard
ORG_ACTIVITY_DAYS = 30    # the manager sees further back
HISTORY_CYCLES = 8
RECENT_ROWS = 20
CYCLE_PICKER = 24

# Summed the same way everywhere: a person's row is their profiles added up,
# and the workspace row is every profile added up.
ROLLUP_KEYS = ("sheet_rows", "logged", "duplicates", "assigned", "own_found",
               "from_others", "applied", "skipped", "pending", "all_time")


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


# SQLite caps the bound parameters in one statement, so every IN (…) built from
# user data is fed through in slices. Kept local rather than imported from
# main.py, which imports this module.
_PARAM_CHUNK = 500


def _chunks(items, size: int = _PARAM_CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _working_day(value: Optional[dt.datetime]) -> Optional[dt.date]:
    """The team's calendar day for a stored UTC timestamp.

    models.to_working does the conversion — one implementation, so a chart and
    an interview can never disagree about which day something happened on.
    """
    return None if value is None else to_working(value).date()


def _today() -> dt.date:
    return working_today()


def blank_stats() -> dict:
    return {"sheet_rows": 0, "logged": 0, "duplicates": 0, "assigned": 0,
            "own_found": 0, "from_others": 0, "applied": 0, "skipped": 0,
            "pending": 0, "done_pct": 0, "applied_pct": 0}


# --------------------------------------------------------------------------- #
# Activity over time
# --------------------------------------------------------------------------- #

def activity(db: Session, profile_ids: Optional[Sequence[int]] = None,
             days: int = ACTIVITY_DAYS,
             date_from: Optional[dt.date] = None,
             date_to: Optional[dt.date] = None) -> list[dict]:
    """Jobs logged per working day, oldest first.

    Always exactly `days` long, zeros included, so the strip keeps its shape on
    a quiet week instead of collapsing to a couple of bars.
    """
    today = _today()
    start = date_from or today - dt.timedelta(days=days - 1)
    end = date_to or today
    if start > end:
        return []
    window = [start + dt.timedelta(days=n)
              for n in range((end - start).days + 1)]
    if profile_ids is not None and not profile_ids:
        return [{"day": day.isoformat(), "count": 0} for day in window]

    # A day either side of the window in UTC: which working day a timestamp
    # belongs to is decided after the conversion, not by the filter.
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(days=days + 1)).replace(tzinfo=None)
    query = select(Application.created_at).where(Application.created_at >= cutoff)
    if profile_ids is not None:
        query = query.where(Application.profile_id.in_(list(profile_ids)))

    tally: Counter = Counter()
    for (stamp,) in db.execute(query).all():
        day = _working_day(stamp)
        if (day is not None and
            (date_from is None or day >= date_from) and
            (date_to is None or day <= date_to)):
            tally[day] += 1
    return [{"day": day.isoformat(), "count": tally.get(day, 0)} for day in window]


def streak(series: Sequence[dict]) -> int:
    """Consecutive working days up to today with at least one job logged.

    Today not being started yet is not a broken streak, so a zero on today alone
    is forgiven. A zero on the day before it is not.
    """
    counts = [row["count"] for row in series]
    if not counts:
        return 0
    walk = counts[:-1] if counts[-1] == 0 else counts
    run = 0
    for count in reversed(walk):
        if count <= 0:
            break
        run += 1
    return run


# --------------------------------------------------------------------------- #
# Per-profile figures
# --------------------------------------------------------------------------- #

def cycle_stats(db: Session, batch_id: Optional[int],
                date_from: Optional[dt.date] = None,
                date_to: Optional[dt.date] = None) -> dict[int, dict]:
    """Every profile's figures for one cycle, keyed by profile id."""
    stats: dict[int, dict] = defaultdict(blank_stats)
    if not batch_id:
        return dict(stats)

    upload_query = select(Upload.profile_id, func.sum(Upload.row_count)).where(
        Upload.batch_id == batch_id)
    if date_from:
        upload_query = upload_query.where(
            Upload.created_at >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        upload_query = upload_query.where(
            Upload.created_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min))
    for profile_id, rows in db.execute(
        upload_query
        .group_by(Upload.profile_id)
    ).all():
        if profile_id is not None:
            stats[profile_id]["sheet_rows"] = int(rows or 0)

    # A job two profiles both logged is the duplicated effort this whole product
    # exists to surface, so it is counted against each of them.
    by_job: dict[int, set[int]] = defaultdict(set)
    batch_application_query = select(BatchApplication.job_id, BatchApplication.profile_id).where(
        BatchApplication.batch_id == batch_id)
    if date_from or date_to:
        batch_application_query = batch_application_query.join(
            Upload, (Upload.batch_id == BatchApplication.batch_id) &
                    (Upload.profile_id == BatchApplication.profile_id))
        if date_from:
            batch_application_query = batch_application_query.where(
                Upload.created_at >= dt.datetime.combine(date_from, dt.time.min))
        if date_to:
            batch_application_query = batch_application_query.where(
                Upload.created_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min))
    for job_id, profile_id in db.execute(
        batch_application_query
    ).all():
        by_job[job_id].add(profile_id)

    for holders in by_job.values():
        shared = len(holders) > 1
        for profile_id in holders:
            stats[profile_id]["logged"] += 1
            # The same number as `logged`, under the name of the question a BD
            # actually asks at the end of a week: how much of what went out did
            # I find myself. Kept as its own key so `own_found + from_others`
            # reads as the whole of the week's work — which is the split the
            # report is built on.
            stats[profile_id]["own_found"] += 1
            if shared:
                stats[profile_id]["duplicates"] += 1

    # Work on the list is dated by when somebody marked it, not by when the
    # cycle put it there. A job dispatched on Monday and applied for on Friday
    # belongs to Friday — that is the day the work happened, and it is the day
    # the person asking "what did I do this week" means.
    changed_at = func.coalesce(Assignment.status_changed_at, Assignment.created_at)
    assignment_query = select(Assignment.profile_id, Assignment.status,
                              func.count(Assignment.id)).where(Assignment.batch_id == batch_id)
    if date_from:
        assignment_query = assignment_query.where(
            changed_at >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        assignment_query = assignment_query.where(
            changed_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min))
    for profile_id, status, count in db.execute(
        assignment_query
        .group_by(Assignment.profile_id, Assignment.status)
    ).all():
        row = stats[profile_id]
        row["assigned"] += count
        if status in ("applied", "skipped", "pending"):
            row[status] += count
            # Anything on a dispatched list is by definition a job somebody
            # else found — a profile is never handed a posting it logged
            # itself. So the applied ones are the other half of the split.
            if status == "applied":
                row["from_others"] += count

    for row in stats.values():
        row["done_pct"] = _pct(row["applied"] + row["skipped"], row["assigned"])
        row["applied_pct"] = _pct(row["applied"], row["assigned"])
    return dict(stats)


def all_time(db: Session, date_from: Optional[dt.date] = None,
             date_to: Optional[dt.date] = None) -> dict[int, int]:
    """Applications each profile has ever recorded, across every cycle."""
    query = select(Application.profile_id, func.count(Application.id))
    if date_from:
        query = query.where(Application.created_at >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        query = query.where(Application.created_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min))
    return {profile_id: count for profile_id, count in db.execute(
        query.group_by(Application.profile_id)).all() if profile_id is not None}


def last_logged(db: Session, date_from: Optional[dt.date] = None,
                date_to: Optional[dt.date] = None) -> dict[int, dt.datetime]:
    query = select(Application.profile_id, func.max(Application.created_at))
    if date_from:
        query = query.where(Application.created_at >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        query = query.where(Application.created_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min))
    return {profile_id: stamp for profile_id, stamp in db.execute(
        query.group_by(Application.profile_id)).all() if profile_id is not None}


def profile_rows(db: Session, profiles: Sequence[Profile], batch_id: Optional[int],
                 owners: dict[int, str], date_from: Optional[dt.date] = None,
                 date_to: Optional[dt.date] = None) -> list[dict]:
    """One row per profile, busiest first."""
    stats = cycle_stats(db, batch_id, date_from, date_to)
    totals = all_time(db, date_from, date_to)
    latest = last_logged(db, date_from, date_to)
    # Take-homes outstanding against each identity. On the row rather than in a
    # separate block, because a board that shows how much a profile applied for
    # while saying nothing about the test it owes a client is showing the half
    # of the picture that cannot lose the work.
    tests = assessments.by_profile(db, [p.id for p in profiles] if profiles else [])

    rows = []
    for profile in profiles:
        stamp = latest.get(profile.id)
        theirs = tests.get(profile.id) or {}
        rows.append({
            "profile_id": profile.id,
            "name": profile.name,
            "headline": profile.headline,
            "platform": profile.platform,
            "user_id": profile.user_id,
            "person": owners.get(profile.user_id),
            # Who the client would actually be meeting, and whether they could
            # take the work. Blank on a profile nobody has been attached to.
            "dev_user_id": profile.dev_user_id,
            "developer": owners.get(profile.dev_user_id),
            "availability": profile.availability or "open",
            # A NULL here is a row that predates the column, and the default is
            # to share — so only an explicit False takes a profile off the board.
            "shared": profile.share_progress is not False,
            "all_time": totals.get(profile.id, 0),
            "last_logged": stamp.isoformat() if stamp else None,
            "assessments_open": theirs.get("open", 0),
            "assessments_overdue": theirs.get("overdue", 0),
            **(stats.get(profile.id) or blank_stats()),
        })
    rows.sort(key=lambda row: (-row["applied"], -row["logged"], row["name"]))
    return rows


def duplication(db: Session, batch_id: Optional[int]) -> dict:
    """Duplicated effort across a whole cycle, counted once per posting.

    Adding up each profile's own duplicate count is the wrong sum here. A job
    Khuram and Zahid both logged appears in both their counts, so two profiles
    finding one posting reads as two duplicated jobs. That figure is right on a
    profile's own row — "ten of the jobs you logged, a colleague had too" — and
    wrong for the team, where the honest questions are how many postings were
    found more than once, and how many rows of typing that cost.

    Both are reported: `duplicates` is the postings, `wasted_rows` is the
    typing. They match the cycle report's own two lines.
    """
    blank = {"duplicates": 0, "wasted_rows": 0, "logged_rows": 0, "duplicate_pct": 0}
    if not batch_id:
        return blank

    by_job: dict[int, set[int]] = defaultdict(set)
    for job_id, profile_id in db.execute(
        select(BatchApplication.job_id, BatchApplication.profile_id)
        .where(BatchApplication.batch_id == batch_id)
    ).all():
        by_job[job_id].add(profile_id)

    found_twice = sum(1 for holders in by_job.values() if len(holders) > 1)
    wasted = sum(len(holders) - 1 for holders in by_job.values() if len(holders) > 1)
    rows = sum(len(holders) for holders in by_job.values())
    return {"duplicates": found_twice, "wasted_rows": wasted,
            "logged_rows": rows, "duplicate_pct": _pct(wasted, rows)}


def _rollup(rows: Sequence[dict]) -> dict:
    summed = {key: sum(row[key] for row in rows) for key in ROLLUP_KEYS}
    summed["done_pct"] = _pct(summed["applied"] + summed["skipped"], summed["assigned"])
    summed["applied_pct"] = _pct(summed["applied"], summed["assigned"])
    summed["duplicate_pct"] = _pct(summed["duplicates"], summed["logged"])
    return summed


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #

def _brief(batch: Optional[Batch]) -> Optional[dict]:
    if batch is None:
        return None
    return {"id": batch.id, "name": batch.name, "status": batch.status,
            "mode": batch.mode, "quota": batch.quota,
            "auto_build_minutes": batch.auto_build_minutes or 0,
            "last_built_at": batch.last_built_at.isoformat() if batch.last_built_at else None,
            "report": batch.report or {}}


def pick_batch(db: Session, batch_id: Optional[int]) -> Optional[Batch]:
    """The cycle a dashboard should open on: the one asked for, else the newest
    cycle still running, else the newest there is."""
    if batch_id:
        return db.get(Batch, batch_id)
    running = db.scalars(select(Batch).where(Batch.status == "open")
                         .order_by(Batch.id.desc()).limit(1)).first()
    return running or db.scalars(select(Batch).order_by(Batch.id.desc()).limit(1)).first()


def cycle_list(db: Session, limit: int = CYCLE_PICKER) -> list[dict]:
    return [{"id": b.id, "name": b.name, "status": b.status}
            for b in db.scalars(select(Batch).order_by(Batch.id.desc()).limit(limit))]


def history(db: Session, limit: int = HISTORY_CYCLES) -> list[dict]:
    """Recent built cycles, oldest first so a trend reads left to right.

    The duplicate rate is the number worth watching: the share of the team's
    typing that two profiles spent on the same posting. It should fall as people
    split their searches up, and this is the only place that shows whether it is.
    """
    built = db.scalars(select(Batch).where(Batch.last_built_at.is_not(None))
                       .order_by(Batch.id.desc()).limit(limit)).all()
    out = []
    for batch in reversed(built):
        report = batch.report or {}
        rows_read = int(report.get("Rows read") or 0)
        duplicates = int(report.get("Duplicate applications") or 0)
        out.append({
            "id": batch.id, "name": batch.name, "status": batch.status,
            "built_at": batch.last_built_at.isoformat() if batch.last_built_at else None,
            "rows_read": rows_read,
            "unique_jobs": int(report.get("Unique jobs") or 0),
            "duplicates": duplicates,
            "dispatched": int(report.get("Jobs put on a list") or 0),
            "duplicate_pct": _pct(duplicates, rows_read),
        })
    return out


# --------------------------------------------------------------------------- #
# The three dashboards
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# The range report — what somebody actually did between two dates
# --------------------------------------------------------------------------- #

def _window(date_from: Optional[dt.date], date_to: Optional[dt.date]):
    """The half-open UTC bounds for a pair of working-day dates.

    Half-open on purpose: `< the day after` catches everything on the closing
    day whatever the time, where `<= the day itself` would silently drop
    anything logged after midnight UTC on it.
    """
    start = dt.datetime.combine(date_from, dt.time.min) if date_from else None
    end = (dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min)
           if date_to else None)
    return start, end


def range_report(db: Session, profile_ids: Optional[Sequence[int]],
                 date_from: Optional[dt.date],
                 date_to: Optional[dt.date]) -> Optional[dict]:
    """Everything that happened between two dates, for one set of profiles.

    A different question from the rest of this module, and it needs its own
    answer. Every other figure here is scoped to a *cycle* — what went out in
    dispatch 14 — because that is the unit the work is organised in. This one
    is scoped to a *fortnight*, because that is the unit people are asked
    about: what did you do between the first and the fifteenth.

    The two do not line up. A cycle opened on the 3rd is still being worked on
    the 20th, and an application logged on the 20th belongs to the 20th no
    matter which cycle put the job in front of somebody. So nothing here reads
    `batches` at all: applications are dated by when they were recorded, work on
    a list by when it was marked, and interviews by when they were held.

    Returns None when no range was asked for. The report is the answer to a
    question about dates, and inventing a default window would put a figure on
    screen that nobody asked the question behind.
    """
    if not (date_from or date_to):
        return None
    if profile_ids is not None and not profile_ids:
        return None

    start, end = _window(date_from, date_to)

    def in_window(query, column):
        if start is not None:
            query = query.where(column >= start)
        if end is not None:
            query = query.where(column < end)
        return query

    # ── What went out ─────────────────────────────────────────────────────
    applied = in_window(
        select(Application.job_id, Application.profile_id, Application.batch_id,
               Application.created_at),
        Application.created_at)
    if profile_ids is not None:
        applied = applied.where(Application.profile_id.in_(list(profile_ids)))
    rows = db.execute(applied).all()

    # Which of those the profile had put into the pool itself. A job it logged
    # on its own sheet has a batch_applications row; one it was handed off
    # somebody else's sheet and later marked applied does not. That is an exact
    # split rather than a guess, and it is the one a BD asks for: of everything
    # I sent this week, how much did I find.
    own: set[tuple[int, int, int]] = set()
    pairs = {(job_id, profile_id, batch_id)
             for job_id, profile_id, batch_id, _ in rows if batch_id is not None}
    if pairs:
        for chunk in _chunks(sorted({job for job, _, _ in pairs})):
            for job_id, profile_id, batch_id in db.execute(
                select(BatchApplication.job_id, BatchApplication.profile_id,
                       BatchApplication.batch_id)
                .where(BatchApplication.job_id.in_(chunk))
            ).all():
                own.add((job_id, profile_id, batch_id))

    own_found = sum(1 for job_id, profile_id, batch_id, _ in rows
                    if (job_id, profile_id, batch_id) in own)

    # ── What was turned down ──────────────────────────────────────────────
    skipped_at = func.coalesce(Assignment.status_changed_at, Assignment.created_at)
    skipped = in_window(
        select(func.count(Assignment.id)).where(Assignment.status == "skipped"),
        skipped_at)
    if profile_ids is not None:
        skipped = skipped.where(Assignment.profile_id.in_(list(profile_ids)))
    skipped_count = db.scalar(skipped) or 0

    # ── Effort per day ────────────────────────────────────────────────────
    per_day: Counter = Counter()
    for _, _, _, stamp in rows:
        day = _working_day(stamp)
        if day is not None:
            per_day[day] += 1
    span = ((date_to or _today()) - (date_from or min(per_day, default=_today()))).days + 1
    span = max(1, span)
    busiest = max(per_day.items(), key=lambda kv: kv[1], default=None)

    # ── What came back ────────────────────────────────────────────────────
    sittings = interviews.load(db, profile_ids)
    if date_from or date_to:
        sittings = [row for row in sittings
                    if (date_from is None
                        or working_label(row.scheduled_at)["day"] >= date_from.isoformat())
                    and (date_to is None
                         or working_label(row.scheduled_at)["day"] <= date_to.isoformat())]
    live = [row for row in sittings if row.status in interviews.LIVE]
    far = interviews.how_far(db, live)

    # The clients who answered, one row per conversation rather than per
    # sitting — "Northwind came back" is one fact however many calls it took.
    lineage = interviews.chains(db, live) if live else {}
    seen_roots: set[int] = set()
    replied: list[dict] = []
    for row in sorted(live, key=lambda r: r.scheduled_at, reverse=True):
        root = (lineage.get(row.id) or {}).get("root", row.id)
        if root in seen_roots:
            continue
        seen_roots.add(root)
        replied.append({
            "client": row.client or "—",
            "role": row.role or "",
            "stage": row.stage or "screening",
            "outcome": row.outcome,
            "rounds": (lineage.get(row.id) or {}).get("rounds", 1),
            "when": working_label(row.scheduled_at),
        })

    total = len(rows)
    return {
        "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
        "days": span,
        "applied": {
            "total": total,
            "own_found": own_found,
            # Everything else went out against a posting a colleague found —
            # the other half of the split, by construction.
            "from_others": total - own_found,
            "skipped": skipped_count,
            "per_day": round(total / span, 1),
            "active_days": len(per_day),
            "busiest": ({"day": busiest[0].isoformat(), "count": busiest[1]}
                        if busiest else None),
        },
        "heard_back": {
            # Conversations, not sittings. A client who ran three rounds
            # replied once.
            "conversations": far["conversations"],
            "rate": _pct(far["conversations"], total),
            "clients": replied[:RECENT_ROWS],
        },
        "interviews": {
            "sittings": len(live),
            "completed": sum(1 for row in live
                             if row.status in ("done", "no_show")),
            "scheduled": sum(1 for row in live if row.status == "scheduled"),
            "offers": sum(1 for row in live if row.outcome in interviews.WON),
            "hired": sum(1 for row in live if row.outcome == "hired"),
            "rejected": sum(1 for row in live if row.outcome == "rejected"),
            **far,
            "by_stage": interviews.by_stage(live),
        },
    }


def for_person(db: Session, user: User, batch: Optional[Batch],
               team_visible: bool, date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None) -> dict:
    """What one person sees about their own work.

    A manager gets every profile here, because a manager who also runs one
    should still see it. The workspace-wide picture is a different screen.
    """
    query = select(Profile).where(Profile.is_active == True)  # noqa: E712
    if user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    mine = list(db.scalars(query.order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}

    rows = profile_rows(db, mine, batch.id if batch else None, owners, date_from, date_to)
    series = activity(db, [p.id for p in mine], date_from=date_from, date_to=date_to)

    totals = _rollup(rows)
    totals["profiles"] = len(rows)

    ids = [p.id for p in mine]
    return {"batch": _brief(batch), "batches": cycle_list(db),
            "profiles": rows, "totals": totals,
            "activity": series, "streak": streak(series),
            # What the typing produced. Every other figure on this screen goes
            # up when somebody works harder; these two only go up when the work
            # was worth sending.
            "interviews": interviews.summary(db, ids, date_from, date_to),
            "funnel": interviews.funnel(db, ids, date_from=date_from, date_to=date_to),
            # The third thing a client can ask for, and the one with a deadline
            # on it. A BD who cannot see it here finds out a take-home was
            # missed from the client's next email.
            "assessments": assessments.summary(db, ids),
            # What happened between two dates, when two dates were asked for.
            # None the rest of the time — see range_report.
            "report": range_report(db, ids, date_from, date_to),
            "team_visible": team_visible}


def team_board(db: Session, batch: Optional[Batch], include_private: bool) -> dict:
    """Every profile's progress side by side.

    `include_private` is the manager's view. A BD sees only the profiles the
    manager left on the board, and is told how many were held back rather than
    being quietly shown a short list and drawing its own conclusions.
    """
    profiles = list(db.scalars(select(Profile).where(Profile.is_active == True)  # noqa: E712
                               .order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}
    rows = profile_rows(db, profiles, batch.id if batch else None, owners)

    hidden = 0
    if not include_private:
        hidden = sum(1 for row in rows if not row["shared"])
        rows = [row for row in rows if row["shared"]]
    for place, row in enumerate(rows, start=1):
        row["rank"] = place

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "rows": rows, "hidden": hidden}


def overview(db: Session, batch: Optional[Batch], date_from: Optional[dt.date] = None,
             date_to: Optional[dt.date] = None) -> dict:
    """The manager's screen: the whole workspace in one pass."""
    profiles = list(db.scalars(select(Profile).where(Profile.is_active == True)  # noqa: E712
                               .order_by(Profile.name)))
    users = list(db.scalars(select(User)))
    owners = {u.id: u.name for u in users}
    batch_id = batch.id if batch else None

    rows = profile_rows(db, profiles, batch_id, owners, date_from, date_to)
    for place, row in enumerate(rows, start=1):
        row["rank"] = place
    by_profile = {row["profile_id"]: row for row in rows}

    handed_in: set[int] = set()
    if batch_id:
        handed_in = {profile_id for (profile_id,) in db.execute(
            select(Upload.profile_id).where(Upload.batch_id == batch_id)).all()
            if profile_id is not None}

    # Each person, with their profiles rolled up. One person may run several,
    # so this is the only view that answers "how is Ali doing" rather than
    # "how is Khuram doing".
    people = []
    for person in users:
        if not person.is_active:
            continue
        theirs = [by_profile[p.id] for p in profiles if p.user_id == person.id]
        if not theirs and person.role == "admin":
            continue                      # a manager running nothing is not on the report
        rolled = _rollup(theirs)
        stamps = [row["last_logged"] for row in theirs if row["last_logged"]]
        people.append({
            "user_id": person.id, "name": person.name, "email": person.email,
            "role": person.role,
            # Whether they may open the dashboard this row describes. A manager
            # always may, whatever the column says.
            "dashboard_visible": person.role == "admin" or person.dashboard_visible is True,
            "profiles": [{"id": row["profile_id"], "name": row["name"]} for row in theirs],
            "runs": len(theirs),
            "handed_in": sum(1 for p in profiles
                             if p.user_id == person.id and p.id in handed_in),
            "last_logged": max(stamps) if stamps else None,
            **rolled,
        })
    people.sort(key=lambda row: (-row["applied"], -row["logged"], row["name"]))

    # The most actionable line on the screen: a cycle cannot be built until two
    # profiles have reported in, and these are the ones holding it up.
    missing = [{"profile_id": p.id, "name": p.name, "headline": p.headline,
                "person": owners.get(p.user_id)}
               for p in profiles if p.id not in handed_in] if batch_id else []

    org = {
        **_rollup(rows),
        # Overrides the summed per-profile duplicate count, which double-counts
        # a posting every profile that found it. See duplication().
        **duplication(db, batch_id),
        "profiles": len(profiles),
        "people": sum(1 for u in users if u.is_active and u.role == "bd"),
        "open_cycles": db.scalar(select(func.count(Batch.id))
                                 .where(Batch.status == "open")) or 0,
        "handed_in": len(handed_in),
        "expected": len(profiles),
    }

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "org": org, "profiles": rows, "people": people, "missing": missing,
            "activity": activity(db, None, days=ORG_ACTIVITY_DAYS,
                                  date_from=date_from, date_to=date_to),
            "history": history(db),
            # The other half of the job. Everything above says how much was
            # sent; this says what came back, and who is free to take it.
            "interviews": interviews.summary(db, date_from=date_from, date_to=date_to),
            "funnel": interviews.funnel(db, date_from=date_from, date_to=date_to),
            "assessments": assessments.summary(db),
            "developers": interviews.developer_rows(db)}


def profile_detail(db: Session, profile: Profile, batch: Optional[Batch],
                   date_from: Optional[dt.date] = None,
                   date_to: Optional[dt.date] = None) -> dict:
    """One profile, close up — for a manager checking on somebody, or a BD
    looking at their own record."""
    owners = {u.id: u.name for u in db.scalars(select(User))}
    batch_id = batch.id if batch else None
    stats = profile_rows(db, [profile], batch_id, owners, date_from, date_to)[0]

    recent = [
        {"title": job.title, "company": job.company, "platform": job.platform,
         "url": job.url, "applied_on": record.applied_on,
         "logged_at": record.created_at.isoformat() if record.created_at else None}
        for record, job in db.execute(
            select(Application, Job).join(Job, Job.id == Application.job_id)
            .where(Application.profile_id == profile.id)
            .order_by(Application.id.desc()).limit(RECENT_ROWS)).all()
    ]

    recent_cycles = db.scalars(select(Batch).order_by(Batch.id.desc()).limit(6)).all()
    per_cycle = []
    if recent_cycles:
        ids = [b.id for b in recent_cycles]
        logged = dict(db.execute(
            select(BatchApplication.batch_id, func.count(BatchApplication.id))
            .where(BatchApplication.batch_id.in_(ids),
                   BatchApplication.profile_id == profile.id)
            .group_by(BatchApplication.batch_id)).all())
        placed: dict[int, dict] = defaultdict(lambda: {"assigned": 0, "applied": 0})
        for cycle_id, status, count in db.execute(
            select(Assignment.batch_id, Assignment.status, func.count(Assignment.id))
            .where(Assignment.batch_id.in_(ids), Assignment.profile_id == profile.id)
            .group_by(Assignment.batch_id, Assignment.status)
        ).all():
            placed[cycle_id]["assigned"] += count
            if status == "applied":
                placed[cycle_id]["applied"] += count
        per_cycle = [{"id": b.id, "name": b.name, "logged": logged.get(b.id, 0),
                      **placed[b.id]} for b in reversed(recent_cycles)]

    series = activity(db, [profile.id], days=ORG_ACTIVITY_DAYS,
                      date_from=date_from, date_to=date_to)
    return {
        "batch": _brief(batch), "batches": cycle_list(db),
        "profile": {"id": profile.id, "name": profile.name,
                    "headline": profile.headline, "platform": profile.platform,
                    "person": owners.get(profile.user_id),
                    "shared": profile.share_progress is not False,
                    # The developer, and what a client is handed when this
                    # identity applies.
                    "dev_user_id": profile.dev_user_id,
                    "developer": owners.get(profile.dev_user_id),
                    "email": profile.email or "",
                    "resume_url": profile.resume_url or "",
                    "skills": profile.skills or "",
                    "timezone": profile.timezone or "",
                    "rate": profile.rate or "",
                    "availability": profile.availability or "open",
                    "bio": profile.bio or ""},
        "stats": stats, "activity": series, "streak": streak(series),
        "recent": recent, "cycles": per_cycle,
        "interviews": interviews.summary(db, [profile.id], date_from, date_to),
        "funnel": interviews.funnel(db, [profile.id], date_from=date_from, date_to=date_to),
        "assessments": assessments.summary(db, [profile.id]),
        # Narrowed to this one identity, which is the difference between this
        # and the same report on a person's dashboard: a BD running four
        # profiles reads the person-wide one as their own week and this one as
        # "how is Khuram doing".
        "report": range_report(db, [profile.id], date_from, date_to),
    }


def for_developer(db: Session, person: User, batch: Optional[Batch],
                  date_from: Optional[dt.date] = None,
                  date_to: Optional[dt.date] = None) -> dict:
    """A developer's own screen.

    The mirror of for_person, and pointed the other way. A BD's dashboard asks
    how much went out; a developer's asks what is coming back and when they
    have to be somewhere. Same cycle figures underneath, because the developer
    is entitled to know how hard their identities are being worked — but the
    thing at the top of the screen is the next interview, not the row count.

    Not gated by `dashboard_visible`. That switch is about being measured
    without anybody deciding to measure you; this is a calendar and a resume,
    and withholding it only means nobody turns up.
    """
    profiles = list(db.scalars(
        select(Profile).where(Profile.is_active == True,  # noqa: E712
                              Profile.dev_user_id == person.id)
        .order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}

    rows = profile_rows(db, profiles, batch.id if batch else None, owners, date_from, date_to)
    # The contact details a BD pastes into an application, alongside the
    # figures, because this is the screen where the developer keeps them right.
    detail = {p.id: p for p in profiles}
    for row in rows:
        profile = detail[row["profile_id"]]
        row.update({"email": profile.email or "",
                    "resume_url": profile.resume_url or "",
                    "skills": profile.skills or "",
                    "timezone": profile.timezone or "",
                    "rate": profile.rate or "",
                    "bio": profile.bio or "",
                    "platform": profile.platform or ""})

    series = activity(db, [p.id for p in profiles], days=ORG_ACTIVITY_DAYS,
                      date_from=date_from, date_to=date_to)
    totals = _rollup(rows)
    totals["profiles"] = len(rows)

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "profiles": rows, "totals": totals,
            "activity": series, "streak": streak(series),
            # The take-homes sitting on this developer's weekend. Same reason
            # the diary is here and not behind the dashboard switch: it is not
            # a measurement of them, it is work they have been given.
            "assessments": assessments.summary(db, [p.id for p in profiles]),
            # A developer's half of the range report. The applications half is
            # in it too and is honest — they are the applications sent under
            # this developer's identities — but their screen leads on the
            # interviews, because that is the half they were in the room for.
            "report": range_report(db, [p.id for p in profiles], date_from, date_to),
            **interviews.for_developer(db, person, profiles,
                                       date_from=date_from, date_to=date_to)}
