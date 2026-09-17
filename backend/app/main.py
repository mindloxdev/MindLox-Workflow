"""Dispatch API.

Run locally:  uvicorn app.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs

The unit of work is a profile, not a person — see models.py.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Iterable, Optional

import bcrypt
import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, create_engine, delete, func, insert, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from . import (assessments, crm, dashboard, exports, history, ingest,
               interviews, matching)
from .models import (ASSESSMENT_CLOSED, ASSESSMENT_STATUSES, AVAILABILITY,
                     COVER, INTERVIEW_MODES, INTERVIEW_OUTCOMES,
                     INTERVIEW_STAGES, INTERVIEW_STATUSES, MODES, ROLES, SPLIT,
                     Application, Assessment, Assignment, Base, Batch,
                     BatchApplication, ClientNote, HistoryImport, Interview,
                     Job, Profile, Setting, Upload,
                     User, applied_stamp, from_working, next_stage,
                     to_working, utcnow, working_label)
from .schema import bring_up_to_date

def _database_url() -> str:
    """Hosted Postgres add-ons hand out `postgres://…`, which SQLAlchemy 2 no
    longer recognises, and none of them say so. Normalise it here so pasting the
    connection string straight from Render, Neon or Heroku just works."""
    url = os.getenv("DATABASE_URL", "sqlite:///./dispatch.db").strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-you-deploy-this")
JWT_HOURS = int(os.getenv("JWT_HOURS", "12"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# Set when one process serves the built browser app as well as the API, which
# is how this deploys: one container, one URL, no proxy to wire up.
WEB_ROOT = os.getenv("WEB_ROOT", "")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# SQLite caps the number of bound parameters in one statement, so every IN (…)
# built from user data is fed through in slices.
_PARAM_CHUNK = 500


def _chunks(items: Iterable, size: int = _PARAM_CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Managed Postgres sits behind a pooler that drops idle connections without
# telling anybody, and this process holds some idle for as long as the gap
# between automatic rebuilds. pool_pre_ping catches a connection that has
# already died; pool_recycle retires one before it gets old enough to. Both are
# harmless against SQLite, which hands back the same file either way.
pool_args = {} if DATABASE_URL.startswith("sqlite") else {"pool_recycle": 300}
engine = create_engine(DATABASE_URL, connect_args=connect_args,
                       pool_pre_ping=True, **pool_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)
bring_up_to_date(engine)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Keep the lists current without anyone pressing anything."""
    ticker = asyncio.create_task(_auto_build_loop()) if AUTO_BUILD_TICK_SECONDS > 0 else None
    try:
        yield
    finally:
        if ticker:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Dispatch", version="2.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Sign in to continue.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Your session expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "That session is not valid.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "This account is no longer active.")
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Only a manager can do that.")
    return user


def can_see_dashboard(user: User) -> bool:
    """Whether this person may look at their own figures.

    A manager always may — both their own and anybody else's. For everyone
    else it is off until a manager opens it, which is the whole point: being
    measured on a screen should be a decision somebody made, not a side effect
    of having an account.
    """
    return user.role == "admin" or user.dashboard_visible is True


def require_dashboard(user: User) -> None:
    if not can_see_dashboard(user):
        raise HTTPException(403, "Your manager has not opened your dashboard yet.")


def owned_profile(profile_id: int, db: Session, user: User) -> Profile:
    """The profile, if this person is allowed to act *as* it.

    Working the list, handing in a sheet, marking a job applied — everything
    that speaks to a client in the profile's name. That is the BD who runs the
    account, and nobody else. The developer behind the profile is deliberately
    not included: they are the person the client will meet, not the person
    applying, and letting them mark jobs applied would put work in a colleague's
    record that colleague did not do.
    """
    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_active:
        raise HTTPException(404, "No such profile.")
    if user.role != "admin" and profile.user_id != user.id:
        raise HTTPException(403, "That profile belongs to someone else.")
    return profile


def linked_profile(profile_id: int, db: Session, user: User) -> Profile:
    """The profile, if this person has any business with it at all.

    A wider door than owned_profile, for the things both sides of a profile
    share — the interview, the resume, the record of how it is doing. Three
    ways to be through it: you manage the workspace, you run the account the
    applications go out from, or you are the developer the client will be
    talking to.
    """
    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_active:
        raise HTTPException(404, "No such profile.")
    if user.role == "admin" or profile.user_id == user.id:
        return profile
    if profile.dev_user_id is not None and profile.dev_user_id == user.id:
        return profile
    raise HTTPException(403, "That profile belongs to someone else.")


def visible_profile_ids(db: Session, user: User) -> Optional[list[int]]:
    """Whose interviews this person may see. None means every one of them,
    which is only ever a manager.

    A BD sees the profiles they run; a developer sees the ones they are sold
    under. An empty list is a real answer — somebody with no profile attached
    sees nothing, not everything.
    """
    if user.role == "admin":
        return None
    column = Profile.dev_user_id if user.role == "dev" else Profile.user_id
    return [row for (row,) in db.execute(
        select(Profile.id).where(Profile.is_active == True,  # noqa: E712
                                 column == user.id)).all()]


# Fields on a profile that describe the developer rather than the identity.
# The developer keeps these current themselves; everything else about a profile
# — its name, who runs it, whether it is on the team board — is the manager's.
DEV_EDITABLE = ("email", "resume_url", "skills", "timezone", "rate",
                "availability", "bio")


def _check_availability(value: str) -> str:
    cleaned = (value or "open").strip().lower()
    if cleaned not in AVAILABILITY:
        raise HTTPException(400, f"Availability must be one of {', '.join(AVAILABILITY)}.")
    return cleaned


def _check_email(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned and "@" not in cleaned:
        raise HTTPException(400, "That does not look like an email address.")
    return cleaned[:255]


def _check_link(value: str, what: str) -> str:
    """A link typed by a person, on its way into somebody else's href.

    Stricter than the sheet reader, which tolerates a bare hostname because
    spreadsheets are full of them. This one is typed into a form by somebody
    who can be told to fix it, and a relative link on a colleague's screen goes
    nowhere useful.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if not re.match(r"^https?://", cleaned, re.I):
        raise HTTPException(400, f"The {what} needs to start with http:// or https://.")
    return cleaned[:2000]


def _check_profile_dev(db: Session, user_id: Optional[int]) -> Optional[int]:
    """A developer is the person the client actually meets. A BD is separate."""
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(400, "No such active developer to attach.")
    if user.role != "dev":
        raise HTTPException(400, "A profile can only be assigned to a developer account.")
    return user.id


def _apply_profile_developer(db: Session, profile: Profile,
                            requested: Optional[int] = None) -> Optional[int]:
    """Attach a developer only when the BD explicitly chooses one for this profile."""
    if requested is None:
        return profile.dev_user_id
    profile.dev_user_id = _check_profile_dev(db, requested)
    return profile.dev_user_id


# --------------------------------------------------------------------------- #
# Request and response shapes
# --------------------------------------------------------------------------- #

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "bd"
    dashboard_visible: bool = False


class UserPatch(BaseModel):
    dashboard_visible: Optional[bool] = None
    # An account outlives the person holding it. When a BD leaves and a new one
    # takes their seat, editing these three hands over every profile they ran
    # and every figure recorded against them in one move — which is the point:
    # reassigning the profiles instead would leave the work split between a name
    # that has gone and a name that has just arrived.
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    # Set when handing the seat over, so the person who left cannot sign in as
    # the person who replaced them.
    password: Optional[str] = None


class ProfileIn(BaseModel):
    name: str
    headline: str = ""
    platform: str = ""
    user_id: Optional[int] = None
    share_progress: bool = True
    # The developer behind the identity. All optional: a profile can be created
    # before anybody is attached to it, and filled in later by whoever it is.
    dev_user_id: Optional[int] = None
    email: str = ""
    resume_url: str = ""
    skills: str = ""
    timezone: str = ""
    rate: str = ""
    availability: str = "open"
    bio: str = ""


class ProfilePatch(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    platform: Optional[str] = None
    user_id: Optional[int] = None
    share_progress: Optional[bool] = None
    dev_user_id: Optional[int] = None
    email: Optional[str] = None
    resume_url: Optional[str] = None
    skills: Optional[str] = None
    timezone: Optional[str] = None
    rate: Optional[str] = None
    availability: Optional[str] = None
    bio: Optional[str] = None


class InterviewIn(BaseModel):
    profile_id: int
    # "2026-08-24T14:30", read as the clock the team works to. See
    # models.from_working — the browser never decides what that means.
    #
    # Optional, because an interview can be started from the job record the
    # moment a client's email arrives, before any time has been agreed. That
    # one is a draft: it holds the client, the role and the links, counts
    # towards nothing, and becomes real when somebody puts a time on it.
    scheduled_at: Optional[str] = None
    client: str = ""
    role: str = ""
    mode: str = "video"
    duration_minutes: int = 30
    link: str = ""
    # The client's own email thread. Optional everywhere it appears — plenty
    # of replies arrive by phone, or through a board's messaging, and a
    # required field would be filled with rubbish rather than left alone.
    email_url: str = ""
    notes: str = ""
    stage: str = "screening"
    job_id: Optional[int] = None
    dev_user_id: Optional[int] = None
    # The round this one follows on from, when it was booked out of a round
    # that was cleared. See POST /api/interviews/{id}/next-round, which is how
    # it is normally set — this is here so a chain can also be repaired by hand.
    previous_id: Optional[int] = None


class NextRoundIn(BaseModel):
    """Booking the round after one that was cleared.

    Everything is optional. The point of the endpoint is that a second round
    should cost one click and no retyping, so every field defaults to what the
    round before it already knows: same profile, same posting, same client,
    same role, and the next rung up the ladder.
    """
    scheduled_at: Optional[str] = None
    stage: Optional[str] = None
    mode: Optional[str] = None
    duration_minutes: Optional[int] = None
    link: str = ""
    email_url: str = ""
    notes: str = ""


class InterviewPatch(BaseModel):
    # The BD's half: when it is, who it is with, what to lead with.
    scheduled_at: Optional[str] = None
    client: Optional[str] = None
    role: Optional[str] = None
    mode: Optional[str] = None
    duration_minutes: Optional[int] = None
    link: Optional[str] = None
    email_url: Optional[str] = None
    notes: Optional[str] = None
    # What happened, and where on the ladder it sits.
    status: Optional[str] = None
    stage: Optional[str] = None
    outcome: Optional[str] = None
    debrief: Optional[str] = None


class AssessmentIn(BaseModel):
    profile_id: int
    title: str = ""
    client: str = ""
    brief: str = ""
    link: str = ""
    # The client's own email thread. Optional; defaults to the one on the
    # interview this came out of, because it is almost always the same thread.
    email_url: str = ""
    # "2026-08-27T17:00" on the team's clock, or empty. Plenty of clients send
    # a test with no deadline at all, and inventing one puts a false red flag
    # on somebody's screen.
    due_at: str = ""
    interview_id: Optional[int] = None
    job_id: Optional[int] = None
    dev_user_id: Optional[int] = None


class AssessmentPatch(BaseModel):
    # The BD's half.
    title: Optional[str] = None
    client: Optional[str] = None
    brief: Optional[str] = None
    link: Optional[str] = None
    email_url: Optional[str] = None
    due_at: Optional[str] = None
    # The developer's half.
    status: Optional[str] = None
    submission_url: Optional[str] = None
    notes: Optional[str] = None


class ClientNoteIn(BaseModel):
    """A manager's own annotation. Advisory: none of it reaches dispatch."""
    priority: Optional[bool] = None
    being_worked: Optional[bool] = None
    note: Optional[str] = None


class SettingsIn(BaseModel):
    team_board_visible: Optional[bool] = None
    # Whether a BD may select a whole list and mark it in one press. See
    # SETTING_DEFAULTS for what turning it off does and does not do.
    bulk_actions_enabled: Optional[bool] = None


class BatchIn(BaseModel):
    name: str
    quota: int = 40
    mode: str = COVER
    one_per_client: bool = False
    auto_build_minutes: int = 10


class BatchPatch(BaseModel):
    """What a manager may change on a cycle that is already running.

    Every field optional and every one absent means "leave it": a screen that
    edits the cap must not also assert the mode it happened to be showing.
    """
    name: Optional[str] = None
    quota: Optional[int] = None
    mode: Optional[str] = None
    one_per_client: Optional[bool] = None
    auto_build_minutes: Optional[int] = None


class TimerIn(BaseModel):
    """Set the cycle clock, or move it. Exactly one of the two is used.

    `minutes` sets the whole budget and starts it counting from now — what a
    manager means by "they get two hours". `add_minutes` moves the budget
    without touching the start, so adding fifteen minutes to a clock that has
    been running an hour leaves an hour already spent; it may be negative,
    which is how time is taken away.

    A budget of zero is no clock at all, and clears the one that is there.
    """
    minutes: Optional[int] = None
    add_minutes: Optional[int] = None


class MappingIn(BaseModel):
    mapping: dict


class ImportPatch(BaseModel):
    """An edit to a history import. Both halves are optional and independent."""
    mapping: Optional[dict] = None
    # Whether these postings go on to the other profiles' lists. The BD picks
    # it when the file is handed in; a manager may change it afterwards on
    # anybody's import.
    share_with_team: Optional[bool] = None


class EntryIn(BaseModel):
    url: str = ""
    title: str = ""
    company: str = ""
    platform: str = ""
    date: str = ""
    description_url: str = ""
    headline: str = ""


class EntriesIn(BaseModel):
    rows: list[EntryIn]


class StatusIn(BaseModel):
    status: str
    # Required when the status is `skipped`, ignored otherwise. See set_status.
    reason: str = ""
    # Turn it down for every profile this person runs, not only this one.
    # Off by default, because two profiles are two candidates and a job wrong
    # for an Accounts Receivable identity may be exactly right for a Customer
    # Service one. On when the reason is about the job rather than the fit —
    # the rate, the location, a client already being worked.
    every_profile: bool = False


class BulkStatusIn(BaseModel):
    """One decision, taken over a whole list at once.

    The same three statuses and the same rules as a single row — a skip still
    has to say why, and the reason is the same sentence for every row in the
    selection, which is the honest shape of the decision somebody is actually
    taking when they select two hundred jobs and turn them all down.
    """
    ids: list[int]
    status: str
    reason: str = ""
    every_profile: bool = False


class JobPatch(BaseModel):
    """An edit to the posting itself, which every profile holding it will see."""
    title: Optional[str] = None
    company: Optional[str] = None
    platform: Optional[str] = None
    url: Optional[str] = None
    description_url: Optional[str] = None


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active,
            # A manager's dashboard is never gated, so it reads True for them
            # whatever the column says.
            "dashboard_visible": can_see_dashboard(u)}


def profile_json(p: Profile, owner: Optional[User] = None,
                 developer: Optional[User] = None) -> dict:
    return {"id": p.id, "name": p.name, "headline": p.headline,
            "platform": p.platform, "user_id": p.user_id,
            "owner": owner.name if owner else None, "is_active": p.is_active,
            # A NULL predates the column and the default is to share, so only an
            # explicit False takes a profile off the board.
            "share_progress": p.share_progress is not False,
            # The developer, and what a client is handed when this identity
            # applies. Every one of these may be empty — a profile nobody has
            # filled in behaves exactly as it did before they existed, and the
            # screens show nothing rather than something wrong.
            "dev_user_id": p.dev_user_id,
            "developer": developer.name if developer else None,
            "developer_email": developer.email if developer else None,
            "email": p.email or "",
            "resume_url": p.resume_url or "",
            "skills": p.skills or "",
            "timezone": p.timezone or "",
            "rate": p.rate or "",
            "availability": p.availability or "open",
            "bio": p.bio or "",
            "label": p.name if not p.headline else f"{p.name} · {p.headline}"}


# The longest clock a manager can set: a working week. Not a rule about how
# people should work, just a guard against a typo — "120" meant as minutes and
# typed as hours is a clock nobody would notice was wrong.
MAX_TIMER_MINUTES = 7 * 24 * 60


def timer_window(b: Batch) -> tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """(start, end) of the cycle clock in UTC, or (None, None) if none is set."""
    minutes = b.timer_minutes or 0
    start = _naive_utc(b.timer_started_at)
    if minutes <= 0 or start is None:
        return None, None
    return start, start + dt.timedelta(minutes=minutes)


def timer_json(b: Batch) -> dict:
    """The clock as the screens need it.

    `seconds_left` is the whole of the contract with the browser. It is counted
    here, on the server, so a laptop whose clock is twenty minutes fast does not
    show its owner twenty minutes less time than everybody else; the browser
    ticks down from it locally and re-reads it on its next poll. Once it reaches
    zero it stays at zero — the clock is over, not counting up. Nothing about the
    cycle changes at that moment, so the number is only ever something to know.
    """
    start, end = timer_window(b)
    if start is None:
        return {"timer_minutes": 0, "timer_started_at": None, "timer_ends_at": None,
                "timer_seconds_left": 0, "timer_running": False}
    left = (end - _naive_utc(utcnow())).total_seconds()
    return {"timer_minutes": b.timer_minutes or 0,
            "timer_started_at": start.isoformat(),
            "timer_ends_at": end.isoformat(),
            "timer_seconds_left": max(0, int(left)),
            "timer_running": left > 0}


def batch_json(b: Batch) -> dict:
    return {"id": b.id, "name": b.name, "status": b.status, "quota": b.quota,
            "mode": b.mode, "one_per_client": b.one_per_client,
            "auto_build_minutes": b.auto_build_minutes or 0,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "computed_at": b.computed_at.isoformat() if b.computed_at else None,
            "last_built_at": b.last_built_at.isoformat() if b.last_built_at else None,
            **timer_json(b),
            "report": b.report or {}}


# --------------------------------------------------------------------------- #
# Auth routes
# --------------------------------------------------------------------------- #

@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password do not match.")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled.")
    return {"token": make_token(user), "user": user_json(user)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


# --------------------------------------------------------------------------- #
# People (manager)
# --------------------------------------------------------------------------- #

@app.get("/api/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [user_json(u) for u in db.scalars(select(User).order_by(User.name)).all()]


@app.get("/api/developers")
def list_developers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Active developers are selectable when booking profile work."""
    return [user_json(u) for u in db.scalars(
        select(User).where(User.role == "dev", User.is_active == True)
        .order_by(User.name)
    ).all()]


@app.post("/api/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Someone already uses that email.")
    if body.role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}.")
    if len(body.password) < 8:
        raise HTTPException(400, "Use a password of at least 8 characters.")
    user = User(email=body.email.lower(), name=body.name.strip(),
                password_hash=hash_password(body.password), role=body.role,
                dashboard_visible=body.dashboard_visible)
    db.add(user)
    db.commit()
    return user_json(user)


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db),
                admin: User = Depends(admin_only)):
    """One person's dashboard, and who the account now belongs to.

    Handing a seat over is an edit rather than a transfer: the profiles, the
    applications and the figures all hang off the account, so renaming it moves
    the whole desk at once and nothing has to be reassigned row by row.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such person.")
    if body.dashboard_visible is not None:
        user.dashboard_visible = body.dashboard_visible
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "A person needs a name.")
        user.name = name
    if body.email is not None:
        email = body.email.strip().lower()
        if not email:
            raise HTTPException(400, "A person needs an email to sign in with.")
        clash = db.scalar(select(User).where(User.email == email, User.id != user_id))
        if clash:
            raise HTTPException(409, f"{clash.name} already uses that email.")
        user.email = email
    if body.role is not None and body.role != user.role:
        if body.role not in ROLES:
            raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}.")
        if user_id == admin.id:
            raise HTTPException(400, "You cannot change your own role — "
                                     "ask another manager to do it.")
        # A profile may only name a developer as its developer, so moving
        # somebody out of that role would leave those profiles pointing at
        # somebody the rules say cannot be there.
        if user.role == "dev" and body.role != "dev":
            behind = db.scalars(select(Profile.name).where(
                Profile.dev_user_id == user_id, Profile.deleted_at.is_(None))).all()
            if behind:
                raise HTTPException(400,
                                    f"{user.name} is the developer behind "
                                    f"{', '.join(behind)}. Put someone else behind "
                                    "them first, or this profile stops being a "
                                    "developer the client can meet.")
        user.role = body.role
    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(400, "Use a password of at least 8 characters.")
        user.password_hash = hash_password(body.password)
    db.commit()
    return user_json(user)


@app.post("/api/users/{user_id}/disable")
def disable_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """They cannot sign in. Everything they did stays, and so do the profiles
    they run — enable puts them straight back to work."""
    if user_id == admin.id:
        raise HTTPException(400, "You cannot disable your own account.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such person.")
    user.is_active = False
    db.commit()
    return user_json(user)


@app.post("/api/users/{user_id}/enable")
def enable_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such person.")
    user.is_active = True
    db.commit()
    return user_json(user)


@app.delete("/api/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """The older spelling of disable, kept so anything still calling it works."""
    return disable_user(user_id, db, admin)


# --------------------------------------------------------------------------- #
# Profiles — the identities jobs are applied under
# --------------------------------------------------------------------------- #

# The three lists a profile can be on. Only "on" is a working screen; the other
# two exist so a manager can find a profile they switched off and put it back.
PROFILE_STATES = ("on", "disabled", "deleted")


def _state_filter(state: str):
    """Which rows belong to one of the three lists.

    Deleting sets `is_active` false as well as stamping `deleted_at`, so every
    query written before deleting existed — and there are many, all asking for
    `is_active == True` — keeps excluding exactly what it should.
    """
    if state == "deleted":
        return Profile.deleted_at.isnot(None)
    if state == "disabled":
        return and_(Profile.is_active == False, Profile.deleted_at.is_(None))  # noqa: E712
    return and_(Profile.is_active == True, Profile.deleted_at.is_(None))  # noqa: E712


def _name_clash(db: Session, name: str,
                exclude_id: Optional[int] = None) -> Optional[Profile]:
    """The profile already holding this name — disabled and deleted ones too.

    Switching a profile off only takes it off the lists; the row keeps its name
    and its history, so it has to keep blocking the name too. Otherwise the same
    identity ends up split across two ids and every figure counted under it is
    half the truth.
    """
    query = select(Profile).where(func.lower(Profile.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Profile.id != exclude_id)
    return db.scalar(query)


def _clash_message(clash: Profile) -> str:
    """Why the name is taken — and, when the holder is off the lists, where.

    A disabled or deleted profile appears on no working screen, so saying only
    "there is already a profile called X" sends a manager hunting a row that is
    not there to find.
    """
    if clash.deleted_at is not None:
        return (f"{clash.name} is deleted, and a deleted profile keeps its name so "
                "the work already recorded under it still adds up. Enable it from "
                "the deleted list below to use it again.")
    if not clash.is_active:
        return (f"{clash.name} is disabled, and a disabled profile keeps its name. "
                "Enable it from the disabled list below instead of making a second "
                "one — its history comes back with it.")
    return (f"There is already a profile called {clash.name}. "
            "Two profiles with one name would split its history in half.")


@app.get("/api/profiles")
def list_profiles(mine: bool = False, state: str = "on",
                  db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Managers see every profile. A BD sees the ones they run, a developer the
    ones they are sold under.

    `state` picks which of the three lists. `disabled` and `deleted` are the
    manager's recovery lists — rows on no working screen that still hold their
    names against anything new, which is the only way to find them again.
    """
    if state not in PROFILE_STATES:
        raise HTTPException(400, f"State must be one of {', '.join(PROFILE_STATES)}.")
    if state != "on" and user.role != "admin":
        raise HTTPException(403, "Only a manager can see profiles that are off the lists.")
    query = select(Profile).where(_state_filter(state))
    if user.role == "dev":
        query = query.where(Profile.dev_user_id == user.id)
    elif mine or user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    owners = {u.id: u for u in db.scalars(select(User)).all()}
    return [profile_json(p, owners.get(p.user_id), owners.get(p.dev_user_id))
            for p in db.scalars(query.order_by(Profile.name)).all()]


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """One profile in full — the identity and the developer behind it.

    Readable by both sides of it, because both need it: the BD is about to
    paste that resume link into an application, and the developer wrote it.
    """
    profile = linked_profile(profile_id, db, user)
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.post("/api/profiles", status_code=201)
def create_profile(body: ProfileIn, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Give the profile a name — whatever the client sees.")
    clash = _name_clash(db, name)
    if clash:
        raise HTTPException(409, _clash_message(clash))
    if body.user_id is None:
        raise HTTPException(400, "A profile must have a BD assigned to it.")
    if not db.get(User, body.user_id):
        raise HTTPException(400, "No such person to run it.")
    dev_id = _check_profile_dev(db, body.dev_user_id)
    profile = Profile(name=name, headline=body.headline.strip(),
                      platform=body.platform.strip(), user_id=body.user_id,
                      share_progress=body.share_progress,
                      dev_user_id=dev_id,
                      email=_check_email(body.email),
                      resume_url=_check_link(body.resume_url, "resume link"),
                      skills=body.skills.strip()[:400],
                      timezone=body.timezone.strip()[:64],
                      rate=body.rate.strip()[:40],
                      availability=_check_availability(body.availability),
                      bio=body.bio.strip())
    db.add(profile)
    db.commit()
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.patch("/api/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfilePatch, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """The manager edits anything. The developer edits their own details.

    Which resume link goes out, which address a client replies to, whether they
    can take work next week — that is the developer's own information, and
    routing every correction through a manager is how it ends up out of date.
    The identity itself — its name, who runs it, whether it is on the team
    board — stays the manager's, because those decide what other people see.
    """
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "No such profile.")

    asked = set(body.model_dump(exclude_unset=True))
    if user.role != "admin":
        if profile.dev_user_id is None or profile.dev_user_id != user.id:
            raise HTTPException(403, "Only a manager can change that profile.")
        beyond = sorted(asked - set(DEV_EDITABLE))
        if beyond:
            raise HTTPException(
                403, f"Only a manager can change {', '.join(beyond)}. "
                     "Your own details — email, resume, skills, rate, timezone, "
                     "availability — are yours to keep current.")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "A profile needs a name.")
        clash = _name_clash(db, name, exclude_id=profile_id)
        if clash:
            raise HTTPException(409, _clash_message(clash))
        profile.name = name
    if body.headline is not None:
        profile.headline = body.headline.strip()
    if body.platform is not None:
        profile.platform = body.platform.strip()
    if body.user_id is not None:
        if not db.get(User, body.user_id):
            raise HTTPException(400, "No such person to run it.")
        profile.user_id = body.user_id
    if body.share_progress is not None:
        profile.share_progress = body.share_progress
    if body.dev_user_id is not None:
        profile.dev_user_id = _check_profile_dev(db, body.dev_user_id)
    if body.email is not None:
        profile.email = _check_email(body.email)
    if body.resume_url is not None:
        profile.resume_url = _check_link(body.resume_url, "resume link")
    if body.skills is not None:
        profile.skills = body.skills.strip()[:400]
    if body.timezone is not None:
        profile.timezone = body.timezone.strip()[:64]
    if body.rate is not None:
        profile.rate = body.rate.strip()[:40]
    if body.availability is not None:
        profile.availability = _check_availability(body.availability)
    if body.bio is not None:
        profile.bio = body.bio.strip()
    db.commit()
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


def _profile_or_404(db: Session, profile_id: int) -> Profile:
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "No such profile.")
    return profile


def _profile_out(db: Session, profile: Profile) -> dict:
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.post("/api/profiles/{profile_id}/disable")
def disable_profile(profile_id: int, db: Session = Depends(get_db),
                    _: User = Depends(admin_only)):
    """Off the working lists, everything kept. The way back is enable.

    A deleted profile that is disabled stays deleted — there is one way back
    from both, and it is the same one.
    """
    profile = _profile_or_404(db, profile_id)
    profile.is_active = False
    db.commit()
    return _profile_out(db, profile)


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    """Off the lists for good, with every record it left behind intact.

    The row is never removed. `interviews` and `assessments` are ON DELETE
    CASCADE, so a real delete would take the diary and the outstanding take-home
    tests with it, and `applications` and `assignments` carry the history every
    report counts. Deleting is therefore a stamp, and the name stays reserved
    because those records still carry it.
    """
    profile = _profile_or_404(db, profile_id)
    if profile.deleted_at is None:
        profile.deleted_at = utcnow()
    profile.is_active = False
    db.commit()
    return _profile_out(db, profile)


@app.post("/api/profiles/{profile_id}/enable")
def enable_profile(profile_id: int, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    """Put a profile back on the working lists, from disabled or from deleted.

    Nothing else is touched, so everything it kept while it was off comes back
    with it and the duplicate guard still knows every posting it has applied to.
    Enabling one that is already on is not an error: the caller asked for a
    profile on the lists, and it is.
    """
    profile = _profile_or_404(db, profile_id)
    if not profile.is_active or profile.deleted_at is not None:
        # `ix_profiles_name` is unique but case-sensitive, while the clash checks
        # are not — so the pair enabling can still walk into is a case variant
        # written straight to the database, by a hand-edit or an importer, while
        # this row was off the lists. Two live profiles under one name, spelled
        # differently, is the thing those checks exist to stop.
        clash = _name_clash(db, profile.name, exclude_id=profile.id)
        if clash:
            raise HTTPException(409, f"A profile called {clash.name} was made while "
                                     "this one was off the lists. Rename one of them first.")
        profile.is_active = True
        profile.deleted_at = None
        db.commit()
    return _profile_out(db, profile)


@app.delete("/api/profiles/{profile_id}/permanent")
def purge_profile(profile_id: int, db: Session = Depends(get_db),
                  _: User = Depends(admin_only)):
    """Remove the row and everything hanging off it. There is no way back.

    `delete_profile` is a stamp precisely so nothing is lost; this is the other
    thing, for a profile that should never have existed — a test row, a typo, a
    duplicate made twice. It is only reachable from the deleted list, so a
    profile has to be stamped deleted before it can be purged: two deliberate
    steps, and the figures visibly drop at the first one rather than at this
    one.

    The dependants go by hand rather than by cascade. `interviews` and
    `assessments` are ON DELETE CASCADE and would go on their own, but
    `uploads`, `applications`, `batch_applications` and `assignments` are plain
    references — under Postgres they would raise, and under SQLite with the
    foreign keys off they would be left pointing at a row that is not there,
    which is the worse of the two. Deleting them here means one behaviour on
    both.

    Jobs are left alone. A posting is shared: the fingerprint that stops two
    BDs typing the same job in twice lives on `jobs`, and taking one out
    because the last profile to apply for it was purged would let it come
    straight back through the front door tomorrow.
    """
    profile = _profile_or_404(db, profile_id)
    if profile.deleted_at is None:
        raise HTTPException(409, "Delete this profile first. Permanent removal is "
                                 "only for profiles already on the deleted list.")
    name = profile.name
    counts = {}
    for label, model in (("sheets", Upload),
                         ("applications", Application),
                         ("cycle applications", BatchApplication),
                         ("dispatched jobs", Assignment),
                         ("interviews", Interview),
                         ("assessments", Assessment)):
        counts[label] = db.execute(
            delete(model).where(model.profile_id == profile.id)).rowcount or 0
    db.delete(profile)
    db.commit()
    return {"ok": True, "name": name, "removed": counts}


# --------------------------------------------------------------------------- #
# Batches
# --------------------------------------------------------------------------- #

@app.get("/api/batches")
def list_batches(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [batch_json(b) for b in db.scalars(select(Batch).order_by(Batch.id.desc())).all()]


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if body.mode not in MODES:
        raise HTTPException(400, f"Mode must be one of {', '.join(MODES)}.")
    batch = Batch(name=body.name.strip() or f"Cycle {utcnow():%d %b}",
                  quota=max(1, body.quota), mode=body.mode,
                  one_per_client=body.one_per_client,
                  auto_build_minutes=max(0, body.auto_build_minutes),
                  created_by=admin.id)
    db.add(batch)
    db.commit()
    return batch_json(batch)


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    uploads = db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    return {
        **batch_json(batch),
        "uploads": [
            {"id": u.id, "profile_id": u.profile_id,
             "profile": profiles[u.profile_id].name if u.profile_id in profiles else "?",
             "headline": profiles[u.profile_id].headline if u.profile_id in profiles else "",
             "person": owners.get(u.user_id, "?"),
             "filename": u.filename, "row_count": u.row_count,
             "usable_count": u.usable_count,
             "headers": u.headers, "mapping": u.mapping}
            for u in uploads
        ],
    }


@app.patch("/api/batches/{batch_id}")
def update_batch(batch_id: int, body: BatchPatch, db: Session = Depends(get_db),
                 _: User = Depends(admin_only)):
    """Change a running cycle's settings.

    These used to be answerable only once, at the moment the cycle was opened,
    which is the moment a manager knows least: the cap that looked right before
    any sheet was in turns out to be starving half the team, and the only way
    out was to close the cycle and start another one — losing the work already
    logged against it.

    Nothing here retracts work. A rebuild only ever replaces assignments still
    sitting at `pending`; a job somebody has already marked applied or skipped
    is their record of this cycle and stays on their list whatever the cap now
    says. So lowering the cap trims what nobody has touched, and raising it
    hands out more.

    The new settings are what the *next* build uses — the one the timer is
    already going to run, or the one the manager asks for with Build now.
    Rebuilding here instead would make saving a typo in the cycle's name a
    minute of the whole team's lists moving under them.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    if batch.status != "open":
        raise HTTPException(400, "This cycle is closed. Reopen it before changing its settings.")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "A cycle needs a name.")
        batch.name = name[:160]
    if body.quota is not None:
        batch.quota = max(1, body.quota)
    if body.mode is not None:
        if body.mode not in MODES:
            raise HTTPException(400, f"Mode must be one of {', '.join(MODES)}.")
        batch.mode = body.mode
    if body.one_per_client is not None:
        batch.one_per_client = body.one_per_client
    if body.auto_build_minutes is not None:
        batch.auto_build_minutes = max(0, body.auto_build_minutes)

    db.commit()
    return batch_json(batch)


# --------------------------------------------------------------------------- #
# Uploads — one sheet per profile, per cycle
# --------------------------------------------------------------------------- #

@app.post("/api/batches/{batch_id}/uploads", status_code=201)
def upload_sheet(batch_id: int, profile_id: int = Form(...), file: UploadFile = File(...),
                 sheet: str = Form(""),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    if batch.status != "open":
        raise HTTPException(400, "This cycle is closed. Ask your manager to open a new one.")
    profile = owned_profile(profile_id, db, user)

    too_big = "That file is over 15 MB. Split it or remove extra columns."
    if (file.size or 0) > MAX_UPLOAD_BYTES:      # rejected before it is read
        raise HTTPException(413, too_big)
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, too_big)
    try:
        frame = ingest.read_table(raw, file.filename or "sheet.csv", sheet=sheet)
    except Exception as exc:
        raise HTTPException(400, f"Could not read that file: {exc}")

    headers = list(frame.columns)
    rows = frame.to_dict(orient="records")
    mapping = ingest.auto_map(headers)
    # Which tab of the workbook this came from. A workbook with a tab per person
    # is this team's normal shape, so the sheet that was read has to be said out
    # loud and the others offered — guessing silently is how somebody ends up
    # handing in a colleague's work under their own profile.
    tab = frame.attrs.get("sheet") or ""
    tabs = list(frame.attrs.get("sheets") or [])

    # One sheet per profile per batch — a re-upload replaces the old one.
    existing = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                              Upload.profile_id == profile.id))
    if existing:
        db.delete(existing)
        db.flush()

    stored = f"{file.filename} — {tab}" if tab else (file.filename or "")
    upload = Upload(batch_id=batch_id, profile_id=profile.id, user_id=user.id,
                    filename=stored[:255], row_count=len(rows), headers=headers,
                    mapping=mapping, rows=rows,
                    usable_count=len(ingest.apply_mapping(rows, mapping)))
    db.add(upload)
    db.commit()

    return {"id": upload.id, "profile_id": profile.id, "profile": profile.name,
            "filename": upload.filename, "row_count": upload.row_count,
            "usable_count": upload.usable_count,
            "headers": headers, "mapping": mapping, "sheet": tab, "sheets": tabs,
            "preview": rows[:5], "fields": ingest.FIELDS}


@app.patch("/api/uploads/{upload_id}/mapping")
def set_mapping(upload_id: int, body: MappingIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "No such upload.")
    owned_profile(upload.profile_id, db, user)
    upload.mapping = {k: v for k, v in body.mapping.items()
                      if k in {f["key"] for f in ingest.FIELDS}}
    # Remapping a column changes how many rows the matcher can read — pointing
    # "Job link" at the right column is often what turns half a sheet from
    # unusable into usable — so the count has to be taken again here.
    upload.usable_count = len(ingest.apply_mapping(upload.rows or [], upload.mapping))
    db.commit()
    return {"ok": True, "mapping": upload.mapping,
            "usable_count": upload.usable_count, "row_count": upload.row_count}


# --------------------------------------------------------------------------- #
# Typing jobs in by hand — the same sheet, entered a row at a time
# --------------------------------------------------------------------------- #

# Column names used when a profile's sheet is typed rather than uploaded. The
# mapping is then the identity, so hand-entered and uploaded sheets travel
# through exactly the same code from here on.
TYPED_HEADERS = {"url": "Job link", "title": "Job title", "company": "Company",
                 "platform": "Platform", "date": "Applied on",
                 "description_url": "Job description link", "headline": "Headline"}


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/entries")
def list_entries(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    upload = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                            Upload.profile_id == profile.id))
    if not upload:
        return {"rows": [], "filename": None, "row_count": 0, "typed": True}
    rows = ingest.project_rows(upload.rows or [], upload.mapping or {})

    # What each typed row has become in the database, so the screen can offer
    # the same two actions the all-time record does. A row that has not been
    # through a build yet is not a job anywhere else and carries no id — which
    # is the truth, and is why `job_id` may be null.
    prints = [matching.fingerprint(row["url"], row["title"], row["company"])[0]
              for row in rows]
    jobs: dict[str, Job] = {}
    for chunk in _chunks({fp for fp in prints if fp}):
        for job in db.scalars(select(Job).where(Job.fingerprint.in_(chunk))):
            jobs[job.fingerprint] = job
    logged = {job_id for (job_id,) in db.execute(
        select(Application.job_id).where(Application.profile_id == profile.id,
                                         Application.job_id.in_([j.id for j in jobs.values()])))
        } if jobs else set()
    sourced = _sourced_jobs(db, [j.id for j in jobs.values()], user) \
        if user.role != "admin" else {j.id for j in jobs.values()}

    out = []
    for row, fingerprint in zip(rows, prints):
        job = jobs.get(fingerprint) if fingerprint else None
        out.append({**row, "headline": profile.headline or "",
                    "job_id": job.id if job else None,
                    "in_record": bool(job and job.id in logged),
                    "can_edit": bool(job and job.id in sourced)})

    return {"rows": out, "filename": upload.filename, "row_count": len(out),
            "usable_count": upload.usable_count,
            "typed": (upload.mapping or {}) == TYPED_HEADERS}


@app.put("/api/batches/{batch_id}/profiles/{profile_id}/entries")
def save_entries(batch_id: int, profile_id: int, body: EntriesIn,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Replace this profile's sheet with what is on screen.

    Saving rewrites the sheet in canonical columns. For a sheet that arrived as
    a file that means any extra columns are dropped — only these five are ever
    read anyway, and the alternative is an editor that quietly disagrees with
    what is stored.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    if batch.status != "open":
        raise HTTPException(400, "This cycle is closed. Ask your manager to open a new one.")
    profile = owned_profile(profile_id, db, user)

    if len(body.rows) > ingest.MAX_ROWS:
        raise HTTPException(413, f"That is over {ingest.MAX_ROWS} rows. Upload it as a file instead.")

    kept = []
    for entry in body.rows:
        record = {"url": ingest.safe_url(entry.url), "title": entry.title.strip(),
                  "company": entry.company.strip(), "platform": entry.platform.strip(),
                  "date": entry.date.strip(),
                  "description_url": ingest.safe_url(entry.description_url),
                  # Applications always belong to the profile's headline.
                  "headline": profile.headline.strip()}
        # Judge on the fields that identify a job. The timestamp is stamped for
        # the user the moment they add a row, so every untouched row carries one
        # — counting it would file a blank row as work.
        if ingest.is_usable(record):
            kept.append({TYPED_HEADERS[key]: value for key, value in record.items()})

    upload = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                            Upload.profile_id == profile.id))

    if not kept:
        # Nothing typed is nothing handed in. Without this, opening the entry
        # screen and clicking away would leave an empty sheet behind, which the
        # manager would see as a profile having reported in.
        if upload is not None:
            db.delete(upload)
            db.commit()
        return {"ok": True, "row_count": 0, "usable": 0, "usable_count": 0,
                "filename": None}

    if upload is None:
        upload = Upload(batch_id=batch_id, profile_id=profile.id, user_id=user.id,
                        filename="Typed in")
        db.add(upload)
    elif upload.mapping != TYPED_HEADERS:
        upload.filename = f"{upload.filename} (edited)" if upload.filename else "Typed in"
    was = ingest.project_rows(upload.rows or [], upload.mapping or {})
    upload.headers = list(TYPED_HEADERS.values())
    upload.mapping = dict(TYPED_HEADERS)
    upload.rows = kept
    upload.row_count = len(kept)
    usable = len(ingest.apply_mapping(kept, TYPED_HEADERS))
    upload.usable_count = usable
    upload.user_id = user.id

    corrected = _propagate_sheet_edits(db, was, kept, user)
    db.commit()

    return {"ok": True, "row_count": len(kept), "usable": usable,
            "usable_count": usable, "filename": upload.filename,
            "corrected": corrected}


def _propagate_sheet_edits(db: Session, before: list[dict], after_raw: list[dict],
                           user: User) -> int:
    """Carry a correction typed on a sheet through to the shared posting.

    Fixing a client's name on your own sheet used to change nothing anybody
    else could see: `build_lists` fills a job's fields only when they are
    empty, so the posting kept whatever it was first given and the sheet and
    the job quietly disagreed from then on.

    Only fields the BD actually changed. Comparing the new sheet against the
    *job* instead would make every save an assertion about every field, so
    re-saving an untouched sheet would stamp its old wording back over a
    colleague's correction — last writer wins, on a screen nobody thinks of as
    writing to shared data. Comparing against the previous sheet says something
    much narrower and truer: this person just edited this field, so this is
    what they mean it to say.

    The link is deliberately not propagated. It is what the fingerprint is
    built from, so changing it does not correct a posting — it names a
    different one, and the row simply becomes that other job on the next build.
    Corrections to identity go through PATCH /api/jobs/{id}, which checks for a
    collision first.
    """
    after = ingest.project_rows(after_raw, TYPED_HEADERS)
    keyed_before: dict[str, dict] = {}
    for row in before:
        fingerprint, _ = matching.fingerprint(row["url"], row["title"], row["company"])
        if fingerprint:
            keyed_before.setdefault(fingerprint, row)

    changed: dict[str, dict] = {}
    for row in after:
        fingerprint, _ = matching.fingerprint(row["url"], row["title"], row["company"])
        old = keyed_before.get(fingerprint) if fingerprint else None
        if not fingerprint or old is None:
            continue
        edits = {field: row[field]
                 for field in ("title", "company", "platform", "description_url")
                 if (row.get(field) or "") != (old.get(field) or "")}
        if edits:
            changed[fingerprint] = edits
    if not changed:
        return 0

    jobs = {job.fingerprint: job for job in db.scalars(
        select(Job).where(Job.fingerprint.in_(list(changed))))}
    if not jobs:
        return 0
    allowed = _sourced_jobs(db, [job.id for job in jobs.values()], user) \
        if user.role != "admin" else {job.id for job in jobs.values()}

    corrected = 0
    for fingerprint, edits in changed.items():
        job = jobs.get(fingerprint)
        if job is None or job.id not in allowed:
            continue
        if "title" in edits:
            job.title = edits["title"][:500]
        if "company" in edits:
            job.company = edits["company"][:300]
            job.company_key = matching.normalize_text(job.company)[:300]
        if "platform" in edits:
            job.platform = edits["platform"][:120]
        if "description_url" in edits:
            job.description_url = ingest.safe_url(edits["description_url"])[:2000]
        corrected += 1
    return corrected


@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "No such upload.")
    owned_profile(upload.profile_id, db, user)
    db.delete(upload)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# History — the months of work that happened before this app
# --------------------------------------------------------------------------- #
#
# A BD arrives here with three months of applying in a spreadsheet and nothing
# in `applications` to show for it, so every rule that reads history reads them
# as somebody who has never applied to anything. See app/history.py for what an
# import writes, why it is not an Upload, and why handing the same file in twice
# is the repair for rows that went missing rather than a mistake to guard
# against.


def _my_import(import_id: int, db: Session, user: User) -> HistoryImport:
    record = db.get(HistoryImport, import_id)
    if not record:
        raise HTTPException(404, "No such import.")
    owned_profile(record.profile_id, db, user)
    return record


def import_json(record: HistoryImport, profile: Optional[Profile] = None) -> dict:
    return {
        "id": record.id, "profile_id": record.profile_id,
        "profile": profile.name if profile else "",
        "batch_id": record.batch_id,
        "filename": record.filename or "",
        "share_with_team": bool(record.share_with_team),
        "headers": record.headers or [], "mapping": record.mapping or {},
        "row_count": record.row_count or 0,
        "usable_count": record.usable_count or 0,
        "cursor": record.cursor or 0,
        "added": record.added or 0, "already": record.already or 0,
        "unusable": record.unusable or 0,
        "jobs": len(record.job_ids or []),
        "status": record.status,
        "created_at": working_label(record.created_at)["label"] if record.created_at else "",
        "finished_at": working_label(record.finished_at)["label"] if record.finished_at else "",
    }


@app.get("/api/history/imports")
def list_imports(profile_id: Optional[int] = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    """Every back-load this person can see, newest first.

    A BD sees their own profiles' and a manager sees everybody's, which is the
    same rule as every other screen here. The half-finished ones are what this
    list is really for: it is where somebody goes when a run was interrupted and
    they need to carry it on.
    """
    query = select(HistoryImport).order_by(HistoryImport.id.desc())
    allowed = visible_profile_ids(db, user)
    if profile_id is not None:
        owned_profile(profile_id, db, user)
        query = query.where(HistoryImport.profile_id == profile_id)
    elif allowed is not None:
        if not allowed:
            return {"imports": []}
        query = query.where(HistoryImport.profile_id.in_(allowed))

    records = db.scalars(query.limit(100)).all()
    profiles = {p.id: p for p in db.scalars(select(Profile).where(
        Profile.id.in_({r.profile_id for r in records})))} if records else {}
    return {"imports": [import_json(r, profiles.get(r.profile_id)) for r in records]}


@app.post("/api/history/imports", status_code=201)
def start_import(profile_id: int = Form(...), file: UploadFile = File(...),
                 share_with_team: bool = Form(True), sheet: str = Form(""),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Read an old sheet and work out what is in it. Nothing is written yet.

    Two steps rather than one, because the columns have to be right before three
    thousand rows are filed against a profile and the only person who can say
    whether the column headed "Link" is the apply link or the description is the
    person who typed it. So this reads the file, guesses the mapping and says
    what it found; `/run` is what writes.

    The cycle open right now is recorded on the import, and it is the one cycle
    whose lists these postings may join — see models.HistoryImport.
    """
    profile = owned_profile(profile_id, db, user)

    too_big = "That file is over 15 MB. Split it in two and import them one after the other."
    if (file.size or 0) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, too_big)
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, too_big)
    try:
        frame = ingest.read_table(raw, file.filename or "history.csv", sheet=sheet)
    except Exception as exc:
        raise HTTPException(400, f"Could not read that file: {exc}")

    headers = list(frame.columns)
    rows = frame.to_dict(orient="records")
    mapping = ingest.auto_map(headers)
    prints, usable = history.plan(rows, mapping)
    # Which tab this came from, and what else the workbook held. An old sheet is
    # nearly always a workbook with a tab per person, so this is the difference
    # between importing your own three thousand rows and importing a colleague's.
    tab = frame.attrs.get("sheet") or ""
    tabs = list(frame.attrs.get("sheets") or [])

    # The cycle these postings may reach, which is whichever one is open. A
    # workspace between cycles can still import — the history is recorded, and
    # it still stops the importer being handed the same posting again — it
    # simply reaches no colleague, and the screen says so rather than
    # pretending otherwise.
    open_batch = db.scalar(select(Batch).where(Batch.status == "open")
                           .order_by(Batch.id.desc()))

    record = HistoryImport(
        profile_id=profile.id, user_id=user.id,
        batch_id=open_batch.id if open_batch else None,
        filename=(f"{file.filename} — {tab}" if tab else (file.filename or ""))[:255],
        share_with_team=bool(share_with_team),
        headers=headers, mapping=mapping, rows=rows, prints=prints,
        row_count=len(rows), usable_count=usable, status="ready")
    db.add(record)
    db.commit()

    return {**import_json(record, profile), "preview": rows[:5],
            "fields": ingest.FIELDS, "sheet": tab, "sheets": tabs,
            "batch_open": bool(open_batch),
            "batch_name": open_batch.name if open_batch else ""}


@app.patch("/api/history/imports/{import_id}")
def adjust_import(import_id: int, body: ImportPatch, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Correct the columns, or change who the postings reach.

    The columns can only move before the first row is written. After that the
    mapping is what the rows already on record were read through, and changing
    it would make the tallies describe a sheet that was never imported — so a
    run that has started is remapped by importing the file again, which costs
    nothing, because everything already filed is recognised and left alone.
    """
    record = _my_import(import_id, db, user)

    if body.mapping is not None:
        if (record.cursor or 0) > 0:
            raise HTTPException(400, "This import has already started writing. "
                                     "Import the file again to read it through "
                                     "different columns — nothing already on "
                                     "record is written twice.")
        record.mapping = {k: v for k, v in body.mapping.items()
                          if k in {f["key"] for f in ingest.FIELDS}}
        record.prints, record.usable_count = history.plan(record.rows or [],
                                                          record.mapping)
    if body.share_with_team is not None:
        record.share_with_team = bool(body.share_with_team)

    db.commit()
    return import_json(record, db.get(Profile, record.profile_id))


@app.post("/api/history/imports/{import_id}/run")
def run_import(import_id: int, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    """Write the next slice, and say what it did.

    One call, one chunk, committed on its own. The caller keeps pressing until
    `done` comes back true; stopping halfway costs nothing, because the import
    remembers how far it got and what is written is written.
    """
    record = _my_import(import_id, db, user)
    if record.status == "done":
        return {"done": True, "cursor": record.cursor, "row_count": record.row_count,
                "added": record.added, "already": record.already,
                "unusable": record.unusable, "jobs": len(record.job_ids or [])}
    return history.run_chunk(db, record)


@app.delete("/api/history/imports/{import_id}")
def delete_import(import_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Forget the sheet. What it filed stays filed.

    Said out loud on the screen, because it is the one thing about this that
    surprises people. The applications this wrote are the profile's history now
    and are indistinguishable from any other — there is no undo, because "undo"
    would mean deleting the record of work that was really done. What goes is
    the file and its tallies, and the postings stop being offered to colleagues
    on the next build.
    """
    record = _my_import(import_id, db, user)
    db.delete(record)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Compute — the heart of it
# --------------------------------------------------------------------------- #

@app.post("/api/batches/{batch_id}/compute")
def compute(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Build the lists now. The timer calls build_lists directly."""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    return build_lists(db, batch)


def build_lists(db: Session, batch: Batch) -> dict:
    batch_id = batch.id
    uploads = db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
    if len(uploads) < 2:
        raise HTTPException(400, "At least two sheets are needed before anything can be compared.")

    # 1. Flatten every sheet into canonical records tagged with the profile it
    #    was handed in for.
    records = []
    for upload in uploads:
        for row in ingest.apply_mapping(upload.rows or [], upload.mapping or {}):
            fp, tier = matching.fingerprint(row["url"], row["title"], row["company"])
            if not fp:
                continue
            records.append({**row, "fp": fp, "tier": tier, "profile_id": upload.profile_id})

    if not records:
        raise HTTPException(400, "No usable rows. Check that a job link, or a title and client, is mapped.")

    # 2. Collapse near-duplicate L3 fingerprints.
    remap = matching.fuzzy_merge(records)
    for record in records:
        if record["fp"] in remap:
            record["fp"] = remap[record["fp"]]
            record["tier"] = "L3f"

    # 3. Upsert jobs, then record applications. Every lookup here is done in
    #    bulk: one query per few hundred fingerprints rather than one query per
    #    row, which is the difference between a snappy Compute and a minute of
    #    staring at a spinner on a real team's sheets.
    known: dict[str, Job] = {}
    for chunk in _chunks({record["fp"] for record in records}):
        for job in db.scalars(select(Job).where(Job.fingerprint.in_(chunk))):
            known[job.fingerprint] = job

    seen: dict[str, Job] = {}
    fresh: list[Job] = []
    for record in records:
        fp = record["fp"]
        # Every record naming this posting is read, not just the first. Two
        # sheets describe one job with different gaps in them — one has the
        # platform, the other the description link — and taking only the first
        # left the job permanently missing whatever that one sheet omitted.
        job = seen.get(fp) or known.get(fp)
        if job is None:
            job = Job(fingerprint=fp, tier=record["tier"], title=record["title"][:500],
                      company=record["company"][:300],
                      company_key=matching.normalize_text(record["company"])[:300],
                      platform=record["platform"][:120], url=record["url"],
                      description_url=record.get("description_url") or "")
            fresh.append(job)
        else:
            job.title = job.title or record["title"][:500]
            if not job.company and record["company"]:
                job.company = record["company"][:300]
                # The searchable form has to move with the name it is derived
                # from, or the job stops matching the client it now says.
                job.company_key = matching.normalize_text(job.company)[:300]
            # Filled here as well as at creation. A job first built from a
            # sheet whose Platform column was not yet mapped — or from a
            # colleague who left the cell blank — kept an empty platform for
            # good, and showed as "—" on every screen from then on even though
            # the sheet behind it named the board all along.
            job.platform = job.platform or record["platform"][:120]
            job.url = job.url or record["url"]
            # One colleague recording the description link is enough for
            # everybody: the job is one row and they all read it.
            job.description_url = job.description_url or (record.get("description_url") or "")
        seen[fp] = job
    if fresh:
        db.add_all(fresh)
        db.flush()

    all_profiles = {p.id: p for p in db.scalars(
        select(Profile).where(Profile.is_active == True)).all()}  # noqa: E712
    applied_by: dict[int, set[int]] = {}
    headline_by_job: dict[int, set[str]] = defaultdict(set)
    applied_on: dict[tuple[int, int], str] = {}
    for record in records:
        job = seen[record["fp"]]
        applied_by.setdefault(job.id, set()).add(record["profile_id"])
        headline = (all_profiles.get(record["profile_id"]).headline
                if record["profile_id"] in all_profiles else "")
        if headline:
            headline_by_job[job.id].add(headline)
        stamp = (record.get("date") or "").strip()
        if stamp:
            applied_on.setdefault((job.id, record["profile_id"]), stamp[:40])

    owner_of = {p.id: p.user_id for p in db.scalars(select(Profile)).all()}

    have: set[tuple[int, int]] = set()
    for chunk in _chunks(applied_by):
        have.update(map(tuple, db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_(chunk))).all()))
    new_applications = [
        {"job_id": job_id, "profile_id": pid, "user_id": owner_of.get(pid),
         "batch_id": batch_id, "applied_on": applied_on.get((job_id, pid))}
        for job_id, pids in applied_by.items() for pid in pids
        if (job_id, pid) not in have
    ]
    if new_applications:
        db.execute(insert(Application), new_applications)

    # The per-cycle record. `applications` is all-time and unique per
    # (job, profile), so it cannot say who collided *in this cycle* once a later
    # cycle exists — that is what the manager's report needs.
    db.execute(delete(BatchApplication).where(BatchApplication.batch_id == batch_id))
    this_cycle = [{"batch_id": batch_id, "job_id": job_id, "profile_id": pid}
                  for job_id, pids in applied_by.items() for pid in pids]
    if this_cycle:
        db.execute(insert(BatchApplication), this_cycle)
    db.flush()

    handed_in = sorted({u.profile_id for u in uploads if u.profile_id})

    # A cycle is open, two profiles have reported in, and a third selling the
    # same skills has logged nothing yet — because they are new, or were away,
    # or simply have not got to it. Leaving them out means the profile with the
    # most spare capacity is the one handed no work, which is backwards.
    #
    # They join as recipients only. Nothing of theirs is in the pool, because
    # they contributed nothing to it, and their own history still blocks
    # anything they have already applied to — a late joiner is given jobs, not
    # given away.
    joined: list[int] = []
    if handed_in:
        joined = matching.similar_profiles(
            [{"id": pid, "skills": all_profiles[pid].skills}
             for pid in handed_in if pid in all_profiles],
            [{"id": pid, "skills": profile.skills}
             for pid, profile in all_profiles.items() if pid not in handed_in])

    participants = sorted(set(handed_in) | set(joined))

    # 4. The pool is what this cycle's sheets hold, and nothing else.
    #
    #    Unworked jobs used to be dragged forward out of earlier cycles, so that
    #    a job somebody ran out of time for did not fall through the cracks.
    #    With one cycle open at a time that reads well. With two it is the bug
    #    the BDs reported: the newer cycle gathered 79 postings and its lists
    #    came out holding 359 places, 190 of them dragged out of the older cycle
    #    and 183 of those never touched. "Others' jobs" was mostly last
    #    fortnight's leftovers, and a cycle's figures counted work it never
    #    gathered.
    #
    #    Worse, both cycles rebuild on the same timer, and each build pulled the
    #    other's untouched rows onto its own lists and deleted them from the
    #    first. The same job moved between cycles every five minutes.
    #
    #    Nothing is lost by leaving it out. Those rows stay exactly where they
    #    were, on the cycle that dispatched them, and that cycle stays in the
    #    round picker whether it is open or closed. Work belongs to the cycle
    #    that gathered it.
    pool_ids = {job.id for job in seen.values()}

    #    Plus whatever anybody back-loaded into *this* cycle. A BD handing in
    #    three months of old spreadsheets is handing the team three months of
    #    postings, and leaving them out would make the import worth something
    #    to the importer — who is blocked from being offered them again — and
    #    nothing at all to the colleague who has never seen them. Bounded to
    #    the cycle the import was filed against, by the same rule as above:
    #    work belongs to the cycle that gathered it, and a back-load must not
    #    trail through every cycle from now on.
    #
    #    `deferred` is the other half of it. These are months old, and the
    #    cycle's own postings are this week's: with a cap of forty a list that
    #    filled up with June before it reached Tuesday would be worse than no
    #    import at all. So they are placed after everything this cycle
    #    gathered, and get what room is left.
    back_loaded = history.shared_postings(db, batch_id)
    pool_ids |= set(back_loaded)

    # 5. What each profile may NOT be given: any posting it has already used.
    #
    #    Used means one of two things and they are blocked identically:
    #    applied for at any time, or looked at and turned down. Per profile,
    #    not per person — Khuram having applied says nothing about whether
    #    Zahid should.
    #
    #    Blocked twice over, by row and by posting, because the row alone is
    #    not enough. The same job reaches this system by several routes — the
    #    listing, the apply flow with `/apply` on the end, a board's mirror of
    #    a company careers page — and those fingerprint differently, so a
    #    posting somebody has already worked comes back as a new row with no
    #    history against it. Both halves of the bug BDs reported are this: a
    #    job they turned down reappearing, and a new cycle handing them work
    #    they had already applied for.
    #
    #    The by-row pass stays, and is not redundant. `_posting_key` needs both
    #    a client and a title, and a row that carries only a link has neither —
    #    for those the row id is the only identity there is.
    blocked: dict[int, set[int]] = defaultdict(set)
    for chunk in _chunks(pool_ids):
        for job_id, pid in db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_(chunk))
        ).all():
            blocked[job_id].add(pid)

    # ...and anything already sitting unworked on one of their other cycles.
    # Not "used" — they have not done anything with it yet — but a job that
    # both cycles gathered would otherwise be handed out twice, one row per
    # cycle, for a single application. It is also the other half of the job
    # that hopped between cycles: whichever cycle built last took it off the
    # one that built first. Now the cycle that dispatched it keeps it.
    if participants:
        for job_id, pid in db.execute(
            select(Assignment.job_id, Assignment.profile_id)
            .where(Assignment.batch_id != batch_id,
                   Assignment.status == "pending",
                   Assignment.profile_id.in_(participants))
        ).all():
            blocked[job_id].add(pid)

    # By posting, for the profiles actually in the running. Two queries rather
    # than one per job: a few thousand rows on a real workspace.
    used: dict[int, set[str]] = defaultdict(set)
    if participants:
        # Named `worked` rather than `history`, which is the module this file
        # imports for back-loading old sheets — one local would have shadowed
        # it for the rest of the function.
        worked = (
            select(Application.job_id, Application.profile_id,
                   Job.url, Job.company_key, Job.title)
            .join(Job, Job.id == Application.job_id)
            .where(Application.profile_id.in_(participants)),
            select(Assignment.job_id, Assignment.profile_id,
                   Job.url, Job.company_key, Job.title)
            .join(Job, Job.id == Assignment.job_id)
            .where(Assignment.status == "skipped",
                   Assignment.profile_id.in_(participants)),
        )
        for query in worked:
            for job_id, pid, url, company_key, title in db.execute(query).all():
                blocked[job_id].add(pid)
                mark = _posting_key(url, company_key, title)
                if mark:
                    used[pid].add(mark)

    job_rows: dict[int, Job] = {job.id: job for job in seen.values()}
    missing = pool_ids - set(job_rows)
    for chunk in _chunks(missing):
        for job in db.scalars(select(Job).where(Job.id.in_(chunk))):
            job_rows[job.id] = job

    headline_by_profile = {pid: (profile.headline or "") for pid, profile in all_profiles.items()}
    # What this cycle's own sheets gathered. A posting in both — somebody
    # back-loaded it and somebody else handed it in this week — is this week's
    # work and is not deferred.
    seen_ids = {job.id for job in seen.values()}
    pool = []
    for job_id in sorted(pool_ids):
        job = job_rows.get(job_id)
        if job is None:
            continue
        against = set(blocked.get(job_id, ()))
        # ...and anyone who has already used this same posting under another
        # link, whether they applied for it or turned it down.
        mark = _posting_key(job.url, job.company_key, job.title)
        if mark:
            against |= {pid for pid, marks in used.items() if mark in marks}
        # The headlines a posting was applied under — this cycle's sheets and
        # any back-load together, because both are somebody saying "this job
        # suited that market" and the builder wants every such vote.
        headlines = headline_by_job.get(job_id, set()) | back_loaded.get(job_id, set())
        pool.append({"job_id": job_id, "company_key": job.company_key or "",
                     "blocked_for": against,
                     "headlines": headlines,
                     # Placed after everything this cycle gathered. A
                     # three-month back-load must not spend a BD's whole cap on
                     # June before it reaches this week.
                     "defer": 1 if (job_id in back_loaded
                                    and job_id not in seen_ids) else 0,
                     "headline_by_profile": headline_by_profile})

    place = matching.cover if batch.mode == COVER else matching.partition
    assigned, stats = place(pool, participants, batch.quota, batch.one_per_client)
    stats["joined_on_skills"] = len(joined)

    # Only the untouched rows are replaced. A job somebody has already marked
    # applied or skipped is their record of this cycle's work, and rebuilding —
    # which now happens on a timer, not just when a manager asks — must not make
    # it vanish from under them.
    #
    # A row that is still on the same list is *kept*, not deleted and minted
    # again. It is the same job on the same list either way, but the id is what
    # the BD's screen holds and what "I applied to this one" is addressed to.
    # Clearing the whole lot and re-inserting gave every untouched job a new id
    # on every rebuild, so for the minute between a rebuild and the screen's
    # next poll — every ten minutes, all day — pressing Applied or Skipped was
    # answered with "No such job on your sheet" and the BD's decision was lost.
    #
    # Invisible to this suite, which runs on SQLite: SQLite hands the deleted
    # rowids straight back out, so the ids came out identical and the bug only
    # existed on the Postgres the product actually runs on, where a sequence
    # never reuses a number.
    rows = db.scalars(select(Assignment).where(Assignment.batch_id == batch_id)).all()
    worked = {(a.profile_id, a.job_id) for a in rows if a.status != "pending"}
    standing = {(a.profile_id, a.job_id): a for a in rows if a.status == "pending"}

    exclusive = batch.mode == SPLIT
    wanted = {(pid, job_id)
              for pid, job_ids in assigned.items() for job_id in job_ids
              if (pid, job_id) not in worked}

    # Gone from the lists: taken by somebody else in a split cycle, pushed out
    # by the cap, or its sheet withdrawn.
    retired = [row.id for pair, row in standing.items() if pair not in wanted]
    for chunk in _chunks(retired):
        db.execute(delete(Assignment).where(Assignment.id.in_(chunk)))

    # The mode can be changed on a running cycle, and the flag the unique index
    # reads has to move with it or a cycle switched to split would stop being
    # held to one profile per job.
    for pair, row in standing.items():
        if pair in wanted and row.exclusive != exclusive:
            row.exclusive = exclusive
    db.flush()

    dispatch = [{"batch_id": batch_id, "job_id": job_id, "profile_id": pid,
                 "user_id": owner_of.get(pid), "status": "pending",
                 "exclusive": exclusive}
                for pid, job_id in sorted(wanted)
                if (pid, job_id) not in standing]
    if dispatch:
        db.execute(insert(Assignment), dispatch)

    # 6. Report for the manager.
    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    matrix = matching.overlap_matrix(
        [{"applied_by": v} for v in applied_by.values()], participants)
    collisions = sum(1 for v in applied_by.values() if len(v) > 1)
    wasted = sum(len(v) - 1 for v in applied_by.values() if len(v) > 1)
    reached = len({job_id for job_ids in assigned.values() for job_id in job_ids})

    batch.report = {
        "Rows read": len(records),
        "Unique jobs": len(seen),
        "Jobs two profiles both applied to": collisions,
        "Duplicate applications": wasted,
        "Jobs nobody could take": stats["saturated"],
        "Jobs held back by the client rule": stats["held_back_client"],
        "Jobs held back by the quota": stats["held_back_quota"],
        "Jobs put on a list": reached,
        "Places on lists": stats["placements"],
        # Profiles that handed nothing in and were given the pool anyway,
        # because they sell the same skills as somebody who did.
        "Profiles pulled in on skills": stats.get("joined_on_skills", 0),
    }
    # Building no longer closes the cycle. People keep logging jobs into an open
    # cycle and the timer keeps the lists current; closing it is a separate act.
    batch.last_built_at = utcnow()
    batch.computed_at = batch.last_built_at
    db.commit()

    counts = defaultdict(lambda: defaultdict(int))
    for profile_id, status, count in db.execute(
        select(Assignment.profile_id, Assignment.status, func.count(Assignment.id))
        .where(Assignment.batch_id == batch_id)
        .group_by(Assignment.profile_id, Assignment.status)).all():
        counts[profile_id][status] = count

    return {
        **batch_json(batch),
        "participants": _participant_json(participants, profiles, owners, counts=counts),
        "matrix": {"names": [profiles[p].name if p in profiles else "?" for p in participants],
                   "rows": [[matrix[a][b] for b in participants] for a in participants]},
    }


def _participant_json(participants, profiles, owners, assigned=None, counts=None) -> list[dict]:
    out = []
    for pid in participants:
        profile = profiles.get(pid)
        out.append({
            "id": pid,
            "name": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "person": owners.get(profile.user_id) if profile else None,
            "assigned": (len(assigned[pid]) if assigned is not None
                         else sum(counts.get(pid, {}).values())),
            "pending": (len(assigned[pid]) if assigned is not None
                        else counts.get(pid, {}).get("pending", 0)),
            "applied": counts.get(pid, {}).get("applied", 0),
            "skipped": counts.get(pid, {}).get("skipped", 0),
        })
    return out


@app.post("/api/batches/{batch_id}/close")
def close_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Stop the rebuilds and stop accepting sheets. Lists stay readable."""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    batch.status = "computed"
    db.commit()
    return batch_json(batch)


@app.post("/api/batches/{batch_id}/reopen")
def reopen_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    batch.status = "open"
    db.commit()
    return batch_json(batch)


# --------------------------------------------------------------------------- #
# The cycle clock
# --------------------------------------------------------------------------- #

@app.put("/api/batches/{batch_id}/timer")
def set_timer(batch_id: int, body: TimerIn, db: Session = Depends(get_db),
              _: User = Depends(admin_only)):
    """Set the clock, move it, or take it away.

    Setting a budget starts it from now; adding to one already running leaves
    the time already spent spent, which is what "give them another twenty
    minutes" means. Taking away more than is left simply ends it.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")

    if body.minutes is not None:
        minutes = body.minutes
        # A fresh budget starts a fresh clock. Anything else would mean a
        # manager who set two hours at nine and two hours again at eleven had
        # given nobody any more time, which is the opposite of what they did.
        started = _naive_utc(utcnow())
    elif body.add_minutes is not None:
        minutes = (batch.timer_minutes or 0) + body.add_minutes
        started = _naive_utc(batch.timer_started_at) or _naive_utc(utcnow())
    else:
        raise HTTPException(400, "Say how many minutes to set, or how many to add.")

    if minutes > MAX_TIMER_MINUTES:
        raise HTTPException(400, "A clock cannot run longer than a week.")
    if minutes <= 0:
        # No clock at all, and the window it measured goes with it. Clearing is
        # the deliberate act; simply running out of time is not, and leaves both
        # of these alone so the figures below still have a window to report on.
        batch.timer_minutes = 0
        batch.timer_started_at = None
    else:
        batch.timer_minutes = minutes
        batch.timer_started_at = started
    db.commit()
    return batch_json(batch)


@app.get("/api/batches/{batch_id}/timer-report")
def timer_report(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """What each profile did inside the window the clock measured.

    The point of the clock is this screen. Every figure is dated by when
    somebody actually marked something, so it says what was done between the
    manager setting the time and the time running out — not what the cycle
    holds in total, which the report above already says.

    `late` is the same work done after the whistle. It is counted rather than
    hidden because a profile that finished everything twenty minutes over is a
    different story from one that stopped, and flattening the two into "did not
    finish in time" would tell the manager the wrong one.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")
    start, end = timer_window(batch)
    if start is None:
        raise HTTPException(404, "No clock has been set on this cycle.")

    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}

    # Everyone the cycle actually concerns: whoever handed a sheet in, plus
    # whoever was given a list. A profile pulled in on skills alone handed in
    # nothing and would otherwise be missing from the one screen that asks
    # what it did with the work it was given.
    taking_part = set(db.scalars(select(Upload.profile_id)
                                 .where(Upload.batch_id == batch_id)).all())
    taking_part |= set(db.scalars(select(Assignment.profile_id)
                                  .where(Assignment.batch_id == batch_id)).all())
    taking_part.discard(None)

    figures = {pid: {"own_jobs": 0, "applied": 0, "skipped": 0,
                     "late": 0, "given": 0, "left": 0} for pid in taking_part}

    # Others' jobs: dated by the moment the BD marked the row.
    marked_in_window: set[tuple[int, int]] = set()
    for profile_id, job_id, status, changed in db.execute(
        select(Assignment.profile_id, Assignment.job_id, Assignment.status,
               Assignment.status_changed_at)
        .where(Assignment.batch_id == batch_id)
    ).all():
        row = figures.setdefault(profile_id, {"own_jobs": 0, "applied": 0, "skipped": 0,
                                              "late": 0, "given": 0, "left": 0})
        row["given"] += 1
        when = _naive_utc(changed)
        if status == "pending" or when is None:
            row["left"] += 1
            continue
        if when < start:
            continue                      # marked before the manager set the clock
        if when <= end:
            row[status] = row.get(status, 0) + 1
            marked_in_window.add((profile_id, job_id))
        else:
            # Done, but after time was up. Still outstanding as far as the
            # clock is concerned, and counted again as late.
            row["left"] += 1
            row["late"] += 1

    # Own jobs: the applications this cycle first recorded for a profile inside
    # the window, less the ones that are really others' jobs the BD marked
    # applied — those are already counted above and must not be counted twice.
    for profile_id, job_id in db.execute(
        select(Application.profile_id, Application.job_id)
        .where(Application.batch_id == batch_id,
               Application.created_at >= start, Application.created_at <= end)
    ).all():
        if (profile_id, job_id) in marked_in_window:
            continue
        row = figures.setdefault(profile_id, {"own_jobs": 0, "applied": 0, "skipped": 0,
                                              "late": 0, "given": 0, "left": 0})
        row["own_jobs"] += 1

    rows = []
    for pid, row in figures.items():
        profile = profiles.get(pid)
        done = row["applied"] + row["skipped"]
        rows.append({
            "id": pid,
            "name": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "person": owners.get(profile.user_id) if profile else None,
            **row,
            "done": done,
            "done_pct": round(done * 100 / row["given"]) if row["given"] else 0,
        })
    rows.sort(key=lambda r: (-(r["own_jobs"] + r["done"]), r["name"]))

    return {**batch_json(batch),
            "started_at": start.isoformat(), "ends_at": end.isoformat(),
            "profiles": rows}


# --------------------------------------------------------------------------- #
# Rebuilding on a timer
# --------------------------------------------------------------------------- #

AUTO_BUILD_TICK_SECONDS = int(os.getenv("AUTO_BUILD_TICK_SECONDS", "60"))
# If a build dies mid-flight the claim would block every later one, so a claim
# older than this is treated as abandoned.
BUILD_CLAIM_TIMEOUT = dt.timedelta(minutes=15)


def _naive_utc(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """SQLite hands back naive datetimes and utcnow() is aware; comparing the
    two raises. Everything stored is UTC, so drop the marker and compare."""
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _posting_key(url: Optional[str], company: Optional[str],
                 title: Optional[str]) -> str:
    """One posting, however it happened to be linked.

    Somebody who applied for a job, or turned one down, has made a judgement
    about the posting rather than about the row it arrived on — so it has to
    survive the same job coming back on a different link. This is the key it
    survives by.

    The ladder is the fingerprint's own, with one rung widened. A platform id
    is kept as it is; a plain URL is stripped back past the apply flow, so a
    listing and its own apply URL agree; a row with no link at all falls back
    to the client and the title, exactly as the fingerprint does.

    An earlier version used the client and the title for *every* row. It was
    far too broad: a client with two openings for one title — ordinary in
    accounts receivable and support — had the second buried by the first, and
    on the sample sheets it held back three quarters of the pool. Both halves
    are still required in the fallback for the same reason: "AI Engineer" at
    two different clients is two jobs.
    """
    mark, tier = matching.fingerprint(url or "", title or "", company or "")
    # Only a plain URL needs the extra work. A platform id already survives
    # every link variant that site can produce — that is what the L1 rules are
    # for — and reaching past it would be actively wrong: pk.indeed.com/viewjob
    # carries its job id in the query string, so stripping the query leaves a
    # stem every Indeed job in the world shares.
    if tier == "L2":
        stem = matching.posting_stem(url)
        if stem:
            return "u:" + stem
    return mark


def _due_for_build(batch: Batch, now: dt.datetime) -> bool:
    if batch.status != "open" or not batch.auto_build_minutes:
        return False
    last = _naive_utc(batch.last_built_at)
    if last is None:
        return True
    return now - last >= dt.timedelta(minutes=batch.auto_build_minutes)


def run_due_builds() -> list[int]:
    """Rebuild every open cycle whose timer has come round. Returns what it built."""
    built: list[int] = []
    db = SessionLocal()
    try:
        now = _naive_utc(utcnow())
        open_cycles = db.scalars(select(Batch).where(Batch.status == "open")).all()
        for batch in open_cycles:
            if not _due_for_build(batch, now):
                continue

            # Claim it with a conditional update: whoever's UPDATE matches a row
            # owns the build. Two workers, or the timer and a manager pressing
            # the button, cannot both be inside build_lists for one cycle.
            claimed = db.execute(
                update(Batch)
                .where(Batch.id == batch.id,
                       or_(Batch.building_since.is_(None),
                           Batch.building_since < now - BUILD_CLAIM_TIMEOUT))
                .values(building_since=now))
            db.commit()
            if claimed.rowcount != 1:
                continue

            try:
                build_lists(db, batch)
                built.append(batch.id)
            except HTTPException:
                pass                    # fewer than two sheets yet; try again next tick
            except Exception as exc:    # noqa: BLE001 — one bad cycle must not stop the rest
                db.rollback()
                print(f"auto-build failed for cycle {batch.id}: {exc}")
            finally:
                db.execute(update(Batch).where(Batch.id == batch.id)
                           .values(building_since=None))
                db.commit()
    finally:
        db.close()
    return built


async def _auto_build_loop() -> None:
    while True:
        await asyncio.sleep(AUTO_BUILD_TICK_SECONDS)
        try:
            await asyncio.to_thread(run_due_builds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:        # noqa: BLE001
            print("auto-build tick failed:", exc)


@app.get("/api/batches/{batch_id}/report")
def report(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    batch = db.get(Batch, batch_id)
    if not batch or not batch.last_built_at:
        raise HTTPException(404, "That cycle has not been built yet.")

    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    participants = sorted({u.profile_id for u in
                           db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
                           if u.profile_id})

    # Only what was handed in for THIS cycle.
    rows = db.execute(
        select(BatchApplication.job_id, BatchApplication.profile_id)
        .where(BatchApplication.batch_id == batch_id)
    ).all()
    applied_by: dict[int, set[int]] = {}
    for job_id, profile_id in rows:
        applied_by.setdefault(job_id, set()).add(profile_id)

    matrix = matching.overlap_matrix(
        [{"applied_by": v} for v in applied_by.values()], participants)

    counts = defaultdict(lambda: defaultdict(int))
    for profile_id, status, count in db.execute(
        select(Assignment.profile_id, Assignment.status, func.count(Assignment.id))
        .where(Assignment.batch_id == batch_id)
        .group_by(Assignment.profile_id, Assignment.status)
    ).all():
        counts[profile_id][status] = count

    hit_twice = [job_id for job_id, pids in applied_by.items() if len(pids) > 1]
    jobs: dict[int, Job] = {}
    for chunk in _chunks(hit_twice):
        for job in db.scalars(select(Job).where(Job.id.in_(chunk))):
            jobs[job.id] = job
    collisions = [
        {"title": jobs[job_id].title, "company": jobs[job_id].company,
         "platform": jobs[job_id].platform, "url": jobs[job_id].url,
         "applied_by": [profiles[p].name if p in profiles else "?"
                        for p in applied_by[job_id]]}
        for job_id in hit_twice if job_id in jobs
    ]

    # What was turned down, and why. A skip is the one decision on a BD's screen
    # that destroys work — the job leaves that profile and no later cycle offers
    # it again — so this is the manager's only sight of it. Read together the
    # reasons usually say something about the searches feeding a profile rather
    # than about the individual postings.
    turned_down = [
        {"profile": profiles[a.profile_id].name if a.profile_id in profiles else "?",
         "title": j.title or "", "company": j.company or "",
         "platform": j.platform or "", "url": j.url or "",
         "reason": a.skip_reason or "",
         "when": working_label(a.status_changed_at)["label"] if a.status_changed_at else ""}
        for a, j in db.execute(
            select(Assignment, Job).join(Job, Job.id == Assignment.job_id)
            .where(Assignment.batch_id == batch_id, Assignment.status == "skipped")
            .order_by(Assignment.status_changed_at.desc().nullslast())
        ).all()
    ]

    return {
        **batch_json(batch),
        "participants": _participant_json(participants, profiles, owners, counts=counts),
        "matrix": {"names": [profiles[p].name if p in profiles else "?" for p in participants],
                   "rows": [[matrix[a][b] for b in participants] for a in participants]},
        "collisions": sorted(collisions, key=lambda c: -len(c["applied_by"]))[:400],
        "turned_down": turned_down[:400],
    }


# --------------------------------------------------------------------------- #
# Assignments
# --------------------------------------------------------------------------- #

def _row_json(a: Assignment, j: Job, source: Optional[dict] = None,
              applied_on: str = "", turned_down_by: Optional[list[str]] = None) -> dict:
    source = source or {}
    return {"id": a.id, "job_id": j.id, "status": a.status, "title": j.title,
            "company": j.company, "platform": j.platform, "url": j.url,
            "description_url": j.description_url or "",
            "applied_on": applied_on,
            # When the posting was found — the stamp off the sheet of whoever
            # put it into the pool, falling back to when it first entered the
            # system. This is the only date a dispatched job can have: it is on
            # this list precisely because this profile has *not* applied to it,
            # so its own `applied_on` is empty until it does, and the column
            # showed "—" on every row of the new-jobs list because of it.
            "found_on": source.get("on") or _first_seen_stamp(j),
            "skip_reason": a.skip_reason or "",
            # Which profiles already applied to this one. It is why the job is
            # on this list at all — somebody else found it — and a BD reading
            # "found by Faizan" knows whose search to ask about when a whole
            # run of them is wrong for this profile.
            "found_by": source.get("names") or [],
            # Another name this same person applies under has already turned
            # this posting down. Said out loud on the row, because the
            # alternative is a BD seeing a job they remember rejecting and
            # concluding the skip did not work.
            "turned_down_by": turned_down_by or []}


def _first_seen_stamp(job: Job) -> str:
    """When this posting first entered the system, on the team's clock.

    The last resort behind a colleague's own "applied on". A sheet handed in
    without a date column leaves every application off it unstamped, and a
    dispatched job with no date at all reads as a job nobody can tell the age
    of — which is the first thing a BD wants to know before opening the link.
    """
    if not job.first_seen:
        return ""
    return to_working(job.first_seen).strftime("%Y-%m-%d %H:%M")


def _found_by(db: Session, job_ids: Iterable[int],
              exclude: Optional[int] = None) -> dict[int, dict]:
    """Who has already applied to each of these jobs, and when.

    The screen is about who actually applied, not the profile label they used.
    `exclude` drops the profile being shown the list — it is on there precisely
    because that profile has *not* applied, so naming it would be nonsense.

    The date comes back with the names because it is the same fact: the job is
    on this list because a colleague applied to it, and when they did is how
    old the posting is. The newest wins when several people hold it — the most
    recent proof the link was still live. Stamps are `YYYY-MM-DD HH:MM`, so
    comparing them as text orders them correctly.
    """
    ids = [job_id for job_id in job_ids]
    if not ids:
        return {}
    out: dict[int, dict] = defaultdict(lambda: {"names": [], "on": ""})
    for chunk in _chunks(ids):
        for job_id, name, profile_id, applied_on in db.execute(
            select(Application.job_id, func.coalesce(User.name, Profile.name),
                   Application.profile_id, Application.applied_on)
            .join(Profile, Profile.id == Application.profile_id)
            .outerjoin(User, User.id == Application.user_id)
            .where(Application.job_id.in_(chunk))
            .order_by(func.coalesce(User.name, Profile.name))
        ).all():
            if profile_id == exclude:
                continue
            found = out[job_id]
            found["names"].append(name)
            stamp = (applied_on or "").strip()
            if stamp > found["on"]:
                found["on"] = stamp
    return dict(out)


def _turned_down_elsewhere(db: Session, profile: Profile,
                           jobs: Iterable[Job]) -> dict[int, list[str]]:
    """Which of this person's other profiles have turned each posting down.

    Matched on the posting rather than the row, for the same reason the build
    blocks on the posting: the same job arrives on several links and would
    otherwise look like a different job to everything except the person
    reading it.
    """
    rows = list(jobs)
    if not rows or profile.user_id is None:
        return {}
    others = db.scalars(select(Profile).where(
        Profile.user_id == profile.user_id, Profile.id != profile.id)).all()
    if not others:
        return {}
    by_name = {p.id: p.name for p in others}
    marked: dict[str, set[str]] = defaultdict(set)
    for pid, url, company_key, title in db.execute(
        select(Assignment.profile_id, Job.url, Job.company_key, Job.title)
        .join(Job, Job.id == Assignment.job_id)
        .where(Assignment.status == "skipped",
               Assignment.profile_id.in_(list(by_name)))
    ).all():
        mark = _posting_key(url, company_key, title)
        if mark:
            marked[mark].add(by_name[pid])
    if not marked:
        return {}
    out: dict[int, list[str]] = {}
    for job in rows:
        names = marked.get(_posting_key(job.url, job.company_key, job.title))
        if names:
            out[job.id] = sorted(names)
    return out


def _assignment_rows(db: Session, batch_id: int, profile_id: int) -> list[dict]:
    """One profile's list for one cycle.

    Skipped jobs are left out entirely. A profile that skipped a job has said
    it is not for them, and it never comes back in a later cycle either — so
    leaving it on screen greyed out is a row that can only ever be scrolled
    past. What stays is what there is still something to do about.
    """
    rows = db.execute(
        select(Assignment, Job, Application.applied_on)
        .join(Job, Job.id == Assignment.job_id)
        .outerjoin(Application, (Application.job_id == Assignment.job_id)
                   & (Application.profile_id == Assignment.profile_id))
        .where(Assignment.batch_id == batch_id, Assignment.profile_id == profile_id,
               Assignment.status != "skipped")
        .order_by(Job.company, Job.title)
    ).all()
    sources = _found_by(db, [j.id for _, j, _ in rows], exclude=profile_id)
    profile = db.get(Profile, profile_id)
    elsewhere = _turned_down_elsewhere(db, profile, [j for _, j, _ in rows]) \
        if profile else {}
    return [_row_json(a, j, sources.get(j.id), applied_on or "", elsewhere.get(j.id))
            for a, j, applied_on in rows]


def _all_assignment_rows(db: Session, batch_id: int) -> dict[int, list[dict]]:
    """Every profile's sheet in one pass, for the whole-batch workbook.

    Unlike the on-screen list this keeps the skipped rows. A download is the
    record of what the cycle dispatched, and a manager auditing it needs to see
    what was turned down as much as what was taken.
    """
    rows = db.execute(
        select(Assignment, Job).join(Job, Job.id == Assignment.job_id)
        .where(Assignment.batch_id == batch_id)
        .order_by(Job.company, Job.title)
    ).all()
    grouped: dict[int, list[dict]] = defaultdict(list)
    for a, j in rows:
        grouped[a.profile_id].append(_row_json(a, j))
    return grouped


# One screenful and then some. A profile with three hundred skips has a problem
# with the searches feeding it, not a reading problem, and the count above the
# list already says how many there are.
SKIPPED_PAGE = 200


@app.get("/api/batches/{batch_id}/skipped")
def skipped_jobs(batch_id: int, profile_id: Optional[int] = None,
                 date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
                 since: Optional[dt.datetime] = None, until: Optional[dt.datetime] = None,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    """What was skipped in this cycle, and why.

    A skip is the one decision on a BD's screen that destroys work — the job
    leaves that profile and no later cycle offers it again — and until now the
    reason lived only on the manager's cycle report. So a count of skips was a
    number nobody could open: a BD could not check their own reasoning back, and
    a manager reading "47 skipped" on somebody's row had to go and find another
    screen to learn whether that was a profile being protected or a week of good
    postings thrown away.

    Scoped the way the count beside it is scoped, or the list would not add up
    to the number that opened it: dated by when the row was marked, and narrowed
    to one profile when one is asked for. A BD sees the profiles they run and a
    manager sees everybody, which is the same rule as every other screen here.

    Two ways to say when, because two kinds of figure open this list. The
    dashboards count whole days, so they send `date_from`/`date_to`. The cycle
    clock counts an exact window — two hours from the moment a manager set it —
    and a list rounded out to whole days under a figure counting one afternoon
    would be the very mismatch this is meant to avoid, so it sends
    `since`/`until` instead.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such cycle.")

    allowed = visible_profile_ids(db, user)
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        if allowed is not None and profile_id not in allowed:
            raise HTTPException(403, "That profile belongs to someone else.")
        allowed = [profile_id]
    if allowed is not None and not allowed:
        return {"batch_id": batch_id, "rows": [], "total": 0}

    query = (select(Assignment, Job, Profile)
             .join(Job, Job.id == Assignment.job_id)
             .join(Profile, Profile.id == Assignment.profile_id)
             .where(Assignment.batch_id == batch_id, Assignment.status == "skipped"))
    if allowed is not None:
        query = query.where(Assignment.profile_id.in_(allowed))

    # The same clock the figures use, so the list and the count agree.
    marked = func.coalesce(Assignment.status_changed_at, Assignment.created_at)
    if date_from:
        query = query.where(marked >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        query = query.where(marked < dt.datetime.combine(date_to + dt.timedelta(days=1),
                                                         dt.time.min))
    if since:
        query = query.where(marked >= _naive_utc(since))
    if until:
        query = query.where(marked <= _naive_utc(until))

    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    rows = [
        {"id": a.id, "job_id": j.id,
         "title": j.title or "", "company": j.company or "",
         "platform": j.platform or "", "url": j.url or "",
         "profile_id": p.id, "profile": p.name,
         "person": owners.get(p.user_id) or "",
         # Said in the BD's own words. Empty only on rows skipped before the
         # reason was asked for, and said so rather than left blank.
         "reason": a.skip_reason or "",
         "when": working_label(a.status_changed_at)["label"] if a.status_changed_at else ""}
        for a, j, p in db.execute(
            query.order_by(Assignment.status_changed_at.desc().nullslast())).all()
    ]
    return {"batch_id": batch_id, "rows": rows[:SKIPPED_PAGE], "total": len(rows)}


@app.get("/api/batches/{batch_id}/my-sheets")
def my_sheets(batch_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every profile this person runs, each with its own list."""
    query = select(Profile).where(Profile.is_active == True)  # noqa: E712
    if user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    mine = db.scalars(query.order_by(Profile.name)).all()
    people = {u.id: u for u in db.scalars(select(User)).all()}
    return {"batch_id": batch_id,
            "profiles": [{**profile_json(p, people.get(p.user_id),
                                         people.get(p.dev_user_id)),
                          "jobs": _assignment_rows(db, batch_id, p.id)} for p in mine]}


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/sheet")
def profile_sheet(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    return {"batch_id": batch_id, "profile": profile_json(profile),
            "jobs": _assignment_rows(db, batch_id, profile.id)}


# --------------------------------------------------------------------------- #
# The record — every job a profile has ever applied to
# --------------------------------------------------------------------------- #

JOB_PAGE = 50


@app.get("/api/jobs")
def job_record(q: str = "", profile_id: Optional[int] = None,
               date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
               limit: int = JOB_PAGE,
               offset: int = 0, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    """Everything applied for, all-time, newest first, searchable.

    The screen a BD opens with a client's email still on the other monitor.
    They paste in the company name or the job title, find the row, and start
    the interview from it — which is what carries the title, the client and
    both links onto the conversation instead of being typed again, wrong.

    Not scoped to a cycle. A reply arrives three weeks after the application
    that earned it, by which time that cycle is closed and, on the cycle-scoped
    screens, gone. This one goes back to the beginning.

    Search runs over the client, the title, the platform and the link, because
    a person pasting out of an email has no idea which field the thing they
    copied lives in. Case-insensitive, and matches anywhere in the value — a
    leading-anchor search would miss "Northwind" inside "The Northwind Group".
    """
    ids = visible_profile_ids(db, user)
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        if ids is not None and profile_id not in ids:
            raise HTTPException(403, "That profile belongs to someone else.")
        ids = [profile_id]
    if ids is not None and not ids:
        return {"rows": [], "total": 0, "limit": limit, "offset": 0, "q": q}

    limit = min(200, max(1, limit))
    offset = max(0, offset)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")

    query = (select(Application, Job, Profile)
             .join(Job, Job.id == Application.job_id)
             .join(Profile, Profile.id == Application.profile_id))
    if ids is not None:
        query = query.where(Application.profile_id.in_(ids))

    needle = (q or "").strip()
    if needle:
        like = f"%{needle.lower()}%"
        query = query.where(or_(
            func.lower(func.coalesce(Job.company, "")).like(like),
            func.lower(func.coalesce(Job.title, "")).like(like),
            func.lower(func.coalesce(Job.platform, "")).like(like),
            func.lower(func.coalesce(Job.url, "")).like(like),
            func.lower(Profile.name).like(like),
        ))

    ordered = db.execute(query.order_by(Application.created_at.desc(), Application.id.desc())).all()
    if date_from or date_to:
        filtered = []
        for row in ordered:
            applied = (row[0].applied_on or "")[:10]
            try:
                applied_day = dt.date.fromisoformat(applied)
            except ValueError:
                continue
            if date_from and applied_day < date_from:
                continue
            if date_to and applied_day > date_to:
                continue
            filtered.append(row)
        ordered = filtered
    total = len(ordered)
    rows = ordered[offset:offset + limit]

    # Who may correct each posting on this page. Worked out for the page rather
    # than the whole result set, and in two queries rather than per row.
    page_jobs = {job.id for _, job, _ in rows}
    sourced = (page_jobs if user.role == "admin"
               else _sourced_jobs(db, page_jobs, user))
    owned = {p.id for p in db.scalars(
        select(Profile).where(Profile.user_id == user.id))} if user.role != "admin" else None

    return {
        "rows": [{
            "job_id": job.id,
            "profile_id": profile.id,
            "profile": profile.name,
            "title": job.title or "",
            "company": job.company or "",
            "platform": job.platform or "",
            "url": job.url or "",
            "description_url": job.description_url or "",
            # What the BD typed on their sheet, kept verbatim. The row's own
            # created_at is when the cycle was built, which is a different day
            # from the one they actually applied.
            "applied_on": application.applied_on or "",
            "logged": working_label(application.created_at)["label"]
                      if application.created_at else "",
            # The posting is one shared row, so correcting it corrects it for
            # everyone holding it — which is why only the person who first
            # logged it may. A manager may always.
            "can_edit": job.id in sourced,
            # Withdrawing an entry is scoped to the profile, so the test is
            # whether this person runs that profile, not who found the job.
            "can_delete": owned is None or profile.id in owned,
        } for application, job, profile in rows],
        "total": total, "limit": limit, "offset": offset, "q": needle,
    }


def _sourced_jobs(db: Session, job_ids: Iterable[int], user: User) -> set[int]:
    """Which of these jobs this person found themselves.

    A job row is shared: once two profiles hold a posting they are reading the
    same title, the same client and the same link, so a correction by one is a
    correction for the other. That is the point — one posting, one description,
    corrected once — but it does mean the right to make it has to sit somewhere
    defensible.

    It sits with whoever *found* the job, and this codebase already draws that
    line precisely: a job a profile put into the pool from its own sheet has a
    `batch_applications` row, while one it was handed off somebody else's sheet
    and later marked applied does not. So being dispatched a job and working it
    does not make it yours to rewrite; typing it in does.

    Deliberately not "the earliest application". Two BDs who log the same
    posting in one cycle are inserted together in one statement, and picking
    the lower id would hand one of them the pen for no reason either could
    explain. They both found it, so they both may correct it.

    History imported from the old spreadsheets predates cycles and has no
    per-cycle row, so an application with no batch at all counts too — those
    came off the BD's own sheet by definition.
    """
    ids = list(job_ids)
    if not ids:
        return set()
    mine = [row for (row,) in db.execute(
        select(Profile.id).where(Profile.user_id == user.id)).all()]
    if not mine:
        return set()

    found: set[int] = set()
    for chunk in _chunks(ids):
        found.update(job_id for (job_id,) in db.execute(
            select(BatchApplication.job_id).where(
                BatchApplication.job_id.in_(chunk),
                BatchApplication.profile_id.in_(mine))).all())
        found.update(job_id for (job_id,) in db.execute(
            select(Application.job_id).where(
                Application.job_id.in_(chunk),
                Application.profile_id.in_(mine),
                Application.batch_id.is_(None))).all())
    return found


def _may_edit_job(db: Session, job_id: int, user: User) -> None:
    """Raise unless this person found the job, or manages the workspace."""
    if user.role == "admin":
        return
    if job_id in _sourced_jobs(db, [job_id], user):
        return
    raise HTTPException(403, "You can only correct a job you logged yourself. "
                             "This one came off somebody else's sheet — ask them, "
                             "or ask your manager.")


def _being_worked(db: Session, company: str, title: str, url: str) -> Optional[dict]:
    """Is this client flagged as already being worked, and by whom?

    A manager's flag, never a block. It cannot stop the row being saved and it
    changes nothing about what dispatch hands out — a flag that quietly held
    jobs back would be a rule whose effect nobody could see, and the reason for
    a missing job would be invisible on the screen it went missing from.
    """
    name = (company or "").strip()
    if not name:
        job = db.scalar(select(Job).where(
            Job.fingerprint == matching.fingerprint(url, title, company)[0])) if url else None
        name = (job.company or "") if job else ""
    key = matching.client_key(name)
    if not key:
        return None
    row = db.scalar(select(ClientNote).where(ClientNote.client_key == key,
                                             ClientNote.being_worked == True))  # noqa: E712
    if row is None:
        return None
    who = db.get(User, row.updated_by) if row.updated_by else None
    return {"client": row.display_name or name,
            "by": who.name if who else None,
            "since": working_label(row.updated_at)["label"] if row.updated_at else None,
            "note": row.note or ""}


@app.get("/api/jobs/check")
def check_duplicate(url: str = "", title: str = "", company: str = "",
                    profile_id: Optional[int] = None,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Has this posting been applied to before, and by whom?

    Called as a BD types a job link, before the row is saved. The link is the
    first thing they paste and the field that identifies a posting, so it is
    the first moment the question can be answered at all.

    Answered on the fingerprint rather than on the text, so the same job pasted
    with a tracking parameter, through a referral link, or with the protocol
    typed differently still comes back as the same job — which is the whole
    point of having a fingerprint.

    Two different answers, deliberately kept apart. `mine` is this profile
    having already applied: a real duplicate, the thing that must never happen
    twice, because it is one identity approaching one client twice. `others` is
    a colleague's profile having applied, which is not a duplicate at all — two
    candidates in the running is what running several profiles is *for* — but
    is still worth knowing before spending the effort.
    """
    fingerprint, tier = matching.fingerprint(url, title, company)
    empty = {"duplicate": False, "fingerprint": "", "tier": "-",
             "job_id": None, "mine": None, "others": []}
    if not fingerprint:
        return empty

    # A client somebody is already working, said in the one dialog a BD is
    # certainly reading. Answered whether or not the posting itself is known,
    # because the point is the company, not the link — and it is advisory:
    # nothing here stops the row being saved.
    working = _being_worked(db, company, title, url)

    job = db.scalar(select(Job).where(Job.fingerprint == fingerprint))
    if job is None:
        return {**empty, "fingerprint": fingerprint, "tier": tier,
                "being_worked": working}

    # Only the profiles this person is entitled to see. A BD is told plainly
    # that a colleague applied — the new-jobs list already names them — but a
    # workspace they have no part in stays out of it.
    visible = visible_profile_ids(db, user)
    rows = db.execute(
        select(Application, Profile, User)
        .join(Profile, Profile.id == Application.profile_id)
        .outerjoin(User, User.id == Application.user_id)
        .where(Application.job_id == job.id)
        .order_by(Application.id.desc())
    ).all()

    mine, others = None, []
    for application, profile, owner in rows:
        entry = {"profile_id": profile.id, "profile": profile.name,
                 "bd": owner.name if owner else "",
                 "applied_on": application.applied_on or "",
                 "logged": working_label(application.created_at)["label"]
                           if application.created_at else ""}
        if profile_id is not None and profile.id == profile_id:
            mine = entry
        elif visible is None or profile.id in visible:
            others.append(entry)

    return {"duplicate": mine is not None, "fingerprint": fingerprint, "tier": tier,
            "job_id": job.id, "title": job.title or "", "company": job.company or "",
            "url": job.url or "", "mine": mine, "others": others,
            "being_worked": working}


@app.patch("/api/jobs/{job_id}")
def edit_job(job_id: int, body: JobPatch, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    """Correct a posting, everywhere at once.

    There is one row per posting, so this is the correction and there is no
    copy of it to go stale: the new-jobs list, every colleague's list, the
    record and the exports all read this row and show the new wording the next
    time they ask for it.

    Changing the link is the one edit that can change what the job *is*. The
    fingerprint is derived from it, so a corrected link re-identifies the
    posting — which is usually the point, since a link typed wrongly is exactly
    what splits one posting into two. If the corrected link turns out to be a
    posting the database already holds separately, this stops rather than
    merging them: joining two job rows silently would take two profiles'
    histories with it.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    _may_edit_job(db, job_id, user)

    if body.title is not None:
        job.title = body.title.strip()[:500]
    if body.company is not None:
        job.company = body.company.strip()[:300]
        job.company_key = matching.normalize_text(job.company)[:300]
    if body.platform is not None:
        job.platform = body.platform.strip()[:120]
    if body.description_url is not None:
        job.description_url = _check_link(body.description_url, "job description link")
    if body.url is not None:
        job.url = _check_link(body.url, "job link")

    # Re-derive identity from whatever the row now says. Done after every field
    # is in place, because a fingerprint falls back to client-and-title when
    # there is no link, and both of those may have changed too.
    fingerprint, tier = matching.fingerprint(job.url, job.title, job.company)
    if not fingerprint:
        raise HTTPException(400, "A job needs a link, or a client and a title.")
    if fingerprint != job.fingerprint:
        clash = db.scalar(select(Job).where(Job.fingerprint == fingerprint,
                                            Job.id != job.id))
        if clash is not None:
            raise HTTPException(409,
                "That link belongs to a posting already recorded separately "
                f"({clash.title or 'untitled'} at {clash.company or 'unknown client'}). "
                "Delete this row instead of pointing it at the other one.")
        job.fingerprint = fingerprint
        job.tier = tier

    db.commit()
    return {"ok": True, "job_id": job.id, "title": job.title or "",
            "company": job.company or "", "platform": job.platform or "",
            "url": job.url or "", "description_url": job.description_url or "",
            "fingerprint": job.fingerprint}


@app.delete("/api/jobs/{job_id}/profiles/{profile_id}")
def delete_entry(job_id: int, profile_id: int, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    """Withdraw one profile's entry, and take the job with it when nobody else
    holds it.

    Deleting has to be thorough or it does not hold. There are four places a
    withdrawn job hides, and leaving any one of them puts it back on screen:

      the profile's sheet   the row the BD typed. Left there, the next
                            automatic rebuild re-reads it and files the
                            application again — within ten minutes on a cycle
                            with the timer on, which reads as the delete having
                            silently failed.
      batch_applications    the per-cycle record of having logged it.
      assignments           the dispatched row. An earlier version of this set
                            it back to `pending` rather than removing it, which
                            put the job straight back on the BD's new-jobs list
                            — the opposite of what withdrawing it means.
      applications          the all-time record.

    The job row itself goes too, but only once nothing points at it. A posting
    two profiles applied to is a posting the other profile still has in its
    record, and deleting it there would take a colleague's history with it. So
    it is removed when it is orphaned and kept when it is not, which is the only
    reading of "delete it" that cannot destroy somebody else's work.
    """
    profile = owned_profile(profile_id, db, user)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    application = db.scalar(select(Application).where(
        Application.job_id == job_id, Application.profile_id == profile.id))
    assignments = db.scalars(select(Assignment).where(
        Assignment.job_id == job_id, Assignment.profile_id == profile.id)).all()
    if application is None and not assignments:
        raise HTTPException(404, "This profile has no entry for that job.")

    # 1. Out of the sheet, so no rebuild can resurrect it.
    #
    # Only sheets belonging to a cycle that is still open. A closed cycle is a
    # finished record — its report says what was handed in that week, and
    # editing that after the fact to tidy up today's mistake would rewrite
    # history nobody asked to change. A closed cycle is also never rebuilt, so
    # there is nothing there to bring the job back.
    removed_from_sheet = 0
    open_sheets = db.scalars(
        select(Upload).join(Batch, Batch.id == Upload.batch_id)
        .where(Upload.profile_id == profile.id, Batch.status == "open")).all()
    for upload in open_sheets:
        mapping = upload.mapping or {}
        original = upload.rows or []
        # One projection for the whole sheet rather than one per row: a BD who
        # uploaded a real spreadsheet has thousands of them.
        projected = ingest.project_rows(original, mapping)
        kept = [raw for raw, record in zip(original, projected)
                if matching.fingerprint(record["url"], record["title"],
                                        record["company"])[0] != job.fingerprint]
        if len(kept) != len(original):
            removed_from_sheet += len(original) - len(kept)
            upload.rows = kept
            upload.row_count = len(kept)
            upload.usable_count = len(ingest.apply_mapping(kept, mapping))

    # 2-4. Out of the cycle record, off the list, out of the history.
    db.execute(delete(BatchApplication).where(
        BatchApplication.job_id == job_id, BatchApplication.profile_id == profile.id))
    db.execute(delete(Assignment).where(
        Assignment.job_id == job_id, Assignment.profile_id == profile.id))
    if application is not None:
        db.delete(application)
    db.flush()

    # 5. And the posting itself, once nobody has applied to it.
    #
    # Applications are the test, not assignments. An application is somebody's
    # work — a real approach to a real client — and deleting a posting somebody
    # else has applied to would take their history with it, which no button on
    # one person's screen should be able to do.
    #
    # An assignment is not work. It is a suggestion the build produced, and it
    # exists only because somebody found the job in the first place. So when
    # the last application goes, the postings on other people's to-do lists are
    # dangling suggestions for a job nobody is claiming any more, and they go
    # too. The next rebuild would have removed them anyway once the job left
    # every sheet; doing it here is what makes the delete look like a delete
    # instead of something that half happens ten minutes later.
    #
    # A conversation is the other thing that keeps a posting alive, and the
    # stronger of the two. An interview or an assessment means the client
    # answered — the rarest and most valuable row in this system — and both
    # tables point at `jobs` without an ON DELETE rule, so deleting underneath
    # one is a foreign-key error on Postgres rather than a tidy-up. Either way
    # the posting stays: a reply outlives the application that earned it.
    still_held = db.scalar(select(func.count()).select_from(Application)
                           .where(Application.job_id == job_id)) or 0
    replied = (db.scalar(select(func.count()).select_from(Interview)
                         .where(Interview.job_id == job_id)) or 0)         + (db.scalar(select(func.count()).select_from(Assessment)
                     .where(Assessment.job_id == job_id)) or 0)
    orphaned = not still_held and not replied
    if orphaned:
        db.execute(delete(BatchApplication).where(BatchApplication.job_id == job_id))
        db.execute(delete(Assignment).where(Assignment.job_id == job_id))
        db.delete(job)

    db.commit()
    return {"ok": True, "job_deleted": orphaned,
            "rows_removed_from_sheet": removed_from_sheet,
            "still_held_by": still_held, "kept_for_replies": replied}


# --------------------------------------------------------------------------- #
# Working the list — one job, or the whole selection
# --------------------------------------------------------------------------- #

STATUSES = ("pending", "applied", "skipped")

# The most rows one press may carry. Not a policy about how much work a person
# is allowed to get through at once — the browser sends a long selection as
# several of these and the result is the same — but a bound on how much one
# request can be asked to do, so a slip of the finger on a five-thousand-row
# list cannot hold a database transaction open for a minute.
BULK_MAX = 500

# Why a skip has to say why, here rather than in the browser, so the rule holds
# for anything that talks to the API. A skip is the one decision on this screen
# that destroys work: the job leaves this profile's list and no later cycle
# offers it again. Asking costs one sentence and is the difference between a
# manager reading "47 skipped" and reading why — which is usually a fixable
# thing about the searches feeding that profile.
NEEDS_REASON = ("Say why you are skipping this one. "
                "Your manager sees the reason, not you deciding alone.")


def _mark(row: Assignment, status: str, reason: str) -> None:
    """One row's status, and the reason that belongs to it."""
    if status == "skipped":
        row.skip_reason = reason[:1000]
    else:
        # Moving off `skipped` retracts the reason with it, rather than leaving
        # a stale explanation attached to a job that is back on the list.
        row.skip_reason = ""
    row.status = status
    row.status_changed_at = utcnow()


def _record_applied(db: Session, rows: Iterable[Assignment]) -> None:
    """Close the loop on everything just marked applied.

    It counts as the profile's history from now on, so no later cycle offers it
    again. Written in one pass rather than one query per row, because the same
    press may carry two hundred of them.
    """
    rows = [row for row in rows if row.status == "applied"]
    if not rows:
        return
    have: set[tuple[int, int]] = set()
    for chunk in _chunks({row.job_id for row in rows}):
        have.update(map(tuple, db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_(chunk))).all()))
    stamp = applied_stamp()
    fresh = []
    for row in rows:
        if (row.job_id, row.profile_id) in have:
            continue
        have.add((row.job_id, row.profile_id))
        fresh.append({"job_id": row.job_id, "profile_id": row.profile_id,
                      "user_id": row.user_id, "batch_id": row.batch_id,
                      "applied_on": stamp})
    for chunk in _chunks(fresh):
        db.execute(insert(Application), chunk)


def _skip_for_other_profiles(db: Session, rows: list[Assignment], reason: str,
                             user: User) -> int:
    """The same skip against every other name this person applies under.

    Per profile is the right default and stays the default: two profiles are
    two candidates in two markets, and a posting wrong for one is often right
    for the other. But when the reason is about the job rather than the fit —
    the rate, on-site only, a client already being worked — a BD was turning
    the same posting down once per profile, week after week, and reasonably
    read that as the skip not working.

    Written as real rows rather than a flag, so every rule that already reads a
    skip — what the next build may not hand out, what the manager's report
    counts as turned down — sees this one without being taught about it.
    """
    if not rows:
        return 0
    by_cycle: dict[int, list[Assignment]] = defaultdict(list)
    for row in rows:
        by_cycle[row.batch_id].append(row)

    also = 0
    for batch_id, cycle_rows in by_cycle.items():
        # In the round, not merely on the payroll: a profile that handed
        # nothing in this cycle, or already holds this job, is one this
        # decision can honestly speak for. One that has been dormant for a
        # month was never offered the posting and must not be recorded as
        # having turned it down.
        taking_part = set(db.scalars(select(Upload.profile_id).where(
            Upload.batch_id == batch_id)).all())
        taking_part |= set(db.scalars(select(Assignment.profile_id).where(
            Assignment.batch_id == batch_id)).all())
        theirs = [p for p in db.scalars(select(Profile).where(
            Profile.user_id == user.id, Profile.is_active == True))   # noqa: E712
            if p.id in taking_part]
        if not theirs:
            continue

        seen: dict[tuple[int, int], Assignment] = {}
        for chunk in _chunks({row.job_id for row in cycle_rows}):
            for mate in db.scalars(select(Assignment).where(
                    Assignment.batch_id == batch_id,
                    Assignment.job_id.in_(chunk),
                    Assignment.profile_id.in_([p.id for p in theirs]))):
                seen[(mate.job_id, mate.profile_id)] = mate

        for row in cycle_rows:
            for profile in theirs:
                if profile.id == row.profile_id:
                    continue
                mate = seen.get((row.job_id, profile.id))
                if mate is None:
                    # Never `exclusive`, even in a split cycle. That flag is
                    # what the partial unique index uses to hold "this job was
                    # handed out to exactly one profile", and this row is not a
                    # dispatch — it is a record that this profile turned the
                    # posting down. Copying the flag across from the row being
                    # skipped made the second one collide with the first, so in
                    # a split cycle skipping for every profile failed outright
                    # and the BD's decision was lost.
                    mate = Assignment(batch_id=batch_id, job_id=row.job_id,
                                      profile_id=profile.id, user_id=profile.user_id,
                                      status="skipped", skip_reason=reason[:1000],
                                      exclusive=False, status_changed_at=utcnow())
                    db.add(mate)
                    seen[(row.job_id, profile.id)] = mate
                    also += 1
                elif mate.status == "pending":
                    # Never over an `applied`: that profile has already used the
                    # posting, and rewriting it as turned down would erase the work.
                    mate.status = "skipped"
                    mate.skip_reason = reason[:1000]
                    mate.status_changed_at = utcnow()
                    also += 1
    return also


@app.patch("/api/assignments/{assignment_id}")
def set_status(assignment_id: int, body: StatusIn, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    row = db.get(Assignment, assignment_id)
    if not row:
        raise HTTPException(404, "No such job on your sheet.")
    owned_profile(row.profile_id, db, user)
    if body.status not in STATUSES:
        raise HTTPException(400, "Status must be pending, applied or skipped.")

    reason = (body.reason or "").strip()
    if body.status == "skipped" and not reason:
        raise HTTPException(400, NEEDS_REASON)

    _mark(row, body.status, reason)
    also_skipped = (_skip_for_other_profiles(db, [row], reason, user)
                    if body.status == "skipped" and body.every_profile else 0)
    _record_applied(db, [row])
    db.commit()

    application = db.scalar(select(Application).where(
        Application.job_id == row.job_id,
        Application.profile_id == row.profile_id))
    return {"ok": True, "status": row.status,
            "skip_reason": row.skip_reason or "",
            "also_skipped": also_skipped,
            "applied_on": application.applied_on if application else ""}


@app.post("/api/assignments/bulk")
def set_status_many(body: BulkStatusIn, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """One decision over a whole selection.

    A BD coming off three months of spreadsheets has a list of several hundred
    postings where the answer to every one of them is the same — already
    applied for under this name before the app existed, or a client the team
    stopped working in June. Taking that decision three hundred times, one
    dropdown at a time, is not more careful than taking it once; it is the same
    decision typed out three hundred times, with three hundred chances to
    mis-click a neighbouring row.

    So this is the same rules, applied to a list. Every row is checked for
    ownership, a skip still has to say why, and the reason is written onto
    every row in the selection — which is the honest shape of the thing: one
    reason is what the person actually has.

    The manager can take it away. `bulk_actions_enabled` is a workspace switch
    and the check is here, on the server, so turning it off is a rule rather
    than a hidden button.
    """
    if body.status not in STATUSES:
        raise HTTPException(400, "Status must be pending, applied or skipped.")
    if not read_settings(db)["bulk_actions_enabled"]:
        raise HTTPException(403, "Your manager has turned off marking a whole list "
                                 "at once. Set the jobs one at a time, or ask them "
                                 "to switch it back on.")

    ids = list(dict.fromkeys(int(i) for i in body.ids))
    if not ids:
        raise HTTPException(400, "Nothing was selected.")
    if len(ids) > BULK_MAX:
        raise HTTPException(400, f"That is {len(ids)} jobs in one go, and {BULK_MAX} "
                                 "is the most one press may carry. Narrow the list "
                                 "or do it in two.")

    reason = (body.reason or "").strip()
    if body.status == "skipped" and not reason:
        raise HTTPException(400, NEEDS_REASON)

    rows: list[Assignment] = []
    for chunk in _chunks(ids):
        rows.extend(db.scalars(select(Assignment).where(Assignment.id.in_(chunk))))
    if not rows:
        raise HTTPException(404, "None of those jobs are on your sheet any more. "
                                 "Reload — somebody may have rebuilt the lists.")

    # Ownership once per profile rather than once per row, and checked for
    # every row before a single one is written. A selection that reaches
    # somebody else's profile is refused whole: half-applying it would leave
    # the person who pressed it with no way to know which half went through.
    for profile_id in {row.profile_id for row in rows}:
        owned_profile(profile_id, db, user)

    for row in rows:
        _mark(row, body.status, reason)
    also_skipped = (_skip_for_other_profiles(db, rows, reason, user)
                    if body.status == "skipped" and body.every_profile else 0)
    _record_applied(db, rows)
    db.commit()

    return {"ok": True, "status": body.status, "updated": len(rows),
            # Said plainly, because it is the number somebody checks against
            # what they thought they had selected. Rows can go missing between
            # selecting and pressing — a rebuild takes an untouched job off a
            # list — and a silent difference is the one thing that would make
            # this button untrustworthy.
            "missing": len(ids) - len(rows),
            "ids": [row.id for row in rows],
            "also_skipped": also_skipped}


# --------------------------------------------------------------------------- #
# Workspace switches
# --------------------------------------------------------------------------- #

# Every switch and its value on a workspace that has never touched the screen.
# Reading falls back to these, so a missing row is the default rather than an
# error, and adding a switch never needs a migration.
SETTING_DEFAULTS = {
    "team_board_visible": False,
    # Whether a BD may select a whole list and mark it in one press.
    #
    # On by default, unlike the team board, because the two switches are about
    # opposite things. The board is somebody else's figures put in front of a
    # person who did not ask to be measured, so it waits to be turned on. This
    # one is a person's own list and their own decision — the same decision the
    # dropdown on every row already lets them take — taken once instead of three
    # hundred times. Withholding it by default would mean every new workspace
    # starts by making its team do the tedious version of something they are
    # already allowed to do.
    #
    # It is a switch rather than a fixture because a manager may reasonably
    # decide a particular team should look at every posting before turning it
    # down. Turning it off does not touch anything already marked; it takes away
    # the press from then on, and the server refuses it as well as the screen
    # hiding it.
    "bulk_actions_enabled": True,
}


def read_settings(db: Session) -> dict:
    stored = {row.key: row.value for row in db.scalars(select(Setting))}
    return {key: stored.get(key, fallback) for key, fallback in SETTING_DEFAULTS.items()}


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Readable by everyone: a BD's app needs to know whether to offer the
    team board at all, and hiding the switch from them would not hide the tab."""
    return read_settings(db)


@app.patch("/api/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db),
                    _: User = Depends(admin_only)):
    for key, value in body.model_dump(exclude_none=True).items():
        if key not in SETTING_DEFAULTS:
            continue
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return read_settings(db)


# --------------------------------------------------------------------------- #
# Dashboards
# --------------------------------------------------------------------------- #

def _person_dashboard(db: Session, person: User, batch_id: Optional[int],
                      date_from: Optional[dt.date], date_to: Optional[dt.date]) -> dict:
    board_open = read_settings(db)["team_board_visible"] or person.role == "admin"
    return {**dashboard.for_person(db, person, dashboard.pick_batch(db, batch_id),
                                   team_visible=board_open, date_from=date_from,
                                   date_to=date_to),
            "person": user_json(person)}


@app.get("/api/dashboard/me")
def dashboard_me(batch_id: Optional[int] = None, date_from: Optional[dt.date] = None,
                 date_to: Optional[dt.date] = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    """Your own progress — but only once a manager has opened it for you.

    Checked here rather than only in the browser, because hiding a tab is not
    the same as refusing a request.
    """
    require_dashboard(user)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return _person_dashboard(db, user, batch_id, date_from, date_to)


@app.get("/api/dashboard/people/{user_id}")
def dashboard_person(user_id: int, batch_id: Optional[int] = None,
                     date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
                     db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """One person's dashboard, exactly as they would see it.

    The same payload /dashboard/me returns for them, so what a manager checks
    before opening it is what the person actually gets — not an approximation
    of it built somewhere else.
    """
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return _person_dashboard(db, person, batch_id, date_from, date_to)


@app.get("/api/dashboard/team")
def dashboard_team(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """Every profile side by side.

    Two gates, and both must be open: this person has a dashboard at all, and
    the workspace shows the board to people who do.
    """
    require_dashboard(user)
    if user.role != "admin" and not read_settings(db)["team_board_visible"]:
        raise HTTPException(403, "Your manager has not opened the team board yet.")
    return dashboard.team_board(db, dashboard.pick_batch(db, batch_id),
                                include_private=user.role == "admin")


@app.get("/api/dashboard/overview")
def dashboard_overview(batch_id: Optional[int] = None, date_from: Optional[dt.date] = None,
                       date_to: Optional[dt.date] = None, db: Session = Depends(get_db),
                       _: User = Depends(admin_only)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return {**dashboard.overview(db, dashboard.pick_batch(db, batch_id), date_from, date_to),
            "settings": read_settings(db)}


@app.get("/api/dashboard/profiles/{profile_id}")
def dashboard_profile(profile_id: int, batch_id: Optional[int] = None,
                      date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One profile close up. `linked_profile` is what stops a BD opening a
    colleague's record — the team board shows totals, not somebody else's diary.

    The developer behind a profile may open it without the dashboard switch a
    BD's figures sit behind. That switch exists so nobody is measured on a
    screen without somebody deciding to; this is the record of an identity that
    goes out in their name, which they are entitled to read.
    """
    profile = linked_profile(profile_id, db, user)
    if not (user.role == "dev" and profile.dev_user_id == user.id):
        require_dashboard(user)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return dashboard.profile_detail(db, profile, dashboard.pick_batch(db, batch_id),
                                    date_from, date_to)


@app.get("/api/dashboard/dev")
def dashboard_developer(batch_id: Optional[int] = None, date_from: Optional[dt.date] = None,
                        date_to: Optional[dt.date] = None, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    """A developer's own screen: their calendar, their identities, their record.

    Open to them from the moment the account exists. A developer who cannot see
    their own interviews misses them, which is a different kind of harm from a
    BD seeing a figure nobody meant to show them.
    """
    if user.role not in ("dev", "admin"):
        raise HTTPException(403, "This screen is for the developers behind the profiles.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return dashboard.for_developer(db, user, dashboard.pick_batch(db, batch_id),
                                   date_from, date_to)


@app.get("/api/dashboard/devs/{user_id}")
def dashboard_developer_as(user_id: int, batch_id: Optional[int] = None,
                           date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
                           db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """One developer's screen, exactly as they see it. Manager only."""
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return dashboard.for_developer(db, person, dashboard.pick_batch(db, batch_id),
                                   date_from, date_to)


# --------------------------------------------------------------------------- #
# Interviews — the first thing here that records an outcome
# --------------------------------------------------------------------------- #

def _clash(db: Session, profile: Profile, when: dt.datetime, minutes: int,
           ignore: Optional[int] = None) -> Optional[dict]:
    """Whether the developer behind this profile is already busy then.

    Checked across every identity the same developer is sold under, not just
    this one. Two profiles are two candidates as far as a client is concerned,
    but they are one person's Tuesday afternoon, and that is exactly where a
    double-booking hides. A profile with nobody behind it is checked only
    against itself.

    Reported, never refused. Back-to-back rounds with the same client are
    normal, a rescheduled interview legitimately overlaps the slot it is
    moving out of, and an app that argues with the person who was on the call
    gets worked around rather than fixed.
    """
    ids = [profile.id]
    if profile.dev_user_id is not None:
        shared = [row for (row,) in db.execute(
            select(Profile.id).where(Profile.dev_user_id == profile.dev_user_id,
                                     Profile.is_active == True)).all()]  # noqa: E712
        ids = shared or ids
    ends = when + dt.timedelta(minutes=max(1, minutes))

    query = select(Interview).where(Interview.profile_id.in_(ids),
                                    Interview.status == "scheduled",
                                    Interview.scheduled_at < ends)
    if ignore is not None:
        query = query.where(Interview.id != ignore)
    for other in db.scalars(query.order_by(Interview.scheduled_at)):
        finish = other.scheduled_at + dt.timedelta(
            minutes=max(1, other.duration_minutes or 30))
        if finish > when:
            names = {p.id: p.name for p in db.scalars(
                select(Profile).where(Profile.id == other.profile_id))}
            return {"id": other.id, "profile": names.get(other.profile_id, "?"),
                    "client": other.client, "when": working_label(other.scheduled_at)}
    return None


def _when(text: str) -> dt.datetime:
    try:
        return from_working(text)
    except ValueError:
        raise HTTPException(400, "That is not a date and time this app can read. "
                                 "Use the picker, or 2026-08-24T14:30.")


def _interview_json(db: Session, row: Interview) -> dict:
    return interviews.decorate(db, [row])[0]


@app.get("/api/interviews")
def list_interviews(profile_id: Optional[int] = None,
                    date_from: Optional[dt.date] = None,
                    date_to: Optional[dt.date] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Today, what is coming, what just happened — for whoever is asking.

    Not behind the dashboard switch. That switch is about being *measured*;
    this is a calendar, and hiding somebody's calendar from them only means
    they miss the call.
    """
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        ids: Optional[list[int]] = [profile_id]
    else:
        ids = visible_profile_ids(db, user)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    rows = interviews.decorate(db, interviews.load(db, ids))
    if date_from or date_to:
        rows = [row for row in rows
                if (date_from is None or row["when"]["day"] >= date_from.isoformat())
                and (date_to is None or row["when"]["day"] <= date_to.isoformat())]
    return {"rows": rows, "counts": interviews.counts(rows),
            "funnel": interviews.funnel(db, ids, date_from=date_from, date_to=date_to),
            # What the scheduling form starts on. Worked out here rather than
            # in the browser: the field means Eastern, and a machine in Karachi
            # prefilling its own clock would suggest a time nine hours from the
            # one it appears to say.
            "suggested_time": working_label(utcnow() + dt.timedelta(hours=1))["input"],
            **interviews.split(rows, date_range=bool(date_from or date_to))}


@app.post("/api/interviews", status_code=201)
def create_interview(body: InterviewIn, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Log a reply that turned into a conversation.

    Either side of the profile, and the manager. The BD runs the account most
    replies arrive at and holds the record of what was applied to; the
    developer is who a client that found them directly will email. Both find
    out first often enough that the one who knows should not have to ask
    somebody else to type it in.

    What stops one reply becoming two rows is not a permission but the clash
    check below, which is reported on every booking against the same developer
    whichever identity it was made under.
    """
    profile = linked_profile(body.profile_id, db, user)
    if body.mode not in INTERVIEW_MODES:
        raise HTTPException(400, f"Mode must be one of {', '.join(INTERVIEW_MODES)}.")
    if body.stage not in INTERVIEW_STAGES:
        raise HTTPException(400, f"Stage must be one of {', '.join(INTERVIEW_STAGES)}.")
    if body.dev_user_id is not None:
        _apply_profile_developer(db, profile, body.dev_user_id)

    job = None
    if body.job_id is not None:
        job = db.get(Job, body.job_id)
        if job is None:
            raise HTTPException(400, "No such job to attach it to.")

    if body.previous_id is not None:
        earlier = db.get(Interview, body.previous_id)
        if earlier is None:
            raise HTTPException(400, "No such earlier round to follow on from.")
        if earlier.profile_id != profile.id:
            raise HTTPException(
                400, "That earlier round was under a different profile. A chain of rounds "
                     "is one client talking to one identity.")

    # No time yet means a draft, started from the job record while the client's
    # email is still open. It is parked an hour out so every screen has
    # something to sort it by, and counted nowhere until a time is agreed.
    draft = not (body.scheduled_at or "").strip()
    when = _naive_utc(utcnow() + dt.timedelta(hours=1)) if draft else _when(body.scheduled_at)

    minutes = min(600, max(5, body.duration_minutes or 30))
    # A draft has no agreed time, so there is nothing yet for it to collide
    # with. Checking anyway would report a clash against a placeholder.
    clash = None if draft else _clash(db, profile, when, minutes)

    # What the BD copied out of the client's email is usually thinner than what
    # is already on the job. Fill the gaps from the record rather than making
    # them retype it, but never overwrite what they did type.
    client = body.client.strip()[:300] or (job.company or "" if job else "")[:300]
    role = body.role.strip()[:300] or (job.title or "" if job else "")[:300]

    row = Interview(profile_id=profile.id, job_id=body.job_id,
                    client=client, role=role,
                    scheduled_at=when, duration_minutes=minutes, mode=body.mode,
                    stage=body.stage,
                    status="draft" if draft else "scheduled",
                    link=_check_link(body.link, "meeting link"),
                    email_url=_check_link(body.email_url, "email link"),
                    notes=body.notes.strip(), previous_id=body.previous_id,
                    created_by=user.id)
    db.add(row)
    db.commit()
    return {**_interview_json(db, row), "clash": clash}


@app.post("/api/interviews/{interview_id}/next-round", status_code=201)
def next_round(interview_id: int, body: NextRoundIn, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    """Book the round after this one, carrying everything the client already said.

    The gap this fills is a real one and it loses work. A screening call goes
    well, somebody sets the outcome to `passed`, and then the second round has
    to be typed from scratch — same client, same role, same posting, retyped
    out of memory by whoever gets to it. So it usually is not typed at all for
    a week, and the client is left waiting on a team that thinks it is winning.

    One press instead. The new round inherits the profile, the posting, the
    client and the role, comes in one rung up the ladder, and is linked back to
    the round that earned it so the whole conversation reads as one thing.

    Pressing it also settles the round before, if nobody has said how that one
    went: you do not book a second round with a client who said no. That is the
    same rule as putting a time on a draft — the act *is* the statement, and a
    second click to confirm what just happened is a click somebody forgets,
    leaving a cleared round sitting in the "nobody said how it went" pile.

    No time is set unless one is given. A client who says "we would like you to
    meet the team" has not yet said when, and inventing a slot would put a
    fictional appointment in a developer's diary.
    """
    earlier = db.get(Interview, interview_id)
    if not earlier:
        raise HTTPException(404, "No such interview.")
    profile = linked_profile(earlier.profile_id, db, user)

    if earlier.status == "draft":
        raise HTTPException(
            400, "That round has no time on it yet, so it has not happened. Give it one "
                 "before booking what follows it.")
    if earlier.status == "cancelled":
        raise HTTPException(
            400, "That round was called off, so it never happened and nothing followed from "
                 "it. Log a fresh interview if the client has come back.")
    if earlier.outcome == "rejected":
        raise HTTPException(
            400, "That round was a no. Nothing follows it — log a fresh interview if the "
                 "client has come back with something else.")

    stage = body.stage or next_stage(earlier.stage or "screening")
    if stage not in INTERVIEW_STAGES:
        raise HTTPException(400, f"Stage must be one of {', '.join(INTERVIEW_STAGES)}.")
    mode = body.mode or earlier.mode
    if mode not in INTERVIEW_MODES:
        raise HTTPException(400, f"Mode must be one of {', '.join(INTERVIEW_MODES)}.")

    draft = not (body.scheduled_at or "").strip()
    when = _naive_utc(utcnow() + dt.timedelta(hours=1)) if draft else _when(body.scheduled_at)
    minutes = min(600, max(5, body.duration_minutes or earlier.duration_minutes or 30))
    clash = None if draft else _clash(db, profile, when, minutes)

    row = Interview(profile_id=earlier.profile_id, job_id=earlier.job_id,
                    client=earlier.client, role=earlier.role,
                    scheduled_at=when, duration_minutes=minutes, mode=mode,
                    stage=stage, status="draft" if draft else "scheduled",
                    link=_check_link(body.link, "meeting link"),
                    # A second round is the same conversation with the same
                    # client, so it is the same email thread until somebody
                    # says otherwise — carried across like the client and the
                    # role rather than retyped.
                    email_url=(_check_link(body.email_url, "email link")
                               if body.email_url else earlier.email_url or ""),
                    notes=body.notes.strip(), previous_id=earlier.id,
                    created_by=user.id)
    db.add(row)

    # Booking what comes next is the statement that this one was cleared —
    # but only once it has actually happened. A client who says at booking time
    # that there will be two rounds is not a report on the first one, and
    # marking a call next Tuesday `done` today would be a lie the diary then
    # tells everybody.
    #
    # Only ever fills a blank, either way: an outcome somebody already recorded
    # — an offer, a hire — is theirs and a scheduling action does not overwrite
    # it.
    happened = _naive_utc(earlier.scheduled_at) < _naive_utc(utcnow())
    if happened:
        if earlier.outcome == "pending":
            earlier.outcome = "passed"
            earlier.reported_by = user.id
            earlier.reported_at = _naive_utc(utcnow())
        if earlier.status == "scheduled":
            earlier.status = "done"

    db.commit()
    return {**_interview_json(db, row), "clash": clash,
            "previous": _interview_json(db, earlier)}


@app.patch("/api/interviews/{interview_id}")
def update_interview(interview_id: int, body: InterviewPatch,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Move it, advance it a stage, or say how it went.

    Either side of the profile may do any of it. The two prose fields are still
    split by who can answer them — `notes` is the brief the BD wrote from the
    client's email, `debrief` is what the person in the room said afterwards —
    but that is a division of labour, not a permission, and a BD who took the
    debrief over the phone types it in themselves.

    Whichever of them types it, the row is the same row, so the update is on
    the other one's screen without anybody being told.
    """
    row = db.get(Interview, interview_id)
    if not row:
        raise HTTPException(404, "No such interview.")
    profile = linked_profile(row.profile_id, db, user)

    clash = None
    if body.scheduled_at is not None:
        row.scheduled_at = _when(body.scheduled_at)
        # Putting a time on a draft is what makes it a real booking. Nothing
        # else has to be pressed: agreeing the time *is* the confirmation, and
        # a second step to say so is a step somebody forgets, leaving a real
        # interview counted nowhere.
        if row.status == "draft":
            row.status = "scheduled"
    if body.duration_minutes is not None:
        row.duration_minutes = min(600, max(5, body.duration_minutes))
    if (body.scheduled_at is not None or body.duration_minutes is not None) \
            and row.status != "draft":
        clash = _clash(db, profile, row.scheduled_at, row.duration_minutes,
                       ignore=row.id)
    if body.client is not None:
        row.client = body.client.strip()[:300]
    if body.role is not None:
        row.role = body.role.strip()[:300]
    if body.mode is not None:
        if body.mode not in INTERVIEW_MODES:
            raise HTTPException(400, f"Mode must be one of {', '.join(INTERVIEW_MODES)}.")
        row.mode = body.mode
    if body.link is not None:
        row.link = _check_link(body.link, "meeting link")
    if body.email_url is not None:
        row.email_url = _check_link(body.email_url, "email link")
    if body.notes is not None:
        row.notes = body.notes.strip()
    if body.debrief is not None:
        row.debrief = body.debrief.strip()
    if body.stage is not None:
        if body.stage not in INTERVIEW_STAGES:
            raise HTTPException(400, f"Stage must be one of {', '.join(INTERVIEW_STAGES)}.")
        row.stage = body.stage
    if body.status is not None:
        if body.status not in INTERVIEW_STATUSES:
            raise HTTPException(400, f"Status must be one of {', '.join(INTERVIEW_STATUSES)}.")
        if body.status != "draft" and row.status == "draft" and body.scheduled_at is None:
            raise HTTPException(
                400, "Give it a date and time first — that is what turns a draft into a "
                     "booking, and there is nothing to put in a diary without one.")
        row.status = body.status
    if body.outcome is not None:
        if body.outcome not in INTERVIEW_OUTCOMES:
            raise HTTPException(400, f"Outcome must be one of {', '.join(INTERVIEW_OUTCOMES)}.")
        if body.outcome != "pending" and row.status == "draft":
            raise HTTPException(
                400, "That one has no time on it yet, so it has not happened. Put it in the "
                     "diary before saying how it went.")
        row.outcome = body.outcome
        # Nobody records how an interview went before it happens. Saying it was
        # a rejection while the row still reads "scheduled" would leave it on
        # somebody's list of things to turn up to, and in the count of
        # interviews nobody has reported back on.
        if body.outcome != "pending" and row.status == "scheduled":
            row.status = "done"

    # Stamp who reported back, so the other side can see the update is
    # first-hand and how fresh it is. Only for the fields that say what
    # happened — moving an interview is not reporting on it.
    if (body.debrief is not None
            or (body.outcome is not None and body.outcome != "pending")
            or (body.status is not None and body.status in ("done", "no_show"))):
        row.reported_by = user.id
        row.reported_at = _naive_utc(utcnow())

    db.commit()
    return {**_interview_json(db, row), "clash": clash}


@app.delete("/api/interviews/{interview_id}")
def delete_interview(interview_id: int, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Remove one entered by mistake.

    Cancelling is the usual thing and keeps the row, because a client who
    pulled out is worth knowing about. This is for the interview that was never
    real — so it is the manager's, or the person who typed it.
    """
    row = db.get(Interview, interview_id)
    if not row:
        raise HTTPException(404, "No such interview.")
    linked_profile(row.profile_id, db, user)
    if user.role != "admin" and row.created_by != user.id:
        raise HTTPException(403, "Cancel it instead, or ask whoever logged it to remove it.")

    # Anything booked out of this one survives it, standing on its own. The
    # link is a convenience and losing it costs a breadcrumb; taking a real
    # second round away with a mistyped first one would cost the work. Done
    # here rather than left to the FK, because SQLite does not enforce ON
    # DELETE unless the pragma is on and this must be true either way.
    db.execute(update(Interview).where(Interview.previous_id == row.id)
               .values(previous_id=None))
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Assessments — the take-home a client sends instead of, or after, a call
# --------------------------------------------------------------------------- #

def _assessment_json(db: Session, row: Assessment) -> dict:
    return assessments.decorate(db, [row])[0]


def _due(text: str) -> Optional[dt.datetime]:
    """A deadline typed on the team's clock, as UTC to store. Empty is None.

    No deadline is a real answer and the commonest one after "next Friday" —
    it must not become today, or every screen shows a red flag nobody set.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return from_working(raw)
    except ValueError:
        raise HTTPException(400, "That is not a date and time this app can read. "
                                 "Use the picker, or 2026-08-27T17:00.")


@app.get("/api/assessments")
def list_assessments(profile_id: Optional[int] = None, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """What has been set, what is outstanding, what is late.

    Not behind the dashboard switch, for the same reason the diary is not: this
    is work somebody has been asked to do, and hiding it from them only means
    it does not get done.
    """
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        ids: Optional[list[int]] = [profile_id]
    else:
        ids = visible_profile_ids(db, user)
    return {**assessments.summary(db, ids),
            # What the form starts on: end of the working day, three days out.
            # Worked out here because the field means Eastern, and a machine in
            # Karachi prefilling its own clock would suggest the wrong evening.
            "suggested_due": working_label(
                utcnow() + dt.timedelta(days=assessments.DUE_SOON_DAYS))["input"]}


@app.post("/api/assessments", status_code=201)
def create_assessment(body: AssessmentIn, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    """Set one. Usually the BD — the client sent them the brief.

    The developer may too. A client that found them directly sends the test
    directly, and making them ask somebody else to type it in is how a deadline
    is lost between two inboxes.
    """
    profile = linked_profile(body.profile_id, db, user)
    if body.dev_user_id is not None:
        _apply_profile_developer(db, profile, body.dev_user_id)

    sitting = None
    if body.interview_id is not None:
        sitting = db.get(Interview, body.interview_id)
        if sitting is None or sitting.profile_id != profile.id:
            raise HTTPException(400, "That interview is not this profile's.")
    job = None
    if body.job_id is not None:
        job = db.get(Job, body.job_id)
        if job is None:
            raise HTTPException(400, "No such job to attach it to.")

    # Fill the gaps from whatever it came out of, and never overwrite what was
    # typed. A BD forwarding a client's email should not retype the client's
    # name when the interview or the job already carries it.
    client = (body.client.strip()
              or (sitting.client if sitting else "")
              or (job.company if job else ""))[:300]
    title = (body.title.strip()
             or (f"Assessment · {job.title}" if job and job.title else "")
             or (f"Assessment · {sitting.role}" if sitting and sitting.role else "")
             or "Assessment")[:300]

    row = Assessment(profile_id=profile.id, interview_id=body.interview_id,
                     job_id=body.job_id or (sitting.job_id if sitting else None),
                     title=title, client=client, brief=body.brief.strip(),
                     link=_check_link(body.link, "assessment link"),
                     # The test almost always arrives on the same thread as the
                     # call that produced it, so the interview's own is the
                     # default rather than something to look up and retype.
                     email_url=(_check_link(body.email_url, "email link")
                                if body.email_url
                                else (sitting.email_url or "" if sitting else "")),
                     due_at=_due(body.due_at), created_by=user.id, updated_by=user.id)
    db.add(row)
    db.commit()
    return _assessment_json(db, row)


@app.patch("/api/assessments/{assessment_id}")
def update_assessment(assessment_id: int, body: AssessmentPatch,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Move the deadline, or say how far along it is.

    Both sides may do either. The halves are a division of labour — the BD has
    the client's email, the developer has the work — not a permission, and a BD
    who was told over the phone that it went in should be able to say so.
    """
    row = db.get(Assessment, assessment_id)
    if not row:
        raise HTTPException(404, "No such assessment.")
    linked_profile(row.profile_id, db, user)

    if body.title is not None:
        row.title = body.title.strip()[:300]
    if body.client is not None:
        row.client = body.client.strip()[:300]
    if body.brief is not None:
        row.brief = body.brief.strip()
    if body.link is not None:
        row.link = _check_link(body.link, "assessment link")
    if body.email_url is not None:
        row.email_url = _check_link(body.email_url, "email link")
    if body.due_at is not None:
        row.due_at = _due(body.due_at)
    if body.submission_url is not None:
        row.submission_url = _check_link(body.submission_url, "submission link")
    if body.notes is not None:
        row.notes = body.notes.strip()
    if body.status is not None:
        if body.status not in ASSESSMENT_STATUSES:
            raise HTTPException(400, f"Status must be one of {', '.join(ASSESSMENT_STATUSES)}.")
        row.status = body.status
        # Stamped once, when it first goes back. A later pass or fail is the
        # client's verdict on the same submission and does not move the date it
        # was handed in.
        if body.status in ASSESSMENT_CLOSED and row.submitted_at is None:
            row.submitted_at = _naive_utc(utcnow())
        if body.status in assessments.OPEN:
            row.submitted_at = None

    row.updated_by = user.id
    db.commit()
    return _assessment_json(db, row)


@app.delete("/api/assessments/{assessment_id}")
def delete_assessment(assessment_id: int, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    """Remove one set by mistake. The manager's, or whoever set it.

    A test the client withdrew is worth keeping and marking, the same way a
    cancelled interview is. This is for the row that was never real.
    """
    row = db.get(Assessment, assessment_id)
    if not row:
        raise HTTPException(404, "No such assessment.")
    linked_profile(row.profile_id, db, user)
    if user.role != "admin" and row.created_by != user.id:
        raise HTTPException(403, "Ask whoever set it to remove it.")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Clients
#
# Manager only, and checked on every route rather than hidden behind a tab. A
# BD reading this screen would be reading every colleague's client relationships
# at once, which is a different thing from the board they are allowed to see.
# --------------------------------------------------------------------------- #

@app.get("/api/crm/clients")
def crm_clients(date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
                status: str = "", q: str = "", sort: str = "last_activity",
                page: int = 1, per_page: int = crm.PER_PAGE,
                db: Session = Depends(get_db), _: User = Depends(admin_only)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date.")
    return crm.client_list(db, date_from, date_to, status=status, q=q, sort=sort,
                           page=page, per_page=per_page)


@app.get("/api/crm/clients/{client_key}")
def crm_client(client_key: str, db: Session = Depends(get_db),
               _: User = Depends(admin_only)):
    detail = crm.client_detail(db, client_key)
    if detail is None:
        raise HTTPException(404, "No client by that name.")
    return detail


@app.put("/api/crm/clients/{client_key}/note")
def crm_save_note(client_key: str, body: ClientNoteIn,
                  db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """The one write on this screen, and it changes nobody's work.

    Kept in main.py rather than in crm.py so that module stays what it says it
    is: a read model with no writes anywhere in it.
    """
    key = (client_key or "").strip()
    if not key:
        raise HTTPException(400, "No client to note.")

    row = db.scalar(select(ClientNote).where(ClientNote.client_key == key))
    if row is None:
        row = ClientNote(client_key=key)
        db.add(row)
    # The spelling a person recognises, refreshed whenever the note is touched,
    # so it survives the last posting at that client being withdrawn.
    detail = crm.client_detail(db, key)
    if detail:
        row.display_name = detail["client"]["client"][:300]
    if not row.display_name:
        row.display_name = key[:300]

    if body.priority is not None:
        row.priority = bool(body.priority)
    if body.being_worked is not None:
        row.being_worked = bool(body.being_worked)
    if body.note is not None:
        row.note = body.note.strip()
    row.updated_by = user.id
    db.commit()
    return crm.client_detail(db, key)["note"]


@app.get("/api/crm/export.xlsx")
def crm_export(date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None,
               status: str = "", q: str = "",
               db: Session = Depends(get_db), _: User = Depends(admin_only)):
    listing = crm.client_list(db, date_from, date_to, status=status, q=q,
                              per_page=crm.MAX_PER_PAGE, page=1)
    everything = crm.client_list(db, date_from, date_to, status=status, q=q,
                                 per_page=listing["totals"]["clients"] or 1, page=1)
    details = [crm.client_detail(db, row["client_key"])
               for row in everything["clients"]]
    data = exports.client_workbook(everything["clients"],
                                   [d for d in details if d])
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="clients.xlsx"'})


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/sheet.xlsx")
def download_profile_sheet(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                           user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    jobs = _assignment_rows(db, batch_id, profile.id)
    if not jobs:
        raise HTTPException(404, "Nothing has been dispatched to this profile in this cycle.")
    data = exports.assignment_workbook(profile.name, jobs)
    filename = f"{profile.name.replace(' ', '-').lower()}-batch-{batch_id}.xlsx"
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/batches/{batch_id}/report.xlsx")
def download_report(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    data = report(batch_id, db, _)
    grouped = _all_assignment_rows(db, batch_id)
    per_profile = {p["name"]: grouped.get(p["id"], []) for p in data["participants"]}
    payload = exports.report_workbook(
        data["report"], per_profile, data["collisions"],
        data["matrix"]["names"], data["matrix"]["rows"],
        data.get("turned_down"))
    return Response(payload, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="dispatch-batch-{batch_id}.xlsx"'})


@app.get("/api/pipeline.xlsx")
def download_pipeline(profile_id: Optional[int] = None, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    """Every conversation and take-home, as a spreadsheet.

    Scoped exactly like the screens it comes from: a BD gets the profiles they
    run, a developer the ones they are sold under, a manager the workspace. The
    same rule everywhere means nobody has to wonder what a downloaded file
    contains before sending it on.

    Not filtered to a cycle, for the reason nothing about interviews ever is: a
    reply that lands three weeks late belongs to the work that earned it, not
    to whichever cycle happened to be open when the client got round to it.
    """
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        ids: Optional[list[int]] = [profile_id]
    else:
        ids = visible_profile_ids(db, user)

    conversations = interviews.decorate(db, interviews.load(db, ids))
    tests = assessments.decorate(db, assessments.load(db, ids))
    if not conversations and not tests:
        raise HTTPException(404, "Nothing has come back yet, so there is nothing to export.")

    payload = exports.pipeline_workbook(conversations, tests)
    stamp = working_label(utcnow())["day"]
    return Response(payload, media_type=XLSX,
                    headers={"Content-Disposition":
                             f'attachment; filename="pipeline-{stamp}.xlsx"'})


@app.get("/api/health")
def health():
    return {"ok": True, "time": utcnow().isoformat()}


# --------------------------------------------------------------------------- #
# First run, and serving the browser app
# --------------------------------------------------------------------------- #

def bootstrap_admin() -> None:
    """Create the first manager from the environment, once, on an empty database.

    A hosted deployment often has no shell to run seed.py in — on Render's free
    tier there is none at all — so the account that lets you in has to be able
    to create itself. Does nothing if any manager already exists, so it cannot
    resurrect an account you deliberately removed.
    """
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or len(password) < 8:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.role == "admin")):
            return
        db.add(User(email=email, name=os.getenv("ADMIN_NAME", "Manager").strip() or "Manager",
                    password_hash=hash_password(password), role="admin"))
        db.commit()
        print(f"Created the first manager account: {email}")
    finally:
        db.close()


bootstrap_admin()

if WEB_ROOT and os.path.isdir(WEB_ROOT):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = os.path.join(WEB_ROOT, "index.html")
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_ROOT, "assets")),
              name="assets")

    # Registered last, so every /api route above already owns its path. React
    # does its own routing, so anything else hands back index.html rather than
    # a 404 — but a wrong /api path must still fail like an API, not like a page.
    @app.get("/{path:path}", include_in_schema=False)
    def browser_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "No such endpoint.")
        candidate = os.path.join(WEB_ROOT, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)
