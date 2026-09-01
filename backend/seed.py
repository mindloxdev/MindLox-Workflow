"""Create the first accounts and profiles, and optionally sample sheets.

    python seed.py                 # accounts and profiles only
    python seed.py --samples       # plus CSVs in ./sample_sheets

The sample data is built to show the thing that matters: two profiles with the
same skills, run by two different people, each handing in what they applied to.
Ali runs Khuram and logs 30 jobs; Sara runs Zahid and logs 50. Ten of those are
the same posting found twice. Run the cycle and Khuram gets back the 40 jobs it
has never seen, Zahid the 20 it has never seen.

Each profile also gets the developer it actually sells, and a diary with an
interview in it today — otherwise the developer half of the app seeds into an
empty screen and there is nothing to look at.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import random
from pathlib import Path

from sqlalchemy import select

from app.main import SessionLocal, engine, hash_password
from app.models import (Assessment, Base, Interview, Profile, User,
                        from_working, working_today)

TEAM = [
    ("ali@example.com", "Ali Raza"),
    ("sara@example.com", "Sara Khan"),
    ("hina@example.com", "Hina Malik"),
]

# The people the profiles actually sell. They sign in, see their own diary and
# keep their own resume current, and never touch a list of jobs.
DEVELOPERS = [
    ("khuram.dev@example.com", "Khuram Gill"),
    ("zahid.dev@example.com", "Zahid Iqbal"),
    ("nadia.dev@example.com", "Nadia Sheikh"),
]

# The identity a client sees, the BD who applies as it, and the developer
# behind it. Khuram and Zahid are two different people with the same skills —
# which is the whole reason this product exists.
PROFILES = [
    {"name": "Khuram", "headline": "AI Engineer", "platform": "Upwork",
     "bd": "ali@example.com", "dev": "khuram.dev@example.com",
     "email": "khuram.gill@example.com",
     "resume_url": "https://example.com/resumes/khuram-gill.pdf",
     "skills": "Python, LLMs, RAG, LangChain, AWS, Postgres",
     "timezone": "PKT · overlaps New York 6pm-2am",
     "rate": "$45-60/hr", "availability": "open",
     "bio": "Six years on production ML. Shipped two RAG systems and a fine-tuned "
            "classifier now serving 40k requests a day."},
    {"name": "Zahid", "headline": "AI Engineer", "platform": "Upwork",
     "bd": "sara@example.com", "dev": "zahid.dev@example.com",
     "email": "zahid.iqbal@example.com",
     "resume_url": "https://example.com/resumes/zahid-iqbal.pdf",
     "skills": "Python, PyTorch, Computer Vision, MLOps, GCP",
     "timezone": "PKT · overlaps New York 7pm-1am",
     "rate": "$50-65/hr", "availability": "limited",
     "bio": "Vision and MLOps. Took a detection model from notebook to a "
            "monitored service on GKE."},
    {"name": "Nadia", "headline": "Full Stack Engineer", "platform": "Upwork",
     "bd": "hina@example.com", "dev": "nadia.dev@example.com",
     "email": "nadia.sheikh@example.com",
     "resume_url": "https://example.com/resumes/nadia-sheikh.pdf",
     "skills": "React, Django, Postgres, Docker, Stripe",
     "timezone": "PKT · overlaps New York 5pm-11pm",
     "rate": "$40-55/hr", "availability": "booked",
     "bio": "Full stack, product-side. Comfortable owning a feature from the "
            "schema to the button."},
]

CLIENTS = [
    "Northwind Digital", "Ravensberg GmbH", "Bluepeak Studio", "Talloak Systems",
    "Verdant Labs", "Kite & Compass", "Orchard Retail Pvt Ltd", "Sable Analytics",
    "Copperline Media", "Harbourstone LLC", "Fernwood Health", "Quillmark Inc",
    "Alderpoint AI", "Mistvale Robotics", "Cobalt & Fern", "Larkspur Data",
]

ROLES = [
    "LLM Fine-tuning Engineer", "RAG Pipeline Developer", "Computer Vision Engineer",
    "ML Ops Engineer - AWS", "Chatbot Developer (OpenAI API)", "Data Scraping Automation",
    "Python Automation Scripts", "Recommendation System Engineer",
    "Speech-to-Text Integration", "Document AI / OCR Specialist",
    "Senior React Developer", "Django Backend Developer",
]

PLATFORMS = ["Upwork", "LinkedIn", "Indeed", "Freelancer"]


def build_url(platform: str, seed: int) -> str:
    if platform == "Upwork":
        return f"https://www.upwork.com/jobs/~01{seed:016x}"
    if platform == "LinkedIn":
        return f"https://www.linkedin.com/jobs/view/{3900000000 + seed}"
    if platform == "Indeed":
        return f"https://pk.indeed.com/viewjob?jk={seed:016x}&from=serp"
    return f"https://www.freelancer.com/projects/php/site-build-{7000000 + seed}"


def seed_accounts() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    created = []

    if not db.scalar(select(User).where(User.role == "admin")):
        db.add(User(email="admin@example.com", name="Manager",
                    password_hash=hash_password("admin12345"), role="admin"))
        created.append("admin@example.com / admin12345   manager")
    for email, name in TEAM:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, name=name,
                        password_hash=hash_password("bdpass12345"), role="bd"))
            created.append(f"{email} / bdpass12345   {name}")
    for email, name in DEVELOPERS:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, name=name,
                        password_hash=hash_password("devpass12345"), role="dev"))
            created.append(f"{email} / devpass12345  {name} (developer)")
    db.commit()

    owners = {u.email: u.id for u in db.scalars(select(User)).all()}
    for spec in PROFILES:
        profile = db.scalar(select(Profile).where(Profile.name == spec["name"]))
        if profile is None:
            db.add(Profile(name=spec["name"], headline=spec["headline"],
                           platform=spec["platform"],
                           user_id=owners.get(spec["bd"]),
                           dev_user_id=owners.get(spec["dev"]),
                           email=spec["email"], resume_url=spec["resume_url"],
                           skills=spec["skills"], timezone=spec["timezone"],
                           rate=spec["rate"], availability=spec["availability"],
                           bio=spec["bio"]))
            created.append(f"profile {spec['name']} ({spec['headline']}) — "
                           f"{spec['bd']} applies as it, {spec['dev']} is it")
        elif profile.dev_user_id is None:
            # A workspace seeded before developers existed. Attach one rather
            # than leaving a profile nobody is behind.
            profile.dev_user_id = owners.get(spec["dev"])
            profile.email = profile.email or spec["email"]
            profile.resume_url = profile.resume_url or spec["resume_url"]
            profile.skills = profile.skills or spec["skills"]
            profile.timezone = profile.timezone or spec["timezone"]
            profile.rate = profile.rate or spec["rate"]
            profile.bio = profile.bio or spec["bio"]
            created.append(f"profile {spec['name']} now has {spec['dev']} behind it")
    db.commit()

    created += seed_interviews(db)
    db.close()

    print("Accounts and profiles ready.")
    for line in created:
        print("  ", line)
    if not created:
        print("   (everything already existed)")


def seed_interviews(db) -> list[str]:
    """A diary with something in it today.

    Written relative to today rather than to fixed dates, so the developer
    screens have an interview on them whenever the seed is run rather than
    only during the week somebody wrote this file. Skipped entirely once a
    single interview exists, so re-running never doubles anybody up.
    """
    if db.scalar(select(Interview).limit(1)):
        return []

    profiles = {p.name: p for p in db.scalars(select(Profile)).all()}
    today = working_today()

    def at(days: int, clock: str):
        day = today + dt.timedelta(days=days)
        return from_working(f"{day.isoformat()}T{clock}")

    # The last field is the developer's debrief — what the person in the room
    # said afterwards. Empty on everything still ahead, because nobody debriefs
    # a call that has not happened, and on the one from yesterday, because that
    # is the row the nag on every screen is pointing at.
    #
    # The last two fields are the rung on the ladder and the developer's
    # debrief. Nothing ahead of today carries a debrief — nobody reports on a
    # call that has not happened — and neither does the one from yesterday,
    # because that is the row the nag on every screen is pointing at.
    #
    #        profile,  days, clock,  client, role, mode, status, outcome, mins, stage, debrief
    plan = [
        ("Khuram", 0, "15:00", "Northwind Digital", "RAG Pipeline Developer",
         "video", "scheduled", "pending", 45, "technical", ""),
        ("Zahid", 0, "17:30", "Sable Analytics", "Computer Vision Engineer",
         "call", "scheduled", "pending", 30, "screening", ""),
        ("Khuram", 2, "14:00", "Verdant Labs", "LLM Fine-tuning Engineer",
         "video", "scheduled", "pending", 60, "final", ""),
        ("Nadia", 3, "16:00", "Orchard Retail Pvt Ltd", "Senior React Developer",
         "video", "scheduled", "pending", 45, "screening", ""),
        # Yesterday, still unreported — this is what puts the nag on the screens.
        ("Nadia", -1, "15:30", "Harbourstone LLC", "Django Backend Developer",
         "video", "scheduled", "pending", 30, "technical", ""),
        ("Nadia", -4, "17:00", "Copperline Media", "Full Stack Engineer",
         "video", "done", "offer", 45, "final",
         "Two rounds in one. They want a start date rather than another call."),
        ("Khuram", -6, "16:00", "Larkspur Data", "Document AI / OCR Specialist",
         "video", "done", "passed", 30, "screening",
         "Went long on the OCR pipeline. They are sending a take-home by Friday."),
        ("Zahid", -9, "18:00", "Talloak Systems", "ML Ops Engineer - AWS",
         "video", "done", "rejected", 45, "technical",
         "Wanted five years of Kubernetes in production. Worth filtering for next time."),
    ]

    made = 0
    booked: dict[str, Interview] = {}
    for name, days, clock, client, role, mode, status, outcome, minutes, stage, debrief in plan:
        profile = profiles.get(name)
        if profile is None:
            continue
        row = Interview(profile_id=profile.id, client=client, role=role,
                        scheduled_at=at(days, clock), duration_minutes=minutes,
                        mode=mode, status=status, outcome=outcome, stage=stage,
                        link="https://meet.example.com/" + name.lower(),
                        # The BD's brief, written when they booked it.
                        notes="Wants to hear about the last thing you shipped.",
                        created_by=profile.user_id,
                        debrief=debrief,
                        # And reported by whoever sat it, when there is
                        # anything to report.
                        reported_by=profile.dev_user_id if debrief else None,
                        reported_at=at(days, clock) if debrief else None)
        db.add(row)
        booked.setdefault(f"{name}:{client}", row)
        made += 1
    db.flush()

    # A reply somebody started from the job record and has not agreed a time
    # for. Every screen has a "waiting on a time" list and it should not be
    # empty on a fresh install, or nobody discovers it exists.
    khuram = profiles.get("Khuram")
    if khuram is not None:
        db.add(Interview(profile_id=khuram.id, client="Ironvale Systems",
                         role="Senior RAG Engineer", scheduled_at=at(0, "12:00"),
                         duration_minutes=45, mode="video", status="draft",
                         stage="screening", created_by=khuram.user_id,
                         notes="Replied to the January application. Wants to talk this week."))
        made += 1

    # And one take-home out of the round that produced it, plus one nobody has
    # started, so the assessments screen has both halves on it.
    cleared = booked.get("Khuram:Larkspur Data")
    if khuram is not None and cleared is not None:
        db.add(Assessment(profile_id=khuram.id, interview_id=cleared.id,
                          title="Take-home · Document AI pipeline",
                          client="Larkspur Data",
                          brief="Extract line items from twenty scanned invoices. "
                                "Python, any OCR stack. Half a day at most.",
                          link="https://example.com/take-home/larkspur",
                          due_at=at(2, "17:00"), status="in_progress",
                          created_by=khuram.user_id, updated_by=khuram.dev_user_id))
    nadia = profiles.get("Nadia")
    if nadia is not None:
        db.add(Assessment(profile_id=nadia.id, title="Coding test · React",
                          client="Orchard Retail Pvt Ltd",
                          brief="Two hours, their platform. Sent before the first call.",
                          due_at=at(-1, "17:00"), status="sent",
                          created_by=nadia.user_id, updated_by=nadia.user_id))

    db.commit()
    return [f"{made} sample interviews, two of them today, one waiting on a time",
            "2 sample assessments, one of them already late"] if made else []


def make_samples(folder: str = "sample_sheets") -> None:
    """Sheets with a known, checkable overlap.

    Khuram logs jobs 0-29. Zahid logs jobs 20-69 — so the two share exactly ten
    postings (20-29). The union is 70. Khuram has never seen 40 of them, Zahid
    has never seen 20, and those are the numbers the cycle should hand back.

    Nadia's sheet uses different column names, blank links on some rows and
    shouty titles, to exercise the auto-mapper and the fuzzy tier.
    """
    random.seed(7)
    Path(folder).mkdir(exist_ok=True)

    def catalogue(n: int) -> dict:
        platform = PLATFORMS[n % len(PLATFORMS)]
        return {"title": ROLES[n % len(ROLES)], "company": CLIENTS[n % len(CLIENTS)],
                "platform": platform, "url": build_url(platform, 1000 + n),
                "date": f"2026-08-{(n % 28) + 1:02d}"}

    plan = [
        ("Khuram", range(0, 30), False),
        ("Zahid", range(20, 70), True),      # 20-29 overlap with Khuram
        ("Nadia", range(70, 110), False),
    ]

    for name, job_ids, tracking in plan:
        rows = []
        for n in job_ids:
            job = catalogue(n)
            url = job["url"]
            if tracking:
                # Same posting, different referral link — must still match.
                url += "?utm_source=email&referrer=digest"
            rows.append({**job, "url": url})

        path = os.path.join(folder, f"{name.lower()}-applied.csv")
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if name == "Nadia":
                writer.writerow(["Sr", "Position Applied", "Client Name",
                                 "Job Portal", "Post Link", "Apply Date"])
                for i, row in enumerate(rows, 1):
                    link = "" if i % 3 == 0 else row["url"]
                    title = row["title"].upper() if i % 4 == 0 else row["title"]
                    writer.writerow([i, title, row["company"], row["platform"],
                                     link, row["date"]])
            else:
                writer.writerow(["Job Title", "Company", "Platform", "Job URL", "Applied On"])
                for row in rows:
                    writer.writerow([row["title"], row["company"], row["platform"],
                                     row["url"], row["date"]])
        print(f"  wrote {path}  ({len(rows)} rows for profile {name})")

    print(f"\nSample sheets are in ./{folder}/")
    print("Khuram logged 30, Zahid logged 50, sharing 10 — a pool of 70.")
    print("A coverage cycle should hand Khuram 40 back and Zahid 20.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", action="store_true", help="also write sample CSVs")
    args = parser.parse_args()
    seed_accounts()
    if args.samples:
        print("\nGenerating sample sheets…")
        make_samples()
