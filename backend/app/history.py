"""Back-loading the months of work a team did before this app existed.

A team arrives here having applied for three months out of spreadsheets. None
of it is in `applications`, so every rule that reads history reads it as a team
that has never applied to anything: cover mode hands them back postings they
worked in July, the duplication figures say nobody has collided with anybody,
and the first month on the new system is spent re-doing the last three.

`import_old_sheets.py` solved that once — from a terminal, for one workbook,
with every tab hand-mapped in the source. This module is the same work as
something a BD does for their own profile, with their own file, as many times
as it takes. The script stays: it is still the right tool for a single workbook
holding the whole team's tabs, and it now shares this module's date reader
rather than keeping a second copy of it.

WHAT AN IMPORT WRITES

`jobs` and `applications`, with `batch_id` left NULL on every application. That
is the whole difference between this and handing in a sheet, and it is not a
detail: an `Upload` is the profile's work *for a cycle* and is counted as such
in the cycle's report, in the duplication matrix and in "handed in 40". Three
months of history is none of those. Filing it as this week's work would put a
job somebody applied for in June into this week's figures for everybody.

What the import's own `batch_id` means is different — see models.HistoryImport.

WHY IT RUNS IN CHUNKS

Three thousand rows is not one request. A run walks the sheet `CHUNK` rows at a
time and records how far it got, so a closed laptop or a restarted server costs
the rows that were in flight and nothing else. Everything already written stays
written, because each chunk commits on its own.

WHY HANDING IN THE SAME FILE AGAIN IS THE REPAIR

Rows do go missing. A connection drops, a browser tab is closed, a server is
redeployed mid-run — and a BD is left with three thousand rows in a file and
two thousand seven hundred and fifty in the system, with no way to tell which
two hundred and fifty are the ones that did not land.

The answer is to hand in the same file again. Jobs are looked up by fingerprint
before being created and `applications` is UNIQUE(job_id, profile_id), so the
two thousand seven hundred and fifty are recognised and left exactly as they
are — not rewritten, not re-dated, not counted twice — and only the missing two
hundred and fifty are inserted. That is true of the script as well; what is new
is that it is *visible*. A run comes back saying what it added, what it found
already on record, and what carries no link and no client and can never be
imported by anybody, so "did it all get in" is a question with an answer on the
screen rather than a thing to hope about.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from . import ingest, matching
from .models import Application, HistoryImport, Job, Profile, utcnow

# Rows per run. Big enough that a three-thousand-row sheet is eight requests
# rather than thirty, small enough that each one commits well inside any
# proxy's idle timeout and a dropped connection costs at most this many rows
# of *progress* — never of data, since what is written is committed.
CHUNK = 400

# A sheet bigger than this is a database export, not a BD's apply log, and
# reading one into memory as JSON would cost more than it could possibly be
# worth. ingest.MAX_ROWS already caps what pandas hands back; this says so in
# a sentence a person can act on.
MAX_ROWS = ingest.MAX_ROWS


def read_date(value: object, today: dt.date | None = None) -> str:
    """The applied-on stamp as YYYY-MM-DD, or "" when the cell says nothing.

    Normalised rather than kept verbatim, unlike a cycle's sheet, because these
    stamps are read against each other. "Found on" takes the newest date across
    everybody holding a posting by comparing the strings, so a sheet written
    "07/22/2026" and a sheet written "2026-07-22" would order wrongly against
    one another for as long as both are on record. One shape, decided here.

    Two formats arrive in real files: real Excel dates, which openpyxl and
    pandas hand back as datetimes, and text, which they do not. Text is read
    US-style, month first, because that is what the sheets using both agree on.

    THE SWAPPED ONES. Excel decides for itself how to read what somebody typed,
    and on a good fraction of rows it reads a day-first date month-first:
    "10/07/2026" was the 10th of July and is stored as the 7th of October. They
    are recognisable without guessing, because they land in the future and
    these are sheets of work already done — a job cannot have been applied for
    next month. Every one becomes a real past date when the two numbers change
    places. A future date that does not survive the swap is left alone; there
    is nothing there to base a repair on.

    The stamp is only ever a label. Identity is the fingerprint, so a date read
    wrongly misstates when a job was applied for, never whether it was.
    """
    today = today or dt.date.today()
    if isinstance(value, (dt.datetime, dt.date)):
        day = value.date() if isinstance(value, dt.datetime) else value
        if day > today:
            try:
                swapped = day.replace(month=day.day, day=day.month)
            except ValueError:
                swapped = day                  # e.g. the 22nd: there is no 22nd month
            if swapped <= today:
                day = swapped
        return day.strftime("%Y-%m-%d")

    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%m/%d/%y", "%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y", "%d %b %Y"):
        try:
            parsed = dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if parsed > today and fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                swapped = parsed.replace(month=parsed.day, day=parsed.month)
            except ValueError:
                swapped = parsed
            if swapped <= today:
                parsed = swapped
        return parsed.strftime("%Y-%m-%d")
    # Unreadable, and kept anyway. A stamp nobody can parse is still what the
    # BD wrote down, and throwing it away would lose the only record of when
    # the job was applied for. It is a label, not a key.
    return text[:40]


def clean_platform(value: object) -> str:
    """"Indeed." and "Direct websites." are the same portal typed twice."""
    text = str(value or "").strip().rstrip(".;").strip()
    if not text:
        return ""
    known = {"indeed": "Indeed", "ziprecruiter": "ZipRecruiter", "linkdin": "LinkedIn",
             "linkedin": "LinkedIn", "monster": "Monster", "glassdoor": "Glassdoor",
             "hiring cafe": "Hiring Cafe", "hiringcafe": "Hiring Cafe",
             "jobright": "Jobright.ai", "jobright ai": "Jobright.ai",
             "jobright.ai": "Jobright.ai", "direct website": "Direct website",
             "direct websites": "Direct website", "dice": "Dice",
             "upwork": "Upwork", "wellfound": "Wellfound",
             "simplyhired": "SimplyHired", "careerbuilder": "CareerBuilder"}
    return known.get(text.lower(), text[:120])


def plan(rows: list[dict], mapping: dict[str, str]) -> tuple[list[str], int]:
    """A fingerprint for every row of the sheet, in the sheet's own order.

    Empty where the row carries nothing a posting can be identified by — no
    link, no client and no title — which is the same test every other part of
    this app uses and is why those rows are reported as unusable rather than
    silently dropped.

    Worked out once, when the sheet arrives and again if the columns are
    remapped, for two reasons. A run then becomes a slice and a loop rather
    than three thousand fingerprints per chunk. And the near-duplicate merge
    below sees the whole sheet at once — chunk by chunk it would only ever
    compare four hundred rows with each other, and the same posting typed two
    ways four hundred rows apart would come out as two jobs.
    """
    projected = ingest.project_rows(rows, mapping)
    records = []
    for record in projected:
        mark, tier = matching.fingerprint(record["url"], record["title"], record["company"])
        records.append({**record, "fp": mark, "tier": tier})

    remap = matching.fuzzy_merge([r for r in records if r["fp"]])
    prints = [remap.get(r["fp"], r["fp"]) if r["fp"] else "" for r in records]
    return prints, sum(1 for mark in prints if mark)


def _best(left: dict, right: dict) -> dict:
    """Two rows naming one posting, merged into the fuller of the two.

    Sheets are typed by people. One row has the platform and no client, the
    next has the client and no link, and taking whichever came first would
    leave the posting permanently missing what the other one knew. The date is
    the exception: the earliest wins, because that is when this profile first
    approached the client and the later row is the same approach typed again.
    """
    out = dict(left)
    for key in ("url", "title", "company", "platform", "description_url"):
        if not out.get(key) and right.get(key):
            out[key] = right[key]
    here, there = out.get("date") or "", right.get("date") or ""
    if there and (not here or there < here):
        out["date"] = there
    return out


def run_chunk(db: Session, record: HistoryImport, size: int | None = None) -> dict:
    """Write the next slice of one import, and say what it did.

    Committed on its own. Whatever this call writes is safe whether or not the
    caller ever asks for the next chunk — which is the point of walking the
    sheet this way, and is why an interrupted import is a resumable one rather
    than a half-written mess nobody can reason about.
    """
    # Read here rather than taken as a default argument, so CHUNK is what the
    # module says now — a default is bound once, when the function is defined,
    # and would ignore anything that changed it afterwards.
    size = size or CHUNK
    rows = ingest.project_rows(record.rows or [], record.mapping or {})
    prints = list(record.prints or [])
    # A sheet stored before `prints` was written, or one whose plan was
    # somehow left short, is planned again here rather than importing a
    # truncated half of itself in silence.
    if len(prints) != len(rows):
        prints, usable = plan(record.rows or [], record.mapping or {})
        record.prints, record.usable_count = prints, usable

    start = max(0, min(record.cursor or 0, len(rows)))
    stop = min(start + max(1, size), len(rows))
    window = list(zip(rows[start:stop], prints[start:stop]))

    unusable = sum(1 for _, mark in window if not mark)

    # One entry per posting named in this slice, fullest reading of it.
    wanted: dict[str, dict] = {}
    for row, mark in window:
        if not mark:
            continue
        row = {**row, "date": read_date(row.get("date")),
               "platform": clean_platform(row.get("platform"))}
        wanted[mark] = _best(wanted[mark], row) if mark in wanted else row

    known: dict[str, Job] = {}
    for chunk in _slices(list(wanted)):
        for job in db.scalars(select(Job).where(Job.fingerprint.in_(chunk))):
            known[job.fingerprint] = job

    fresh: list[Job] = []
    for mark, row in wanted.items():
        job = known.get(mark)
        if job is None:
            # The tier this row would fingerprint to on its own. When that is
            # not the fingerprint it was actually filed under, the near-
            # duplicate merge moved it — which is exactly what L3f records.
            own, tier = matching.fingerprint(row["url"], row["title"], row["company"])
            job = Job(fingerprint=mark, tier=tier if own == mark else "L3f",
                      title=(row["title"] or "")[:500],
                      company=(row["company"] or "")[:300],
                      company_key=matching.normalize_text(row["company"])[:300],
                      platform=(row["platform"] or "")[:120],
                      url=row["url"] or "",
                      description_url=row.get("description_url") or "")
            known[mark] = job
            fresh.append(job)
        else:
            # Filling a gap, never overwriting. The posting is one row shared
            # by everybody holding it, and a back-load is the oldest, least
            # reliable description of it in the building — it may correct an
            # empty field and must not correct a full one.
            if not job.company and row["company"]:
                job.company = row["company"][:300]
                job.company_key = matching.normalize_text(job.company)[:300]
            job.title = job.title or (row["title"] or "")[:500]
            job.platform = job.platform or (row["platform"] or "")[:120]
            job.url = job.url or (row["url"] or "")
            job.description_url = job.description_url or (row.get("description_url") or "")
    if fresh:
        db.add_all(fresh)
        db.flush()

    # Which of these this profile is already on record for. This is the whole
    # top-up story in two queries: what is here stays untouched, what is not
    # here is written.
    ids = {mark: known[mark].id for mark in wanted}
    have: set[int] = set()
    for chunk in _slices(list(ids.values())):
        have.update(job_id for (job_id,) in db.execute(
            select(Application.job_id).where(
                Application.profile_id == record.profile_id,
                Application.job_id.in_(chunk))).all())

    new_rows = [{"job_id": ids[mark], "profile_id": record.profile_id,
                 "user_id": record.user_id,
                 # NULL, and deliberately. History is not a cycle's work — see
                 # the module docstring.
                 "batch_id": None,
                 "applied_on": row["date"] or None}
                for mark, row in wanted.items() if ids[mark] not in have]
    for chunk in _slices(new_rows):
        db.execute(insert(Application), chunk)

    # Every posting this import has resolved, whether it wrote the application
    # or found one already there. This is what puts them on the other profiles'
    # lists, and a job a colleague has never seen is no less worth offering
    # them because this profile had already recorded it.
    seen_ids = list(record.job_ids or [])
    seen = set(seen_ids)
    for job_id in ids.values():
        if job_id not in seen:
            seen.add(job_id)
            seen_ids.append(job_id)

    record.job_ids = seen_ids
    record.added = (record.added or 0) + len(new_rows)
    record.already = (record.already or 0) + (len(ids) - len(new_rows))
    record.unusable = (record.unusable or 0) + unusable
    record.cursor = stop
    record.status = "done" if stop >= len(rows) else "running"
    if record.status == "done" and record.finished_at is None:
        record.finished_at = utcnow()
    db.commit()

    return {"done": record.status == "done", "cursor": record.cursor,
            "row_count": len(rows), "added": record.added,
            "already": record.already, "unusable": record.unusable,
            "jobs": len(record.job_ids or [])}


def shared_postings(db: Session, batch_id: int) -> dict[int, set[str]]:
    """The postings back-loaded into this cycle, and the headlines behind them.

    A history import is filed against whichever cycle was open when it ran, and
    those postings join that cycle's pool and no other. The headline comes with
    them for the same reason a sheet's does: a posting applied for under an
    Accounts Receivable identity belongs on the lists of the profiles selling
    that, not on a Customer Service one's.

    Only imports the BD left shared, and only ones that actually resolved
    something. An import switched off — by the person who made it or by the
    manager — stops feeding the lists from the next build, and nothing already
    dispatched is taken back off anybody, because the builder only ever
    replaces rows nobody has touched.
    """
    if not batch_id:
        return {}
    rows = db.execute(
        select(HistoryImport.job_ids, Profile.headline)
        .join(Profile, Profile.id == HistoryImport.profile_id)
        .where(HistoryImport.batch_id == batch_id,
               HistoryImport.share_with_team == True)      # noqa: E712
    ).all()

    out: dict[int, set[str]] = {}
    for job_ids, headline in rows:
        for job_id in job_ids or []:
            bucket = out.setdefault(job_id, set())
            if headline:
                bucket.add(headline)
    return out


def _slices(items: list, size: int = 500):
    """SQLite caps bound parameters per statement; every IN (…) is fed in slices."""
    for start in range(0, len(items), size):
        yield items[start:start + size]
