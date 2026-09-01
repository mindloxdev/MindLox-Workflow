"""Take-homes, tests and written exercises. Reads only.

The third thing a client can ask for, after a reply and a call, and the one
that costs a developer a weekend. It sits in the same shape as an interview and
for the same reason: two people write to it and they write different halves.

  The BD sets it        the client sent them the brief, the link and the
                        deadline, so those are theirs.
  The developer does it how far along they are, what they submitted, and what
                        they want their BD to know.

Neither half is guesswork for its owner and neither is first-hand for the other,
which is the same line the interview is split along.

    sent          the client has asked for it. Nobody has started.
    in_progress   the developer picked it up.
    submitted     it went back. What happens next is the client's move.
    passed        it cleared.
    failed        it did not.

`overdue` is the number worth putting on a screen: still open, and the deadline
is behind us. A deadline nobody is watching is the same as no deadline, and an
assessment missed quietly costs the interview that earned it.

Timestamps are stored UTC and read back on the team's clock, like everything
else here. models.working_label does that conversion once, on the server.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (ASSESSMENT_CLOSED, Application, Assessment, Interview, Job,
                     Profile, User, utcnow, working_label)

OPEN = ("sent", "in_progress")
DUE_SOON_DAYS = 3


def _naive_utc(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """Stored timestamps are naive UTC; utcnow() is aware. Comparing the two
    raises, so the marker comes off before anything is compared."""
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def load(db: Session, profile_ids: Optional[Sequence[int]] = None) -> list[Assessment]:
    """Every assessment for these profiles, soonest deadline first.

    `profile_ids=None` is the whole workspace, which only a manager asks for.
    An empty list means this person is attached to no profile and the honest
    answer is nothing — not everything.

    Rows with no deadline sort last rather than first. A client who set no date
    is not more urgent than one who set tomorrow, and NULLs sorting to the top
    is how the least pressing thing ends up at the top of somebody's list.
    """
    if profile_ids is not None and not profile_ids:
        return []
    query = select(Assessment)
    if profile_ids is not None:
        query = query.where(Assessment.profile_id.in_(list(profile_ids)))
    rows = list(db.scalars(query))
    rows.sort(key=lambda row: (row.due_at is None,
                               _naive_utc(row.due_at) or dt.datetime.max,
                               -row.id))
    return rows


def decorate(db: Session, rows: Sequence[Assessment]) -> list[dict]:
    """Assessment rows as the browser wants them.

    Three queries whatever the length of the list: the profiles behind the
    rows, the people behind the profiles, and the jobs the work came from. The
    names are denormalised in rather than left as ids, because every screen
    showing an assessment shows who it is for and who set it.
    """
    if not rows:
        return []
    profile_ids = {row.profile_id for row in rows}
    profiles = {p.id: p for p in db.scalars(
        select(Profile).where(Profile.id.in_(profile_ids)))}

    wanted = {p.user_id for p in profiles.values()} | {p.dev_user_id for p in profiles.values()}
    wanted |= {row.created_by for row in rows} | {row.updated_by for row in rows}
    wanted.discard(None)
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))} if wanted else {}

    job_ids = {row.job_id for row in rows} - {None}
    jobs = {j.id: j for j in db.scalars(
        select(Job).where(Job.id.in_(job_ids)))} if job_ids else {}

    interview_ids = {row.interview_id for row in rows} - {None}
    sittings = {i.id: i for i in db.scalars(
        select(Interview).where(Interview.id.in_(interview_ids)))} if interview_ids else {}

    # When this identity applied for the posting, exactly as it was typed on
    # the sheet — the same field, worked out the same way, as on an interview.
    # A take-home and the call that produced it describe one conversation, and
    # two screens disagreeing about when the application went out is worse than
    # neither of them saying.
    #
    # Keyed on job *and* profile: two identities can have applied to the same
    # posting on different days, and showing one of them under the other is
    # worse than showing nothing.
    applied_on: dict[tuple[int, int], str] = {}
    if job_ids:
        for job_id, profile_id, stamp in db.execute(
            select(Application.job_id, Application.profile_id, Application.applied_on)
            .where(Application.job_id.in_(job_ids))
        ).all():
            applied_on[(job_id, profile_id)] = stamp or ""

    now = _naive_utc(utcnow())
    soon = now + dt.timedelta(days=DUE_SOON_DAYS)

    out = []
    for row in rows:
        profile = profiles.get(row.profile_id)
        developer = people.get(profile.dev_user_id) if profile else None
        job = jobs.get(row.job_id)
        sitting = sittings.get(row.interview_id)
        due = _naive_utc(row.due_at)
        still_open = row.status in OPEN
        out.append({
            "id": row.id,
            "profile_id": row.profile_id,
            "profile": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "developer": developer.name if developer else None,
            "developer_id": profile.dev_user_id if profile else None,
            "interview_id": row.interview_id,
            # What the assessment came out of, when it came out of a call. The
            # stage is what makes it readable — "after the technical round".
            "interview": ({"id": sitting.id, "stage": sitting.stage or "screening",
                           "when": working_label(sitting.scheduled_at)}
                          if sitting else None),
            "job_id": row.job_id,
            # The whole posting, the same six fields an interview carries.
            # A developer opening a take-home wants the wording that was
            # applied to, and the apply link is usually dead by the time a
            # client gets round to sending a test.
            "job": ({"id": job.id, "title": job.title or "", "company": job.company or "",
                     "url": job.url or "", "description_url": job.description_url or "",
                     "platform": job.platform or "",
                     "applied_on": applied_on.get((job.id, row.profile_id), "")}
                    if job else None),
            "title": row.title,
            "client": row.client,
            "brief": row.brief,
            "link": row.link,
            "due": working_label(row.due_at) if row.due_at else None,
            "status": row.status,
            "submission_url": row.submission_url,
            "notes": row.notes,
            "submitted": working_label(row.submitted_at) if row.submitted_at else None,
            "set_by": (people[row.created_by].name if row.created_by in people else None),
            "updated_by": (people[row.updated_by].name if row.updated_by in people else None),
            "is_open": still_open,
            # Only an open one can be late. A submitted assessment that went in
            # after the deadline is a thing that happened, not a thing to chase.
            "overdue": bool(still_open and due and due < now),
            "due_soon": bool(still_open and due and now <= due <= soon),
        })
    return out


def counts(rows: Sequence[dict]) -> dict:
    """The figures a headline is made of."""
    return {
        "open": sum(1 for row in rows if row["is_open"]),
        "overdue": sum(1 for row in rows if row["overdue"]),
        "due_soon": sum(1 for row in rows if row["due_soon"]),
        "submitted": sum(1 for row in rows if row["status"] in ASSESSMENT_CLOSED),
        "passed": sum(1 for row in rows if row["status"] == "passed"),
        "failed": sum(1 for row in rows if row["status"] == "failed"),
        "total": len(rows),
    }


def split(rows: Sequence[dict]) -> dict:
    """One decorated list, cut into what a screen shows.

    Open work first and in deadline order, because that is the only part
    anybody has to act on. Finished work is kept — an assessment that failed is
    worth seeing next to the interview it came from — but it goes underneath.
    """
    return {
        "open": [row for row in rows if row["is_open"]],
        "closed": [row for row in rows if not row["is_open"]],
    }


def summary(db: Session, profile_ids: Optional[Sequence[int]] = None) -> dict:
    rows = decorate(db, load(db, profile_ids))
    return {"rows": rows, **split(rows), "counts": counts(rows)}


def by_profile(db: Session, profile_ids: Optional[Sequence[int]] = None) -> dict[int, dict]:
    """Counts per profile, for the boards that show one row per identity.

    One pass over the whole set rather than a query per profile, so a workspace
    with forty identities costs the same as one with two.
    """
    grouped: dict[int, list[dict]] = {}
    for row in decorate(db, load(db, profile_ids)):
        grouped.setdefault(row["profile_id"], []).append(row)
    return {profile_id: counts(rows) for profile_id, rows in grouped.items()}


def by_developer(db: Session) -> dict[int, dict]:
    """Counts per developer, added up across every identity they are sold under.

    The manager's question is "who has a take-home sitting on them", and that
    is a fact about a person's weekend rather than about an identity — a
    developer running three profiles with one open test each has three, and
    seeing them as three separate ones is how they get missed.
    """
    grouped: dict[int, list[dict]] = {}
    for row in decorate(db, load(db, None)):
        if row["developer_id"]:
            grouped.setdefault(row["developer_id"], []).append(row)
    return {dev_id: counts(rows) for dev_id, rows in grouped.items()}


def for_interviews(db: Session, interview_ids: Sequence[int]) -> dict[int, list[dict]]:
    """Assessments grouped by the interview that produced them.

    So an interview row can say "and a take-home came out of this" without
    every screen that shows interviews having to fetch assessments separately.
    """
    ids = [i for i in interview_ids if i]
    if not ids:
        return {}
    rows = decorate(db, list(db.scalars(
        select(Assessment).where(Assessment.interview_id.in_(ids)))))
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["interview_id"], []).append(row)
    return grouped
