"""Database schema.

The unit of work is a PROFILE, not a person.

A profile is the identity a job is applied under — "Khuram, AI Engineer" on
Upwork. One person may run several; two people may share one during a handover.
What must never happen twice is the same *profile* approaching the same client,
because that is one identity applying twice. Two different profiles applying to
the same posting is not a duplicate at all — it is two candidates in the running,
which is the whole point of running more than one profile.

So every history record hangs off profile_id, and user_id rides along only to
answer "who did the typing".

The constraints that carry the product:

  applications  UNIQUE(job_id, profile_id)
      one identity can log a job only once, ever

  assignments   UNIQUE(batch_id, job_id, profile_id)
      a cycle never puts the same job on one profile's list twice

  assignments   UNIQUE(batch_id, job_id) WHERE exclusive
      only for split cycles, where the manager asked for no two profiles to
      share a job. It is a partial index because coverage cycles deliberately
      hand one job to everybody eligible, and a blanket constraint would
      forbid the normal case.
"""
from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

COVER = "cover"      # everyone gets every job they have not worked
SPLIT = "split"      # one job goes to exactly one profile
MODES = (COVER, SPLIT)

# Who signs in, and what the app is for them. A manager runs cycles; a BD works
# profiles; a developer is the person those profiles actually sell — they sit
# the interview and do the work, and the only screen they need is their own.
ROLES = ("admin", "bd", "dev")

# What a developer's calendar looks like. A BD reads this before applying under
# a profile: there is no point winning an interview for somebody who cannot
# take the work.
AVAILABILITY = ("open", "limited", "booked")

INTERVIEW_MODES = ("video", "call", "onsite", "async")
# `draft` is a conversation that exists without a time yet. A client replies,
# whoever read the email finds the job in the record and starts an interview
# from it there and then — the title, the client and the link come across
# straight away, and the time follows once it is agreed. Everything else about
# a draft behaves as if it were not there: it is in no rate, no funnel and no
# count of what is coming, because none of that is true of it yet.
INTERVIEW_STATUSES = ("draft", "scheduled", "done", "cancelled", "no_show")
# `passed` is a round cleared, not the end of it. Both `offer` and `hired`
# count as an offer; only `hired` counts as work actually won.
INTERVIEW_OUTCOMES = ("pending", "passed", "offer", "hired", "rejected")

# The ladder a job climbs. Ordered, and the order is the product: a screening
# call and a final round are not the same event and a team that cannot tell
# them apart cannot see where its conversations die. `assessment` is a rung
# rather than something beside the ladder, because a take-home is a stage a
# candidate is at — the client is not talking to anybody else while it is out.
INTERVIEW_STAGES = ("screening", "technical", "assessment", "final", "offer")


def next_stage(stage: str) -> str:
    """The rung after this one, or the top rung if there is nothing above it.

    Used when a round is cleared and the next one is booked from it. A guess
    rather than a rule — plenty of clients skip the take-home, or run two
    technical rounds — so it is only ever the value the form opens on, and
    whoever books it can move it.
    """
    try:
        index = INTERVIEW_STAGES.index(stage)
    except ValueError:
        return INTERVIEW_STAGES[0]
    return INTERVIEW_STAGES[min(index + 1, len(INTERVIEW_STAGES) - 1)]

# A take-home, a test, a written exercise. The BD sets it because the client
# sent it to them; the developer does it because they are the one who can.
ASSESSMENT_STATUSES = ("sent", "in_progress", "submitted", "passed", "failed")
# Only these say the assessment is finished with.
ASSESSMENT_CLOSED = ("submitted", "passed", "failed")


# The team works to Eastern time, so that is what "applied on" means. Stored
# timestamps stay UTC; this is only for the stamp a person reads. Change it here
# and in the browser app's EntryTable if the team ever moves.
WORKING_TIMEZONE = os.getenv("TIMEZONE", "America/New_York")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def applied_stamp() -> str:
    """Today's date and time where the team actually works.

    ZoneInfo needs the tzdata package on Windows, and a machine without it
    should not take the app down over a cosmetic timestamp — hence the fallback.
    """
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(WORKING_TIMEZONE))
    except Exception:
        now = dt.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M")


def working_zone():
    """The team's timezone, or None on a machine with no timezone database.

    ZoneInfo needs the tzdata package on Windows. A missing one should cost a
    cosmetic hour, not take the app down, so every caller here has a fallback.
    """
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(WORKING_TIMEZONE)
    except Exception:
        return None


def to_working(value: dt.datetime) -> dt.datetime:
    """A stored timestamp as the wall clock where the team works.

    Everything is stored UTC and SQLite hands it back with no marker at all, so
    the marker goes on here — otherwise it reads as local time and a nine
    o'clock interview turns up in the middle of the night.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    zone = working_zone()
    return value.astimezone(zone) if zone else value.astimezone()


def working_today() -> dt.date:
    return to_working(dt.datetime.now(dt.timezone.utc)).date()


def from_working(text: str) -> dt.datetime:
    """A date and time typed on the team's clock, as UTC to store.

    Interviews are agreed in Eastern time because that is the clock the clients
    and the team both work to — see WORKING_TIMEZONE. So "14:30" typed into the
    form means half past two in New York, wherever the person typing it is
    sitting. A string that carries its own offset is believed instead, which is
    what makes the field safe to round-trip through an edit form.
    """
    raw = (text or "").strip().replace(" ", "T")
    if not raw:
        raise ValueError("Give the interview a date and a time.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    stamp = dt.datetime.fromisoformat(raw)
    if stamp.tzinfo is None:
        zone = working_zone()
        stamp = stamp.replace(tzinfo=zone) if zone else stamp.astimezone()
    return stamp.astimezone(dt.timezone.utc).replace(tzinfo=None)


def working_label(value: dt.datetime) -> dict:
    """Every form of one timestamp the browser needs, worked out on the server.

    The app is anchored to one timezone, so the browser must not be the thing
    that decides what "half past two" means — a BD in Karachi and a developer
    in Lisbon have to read one interview as the same moment. `input` is the
    format an <input type="datetime-local"> wants handed back to it.
    """
    local = to_working(value)
    stamp = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return {"iso": stamp.isoformat(),
            "day": local.date().isoformat(),
            "time": local.strftime("%H:%M"),
            "label": local.strftime("%a %d %b · %H:%M"),
            "input": local.strftime("%Y-%m-%dT%H:%M")}


class User(Base):
    """A person who signs in. Managers run cycles; BDs work profiles."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="bd")  # admin | bd
    is_active = Column(Boolean, nullable=False, default=True)
    # Whether this person may open their own dashboard — their figures, their
    # progress, their streak. Off until a manager turns it on, so nobody is
    # measured on a screen before somebody decided to measure them. A manager
    # can always see it, for anyone, either way.
    dashboard_visible = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow)


class Profile(Base):
    """The identity a job is applied under.

    `name` is what the client sees — "Khuram". `headline` is the resume behind
    it — "AI Engineer". Two profiles with the same headline are exactly the
    case this system is built for: same skills, different candidates, both
    free to approach the same job.

    Two people stand behind a profile and they are not the same person.
    `user_id` is the BD who runs the account and does the typing. `dev_user_id`
    is the developer the profile actually sells — the one who sits the
    interview and writes the code. Either may be empty: an identity can exist
    before anybody is behind it, and a developer can be attached later.

    The contact fields — email, resume, skills, rate, timezone — describe the
    developer but live here rather than on their account, because what a client
    is handed is the profile. One developer running two identities may well
    send two different resumes into two different markets, and hanging these
    off the person would force those two to be one.
    """
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    headline = Column(String(160), nullable=False, default="")
    platform = Column(String(120), nullable=False, default="")
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # who runs it
    is_active = Column(Boolean, nullable=False, default=True)
    # Whether this profile's progress appears on the shared team board. The
    # board as a whole is gated by a workspace switch the manager holds; this
    # takes one profile off it without hiding everybody.
    share_progress = Column(Boolean, nullable=False, default=True)

    # The developer behind the identity, and what a client is handed when it
    # applies. All optional — a profile behaves exactly as it did before
    # without any of it, and the screens simply have nothing to show.
    dev_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    email = Column(String(255), nullable=False, default="")
    resume_url = Column(Text, nullable=False, default="")
    skills = Column(String(400), nullable=False, default="")
    timezone = Column(String(64), nullable=False, default="")
    rate = Column(String(40), nullable=False, default="")
    availability = Column(String(16), nullable=False, default="open")
    bio = Column(Text, nullable=False, default="")

    created_at = Column(DateTime, default=utcnow)


class Setting(Base):
    """Workspace switches the manager holds.

    One row per key with a JSON value, so a new switch is a new row rather than
    a migration. The only one so far decides whether the team board — every
    profile's progress side by side — is something a BD may open, or something
    only the manager sees. It starts closed: a board that appears without
    anyone deciding to show it is a performance ranking nobody agreed to.
    """
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Batch(Base):
    """One dispatch cycle. Sheets go in, lists come out.

    A cycle stays `open` while people are still working it: sheets keep
    arriving and the lists are rebuilt on a timer, so a job somebody logs at
    two o'clock is off everyone else's list by ten past. Closing it is a
    separate, deliberate act — that is what stops the rebuilds.
    """
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    status = Column(String(16), nullable=False, default="open")  # open | computed
    mode = Column(String(16), nullable=False, default=COVER)      # cover | split
    quota = Column(Integer, nullable=False, default=40)
    one_per_client = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utcnow)
    computed_at = Column(DateTime, nullable=True)
    report = Column(JSON, default=dict)

    # Minutes between automatic rebuilds; 0 means only when asked.
    auto_build_minutes = Column(Integer, nullable=False, default=10)
    last_built_at = Column(DateTime, nullable=True)
    # Held for the duration of a build so two workers, or a manager and the
    # timer, cannot rebuild the same cycle at once.
    building_since = Column(DateTime, nullable=True)


class Upload(Base):
    """A raw sheet, handed in for one profile.

    Rows are kept verbatim so the column mapping stays editable right up until
    the cycle is computed.
    """
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # who uploaded
    filename = Column(String(255))
    row_count = Column(Integer, default=0)
    headers = Column(JSON, default=list)
    mapping = Column(JSON, default=dict)
    rows = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("batch_id", "profile_id", name="uq_sheet_per_profile"),)


class Job(Base):
    """A posting, identified by fingerprint. Global, not per-cycle, so history
    carries across cycles."""
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String(400), unique=True, nullable=False, index=True)
    tier = Column(String(8))
    title = Column(String(500))
    company = Column(String(300))
    company_key = Column(String(300), index=True)
    platform = Column(String(120))
    url = Column(Text)
    # Where the posting itself is written out, when that is somewhere other
    # than the apply link. A BD reading a client's reply three weeks later
    # needs the wording that was applied to, and the apply link is usually
    # dead by then — an expired posting redirects to a board's home page and
    # takes the description with it.
    description_url = Column(Text, nullable=False, default="")
    first_seen = Column(DateTime, default=utcnow)


class Application(Base):
    """All-time history: this profile has approached this job. Never re-issued."""
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
    applied_on = Column(String(40))
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_application"),)


class BatchApplication(Base):
    """Who applied to what, *in this cycle*.

    `applications` is all-time and unique per (job, profile), so it cannot say
    who collided in cycle 12 once cycle 13 exists — the row belongs to whichever
    cycle saw it first. This keeps the per-cycle picture the report needs.
    """
    __tablename__ = "batch_applications"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    __table_args__ = (UniqueConstraint("batch_id", "job_id", "profile_id",
                                       name="uq_batch_application"),)


class Assignment(Base):
    """A job placed on one profile's list for one cycle.

    `exclusive` mirrors the cycle's mode onto the row so the partial unique
    index below can hold the split-mode guarantee at the database level, while
    leaving coverage cycles free to hand one job to every eligible profile.
    """
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(String(16), default="pending")  # pending | applied | skipped
    exclusive = Column(Boolean, nullable=False, default=False)
    status_changed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("batch_id", "job_id", "profile_id", name="uq_job_per_profile"),
        Index("uq_job_dispatched_once", "batch_id", "job_id",
              unique=True,
              sqlite_where=Column("exclusive") == True,          # noqa: E712
              postgresql_where=Column("exclusive") == True),     # noqa: E712
    )


class Interview(Base):
    """A client wanting to talk to whoever is behind a profile.

    This is the first table in the system that records an *outcome*. Everything
    before it counts effort — rows typed, jobs dispatched, duplication avoided —
    and a team can improve every one of those figures without winning a single
    piece of work. An interview is the first thing that says the applications
    landed, and an outcome on it is the first thing that says they were worth
    sending.

    It hangs off the profile, not the developer, for the same reason everything
    else does: the client is talking to "Khuram, AI Engineer". Who that is, and
    whose calendar it lands in, is `profiles.dev_user_id` and may change.

    Two people write to this row and they write different halves of it. The BD
    runs the account the client replied to, so booking it is theirs: the time,
    the client, the link, the brief. The developer is the one who was in the
    room, so what came of it is theirs: the status, the outcome, the debrief.
    Neither half is guesswork for the person who owns it and neither is
    first-hand for the person who does not, which is why the split is enforced
    on the server rather than left to whoever opens the form first.

    `job_id` is set when the interview came from a posting the system already
    knows about and left empty when it did not — plenty of replies arrive weeks
    later, or through a channel the sheets never saw. `client` and `role` are
    kept on the row either way, so a purged job cannot leave an interview
    describing nothing.
    """
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)
    client = Column(String(300), nullable=False, default="")
    role = Column(String(300), nullable=False, default="")
    # UTC, like every other stored timestamp. What the team typed was Eastern;
    # from_working() did the conversion and working_label() undoes it.
    scheduled_at = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=30)
    mode = Column(String(16), nullable=False, default="video")
    link = Column(Text, nullable=False, default="")
    status = Column(String(16), nullable=False, default="scheduled")
    # Where on the ladder this sitting is. Kept on the interview rather than on
    # the job, because one job produces several of them and each is at a
    # different rung — that progression is the thing worth seeing.
    stage = Column(String(16), nullable=False, default="screening")
    outcome = Column(String(16), nullable=False, default="pending")
    # The BD's brief, written when the interview is booked: what the client
    # asked for, what to lead with. It belongs to whoever runs the account.
    notes = Column(Text, nullable=False, default="")
    # The developer's account of it afterwards. A separate field rather than
    # more text in `notes`, because they are written by different people at
    # different times and one must not overwrite the other — a debrief typed
    # over the top of the brief loses what the BD asked for, and there is no
    # copy of it anywhere else.
    debrief = Column(Text, nullable=False, default="")
    # Who said how it went, and when. The outcome is the only figure in this
    # product that cannot be improved by typing faster, so it is worth knowing
    # whose word it is — usually the developer who was in the room.
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reported_at = Column(DateTime, nullable=True)
    # The round this one follows on from, when it was booked out of a round
    # that was cleared. Empty for a first conversation and for anything logged
    # on its own.
    #
    # The link is what turns five separate rows into one story. A client who
    # ran a screening call, a take-home and two technical rounds before saying
    # no is not the same as four clients who each said no after one call, and
    # in a flat list of interviews those two look identical. It also stops the
    # second round being retyped: the client, the role and the posting come
    # across from the round that earned it.
    #
    # ondelete SET NULL rather than CASCADE. Removing a mistyped screening call
    # must not silently take the real technical round with it — the chain is a
    # convenience, and losing it costs a breadcrumb, not a record.
    previous_id = Column(Integer, ForeignKey("interviews.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # Every screen asks the same question — what is next for this profile —
        # so the index answers it in the order the screens want it.
        Index("ix_interview_profile_time", "profile_id", "scheduled_at"),
    )


class Assessment(Base):
    """A take-home, a test, a written exercise. Set by the BD, done by the dev.

    Its own table rather than a field on an interview, because a client can
    send a test before anybody has spoken — plenty of boards screen that way
    round — and an assessment that could only exist under an interview would
    force somebody to invent a call that never happened to record it.

    `interview_id` is the optional link back to the conversation that produced
    it, which is the common case and is what puts it on that interview's row.
    `job_id` is the posting it came from, when the system knows it. Both may be
    empty; `profile_id` never is, because an assessment is always work somebody
    is being asked to do under one identity.

    The split of who writes what mirrors the interview exactly. The BD sets it
    — the client sent them the brief, the link and the deadline. The developer
    answers it: how far along they are, what they submitted, and what they want
    their BD to know. Neither half is guesswork for its owner.
    """
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id", ondelete="SET NULL"),
                          nullable=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)

    # The BD's half.
    title = Column(String(300), nullable=False, default="")
    client = Column(String(300), nullable=False, default="")
    brief = Column(Text, nullable=False, default="")
    link = Column(Text, nullable=False, default="")
    # UTC like everything else. Nullable, because plenty of clients send a test
    # with no deadline at all and inventing one would put a false red flag on
    # somebody's screen.
    due_at = Column(DateTime, nullable=True, index=True)

    # The developer's half.
    status = Column(String(16), nullable=False, default="sent")
    submission_url = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    submitted_at = Column(DateTime, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # What every screen asks: what is outstanding for this identity, soonest
        # deadline first.
        Index("ix_assessment_profile_due", "profile_id", "due_at"),
    )
