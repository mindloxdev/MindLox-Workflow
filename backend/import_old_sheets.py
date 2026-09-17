"""Load the team's old apply sheets into the database as history.

    python import_old_sheets.py "../Old Apply sheets.xlsx"            # dry run
    python import_old_sheets.py "../Old Apply sheets.xlsx" --commit   # write it

These sheets predate the app. They are not a dispatch cycle and must not be
filed as one: an `Upload` belongs to a batch, and inventing a batch for work
done months ago would put it in that cycle's report and in everybody's
duplication figures. So this writes `jobs` and `applications` only, with
`batch_id` left NULL — the same shape `build_lists` produces, minus the cycle.

What that buys is the thing the sheets are for. `applications` is the all-time
record, and cover mode dispatches a job to a profile only if that profile has
never applied to it. Loading the history is what stops the team being handed,
for the third time, a posting they already worked in July.

WHICH PROFILE A ROW BELONGS TO

Every BD runs two identities — an Accounts Receivable one and a Customer
Service (VA) one — and the sheets record both in a single tab, with a "VA jobs"
column ticked on the VA rows. So the tick is the profile:

    ticked   -> the BD's VA profile
    blank    -> the BD's AR profile

That reading is not a guess. Splitting each sheet on the column and counting
the title words gives "patient / customer / service / care / access / support"
on the ticked side and "billing / revenue / cycle / accounts / receivable /
claims" on the blank side, in all four sheets, which is exactly the two
headlines those profiles carry.

Sidra's two tabs are both VA identities in their own right — Fatima Rizvi and
Rangeena — so each goes to its own profile whole, and the stray ticks in them
are ignored.

IDEMPOTENT

`applications` is UNIQUE(job_id, profile_id) and jobs are looked up by
fingerprint before being created, so running this twice adds nothing the second
time. That is what makes a dry run worth trusting: the counts it prints are
what a real run would insert.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter, defaultdict

import openpyxl
from sqlalchemy import insert, select

from app.main import SessionLocal
from app import history, ingest, matching
from app.models import Application, Job, Profile, User

# Columns 0-4 are the same five in every tab, whatever the headings call them
# ("Date", "Date :", "fDate", "Column 1" all sit at 0). The VA column moves
# about, so it is found by its heading instead of its position.
DATE, PORTAL, COMPANY, URL, TITLE = 0, 1, 2, 3, 4


def _is_va_heading(value: object) -> bool:
    text = str(value or "").strip().lower().replace(" ", "")
    return text in ("vajobs", "vajob")


# One entry per tab we import. `va` alone means the whole tab is that profile;
# `ar` + `va` means split it on the VA column.
SHEETS = {
    "Faria":                    {"bd": "faria@mindlox.ai",
                                 "ar": "Fahad Hassan AR", "va": "Fahad Hassan VA"},
    "Hafsa":                    {"bd": "hafsa@mindlox.ai",
                                 "ar": "Farhan Ahmad AR", "va": "Farhan Ahmad VA"},
    "Aleena ":                  {"bd": "aleena@mindlox.ai",
                                 "ar": "Hasnain Haider AR", "va": "Hasnain Haider VA"},
    "Maimoona":                 {"bd": "maimona@mindlox.ai",
                                 "ar": "Adil Rehman AR", "va": "Adil Rehman VA"},
    "Sidra as Fatima rizvi VA": {"bd": "sidra@mindlox.ai", "ar": None,
                                 "va": "Fatima Rizvi VA"},
    "Sidra As Rangeena VA":     {"bd": "sidra@mindlox.ai", "ar": None,
                                 "va": "Rangeena VA"},
    # Sehar has no account here; the tab's own Profile column says every row was
    # applied as Rangeena, so it joins that identity's history.
    "Sehar batool.":            {"bd": "sidra@mindlox.ai", "ar": None,
                                 "va": "Rangeena VA"},
}

# No heading, no date and no profile column — four bare columns of title,
# client, location and link. Nothing says whose work it was, and filing it
# against a profile on a guess would credit somebody with 46 applications they
# may never have sent.
SKIP_SHEETS = {"Sheet10"}


# The date reader and the portal tidier both moved to app/history.py when the
# same job became something a BD does for themselves from their own screen.
# There is one copy of each and this is not it — a workbook read from a terminal
# and a sheet dropped on a browser have to file identical stamps, or "found on"
# orders two records of the same posting wrongly for as long as both are held.
clean_platform = history.clean_platform
parse_date = history.read_date


def read_sheet(worksheet) -> tuple[list[dict], Counter]:
    """Every usable row of one tab, in the canonical shape the matcher wants."""
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return [], Counter()
    header = rows[0]
    va_column = next((i for i, cell in enumerate(header) if _is_va_heading(cell)), None)

    out, why = [], Counter()
    for raw in rows[1:]:
        def cell(index):
            return raw[index] if index is not None and index < len(raw) else None

        record = {
            "url": ingest.safe_url(str(cell(URL) or "").strip()),
            "title": str(cell(TITLE) or "").strip(),
            "company": str(cell(COMPANY) or "").strip(),
            "platform": clean_platform(cell(PORTAL)),
            "date": parse_date(cell(DATE)),
            "description_url": "",
            "headline": "",
        }
        # "URL" appears as a literal placeholder in a few cells.
        if record["url"].strip().lower() in ("url", "n/a", "na", "-"):
            record["url"] = ""
        if not ingest.is_usable(record):
            why["blank row"] += 1
            continue
        flag = str(cell(va_column) or "").strip()
        record["is_va"] = bool(flag)
        out.append(record)
    return out, why


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("--commit", action="store_true",
                        help="write to the database (otherwise this is a dry run)")
    args = parser.parse_args()

    book = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    db = SessionLocal()

    profiles = {p.name: p for p in db.scalars(select(Profile)).all()}
    users = {u.email: u for u in db.scalars(select(User)).all()}

    missing = set()
    for tab, plan in SHEETS.items():
        if tab not in book.sheetnames:
            missing.add(f"tab {tab!r}")
        if plan["bd"] not in users:
            missing.add(f"user {plan['bd']}")
        for key in ("ar", "va"):
            if plan[key] and plan[key] not in profiles:
                missing.add(f"profile {plan[key]!r}")
    if missing:
        print("Cannot start. Not found:", ", ".join(sorted(missing)))
        return 1

    # 1. Read every tab, tagging each row with the profile it belongs to.
    records: list[dict] = []
    per_tab: dict[str, Counter] = {}
    for tab, plan in SHEETS.items():
        rows, why = read_sheet(book[tab])
        tally = Counter()
        for row in rows:
            name = plan["va"] if (row["is_va"] or not plan["ar"]) else plan["ar"]
            row["profile_id"] = profiles[name].id
            row["user_id"] = users[plan["bd"]].id
            tally[name] += 1
            records.append(row)
        tally.update({f"({reason})": n for reason, n in why.items()})
        per_tab[tab] = tally
    for tab in book.sheetnames:
        if tab not in SHEETS and tab not in SKIP_SHEETS:
            print(f"  note: tab {tab!r} is not in the plan and was left alone")

    print("\nRead from the workbook")
    for tab, tally in per_tab.items():
        parts = ", ".join(f"{name} {n}" for name, n in sorted(tally.items()))
        print(f"  {tab:<26} {parts}")
    print(f"  {'':<26} {len(records)} rows to file")

    # 2. Fingerprint, then collapse the near-identical title/client ones, exactly
    #    as build_lists does — otherwise the same posting typed two ways would
    #    become two jobs here and one job there.
    usable = []
    for record in records:
        fp, tier = matching.fingerprint(record["url"], record["title"], record["company"])
        if not fp:
            continue
        usable.append({**record, "fp": fp, "tier": tier})
    remap = matching.fuzzy_merge(usable)
    for record in usable:
        if record["fp"] in remap:
            record["fp"], record["tier"] = remap[record["fp"]], "L3f"

    tiers = Counter(r["tier"] for r in usable)
    print(f"\nFingerprints: {len(usable)} rows, {len({r['fp'] for r in usable})} distinct jobs"
          f"  ({', '.join(f'{k} {v}' for k, v in sorted(tiers.items()))})")

    # 3. Which of those jobs the database already has.
    wanted = {r["fp"] for r in usable}
    known: dict[str, Job] = {}
    for chunk in [list(wanted)[i:i + 500] for i in range(0, len(wanted), 500)]:
        for job in db.scalars(select(Job).where(Job.fingerprint.in_(chunk))):
            known[job.fingerprint] = job
    print(f"  {len(known)} of those already exist; {len(wanted) - len(known)} are new")

    # 4. Create the missing jobs.
    made: dict[str, Job] = {}
    for record in usable:
        fp = record["fp"]
        if fp in known or fp in made:
            continue
        made[fp] = Job(fingerprint=fp, tier=record["tier"], title=record["title"][:500],
                       company=record["company"][:300],
                       company_key=matching.normalize_text(record["company"])[:300],
                       platform=record["platform"][:120], url=record["url"],
                       description_url="")

    # 5. One application per (job, profile), earliest date wins.
    stamp: dict[tuple[str, int], str] = {}
    owner: dict[tuple[str, int], int] = {}
    for record in usable:
        key = (record["fp"], record["profile_id"])
        date = record["date"]
        if key not in stamp or (date and (not stamp[key] or date < stamp[key])):
            stamp[key] = date
            owner[key] = record["user_id"]

    per_profile = Counter(pid for _, pid in stamp)
    undated = sum(1 for value in stamp.values() if not value)
    dates = sorted(v for v in stamp.values() if v)
    print(f"\nApplications to file: {len(stamp)}"
          f"   dated {dates[0]} to {dates[-1]}" if dates else "")
    if undated:
        print(f"  {undated} carry no readable date and are filed with a blank stamp")

    names = {p.id: p.name for p in profiles.values()}
    print("\nPer profile (new applications, before removing ones already recorded)")
    for pid, n in sorted(per_profile.items(), key=lambda kv: names[kv[0]]):
        print(f"  {names[pid]:<22} {n:>6}")

    if not args.commit:
        print("\nDry run. Nothing was written. Re-run with --commit to apply.")
        db.close()
        return 0

    # ---- write ------------------------------------------------------------
    if made:
        db.add_all(list(made.values()))
        db.flush()
    job_id_of = {fp: job.id for fp, job in {**known, **made}.items()}

    pairs = [(job_id_of[fp], pid) for fp, pid in stamp]
    have: set[tuple[int, int]] = set()
    for chunk in [pairs[i:i + 500] for i in range(0, len(pairs), 500)]:
        have.update(map(tuple, db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_([j for j, _ in chunk]))).all()))

    fresh = [{"job_id": job_id_of[fp], "profile_id": pid,
              "user_id": owner[(fp, pid)], "batch_id": None,
              "applied_on": stamp[(fp, pid)] or None}
             for fp, pid in stamp if (job_id_of[fp], pid) not in have]

    for chunk in [fresh[i:i + 500] for i in range(0, len(fresh), 500)]:
        db.execute(insert(Application), chunk)
    db.commit()

    print(f"\nWritten. {len(made)} new jobs, {len(fresh)} new applications, "
          f"{len(stamp) - len(fresh)} already on record and left alone.")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
