# Dispatch

Your team hands in the sheet of jobs each profile applied to. The system works
out which postings are the same job across every sheet, shows you how much
effort was spent twice, and gives each profile back the jobs it has never tried.

Then it follows what all that typing turned into: who is interviewing today,
who is free to take work, and how much of it ended in an offer.

---

## The idea in one example

Ali runs the profile **Khuram**, an AI engineer. Sara runs **Zahid**, also an AI
engineer. Same skills, same job boards, two different candidates.

Khuram applied to 30 jobs. Zahid applied to 50. Ten of those were the same
posting found twice, so between them they reached **70 distinct jobs**.

Run the cycle:

| | applied | pool | comes back |
|---|---|---|---|
| Khuram | 30 | 70 | **40** |
| Zahid | 50 | 70 | **20** |

Khuram gets the 40 it has never seen. Zahid gets the 20 it has never seen. The
ten both had already used go to nobody.

Note that Khuram is handed jobs **Zahid already applied to**, and that is
correct. They are two candidates, not one person applying twice — the client
sees two applicants. The only thing the system will never do is offer a profile
a job that *same profile* has already used.

---

## Profiles, not people

This is the distinction the whole product turns on.

- A **person** signs in. Ali, Sara, the manager.
- A **profile** is the identity a job is applied under — the name and resume the
  client sees. "Khuram, AI Engineer".

One person can run several profiles. A profile can be handed to a different
person. All history — what has been applied to, what has been dispatched —
belongs to the **profile**, because that is what the client recognises.

Two profiles sharing a headline is not a problem to solve. It is the normal case.

---

## Who is behind the profile

A profile is an identity. Somebody has to actually be it.

- The **BD** runs the account and does the applying. On screen: *run by*.
- The **developer** is who the profile sells — the person who sits the
  interview and writes the code. On screen: *developer*.

Two different people, kept apart on purpose. The BD holds the profile's whole
record: what it applied to, what came back, where each of those stands, and the
diary of every reply that turned into a conversation. A developer can never
mark a job applied, because that would put work into a BD's record that the BD
did not do, and retire a posting from the rotation on the strength of somebody
who never applied for it.

What the developer owns is their own information: the email a client replies
to, the resume link the BD attaches, their skills, their rate, the hours they
can actually be reached, and whether they can take work at all.

Those live on the **profile**, not on their account. One developer running two
identities may well send two different resumes into two different markets, and
hanging the fields off the person would force those two to be one.

They keep it current themselves. Routing "here is my new CV" through a manager
is how a stale link ends up on the next fifty applications.

---

## What the applications turned into

Everything above this counts effort — rows typed, duplication avoided, lists
worked through. A team can improve every one of those figures without winning a
single piece of work.

An **interview** is the first thing here that records an outcome.

**Either side books it.** The BD runs the account most replies arrive at and
holds the record of everything applied for; the developer is who a client that
found them directly will email. Both find out first often enough that the one
who knows should not have to ask somebody else to type it in. What stops one
reply becoming two rows is not a permission but the clash check — it fires on
any booking against the same developer, whichever identity it was made under.

**The row still has two halves**, because two different people can answer them:

| | Usually the BD | Only the developer really knows |
|---|---|---|
| when it is, how long, where | ✓ | |
| the client, the role, the link | ✓ | |
| the brief — what to lead with | ✓ | |
| happened / no show / cancelled | | ✓ |
| the outcome | | ✓ |
| the debrief — how the call actually went | | ✓ |

That is a division of labour, not a permission: either side may write either
half, and a BD who took the debrief over the phone types it in themselves. What
the app will not do is let the brief and the debrief overwrite each other. They
are separate fields, because a debrief typed over the top of a brief loses what
the client actually asked for and there is no second copy of it anywhere.

Every update is on the other person's screen within the minute with no
forwarding, and the row says whose word it is — *Khuram Gill reported it ·
Mon 24 Aug · 12:05*.

### The ladder

A conversation is not one event. It climbs:

```
screening  ->  technical  ->  assessment  ->  final  ->  offer
```

Each sitting carries its rung, and the dashboard shows how many reached each
one, how many went on, and how many ended there. That is the thing a single
applications-to-offers percentage cannot tell you: a team losing everybody at
**technical** has a tooling problem, one losing them at **final** has a rate or
an availability problem, and those call for opposite fixes.

`assessment` is a rung rather than something beside the ladder, because a
take-home is a place a candidate is *at* — the client is not talking to anyone
else while it is out.

### Climbing it

A round that goes well used to leave the next one to be typed from scratch —
same client, same role, same posting, retyped out of memory by whoever got to
it. So it often was not typed for a week, and the client was left waiting on a
team that thought it was winning.

Press **next round** on any sitting that has happened. The new one inherits the
profile, the posting, the client and the role, comes in one rung up the ladder,
and is linked back to the round that earned it. No time is set unless you give
one, so it lands under **Waiting on a time** like any other reply nobody has
agreed an hour for.

Pressing it also settles the round before, if nobody has said how that one went
— you do not book a second round with a client who said no. Same rule as
putting a time on a draft: the act *is* the statement. An outcome somebody
already recorded is never overwritten, and a round still in the future is not
marked done, because a client saying up front that there will be two rounds is
not a report on the first one.

Linked rounds read as one conversation: *round 2 of 3 · after the screening
call*. That matters because a client who ran four rounds and then said no is a
different fact from four clients who each said no after one call, and in a flat
list of interviews those two are indistinguishable.

Removing a round never takes what followed it. The link is a convenience;
losing it costs a breadcrumb, while deleting a real second round along with a
mistyped first one would cost the work.

### Cleared, and nothing booked after

The quietest way this product loses work. The client said yes, no next round
was ever put in, and on every other screen that row reads as a success — it has
a good outcome and nothing about it looks unfinished.

So it is counted and listed on its own: **cleared, and nothing booked after
it**, on the BD's screen, the developer's desk and the manager's overview.
Booking the next round is what clears it. A hire never appears there — nothing
follows a hire; it is the end of the ladder, not a gap in it.

### A reply, before there is a time

A client answers on Tuesday and the call is not agreed until Thursday. In
between, the conversation exists and nothing in a diary can hold it.

So it can be started with no time at all. Open **All jobs**, find the posting
they replied about, and press *they replied* — the row waits under **Waiting on
a time**. It is in no rate, no funnel and no count of what is coming, because
none of that is true of it yet. Putting a time in is what books it; there is
deliberately no second confirm button, since agreeing the time *is* the
confirmation and an extra step is one somebody forgets.

The whole posting travels with it, not a useful-looking subset:

| Job title | Client | Job link | Description link | Platform | Applied on |
|---|---|---|---|---|---|

Those six are what a BD has in front of them when they answer the email, and
they stay on the row through booking, through every round after it, and into
the export. **Applied on** is the date that profile wrote on its own sheet —
kept per identity, because two profiles can have applied to one posting on
different days and showing one of them under the other is worse than showing
nothing.

The booking form does the same thing from the other direction. **Which job did
they reply about?** searches the record for the profile you are booking under,
and picking a row attaches the posting and fills the client and the role if you
have not typed them. Both ways in produce the same row, rather than one that
carries the posting and one typed out of memory a fortnight later. Changing the
profile on the form drops anything already attached — a job the *other*
identity applied to is not this conversation.

---

## Every job, and finding the one they mean

A client's reply names a company and maybe a job title. It arrives three weeks
after the application that earned it, by which time that cycle is closed and
gone from every cycle-scoped screen in the app.

**All jobs** is the one screen that goes back to the beginning. Every posting
every profile you run has ever applied to, searchable by client, title,
platform or link — because somebody pasting out of an email has no idea which
field the thing they copied lives in. Find the row, start the conversation from
it, and nothing is retyped.

Two links are kept per job, not one:

- **the apply link** — where the application went;
- **the job description link** — where the posting is written out.

They are usually the same on the day and rarely the same three weeks later. An
expired posting redirects to a board's home page and takes the wording with it,
and the wording is exactly what a BD needs when the client finally answers. The
description link is never part of a fingerprint: two profiles can hold two
different links to the same job's description, and matching on it would split
one posting in two.

---

## Assessments

The third thing a client can ask for, after a reply and a call, and the one
that costs a developer a weekend.

Same shape as an interview and split the same way. The BD sets it — the client
sent them the brief, the link and the deadline. The developer does it, and says
how far along they are and what went back. Either may write either half.

    sent -> in progress -> submitted -> passed / did not pass

It does not need an interview to exist first. Plenty of clients screen with a
test before anybody speaks, and an assessment that could only hang off a call
would force somebody to invent a call that never happened. When it *did* come
out of a round, it links back to it and reads as "after the technical round".

It carries the same posting an interview does — the six fields above, worked
out the same way, including that profile's own **applied on** date. Name a call
on the form and the posting comes across with it, because the call already
knows which one; leave the call blank and the same job search offers it
directly. A take-home and the conversation that produced it are one thing, and
two screens describing it differently is worse than neither of them saying.

**No deadline is a real answer**, and the commonest one after "next Friday". It
stays empty rather than becoming today, because an invented deadline is a red
flag on somebody's screen that nobody set. One that *is* set and passes turns
the row over — but only while it is still open. A take-home submitted late is a
thing that happened, not a thing to chase.

A deadline is the one thing here that goes wrong **silently**. Every other
figure in this app understates itself when nobody touches it — an unreported
interview makes a good week look quiet. A missed assessment does the opposite:
nothing changes on any screen, the row sits there looking exactly as it did
yesterday, and the first anybody hears of it is the client's next email. So it
is carried everywhere rather than kept in its own tab:

- on **every dashboard** — the BD's, the developer's, the manager's, and a
  single profile's page;
- on the **interview row it came out of**, because when a client has sent a
  test the test *is* the state of that conversation, and having to open a
  second tab to find out whether you are waiting on the client or on your own
  developer is how a week goes past;
- on the **developer board**, as a column. "Free on Thursday" is not free when
  a test is due Friday, and a manager reading availability off the diary alone
  books straight over it. An overdue one sorts that developer to the top.

- **The time is Eastern.** Always, said out loud on the form and again on every
  row. A BD in Karachi and a developer in Lisbon have to read one appointment
  as the same moment, so the browser never gets to decide what "half past two"
  means — the server does it once and hands back a preformatted string.
- **A double-booking is caught across identities.** Two profiles are two
  candidates as far as a client is concerned. They are also one person's
  Tuesday afternoon, and that is exactly where the clash hides. Booking over an
  existing interview for the same developer is flagged, with what it collides
  with. It is not refused: a reschedule legitimately overlaps the slot it is
  leaving, and an app that argues with the person who was on the call gets
  worked around rather than fixed.
- **The outcome is what moves the numbers** — *next round*, *offer*, *hired*,
  *no*. Recording one also records that the interview happened, because nobody
  says how a call went before it takes place.
- **A cancellation is never a rejection.** A client who pulled out before the
  call turned nobody down, and counting it as one makes a quiet week look like
  a bad one. It stays on the list, greyed, because a slot that vanishes
  silently reads the same as a slot that was never booked.

What comes out of it is the one figure in this product that cannot be improved
by typing faster:

```
applications  ->  interviews  ->  offers  ->  hired
    1,240             34             6          2
                 2.7% of         18% of
                 applications    interviews
```

And the number to read before any of them: **interviews that have been and gone
with nobody saying how they went**. Every rate above is understated until
somebody does, so the app counts them and says so, rather than quietly
reporting a figure it knows is too low.

All of it downloads. **Download as Excel** on the interviews screen gives two
sheets — every conversation, with its round and what it followed, and every
take-home with its deadline and what went back. It is scoped exactly like the
screen it comes from: a BD gets the profiles they run, a developer the ones
they are sold under, a manager the workspace. Everything else this app exports
counts what went *out*; this is the half that says what came back, and it is
the half somebody is asked about at the end of a quarter.

---

## What happens when you press "Build the lists"

1. **Every row is fingerprinted.** Same job, different link, must resolve to the
   same identity. Four tiers, first hit wins:

   | Tier | Rule | Typical share |
   |---|---|---|
   | L1 | Platform's own job ID pulled out of the URL (Upwork `~01…`, LinkedIn `/jobs/view/…`, Indeed `jk=…`) | ~85% |
   | L2 | Canonical URL — protocol, `www.`, tracking params and trailing slash stripped | ~8% |
   | L3 | Client + title, when there is no usable link | ~6% |
   | L3f | L3 rows merged when client *and* title are both a close fuzzy match | reposts and reworded titles |

   The named platforms mint globally unique IDs, so an Upwork `~01…` is that job
   and nothing else. The generic fallbacks — "a long number in the path" — match
   a shape that repeats on every board in existence, so those keys carry the
   hostname too. Otherwise `example.com/careers/12345678` and
   `different.com/openings/12345678` would collapse into one job and one of the
   two postings would quietly vanish from the pool.

2. **Applications are recorded** — one row per profile per job, for good.

3. **The pool is built** from this cycle's sheets *plus* anything still sitting
   unworked on a participating profile's list from an earlier cycle. A job
   somebody ran out of time for does not fall through the cracks.

4. **The lists rebuild themselves.** A cycle stays open while the team works it.
   Every few minutes — you pick 5, 10, 15 or 30 when opening it — the server
   rebuilds every open cycle that has at least two sheets in it. Nobody presses
   anything: a job Ali logs at two o'clock is off the other profiles' lists by
   ten past.

   Rebuilding never disturbs work already done. Jobs a profile has marked
   **applied** or **skipped** keep their place and their status; only the
   untouched rows are recalculated. Closing the cycle is what stops the timer.

5. **Each profile is given what it has not used.** Two modes, chosen when you
   open the cycle:

   - **Cover every profile** (default) — each profile gets every pooled job it
     has not applied to or skipped. This is the Khuram-and-Zahid case above.
   - **Split the pool** — each job goes to exactly one profile, nobody overlaps.
     For a team where the profiles are really one identity and a second
     application would read as a repeat.

   A quota caps each list. When it bites, the jobs almost nobody is eligible for
   go out first, so a rare opening is not lost to a job everyone could have taken.

6. **The database holds the line.** `assignments` is unique on
   (batch, job, profile), so one cycle can never put the same job on one
   profile's list twice. Split cycles additionally carry a partial unique index
   on (batch, job) — so even with a bug, or two managers pressing the button at
   once, a split cycle cannot hand one posting to two profiles.

A job leaves a profile's rotation for good only when that profile marks it
**applied** or **skipped**. Anything left as *to do* comes back next cycle.

A **skipped** job also leaves the list the instant it is marked. There is
nothing further to do about a posting this profile has turned down, and it is
never offered again — so a greyed-out row that can only be scrolled past is not
worth the space. The mark itself is kept underneath, because that row is what
stops the job coming back. Downloads keep every row, skipped included: a
download is the record of what the cycle dispatched, not a list of things to do.

Every job on a list also says **who found it**. A run of jobs from one
colleague's profile that are all wrong for yours is a fixable thing — but only
if you can see whose search they came from. Press one of those names and the
list narrows to everything that profile found, because reading "found by
Faizan" on a single row is a curiosity while seeing the whole run of them
together is what tells you whether to trust the next twenty. The same box
filters by client, title, platform or link, and the download carries the tag
too — a file somebody works through on a train should not be a worse document
than the screen it came from.

### Profiles that have not handed anything in

A cycle opens, two profiles report in, and a third selling the same skills has
logged nothing yet — because they are new, or were away, or have not got to it.
Leaving them out means the profile with the most spare capacity is the one
handed no work, which is backwards. So they join as recipients: they receive
the pool without having fed it, and their own history still blocks anything
they have already applied to. A late joiner is given jobs, not given away.

Matched on **skills**, not on the headline, so "AI Engineer" and "ML Engineer"
are recognised as the same market. Two guards keep it from being a free-for-all:

- A profile with **no skills recorded is never pulled in.** An empty field is
  not a match — it is a profile nobody has finished setting up, and handing it
  a stranger's pool would be a guess rather than an inference.
- **Shared tooling does not count on its own.** An AI engineer and a front-end
  engineer both run Postgres in Docker on AWS. Matching on that is exactly how
  a full-stack profile ends up in an AI cycle, so infrastructure is stripped
  before the comparison; a shared language or framework still counts.

The report says how many were pulled in this way, so a manager seeing jobs on a
list they did not expect can find out how they got there.

---

## The dashboards

Both roles land on a dashboard. It is the screen that says what is waiting,
and every route out of it is one button away.

### Yours

Once your manager has opened it for you. It leads on the one number worth acting
on — jobs still sitting unworked on your list — with the
button that takes you to them.

Under it: what you logged this cycle, how much of it a colleague had already
found, how much of your list you have worked through, a fortnight of daily
activity, and a card per profile you run — each saying whether that identity
owes a client a take-home, because a card about how much went out is half the
story if it is silent about the test that could lose it. Below that, what the
applications turned into, any conversation that cleared a round and then
stopped, and the take-homes outstanding against your profiles. The duplicate
count is the one to read twice. If ten of the thirty jobs you logged were already on somebody
else's sheet, your search and theirs are covering the same ground, and that is
fixable at the source in a way no amount of dispatching can match.

### The developer's

Their day, not their score.

It opens on the next interview — the time, the client, the identity they are
being sold as, and the button that joins the call. Today's list sits under it,
then what is coming in the fortnight.

A developer may be sold under several identities, and the question they
actually have is usually about one of them — *what has Khuram got today*. So
the screen narrows to one profile at a time, and the figures narrow with it
rather than staying whole and quietly disagreeing with the list underneath
them. **All of them** is still there and is where it opens.

The booking is read-only to them. What they write is the half a BD cannot
answer: whether the call happened, what came of it, and — under **notes** on
the row — how it actually went. It reaches their BD the moment they save it.

They book too, and they advance a round themselves. A client that found them
directly emails them directly, and the developer is usually the first to know a
second round is wanted — the client said so in the room. Making them ask
somebody else to type it in is how a week goes by. What stops one reply
becoming two rows is not a permission but the clash check, which fires on any
booking against the same developer whichever identity it was made under.

Then their own record: how many applications have gone out in their name, how
many became conversations, what came of them. They are entitled to that. It is
their name on every one of those applications. Alongside it, the take-homes
sitting on their week and any conversation that cleared a round and then
stopped — the one thing on that screen they can fix in a single press.

**My details** is the other half of the screen and the part a BD depends on:
resume link, email, skills, rate, the hours they can be reached — and one
switch that matters more than the rest. **Can you take work?** Marked *booked
up*, it appears on the BD's screen before they apply, because winning an
interview for somebody who cannot start costs the client's goodwill as well as
an afternoon.

Availability saves the moment it is pressed. Everything else on the card waits
for **Save** — a colleague acts on availability within the hour, and a draft
nobody submitted is a developer still quietly showing as free.

### The manager's

The same picture for the whole workspace, plus the things only a manager can
act on:

- **Who has not handed in.** Named, not counted. A cycle cannot be built until
  two profiles have reported in, so this is usually the thing holding it up.
- **Each person, rolled up.** One person may run several profiles, so this is
  the only view that answers "how is Ali doing" rather than "how is Khuram
  doing". **Open** on a row shows you their dashboard as they would see it, with
  the switch that decides whether they can.
- **Every profile**, ranked, clickable. Clicking one opens it: its figures, a
  month of activity, how it has done cycle by cycle, and the last twenty jobs
  it logged.
- **Duplicated effort over time.** The share of the team's typing that two
  profiles spent on the same posting, cycle by cycle. It is the number this
  whole tool exists to bring down, and the only place you can see whether it
  is going down.
- **What it all produced.** The funnel for the whole workspace, today's
  interviews by name and hour, and the count of interviews nobody has reported
  back on.
- **Conversations that stalled.** Cleared a round, nothing booked after it.
  Read-only from here on purpose: whoever runs that profile books the next
  round, and their screen is one click away under *The developers* — a manager
  quietly booking into somebody else's client relationship is how one reply
  becomes two conversations.
- **Take-homes across the workspace**, late first. The only work in this
  product with a deadline on it, and until now the only kind a manager had no
  screen for at all.
- **The developers.** Who is behind each profile, whether they could start on
  Monday, what is in their diary, and how many take-homes are sitting on them.
  **Open** on a row is that developer's own screen, and outcomes can be
  recorded from it — the person chasing them is usually the one looking.

### Between two dates

Every figure above is scoped to a **cycle** — what went out in dispatch 14 —
because that is the unit the work is organised in. It is not the unit people
are asked about. "What did you do between the first and the fifteenth" is a
question about a fortnight, and a cycle opened on the 3rd is still being worked
on the 20th.

So the dashboards take a **From / To** pair, and setting one replaces the usual
today-and-next-fortnight view rather than sitting beside it. Nothing in the
report reads `batches` at all: applications are dated by when they were
recorded, work on a list by when it was **marked**, and interviews by when they
were **held**. A job dispatched on Monday and applied for on Friday belongs to
Friday, because that is the day the work happened.

A BD gets both halves:

```
1 Aug – 15 Aug · 15 days

  140 applications      9.3 a day        11 days worked
   92 you found         48 from colleagues      12 skipped

  ███████████████████████████░░░░░░░░░░░    66% off your own search
```

The split is exact rather than a guess. A posting off this profile's own sheet
has a `batch_applications` row; one handed over by the cycle and later marked
applied does not. Those two numbers always add up to the total.

Then what it produced — and this half is what a **developer** sees on their own
desk, since they sent none of the applications:

```
  9 clients talked, across 14 interviews · 6% of what went out

  11 held    3 to come    5 one round only    4 reached a 2nd    2 reached a 3rd
  furthest one got: 4 rounds
```

**Conversations, not sittings.** A client who ran three rounds replied once, and
counting rows would say a team that ran one long process with a single client
had more second rounds than a team that reached four clients once each — the
exact inversion of what the person asking wants to know. Under it, one row per
client: who they were, what they were for, how far it got, how it ended.

A chain is measured whole, in both directions. A screening call inside the
window whose technical round lands next month still counts as reaching a second
round, and last month's screening call does not become a second conversation
just because this month's follow-up is in view. Clipping either end would make
the answer depend on where the window happened to fall.

The same report is on a **single profile's page**, narrowed to that identity —
which is the difference between "my week" and "how is Khuram doing".

### Who may see whose numbers

Two switches, and they answer different questions. The manager sees everything
whatever they are set to.

**1. May this person see their own figures?**

Nobody gets a dashboard until the manager opens it, one person at a time. A new
account starts closed. Being measured on a screen should be a decision somebody
made, not a side effect of having a login.

The manager opens **Dashboard → Their dashboard**, hits **Open** on somebody's
row, and is looking at that person's dashboard — the real one, the same
component fed the same payload, so what you check before opening it is exactly
what they will get. The switch to hand it over sits on top of it. It is also in
the **Dashboard** column of **People and profiles** for when you already know.

Closing it takes nothing away from the work. Their list, the sheet they hand in,
everything under **My work** is untouched — only the screen of figures goes, and
the tab with it.

**2. May they see each other?**

The **team board** — every profile side by side, ranked — is the manager's by
default. One workspace-wide switch opens it to everybody who already has a
dashboard of their own; it never reaches somebody whose own is still closed.

Open it when the team should see the duplication they are creating between
them; leave it shut when a ranking is not what they need. One profile can be
taken off it without hiding everyone, from **People and profiles** or the
switch under the board. It stays on the manager's screen.

**3. And the developers?**

Neither switch touches them, deliberately. Both exist so that nobody is
*measured* on a screen without somebody deciding to measure them. A developer's
screen is their own calendar and their own resume — withholding it protects
nobody and just means they miss the call.

They see the identities they are sold under and nothing else. Another
developer's diary, another profile's list of jobs, the team board: all refused
on the server, not merely absent from the tabs.

Nobody ever sees another profile's *jobs*. The board carries totals; the
drill-down into one profile's record refuses anyone but its owner, its
developer, and the manager.

Both checks are on the server. A closed dashboard is not a hidden tab — it is a
`403`, and the tab is hidden only so nobody walks into one.

---

## Run it locally

You need Python 3.10+ and Node 18+. Nothing else.

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
# paste that into JWT_SECRET in .env

python seed.py --samples           # accounts, profiles and test sheets
uvicorn app.main:app --reload --port 8000
```

Leave that running. API docs are at <http://localhost:8000/docs>.

Seeded accounts:

| Email | Password | Role | Profile |
|---|---|---|---|
| `admin@example.com` | `admin12345` | Manager | — |
| `ali@example.com` | `bdpass12345` | BD | applies as Khuram |
| `sara@example.com` | `bdpass12345` | BD | applies as Zahid |
| `hina@example.com` | `bdpass12345` | BD | applies as Nadia |
| `khuram.dev@example.com` | `devpass12345` | Developer | *is* Khuram |
| `zahid.dev@example.com` | `devpass12345` | Developer | *is* Zahid |
| `nadia.dev@example.com` | `devpass12345` | Developer | *is* Nadia |

The seed also writes a diary — two interviews today, some ahead, some behind,
and one that happened yesterday with no outcome recorded, so the screens have
something on them. It is skipped entirely once a single interview exists, so
re-running the seed never doubles anybody up.

**Change these before anyone else can reach the server.**

### 2. Frontend

New terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite forwards `/api` to port 8000, so there is
nothing to configure.

---

## Test it end to end

`python seed.py --samples` writes three CSVs into `backend/sample_sheets/`,
built so the arithmetic is checkable by hand. Khuram's sheet holds jobs 0–29,
Zahid's holds 20–69 — exactly ten in common. Nadia's sheet deliberately uses
different column names, blank links on some rows and shouty uppercase titles, to
exercise the auto-mapper and the fuzzy tier.

**Walk it through by hand:**

1. Sign in as `admin@example.com`. Open a cycle called `Test`, cap 500, leaving
   **Cover every profile** selected.
2. Sign out. Sign in as `ali@example.com`, drop `khuram-applied.csv`. Sign out.
   Sign in as `sara@example.com`, drop `zahid-applied.csv`.
3. Sign back in as admin and press **Build the lists**.
4. Khuram should show 40 and Zahid 20, with ten jobs both had already applied to.
5. Sign in as Ali — Khuram's list is there, 40 jobs, none of them anything
   Khuram has touched before. **Who you are applying as** at the top carries
   Khuram's resume link and email, one click from being pasted into an
   application.
6. Still as Ali, open **Interviews** and log one for this afternoon. Sign out,
   sign in as `khuram.dev@example.com`, and it is at the top of their screen —
   nothing was emailed and nobody was told.

**Or let the tests do it:**

```bash
cd backend
pytest test_matching.py -v      # 26 rules: fingerprints, fuzzy merge, both modes
pytest test_e2e.py -v -s        # full round trip, prints the report
pytest test_dashboard.py -v     # the figures, and who may see whose
pytest test_developer.py -v     # the developer side: the clock, the clash, the funnel
pytest test_pipeline.py -v      # the record, the ladder, assessments, skill joins
pytest                          # all of it
```

Expected output on the sample data:

```
Rows read                              80
Unique jobs                            70
Jobs two profiles both applied to      10
Duplicate applications                 10
Jobs nobody could take                 10
Jobs put on a list                     60

Khuram   AI Engineer   Ali Raza    40 jobs
Zahid    AI Engineer   Sara Khan   20 jobs
```

`test_e2e.py` asserts what matters: a profile is never handed a job it already
used, one person's two profiles do not restrict each other, unworked jobs come
back and worked ones do not, split cycles keep every job to one profile,
rebuilding gives the same answer, one cycle's report never counts another's, and
nothing a spreadsheet can contain becomes a live link or an Excel formula on a
colleague's machine.

---

## Using it for real

1. Sign in as manager → **People and profiles**. Add your team — BDs, and a
   **developer** account for each person your profiles actually sell. Then add
   a profile per identity and say two things about it: which BD runs it, and
   which developer it is. Delete the samples. Decide there, or later from the
   dashboard, who gets to see their own figures — a new BD starts without, and
   a developer does not need the switch at all.
2. **Batches** → open a cycle. Pick the mode, the cap, and how often the lists
   should rebuild. Then leave it alone.
3. Each developer signs in once to fill in their own card under **My
   details** — resume link, email, skills, rate, hours. Nothing else asks them
   for it, and a profile with no resume link is a BD applying with nothing to
   attach.
4. Each BD signs in and picks the profile they are working as. Three tabs:
   - **Jobs I applied to** — either *Add manually*, which gives a table where
     every **+ New entry** adds a row stamped with the current Eastern time, or
     *Upload a sheet* for anyone who already keeps a spreadsheet. Any column
     layout works; the mapper guesses and they can correct it.
   - **New jobs** — what this profile has never applied to, refreshed as the
     lists rebuild.
   - **Interviews** — replies that turned into conversations, and the outcomes.
5. Nobody needs to press anything. The lists rebuild on the timer as sheets
   arrive; **Build now** is there if you want it immediately. **Dashboard**
   shows you who has handed in, who is working their list and who is not,
   without opening anything.
5. Work the list in the browser or download it as Excel. Marking jobs
   **applied** or **skipped** as you go is what keeps the next cycle accurate,
   and those marks survive every rebuild.
6. When a client replies, open **All jobs**, search for what they mentioned,
   and press *they replied* on the row. The posting comes across whole and the
   conversation waits under **Interviews → Waiting on a time**. Put a time on
   it once you have agreed one and it is booked — you are told there and then
   if it collides with something that developer already has. Either side may
   book; a developer emailed directly does not have to forward it first.
7. Afterwards the **developer** records how it went, and writes the debrief
   under **notes** on the row. They were in the room; nobody else can answer it
   first-hand. Both appear on the BD's screen within the minute, tagged with
   who said so and when. That single outcome field is what makes every rate in
   the app mean anything.
7b. If the client sends a take-home, put it under **Assessments** with whatever
   deadline they gave — or none, if they gave none. The developer picks it up
   there, and anything still open past its deadline is called out on both
   screens.
8. **Close cycle** when the round is done. That stops the rebuilds and stops
   accepting sheets. Reopen it if you closed too early. Interviews are not
   attached to a cycle and are unaffected: a reply that arrives three weeks
   late belongs to the work that earned it.

Sheets can be any of `.xlsx`, `.xls`, `.csv`, `.tsv`. Only six columns are
read — job link, job title, client, job description link, platform, applied
on — and everything else is ignored. The mapper guesses which is which and the
guess is editable.

### Reading the overlap matrix

If two profiles show heavy overlap, they are running near-identical searches.
That is not automatically bad — two candidates covering the same ground is
sometimes the plan — but it means your *discovery* is duplicated even if your
applications are not. Fixing that at the source (different filters, different
boards, split by skill) widens the pool before this tool ever runs.

### What it does not do

It sends no email and no notification. An interview logged here appears on the
developer's screen the next time it refreshes, which is within the minute, and
nowhere else. If somebody needs a phone to buzz, that is still a phone.

It has no way to search a job board. The pool is only ever what your team typed
into their sheets, so a list is "jobs my colleagues found that this profile has
not used", never fresh leads. It also has no notion of skill matching: if a
full-stack profile hands in a sheet, those jobs are offered to your AI profiles
too. Keep unrelated specialisms in separate cycles if that matters to you.

---

## Upgrading an existing database

Version 1 keyed everything on the person who uploaded a sheet. Version 2 keys it
on the profile. The app upgrades itself on first start: it creates one profile
per existing person, carries their whole history onto it, labels every existing
cycle as a `split` cycle (which is what v1 always did), and rebuilds the tables
whose constraints changed. Nothing is lost and the step is idempotent.

Managers get a profile too, since v1 could not rule out that they had uploaded a
sheet. Retire it from **People and profiles** if it is not wanted.

Version 2.2 added the developer behind a profile, and interviews. That one is
purely additive — a new table and eight optional columns, all empty — so
upgrading to it is a restart and nothing else. Every existing profile carries
on with nobody behind it and no diary, which is exactly how it behaved before
the columns existed, until a manager attaches somebody.

Version 2.3 added the developer's half of an interview — the debrief, and who
reported it. Three optional columns on `interviews`, no row rewritten: one from
before the split keeps its brief and simply has no debrief, which is the truth
about it.

Version 2.4 added the stage ladder, the job description link, drafts and
assessments. `assessments` is a new table `create_all` makes on its own; the
rest is two more optional columns. Every interview already recorded lands on
`screening`, which is what most first conversations were, and can be moved.

Version 2.5 linked a round to the one it followed on from, so a client who ran
four rounds reads as one story rather than four unrelated rows. One nullable
column on `interviews`. Every interview already recorded has no predecessor,
which is exactly what an empty column says.

All of these are restart-only. Back up the file first anyway — it is one `cp`.

---

## Deploying

**Docker** (Postgres included):

```bash
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))") \
  docker compose up --build
# app on :8080, API on :8000
docker compose exec api python seed.py
```

**Cheap VPS**, roughly $6/month, no Docker:

```bash
# backend
pip install -r requirements.txt
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000 -w 2

# frontend
npm run build          # serve frontend/dist with nginx, proxy /api to :8000
```

Put nginx in front with a Let's Encrypt certificate. `frontend/nginx.conf`
already has the proxy rule.

### The rebuild timer, when hosted

The timer runs inside the app process, so it only ticks while the app is awake.
On a plan that sleeps when idle — Render's free tier, for one — a cycle left
untouched overnight will not rebuild until someone next opens the page, at which
point it catches up on the first tick. Anything always-on rebuilds exactly on
schedule.

`AUTO_BUILD_TICK_SECONDS` sets how often it looks for due cycles (60 by
default); `0` switches the timer off entirely. Running several workers is safe:
a cycle is claimed with a conditional update before it is built, so only one
worker builds it.

### Before it faces the internet

- Set a real `JWT_SECRET` and remove every seeded account.
- Serve over HTTPS. Tokens are in `sessionStorage`; plain HTTP leaks them.
- Switch `DATABASE_URL` to Postgres and set up backups.
- Set `CORS_ORIGINS` to your real domain only.

---

## Layout

```
backend/
  app/
    main.py       FastAPI app, auth, all routes
    models.py     Tables, and the constraints that carry the guarantees
    matching.py   Fingerprints, fuzzy merge, skills overlap, cover and split
    dashboard.py  Progress figures — read-only queries, no writes anywhere
    interviews.py The diary, the ladder and the funnel — read-only too
    assessments.py Take-homes and their deadlines — read-only too
    ingest.py     Spreadsheet reading and column auto-detection
    exports.py    Excel output — dispatched lists, the cycle report, the pipeline
    schema.py     The v1 -> v2 upgrade, and the columns added since
  schema.sql      The whole Postgres schema, for review or for Supabase
  seed.py         First accounts, profiles, developers and the sample data
  test_matching.py, test_e2e.py, test_dashboard.py, test_developer.py,
  test_pipeline.py

frontend/
  src/
    App.jsx       Shell and role routing
    api.js        Fetch wrapper, token handling, downloads
    views/
      Login.jsx            Sign in
      PersonDashboard.jsx  One person's progress — the screen itself
      Dashboard.jsx        Fetches it for the person whose it is
      ManagerDashboard.jsx The workspace, each person, and the two switches
      BdHome.jsx           Logging jobs and working the list
      DevHome.jsx          A developer's day — the diary and their record
      DevProfiles.jsx      What a client is handed, kept by the developer
      Interviews.jsx       Scheduling and the diary — one component, three screens
      JobRecord.jsx        Every job ever applied for, searched, and the
                           interview started from a row
      Assessments.jsx      Take-homes: set on one side, done on the other
      AdminHome.jsx        Running cycles
      People.jsx           People, profiles, developers, and who is on the board
      shell.jsx            Toasts, the command palette and the theme — the
                           parts that outlive whichever screen is mounted
      widgets.jsx          Tiles, sparklines, the board, the funnel, the stage
                           ladder, the stalled list, the take-home board and
                           the between-two-dates report
    styles.css             The design system: one neutral ramp, four semantic
                           families, and every component this app uses
```

`dashboard.py` and `interviews.py` never write. A dashboard can be opened while
the timer is halfway through rebuilding a cycle without disturbing it.

Every interview timestamp is stored UTC and converted exactly once, in
`models.working_label`, which hands the browser the day, the time, a label and
the value a `datetime-local` input wants back. Nothing in the browser does date
arithmetic, so there is no second implementation of "what day is that" to drift
away from the first.

`PersonDashboard.jsx` is rendered by both the person it belongs to and the
manager looking at them — same component, same payload, one `viewingAs` prop
that changes "your list" to "Ali's list" and removes the buttons that would put
a manager inside somebody else's work. There is no second, approximate copy of
that screen to drift out of step with the real one.

All the dispatch logic lives in `matching.py` with no database or framework
imports, so you can change a rule and see the effect from the unit tests in
under a second.

### Tuning the matcher

In `matching.py`:

- `_ID_RULES` — add a pattern when you start using a new job board. This is the
  highest-value change; a native ID beats every other tier. The third element of
  each rule says whether the ID is only unique *within one site*: leave it `True`
  unless the board mints IDs that are unique across the whole internet, because a
  `False` there silently fuses jobs from unrelated boards.
- `fuzzy_merge(threshold=88, client_threshold=82)` — lower these to catch more
  reposts at the risk of fusing genuinely different jobs. Raise them if you see
  distinct jobs being merged.
- `_SUFFIX` — company-name noise words to ignore.

Change any of them, then run `pytest test_matching.py` to see what moved.
