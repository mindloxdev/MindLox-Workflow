"""The client account view: everything already recorded, grouped by company.

Reads only. Like `dashboard.py`, `interviews.py` and `assessments.py`, nothing
here writes, so a manager can open this while the timer is halfway through
rebuilding a cycle. The one write in this feature — the manager's own note — is
a route in `main.py`, because it is not a question about the data.

Every other screen in this app is organised by profile, by person or by cycle.
None of those can answer the questions a manager is actually asked: have we
approached Northwind before and how did it go, which clients are live, which
replied and then went quiet, are three of our profiles all applying into the
same company this month. The data was always there; it was never grouped by the
company.

Nothing here is a new source of truth. It is a different cut of `jobs`,
`applications`, `interviews` and `assessments`, and where a rule already exists
it is called rather than restated — the funnel's view of what counts as a
conversation, the chain that turns four sittings into one story, the deadline
that makes a test overdue. A second, slightly different copy of any of those is
how two screens come to disagree about the same client.

The client key is the normalised company name and nothing else — see
`matching.client_key`. There is no clients table and there is not going to be
one: a company is a name somebody typed on a sheet, and the moment identity
lives in a row somebody has to maintain it.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import assessments, interviews, matching
from .dashboard import application_day
from .models import (Application, BatchApplication, ClientNote, Job, Profile,
                     User, to_working, working_label)

# How long a live client can sit untouched before it is worth saying so. Two
# weeks: long enough that a slow week does not raise it, short enough that a
# client who replied and was then forgotten is caught in the same month.
QUIET_DAYS = 14

PER_PAGE = 50
MAX_PER_PAGE = 200

# The ladder, and the order a client is tested against it. First match wins.
#
# Not simply "furthest along": `test_out` and `stalled` beat `in_conversation`
# because those two are the ones waiting on somebody here. A client sitting at
# "in conversation" is fine; a client sitting on an unanswered test is not, and
# a board that files them together hides the only one worth acting on.
#
# `closed` sits below the live states rather than above them. A client who said
# no in March and is talking again in September is talking again.
STATUSES = (
    ("hired", "Hired"),
    ("offer", "Offer"),
    ("test_out", "Assessment out"),
    ("stalled", "Stalled"),
    ("in_conversation", "In conversation"),
    ("replied", "Replied, no time agreed"),
    ("closed", "Closed"),
    ("approached", "Approached"),
)
STATUS_LABELS = dict(STATUSES)
STATUS_ORDER = [key for key, _ in STATUSES]

# The states where somebody is still expected to do something. Going quiet only
# means anything in one of these — a hired client is not neglected, and an
# approached one with no reply has nothing to chase yet.
LIVE_STATUSES = ("offer", "test_out", "stalled", "in_conversation", "replied")


def _day(value: Optional[dt.datetime]) -> Optional[dt.date]:
    return None if value is None else to_working(value).date()


def _in_window(day: Optional[dt.date], date_from: Optional[dt.date],
               date_to: Optional[dt.date]) -> bool:
    """Dated by when the work happened, never by which cycle it belonged to.

    A reply that lands three weeks after the application that earned it belongs
    to the day it landed, and filtering it into whichever cycle happened to be
    open would credit the wrong fortnight.
    """
    if day is None:
        return not (date_from or date_to)
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


# --------------------------------------------------------------------------- #
# Gathering
# --------------------------------------------------------------------------- #

def _gather(db: Session) -> dict:
    """Every row this screen reads, in one pass, keyed by client.

    A handful of queries for the whole workspace rather than a few per client:
    a team a year in has thousands of clients, and a per-client query is the
    shape that turns a page into a minute.
    """
    jobs = {job.id: job for job in db.scalars(select(Job))}
    profiles = {p.id: p for p in db.scalars(select(Profile))}
    people = {u.id: u for u in db.scalars(select(User))}

    postings: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}

    # Who found each posting, per cycle. Two profiles against one job is the
    # duplicated effort the whole product exists to surface, and at one client
    # a run of them is a search problem rather than a dispatch problem.
    found_by: dict[int, set[int]] = defaultdict(set)
    for job_id, profile_id in db.execute(
            select(BatchApplication.job_id, BatchApplication.profile_id)).all():
        found_by[job_id].add(profile_id)

    for row in db.scalars(select(Application)):
        job = jobs.get(row.job_id)
        if job is None:
            continue
        key = job.company_key or matching.client_key(job.company)
        if not key:
            continue
        profile = profiles.get(row.profile_id)
        when = application_day(row.applied_on, row.created_at)
        # The spelling last recorded, not the key. `northwind health` is a slug;
        # "Northwind Health, Inc." is what a person recognises.
        names[key] = job.company or names.get(key, "")
        postings[key].append({
            "job_id": job.id,
            "title": job.title or "",
            "url": job.url or "",
            "description_url": job.description_url or "",
            "platform": job.platform or "",
            "profile_id": row.profile_id,
            "profile": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "bd": (people[profile.user_id].name
                   if profile and profile.user_id in people else None),
            "developer": (people[profile.dev_user_id].name
                          if profile and profile.dev_user_id in people else None),
            "applied_on": row.applied_on or "",
            "day": when,
            "found_here": row.profile_id in found_by.get(job.id, set()),
            "found_by_count": len(found_by.get(job.id, set())),
        })

    talks: dict[str, list[dict]] = defaultdict(list)
    for row in interviews.decorate(db, interviews.load(db, None)):
        key = matching.client_key(row["client"])
        if not key:
            continue
        names.setdefault(key, row["client"] or "")
        talks[key].append(row)

    tests: dict[str, list[dict]] = defaultdict(list)
    for row in assessments.decorate(db, assessments.load(db, None)):
        key = matching.client_key(row["client"])
        if not key:
            continue
        names.setdefault(key, row["client"] or "")
        tests[key].append(row)

    notes = {row.client_key: row for row in db.scalars(select(ClientNote))}
    for key, row in notes.items():
        names.setdefault(key, row.display_name or "")

    return {"postings": postings, "talks": talks, "tests": tests,
            "notes": notes, "names": names}


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #

def _status(talks: Sequence[dict], tests: Sequence[dict]) -> str:
    """Derived, never typed.

    A status somebody sets by hand is a status somebody forgets to change, and
    the screen then says a client is live three months after they said no. Every
    rule below reads a row somebody already had to write for a different reason.
    """
    live = [row for row in talks if not row["is_draft"] and row["status"] != "cancelled"]
    outcomes = {row["outcome"] for row in live}

    if "hired" in outcomes:
        return "hired"
    if "offer" in outcomes:
        return "offer"
    if any(row["is_open"] for row in tests):
        return "test_out"
    if any(row["cleared_nothing_next"] for row in live):
        return "stalled"

    # Anything booked or held that has not settled either way. `rejected` is
    # settled; `pending` on a call that has been and gone is not — nobody has
    # said how it went, and that is a conversation waiting on an answer rather
    # than a client who has gone.
    if any(row["outcome"] not in ("rejected", "hired", "offer") for row in live):
        return "in_conversation"
    if any(row["is_draft"] for row in talks):
        return "replied"
    if "rejected" in outcomes:
        return "closed"
    return "approached"


def _furthest(talks: Sequence[dict]) -> str:
    """The furthest rung any conversation with this client reached."""
    live = [row for row in talks if not row["is_draft"] and row["status"] != "cancelled"]
    rungs = [row["stage"] for row in live if row.get("stage")]
    if not rungs:
        return ""
    order = list(interviews.INTERVIEW_STAGES)
    return max(rungs, key=lambda stage: order.index(stage) if stage in order else -1)


def _next_up(talks: Sequence[dict]) -> Optional[dict]:
    """The next thing anybody has to turn up to, already formatted."""
    ahead = [row for row in talks
             if row["status"] == "scheduled" and not row["is_past"] and not row["is_draft"]]
    if not ahead:
        return None
    soonest = min(ahead, key=lambda row: row["when"]["iso"])
    return {"when": soonest["when"], "profile": soonest["profile"],
            "stage": soonest["stage"], "id": soonest["id"]}


def _last_activity(postings: Sequence[dict], talks: Sequence[dict],
                   tests: Sequence[dict]) -> Optional[dt.date]:
    days = [row["day"] for row in postings if row["day"]]
    days += [dt.date.fromisoformat(row["when"]["day"]) for row in talks]
    days += [dt.date.fromisoformat(row["due"]["day"]) for row in tests if row.get("due")]
    return max(days) if days else None


# --------------------------------------------------------------------------- #
# The list
# --------------------------------------------------------------------------- #

def _note_json(row: Optional[ClientNote], people: dict[int, str]) -> dict:
    if row is None:
        return {"priority": False, "being_worked": False, "note": "",
                "updated_by": None, "updated_at": None}
    return {"priority": bool(row.priority), "being_worked": bool(row.being_worked),
            "note": row.note or "",
            "updated_by": people.get(row.updated_by),
            "updated_at": working_label(row.updated_at)["label"] if row.updated_at else None}


def _rows(db: Session, date_from: Optional[dt.date],
          date_to: Optional[dt.date]) -> list[dict]:
    data = _gather(db)
    people = {u.id: u.name for u in db.scalars(select(User))}
    windowed = bool(date_from or date_to)
    out = []

    for key in sorted(set(data["postings"]) | set(data["talks"])
                      | set(data["tests"]) | set(data["notes"])):
        postings = data["postings"].get(key, [])
        talks = data["talks"].get(key, [])
        tests = data["tests"].get(key, [])

        if windowed:
            postings = [row for row in postings
                        if _in_window(row["day"], date_from, date_to)]
            talks = [row for row in talks
                     if _in_window(dt.date.fromisoformat(row["when"]["day"]),
                                   date_from, date_to)]
            tests = [row for row in tests
                     if row.get("due") is None
                     or _in_window(dt.date.fromisoformat(row["due"]["day"]),
                                   date_from, date_to)]
            if not (postings or talks or tests):
                continue

        status = _status(talks, tests)
        last = _last_activity(postings, talks, tests)
        first = min((row["day"] for row in postings if row["day"]), default=None)
        own = sum(1 for row in postings if row["found_here"])

        out.append({
            "client_key": key,
            "client": data["names"].get(key) or key,
            "status": status,
            "status_label": STATUS_LABELS[status],
            # Applications sent, split the way every other screen splits it:
            # what these profiles found themselves, and what a colleague found
            # and handed over. The two add up to the total, always.
            "applications": len(postings),
            "own_jobs": own,
            "others_jobs": len(postings) - own,
            # Counted once per posting, not once per person who found it. Two
            # profiles finding one job is one piece of duplicated effort, and
            # counting it twice turns a figure meant to be acted on into one
            # nobody trusts.
            "found_twice": len({row["job_id"] for row in postings
                                if row["found_by_count"] > 1}),
            "profiles": sorted({row["profile"] for row in postings}
                               | {row["profile"] for row in talks}),
            "bds": sorted({row["bd"] for row in postings if row["bd"]}
                          | {row["bd"] for row in talks if row.get("bd")}),
            "developers": sorted({row["developer"] for row in postings if row["developer"]}
                                 | {row["developer"] for row in talks if row.get("developer")}),
            "furthest": _furthest(talks),
            "open_tests": sum(1 for row in tests if row["is_open"]),
            "overdue_tests": sum(1 for row in tests if row["overdue"]),
            "next_up": _next_up(talks),
            "first_seen": first.isoformat() if first else None,
            "last_activity": last.isoformat() if last else None,
            "quiet_days": (dt.date.today() - last).days if last else None,
            "note": _note_json(data["notes"].get(key), people),
        })
    return out


SORTS = {
    "client": lambda row: row["client"].lower(),
    "status": lambda row: STATUS_ORDER.index(row["status"]),
    "applications": lambda row: -row["applications"],
    "own_jobs": lambda row: -row["own_jobs"],
    "others_jobs": lambda row: -row["others_jobs"],
    "found_twice": lambda row: -row["found_twice"],
    "open_tests": lambda row: -row["open_tests"],
    "furthest": lambda row: row["furthest"],
    "next_up": lambda row: (row["next_up"] or {}).get("when", {}).get("iso", "~"),
    "last_activity": lambda row: row["last_activity"] or "",
}


def _matches(row: dict, needle: str) -> bool:
    """Somebody pasting out of an email does not know which field it lives in."""
    hay = " ".join([row["client"], row["status_label"], *row["profiles"],
                    *row["bds"], *row["developers"]]).lower()
    return needle in hay


def client_list(db: Session, date_from: Optional[dt.date] = None,
                date_to: Optional[dt.date] = None, status: str = "",
                q: str = "", sort: str = "last_activity",
                page: int = 1, per_page: int = PER_PAGE) -> dict:
    rows = _rows(db, date_from, date_to)

    needle = (q or "").strip().lower()
    if needle:
        rows = [row for row in rows if _matches(row, needle)]
    if status:
        rows = [row for row in rows if row["status"] == status]

    # Counted before the page is cut, so the columns say how many clients are in
    # each state rather than how many happen to be on this page.
    totals = {key: 0 for key, _ in STATUSES}
    for row in rows:
        totals[row["status"]] += 1

    key = SORTS.get(sort or "last_activity", SORTS["last_activity"])
    rows.sort(key=key, reverse=(sort or "last_activity") == "last_activity")

    per_page = min(MAX_PER_PAGE, max(1, per_page))
    page = max(1, page)
    start = (page - 1) * per_page
    return {
        "clients": rows[start:start + per_page],
        "totals": {"clients": len(rows), "by_status": totals,
                   "applications": sum(row["applications"] for row in rows),
                   "found_twice": sum(row["found_twice"] for row in rows)},
        "page": {"page": page, "per_page": per_page, "pages": max(
            1, (len(rows) + per_page - 1) // per_page)},
        "statuses": [{"key": k, "label": v} for k, v in STATUSES],
        "needs_you": needs_you(rows),
    }


# --------------------------------------------------------------------------- #
# What needs you, client-side
# --------------------------------------------------------------------------- #

def needs_you(rows: Sequence[dict]) -> list[dict]:
    """The same three rules as every other list in this app: say what is wrong,
    say why it matters, and carry the route to the thing that fixes it."""
    items = []

    def add(key, level, clients, title, body):
        if clients:
            items.append({"key": key, "level": level, "title": title, "body": body,
                          "clients": [{"client_key": c["client_key"],
                                       "client": c["client"]} for c in clients[:8]],
                          "count": len(clients)})

    add("replied", "now",
        [r for r in rows if r["status"] == "replied"],
        "replied with no time agreed",
        "They replied and said yes. Nobody has anything to turn up to until a "
        "time is on it, and the client is wondering in the meantime.")
    add("overdue", "now",
        [r for r in rows if r["overdue_tests"]],
        "an assessment past its deadline",
        "Nothing on any screen changes when a deadline passes. This is the only "
        "warning there is.")
    add("stalled", "chase",
        [r for r in rows if r["status"] == "stalled"],
        "cleared a round with nothing booked after",
        "They agreed to another round and nothing was ever arranged, usually "
        "because each side thought the other was doing it.")
    add("today", "today",
        [r for r in rows if r["next_up"] and r["next_up"]["when"]["day"]
         == dt.date.today().isoformat()],
        "an interview today",
        "Eastern time. Whoever runs the profile books and rearranges; this "
        "screen only reads.")
    add("quiet", "chase",
        [r for r in rows if r["status"] in LIVE_STATUSES
         and (r["quiet_days"] or 0) > QUIET_DAYS],
        f"gone quiet for more than {QUIET_DAYS} days",
        "Still open on our side, and nothing has happened for a fortnight. "
        "Either it is finished and nobody said so, or it needs a nudge.")
    return items


# --------------------------------------------------------------------------- #
# One client, whole
# --------------------------------------------------------------------------- #

def _found_twice(postings: Sequence[dict]) -> list[dict]:
    """One entry per posting that more than one profile went out and found."""
    by_job: dict[int, dict] = {}
    for row in postings:
        if row["found_by_count"] < 2 or not row["found_here"]:
            continue
        entry = by_job.setdefault(row["job_id"], {
            "job_id": row["job_id"], "title": row["title"], "url": row["url"],
            "platform": row["platform"], "profiles": [],
        })
        if row["profile"] not in entry["profiles"]:
            entry["profiles"].append(row["profile"])
    for entry in by_job.values():
        entry["profiles"].sort()
    return sorted(by_job.values(), key=lambda row: row["title"].lower())


def client_detail(db: Session, client_key: str) -> Optional[dict]:
    data = _gather(db)
    key = (client_key or "").strip()
    if key not in data["postings"] and key not in data["talks"] \
            and key not in data["tests"] and key not in data["notes"]:
        return None

    people = {u.id: u.name for u in db.scalars(select(User))}
    postings = sorted(data["postings"].get(key, []),
                      key=lambda row: (row["day"] or dt.date.min), reverse=True)
    talks = data["talks"].get(key, [])
    tests = data["tests"].get(key, [])
    status = _status(talks, tests)
    last = _last_activity(postings, talks, tests)
    first = min((row["day"] for row in postings if row["day"]), default=None)

    # One block per conversation, not one row per sitting. A client who ran four
    # rounds is one story; four rows look like four clients who each said no
    # once, and the difference is the whole point of the chain.
    chains: dict[int, list[dict]] = defaultdict(list)
    for row in talks:
        chains[row.get("root") or row["id"]].append(row)
    conversations = [
        {"rounds": sorted(rows, key=lambda row: row["when"]["iso"])}
        for rows in chains.values()
    ]
    conversations.sort(key=lambda block: block["rounds"][-1]["when"]["iso"], reverse=True)

    return {
        "client": {
            "client_key": key,
            "client": data["names"].get(key) or key,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "first_seen": first.isoformat() if first else None,
            "last_activity": last.isoformat() if last else None,
            "applications": len(postings),
            "own_jobs": sum(1 for row in postings if row["found_here"]),
            "others_jobs": sum(1 for row in postings if not row["found_here"]),
            "profiles": sorted({row["profile"] for row in postings}
                               | {row["profile"] for row in talks}),
            "bds": sorted({row["bd"] for row in postings if row["bd"]}),
            "developers": sorted({row["developer"] for row in postings if row["developer"]}
                                 | {row["developer"] for row in talks if row.get("developer")}),
        },
        "conversations": conversations,
        "tests": sorted(tests, key=lambda row: (row.get("due") or {}).get("iso", "~")),
        "postings": postings,
        # Postings two profiles both went out and found — one entry per
        # posting, naming everyone who found it. One row per finder would say
        # "found twice" twice, which is the shape that makes a figure meant to
        # be acted on into one nobody trusts.
        "found_twice": _found_twice(postings),
        "note": _note_json(data["notes"].get(key), people),
    }
