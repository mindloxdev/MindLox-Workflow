# Dispatch

Your team hands in the sheet of jobs each profile applied to. The system works
out which postings are the same job across every sheet, shows you how much
effort was spent twice, and gives each profile back the jobs it has never tried
within the same headline market.

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
Profiles with different headlines are kept in separate dispatch markets: a VA
profile receives VA others' jobs, while an Accounts Receivable profile receives
Accounts Receivable others' jobs.

---

## The words this uses

One name per thing, on every screen, whoever is looking. A manager, a BD and a
developer reading the same number have to read the same word for it, or they
are not discussing the same number.

| Word | What it counts |
|---|---|
| **Own jobs** | Jobs somebody went out and found on their own sheet, and applied for. |
| **Others' jobs** | Jobs a colleague found, that the cycle handed over, and this profile then applied for. |
| **Applied this cycle** | Own jobs + others' jobs. The week's work, whole. All-time and per-client counts of the same thing stay **applications sent** — they are not this cycle's. |
| **Applied** | Marked as gone out. |
| **Skipped** | Looked at and said no to, with a reason. Never offered to that profile again. Never called "turned down". |
| **Still to do** | Handed over and not yet answered either way. Comes back next cycle. |
| **Found twice** | A posting two profiles both went out and found. The second search was time spent for nothing. |
| **Cycle** | One dispatch: everybody hands in, the lists are built, the team works them. Never a "round" and never a "batch" — `batches` is a table name, not a word anybody reads. |
| **Round** | One conversation in an interview ladder. Only ever that. |
| **Cycle clock** | A countdown the manager sets on a cycle. Every BD sees the same one; it changes nothing when it ends. |
| **Assessment** | The exercise a client sets and the developer does. Never a "test" and never a "take-home" — it was going under all three at once. |

Nothing on a screen is named after the column it is stored in. The database
still says `logged`, `assigned` and `done_pct`; a person reading the app never
sees any of the three. The mapping lives at the top of
`frontend/src/views/widgets.jsx` so the next person changing a label can see
what the words already mean.

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

### A link to the client's own email

Optional, on an interview and on an assessment. The meeting link is where to be at two
o'clock; this is what the client actually asked for, and three weeks later it is
the only place their words still exist. A separate field on purpose — storing
one in the other means whoever needs the wording opens a dead meeting room.

It can be added at any of four moments: booking the interview, pressing **they
replied** on the job record (the cheapest moment there will ever be, since the
BD is reading the reply at that instant), recording an assessment, or afterwards in the
**notes** drawer on any row. Either side can add it: a reply gets booked in ten
seconds off a phone and the thread gets pasted in later, from a desk.

Two defaults, both overridable. The **next round keeps the thread of the round
it follows**, because it is the same conversation with the same client. A
**assessment takes the thread off the call that produced it**. Both appear beside the
meeting link as *their email* rather than a second anonymous *open* — the two
links go to completely different places, and picking the wrong one at two
o'clock costs a meeting. The pipeline download carries a **Client email**
column.

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
assessment is a place a candidate is *at* — the client is not talking to anyone
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

| Job title | Company | Job link | Description link | Platform | Applied on |
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

Called **assessments** on every screen. The app had been using three words —
assessment, take-home, test — for one thing, which on the glossary's own rule
is three different things to anybody reading two screens. `assessments` is the
table as well, so the word a person reads and the word the store uses agree.

The third thing a client can ask for, after a reply and a call, and the one
that costs a developer a weekend.

Same shape as an interview and split the same way. The BD sets it — the client
sent them the brief, the link and the deadline. The developer does it, and says
how far along they are and what went back. Either may write either half.

    sent -> in progress -> submitted -> passed / did not pass

It does not need an interview to exist first. Plenty of clients screen with a
assessment before anybody speaks, and one that could only hang off a call
would force somebody to invent a call that never happened. When it *did* come
out of a round, it links back to it and reads as "after the technical round".

It carries the same posting an interview does — the six fields above, worked
out the same way, including that profile's own **applied on** date. Name a call
on the form and the posting comes across with it, because the call already
knows which one; leave the call blank and the same job search offers it
directly. An assessment and the conversation that produced it are one thing, and
two screens describing it differently is worse than neither of them saying.

**No deadline is a real answer**, and the commonest one after "next Friday". It
stays empty rather than becoming today, because an invented deadline is a red
flag on somebody's screen that nobody set. One that *is* set and passes turns
the row over — but only while it is still open. An assessment submitted late is a
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
  assessment the assessment *is* the state of that conversation, and having to open a
  second tab to find out whether you are waiting on the client or on your own
  developer is how a week goes past;
- on the **developer board**, as a column. "Free on Thursday" is not free when
  an assessment is due Friday, and a manager reading availability off the diary alone
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
assessment with its deadline and what went back. It is scoped exactly like the
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

3. **The pool is built** from this cycle's sheets, and nothing else. A cycle
   hands out the work it gathered.

   Untouched jobs used to be dragged forward out of earlier cycles as well, so
   that a job somebody ran out of time for did not fall through the cracks.
   With one cycle open that reads well. With two open at once it was the bug the
   BDs reported: the newer cycle gathered 79 postings and its lists came out
   holding 359 places, 190 of them dragged out of the older cycle and 183 of
   those never touched. "Others' jobs" was mostly last fortnight's leftovers,
   and a cycle's figures counted work it never gathered. Both cycles rebuild on
   the same timer, so each build pulled the other's untouched rows onto its own
   lists and deleted them from the first — one job moving between two cycles
   every five minutes.

   Nothing is lost by leaving them out. The row stays on the cycle that
   dispatched it, that cycle stays in the **Cycle** picker whether it is open or
   closed, and while it is open its own timer keeps re-offering it.

4. **The lists rebuild themselves.** A cycle stays open while the team works it.
   Every few minutes — you pick 5, 10, 15 or 30 when opening it — the server
   rebuilds every open cycle that has at least two sheets in it. Nobody presses
   anything: a job Ali logs at two o'clock is off the other profiles' lists by
   ten past.

   Rebuilding never disturbs work already done. Jobs a profile has marked
   **applied** or **skipped** keep their place and their status; only the
   untouched rows are recalculated. Closing the cycle is what stops the timer.

5. **Each profile is given what it has not used.** Jobs are first restricted to
  profiles with the same headline as the profile(s) that found them. Two modes,
  chosen when you
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
**applied** or **skipped**. Anything left as *to do* stays on the cycle that
handed it over, and that cycle keeps offering it while it is open — it does not
follow the profile into the next one.

A profile is also never handed a job already waiting on one of its other lists.
That is not history — nothing has been done with it yet — but two rows for one
application is work counted twice, and with two cycles open it is the other half
of the job that hopped between them.

A **skipped** job also leaves the list the instant it is marked. There is
nothing further to do about a posting this profile has skipped, and it is
never offered again — so a greyed-out row that can only be scrolled past is not
worth the space. The mark itself is kept underneath, because that row is what
stops the job coming back. Downloads keep every row, skipped included: a
download is the record of what the cycle dispatched, not a list of things to do.

Every job on a list also says **who found it** and **when it was found** — the
stamp off the sheet of whoever put it into the pool, falling back to when the
posting first entered the system. That column used to read this profile's own
*applied on*, which is empty on every row of that list by definition: a job is
on it precisely because this profile has not applied. It showed a dash on every
row for as long as the screen existed. What a BD wants before opening a link is
how old the posting is, and now that is what it says.

A run of jobs from one colleague's profile that are all wrong for yours is a
fixable thing — but only
if you can see whose search they came from. Press one of those names and the
list narrows to everything that profile found, because reading "found by
Faizan" on a single row is a curiosity while seeing the whole run of them
together is what tells you whether to trust the next twenty. The same box
filters by client, title, platform or link, and the download carries the tag
too — a file somebody works through on a train should not be a worse document
than the screen it came from.

### The same job, arriving on a different link

A profile is never handed a posting it has already used — applied for at any
time, or skipped. That was blocked on the *row*, and the row was not
enough.

One posting reaches this system by several routes. A colleague browsing pastes
the listing; a colleague who actually applied pastes whatever the apply button
left in the address bar. Workday appends `/apply/autofillWithResume`, iCIMS
appends `/job`, most others append `/apply`. Those are different URLs, so they
fingerprint differently, so the posting arrived as a fresh row with no history
against it — and the cycle handed somebody work they had already done, or a job
they had already skipped.

So the block reads the **posting**, using the fingerprint's own ladder with one
rung widened:

| The link says | What identifies the posting |
|---|---|
| A platform ID (Upwork, LinkedIn, Indeed) | The ID, untouched. Those already survive every link variant that site can produce. |
| A plain URL | The URL with the apply-flow tail stripped off the end. |
| No link at all | Client + title, exactly as the L3 fingerprint does. |

Deliberately narrow, and narrow the hard way. An earlier version used client +
title for *every* row: on the sample sheets it held back **52 of 70 jobs**,
because one application for "AR Specialist at Northwind" buried every other AR
Specialist role at that client. A version after that cut the URL on depth
instead, which read `ovationhealthcare…/en-US/ovationhealthcare` as the identity
and collapsed every job at that employer into one. `job` and `jobs` are only
ever stripped when they are the very last segment, because they sit in the
middle of nearly every careers URL there is.

**What it still does not catch.** A posting mirrored on a job board *and* the
client's own careers site has two unrelated URLs and stays two rows, so it can
be handed over twice. Merging those would mean going back to client + title,
which costs more than it saves. They are counted, at least: both show up under
**found twice**.

### The same client, spelled two ways

`matching.client_key` is the normalised company name and nothing else — the same
rule `jobs.company_key` is already built from, so "Northwind Health, Inc." and
"northwind health" are one client wherever they are read. There is no clients
table and there is not going to be one: a company is a name somebody typed on a
sheet, and the moment identity lives in a row somebody has to maintain it.

Deliberately not fuzzy. The fuzzy tier above only ever collapses two rows when
the client *and* the title are both close; loosening that to the client alone
would quietly fuse two companies' whole histories, which on a screen a manager
reads before an account call is the worst thing this could do.

### Profiles that have not handed anything in

A cycle opens, two profiles report in, and a third selling the same skills has
logged nothing yet — because they are new, or were away, or have not got to it.
Leaving them out means the profile with the most spare capacity is the one
handed no work, which is backwards. So they join as recipients: they receive
the pool without having fed it, and their own history still blocks anything
they have already applied to. A late joiner is given jobs, not given away.

Profiles that have not handed anything in are still found by **skills**, then
receive only jobs whose headline matches their own. Two guards keep it from
being a free-for-all:

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

Every role lands on a screen that opens with the same thing: **one list of what
will not fix itself**, hardest first, each row carrying the button that deals
with it.

Each of these screens had grown its own stack of coloured banners, in whatever
order the code happened to check them. A BD could have an interview starting in
forty minutes sitting underneath a note about a spreadsheet, and a developer's
one irreplaceable job — saying how the interview actually went — was a tile in a
row of six. There is one list now, and every item obeys three rules:

1. It says what is wrong in a sentence somebody would say out loud, with the
   number inside the sentence rather than floating beside it.
2. It says why it matters. *3 replies waiting* is a fact; *three clients are
   waiting on us* is a reason to move.
3. It carries the button that fixes it. A screen that reports a problem without
   a route to it is a dead end.

Urgency is a word as well as a colour — **Do this now**, **Worth chasing**,
**Happening today**, **When you can** — so the order survives a phone in
sunlight and every common kind of colour blindness.

### Yours

Once your manager has opened it for you. It leads on the one number worth acting
on — others' jobs still sitting unworked on your list — with the button that
takes you to them.

Then four figures, not the ten that used to be there, four of which needed a
tooltip to be read at all: **applications sent** this cycle, how many of those
were **others' jobs**, how many were **also found by somebody else**, and how
many **clients wanted to talk**. Each says which window it counts over, because
two of them are this cycle and two are all-time and nothing in the words says
which. The rest — what was handed over, what was skipped, how far through
the list you are, the streak, today's interviews, assessments outstanding — sits under
them in one quiet row, because none of those is worth a headline on its own.

Below that: what the applications turned into, any conversation that cleared a
cycle and then stopped, the assessments clients set, and a fortnight of daily
activity. **Break it down by profile** folds the per-profile cards away, since
most mornings the total is the answer and a row of cards between the figures and
the diary is just distance.

The **found twice** count is the one to read twice. If ten of the thirty jobs
you found were already on somebody else's sheet, your search and theirs are
covering the same ground, and that is fixable at the source in a way no amount
of dispatching can match.

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

Their list opens on **what only you can do**, because that is literally true.
A developer was in the room; until they say how it went, the answer does not
exist anywhere for anybody to find. It used to be a tile in a row of six and a
paragraph halfway down the page.

Then their own record, in four figures rather than six: interviews to turn up to
in the next seven days, interviews **with no result recorded** — which reads as
*nothing is owed* when it is zero rather than as an accusation — applications
sent in their name, and offers. They are entitled to that. It is their name on
every one of those applications. Alongside it, the assessments sitting on their week
and any conversation that cleared a round and then stopped — the one thing on that screen they can fix in a single press.

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

Written for somebody who does not use the rest of the app and should not have to
learn its vocabulary to read it.

**What needs you.** The list, hardest first: clients waiting on a time, assessments
past a deadline, sheets not handed in, interviews today, conversations that went
quiet, results nobody recorded.

**One line each.** The title already says what is wrong and how many; *why it
matters* opens when somebody presses the row. Six of these with a paragraph
apiece was the screenful that pushed everything else below the fold.

**The four numbers.** Applied this cycle, how many of those came off a
colleague's sheet, and — all-time, because a reply lands weeks after the
application that earned it — clients who wanted to talk and offers of work. Nine
tiles were a wall the eye slid off, and the ones that mattered were in the
middle of it. Each card says which window it counts over, and what the four
*mean* is one press underneath rather than a paragraph inside every card.

**What the applications turned into.** Applications, interviews, offers, hires,
drawn as bars on one shared scale. Four boxes with arrows between them hid the
only thing worth seeing — the drop. A thousand applications and seventy
interviews look identical when each is a number in its own box. One colour: the
length is the measurement, and every bar is labelled with its own name, number
and rate, so nothing depends on telling hues apart.

**Effort spent twice.** Said as typing rather than as a percentage. *94 jobs
were typed in twice* is a morning somebody spent twice; *18%* is a statistic.
With the trend beside it, cycle by cycle — the number this whole tool exists to
bring down, and the only place you can see whether it is going down.

**How each person is doing.** One row per person, everything they run added
together. Five columns, not nine: who, how much went out, how far through their
handed-over work they are, and when they last did any. The rest — own jobs,
others' jobs, found twice, sheets in, and the switch that decides whether they
can see their own figures — opens on that row.

Two targets per row, never one doing two jobs: the **name** opens their screen,
the **chevron** opens their numbers. A row that did both would navigate away
from somebody trying to read it. It opens on **today**, because the question a manager walks in with is
"has the team started", and a cycle-to-date total answers that identically on a
busy Monday and a dead one. A **This cycle** switch sits beside the heading, and
dates typed into the filter take over from both — somebody who has just asked
for 1–15 September did not mean today. Only that table follows the switch:
narrowing the four numbers, the drop and the duplication to one morning would
make every one of them read as a bad week.

The columns add up. **Applied this cycle** is everything they applied for, and
the two columns after it are that same number split — **own jobs** and
**others' jobs**. They used not to: the column counted only jobs off a
colleague's sheet while the same words at the top of the page meant everything,
so a headline of 224 sat over a column summing to 52.

Developers are not on this table. A row of zeros against a developer's name says
nothing except that they are a developer, and they have their own section. A
*BD* with no profile stays, and is named underneath — that is somebody who
cannot do their job.

**Opening somebody takes you to their screen.** Their name as the heading, a
back link at the top, their dashboard exactly as they see it, and the switch
that decides whether they can see it. It used to be appended underneath, which
meant a manager pressed a row and nothing appeared to happen — what they had
asked for was a screenful further down, past the table they had just used. The
same is true of a profile from **every profile** and of **Open** on a developer.
It scrolls to the top on the way in and back to the row you pressed on the way
out, and the cycle, the dates and the Today/This cycle switch are as you left
them.

**Everything else starts closed.** What the applications turned into, effort
spent twice, the day-by-day strip, interviews and assessments, the developers, every
profile separately, and who may see whose figures — each its own section, each
opening when somebody asks for it. A manager who opens this screen once a
morning should be finished before any of them, and the things they came for stop
being findable if six tables sit under them.

**A closed section carries the number it is worth opening for** — *1 offer*,
*48*, *3 developers*. That is the difference between progressive disclosure and
hidden information: "there are two things in here", not "there might be
something in here".

Each header is a real button with `aria-expanded` and `aria-controls`, and the
panel carries `hidden` rather than a class that merely hides it — so a closed
section is out of the tab order and out of the accessibility tree, not sitting
there invisible for anybody using a screen reader.

Two of those sections are worth calling out:

- **Conversations that stalled.** Cleared a round, nothing booked after it.
  Read-only from here on purpose: whoever runs that profile books the next
  round, and their screen is one click away — a manager quietly booking into
  somebody else's client relationship is how one reply becomes two
  conversations.
- **The developers.** Who is behind each profile, whether they could start on
  Monday, what is in their diary, and how many assessments are sitting on them.
  **Open** is that developer's own screen, and outcomes can be recorded from it
  — the person chasing them is usually the one looking.

### Clients

Every other screen is organised by profile, by person or by cycle. None of them
answers the question a manager is actually asked on the phone: **have we been to
Northwind before, and how did it go.**

Nothing here is a new source of truth. It is the same postings, conversations
and assessments, grouped by the company instead of by the person who typed them, with
one small table for the manager's own annotations.

**Status is derived, never typed.** A status somebody sets by hand is a status
somebody forgets to change, and the screen then says a client is live three
months after they said no. Every rule reads a row somebody already had to write
for a different reason:

| Status | How it is derived |
|---|---|
| Hired | An outcome of hired |
| Offer | An outcome of offer, no hire |
| Assessment out | An open assessment, whatever the interviews say |
| Stalled | Cleared a round with nothing booked after |
| In conversation | Booked or held, not settled either way |
| Replied, no time agreed | A reply started from the job record, no time on it |
| Closed | The last recorded outcome is a no |
| Approached | Applications exist, no reply |

A client sits in exactly one column, the furthest up that ladder — except that
**Assessment out** and **Stalled** beat **In conversation**, because those two are
waiting on somebody here. A client at "in conversation" is fine; a client
sitting on an unanswered assessment is not, and filing them together hides the only
one worth acting on. **Closed** sits *below* the live states rather than above
them: a client who said no in March and is talking again in September is talking
again.

A cancelled interview is never a rejection, and an interview nobody has reported
on is not a loss. Both rules already exist in the funnel and are called rather
than restated.

**A table by default, a board on a switch.** A board is easier to turn round and
show somebody; a table is easier to read on a Monday, which is what this screen
is mostly for.

**Opening a row opens the client**, on its own page, the same way opening a
person does from the team table. Inside: the conversations as one block per
chain rather than one row per sitting, the meeting link and *their email* named
separately, the brief and the debrief side by side; the assessments and their
deadlines; every posting ever applied to there, which is the answer to *have we
been here before*; and what was found twice, because a run of those at one
company is a search problem rather than a dispatch problem.

**The annotation is advisory and says so.** A priority flag, an *already being
worked* flag and a free-text note. None of it filters the pool, skips anything
or changes what dispatch hands out — a flag that quietly held jobs back would be
a rule whose effect nobody could see, and the reason for a missing job would be
invisible on the screen it went missing from. So it is surfaced instead: a BD
logging a job at a flagged client is told in the dialog they already get as they
type a link, with the same way past it.

The note is keyed on the derived client key and carries the spelling last seen,
so it outlives the last posting at that client being withdrawn — which is
exactly when somebody most wants to read *approached in March, went quiet*.

**Manager only, checked on the server.** The tab being absent for everybody else
is a courtesy; the `403` is the control.

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

The manager presses somebody's row under **how each person is doing** and is
taken to that person's screen — the real one, the same component fed the same
payload, so what you check before opening it is exactly what they will get. The
switch to hand it over sits at the top of it, beside their name. It is also in
the **Own figures** column of the team table, and in the **Dashboard** column of
**People and profiles**, for when you already know.

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

`backend/.env` is read by `app/__init__.py` on startup, before anything in the
package looks at the environment — so `DATABASE_URL`, `JWT_SECRET` and
`CORS_ORIGINS` all come from that one file and there is nothing to export by
hand. A real environment variable beats a line in the file, which is what keeps
`DATABASE_URL=… pytest` and every hosted deployment working unchanged.

`.env` is in `.gitignore`; `.env.example` is the copy that is committed. Keep
real credentials out of the example.

### Pointing it at Postgres

Put the connection string in `backend/.env` and restart. Nothing else changes —
the tables, the upgrade in `schema.py` and the partial unique index that carries
split mode are all created on first start.

```ini
# Neon, Supabase, Render, Heroku — paste the string exactly as they give it
DATABASE_URL=postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

`postgres://` and `postgresql://` are both rewritten to `postgresql+psycopg2://`
in `app/main.py`, because SQLAlchemy 2 rejects the first and no host mentions it.
Connections are pre-pinged and recycled every five minutes, so a pooler that
drops an idle connection between rebuilds costs nothing.

Check it took:

```bash
python -c "from app.main import engine; print(engine.dialect.name, engine.url.host)"
curl http://localhost:8000/api/health
```

The first says `postgresql` and your host; a reply of `sqlite` and `None` means
the `.env` is not where the app is looking — it belongs next to `seed.py`, in
`backend/`, not in the repository root.

**On a database the team is already using, `seed.py` is not the way in.** It
only ever adds what is missing, but it adds sample accounts and sample sheets
to a real workspace. Use `ADMIN_EMAIL` / `ADMIN_PASSWORD` instead, which create
one manager on an empty database and do nothing on a database that already has
one — see [Deploying](#deploying).

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
pytest test_matching.py -v      # the identity rules: fingerprints, the apply
                                # stem, fuzzy merge, both dispatch modes
pytest test_e2e.py -v -s        # full round trip, prints the report
pytest test_dashboard.py -v     # the figures, and who may see whose
pytest test_developer.py -v     # the developer side: the clock, the clash, the funnel
pytest test_pipeline.py -v      # the record, the ladder, assessments, skill joins
pytest test_crm.py -v           # clients: the key, the derived status, permission
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
used, one person's two profiles do not restrict each other, unworked jobs stay
on the cycle that dispatched them rather than following the profile forward,
split cycles keep every job to one profile,
rebuilding gives the same answer, one cycle's report never counts another's, and
nothing a spreadsheet can contain becomes a live link or an Excel formula on a
colleague's machine.

It is also the test that catches an over-eager matcher. Both attempts at the
posting rule that were too broad showed up here first, as `Khuram 18, Zahid 0`
against the expected `40` and `20` — the arithmetic in **The idea in one
example** is checkable by hand precisely so that a rule which quietly stops
dispatching work cannot pass.

---

## Logging a job

### The link is checked as you type it

The job link is the first thing pasted into a row and the field that identifies
a posting, so it is the first moment anybody can be told they are about to log
something twice. On leaving the link cell the server is asked, and answers on
the **fingerprint** rather than the text — the same job pasted with a tracking
parameter, through a referral link, or with the protocol typed differently
still comes back as the same job.

Two different answers, and they are not the same kind of thing:

| What came back | What it means |
|---|---|
| **Duplicate entry found** | *This* profile already applied, and the date it did. One identity approaching one client twice, which is the thing the whole product exists to prevent. |
| **Somebody else has applied to this** | A colleague's profile holds it. Not a duplicate at all — a different profile is a different candidate, which is the point of running several — but worth knowing before spending the time. |

It arrives as a dialog over the page, not a line above the table — a banner in a
scrolling grid is missed exactly when it matters, because the BD has already
moved to the next cell. Either way the row is yours to keep: **Ignore — keep
this row** files it anyway (Enter, or Escape, does the same), and the answer is
remembered for that link so you are not asked twice.

### Nothing saves until you say so

Every cell used to write to the server on blur, so a half-typed row was already
the sheet and a row abandoned mid-thought stayed in it. A row is now committed
when you press **+ New entry** to start the next one, **Save now**, or Enter on
the last row. Until then the screen says *Not saved yet* and closing the tab
warns you.

### A skip has to say why

Marking a job **skipped** retires it from that profile for good — no later cycle
offers it again — so it is the one status change that asks a question first. The
reason lands in `assignments.skip_reason` and appears on the manager's cycle
report under **Turned down, and why**.

Read together rather than one at a time: a run of *wrong seniority* against one
profile is usually something about the searches feeding it, not about the
postings.

### A skip belongs to the profile, and can cover all of them

Skipping a job is scoped to the profile it was skipped under. Two
profiles are two candidates in two markets: a posting wrong for an Accounts
Receivable identity is often exactly right for a Customer Service one, and
blocking both would destroy work.

That is right, and it is also how a BD running two names came to report the
skip as broken. They turned a job down under one name and met it again the
following week under the other — more often than they were skipping, on a
simulated fortnight of a real-sized team.

Half the reasons people skip are about the *fit*: wrong seniority, wrong
market. The other half are about the *job*: the rate, on-site only, a client
already being worked. Those apply to every name. So the dialog asks, once:

> **Turn it down for all 2 profiles I run**
> Leave this off when the job is simply wrong for **Khuram** — it may suit one
> of your other names. Tick it when the reason is about the job itself.

Off by default. Ticked, the posting is gone from every name that person applies
under and does not come back. Two guards: it never overwrites a profile that
has already **applied** — that is work, not a rejection — and it only records
against profiles actually taking part in that cycle, because writing a skip
against a dormant profile would tell a manager it skipped a job it was
never offered.

And when it *is* only per-profile, the other list says so instead of looking
broken:

> **Senior AR Specialist** — *you turned this down under Khuram*

### Correcting a posting, and withdrawing an entry

Both live on **All jobs**, on the row itself.

**edit** rewrites the posting — title, client, platform, either link. There is
one job row, so the correction reaches every profile holding it, the others'
jobs lists included, straight away. Correcting the same fields **on your own sheet**
does the same thing, and only for fields you actually changed: comparing the
sheet against the job instead would make every save an assertion about every
field, so re-saving an untouched sheet would stamp its old wording back over a
colleague's correction. It is offered only to whoever *found* the job:
somebody who typed it onto their own sheet, or whose imported history carries
it. Being dispatched a job and marking it applied does not make it yours to
rewrite. Two BDs who both typed the same posting in both found it, and both
may correct it.

Correcting the link re-identifies the job, which is usually the point — a link
typed wrongly is exactly what splits one posting into two. If the corrected
link turns out to be a posting already recorded separately the edit is refused
rather than merging them, because fusing two job rows would take two profiles'
histories with it.

**delete** takes the entry out, properly. A withdrawn job used to hide in four
places, and leaving any one of them put it back on screen — so all four go: the
row on the profile's sheet (otherwise the next automatic rebuild re-reads it and
files the application again, ten minutes later), the per-cycle record, the
dispatched row on the list, and the all-time application.

The posting itself goes too, **unless** somebody else is still holding it:

| Still there | What happens |
|---|---|
| Another profile applied to it | Kept. Their record is not this person's to delete. |
| A client replied — an interview or assessment | Kept. A reply is the rarest row in the system and outlives the application that earned it. |
| Only other people's *to-do* rows | Deleted, and those rows with it. An assignment is a suggestion the build produced, not work — it existed only because somebody found the job. |

The same **delete** sits on each row of **Own jobs**. A row that has been through
a build is a job in the record as well as a line on the sheet, so it is deleted
from both; a row that has never been built is simply dropped.

---

## Loading history from the old spreadsheets

Before the app, the team kept one tab per BD in a single workbook. `import_old_sheets.py`
loads those into the database as history:

```bash
cd backend
python import_old_sheets.py "../Old Apply sheets.xlsx"            # dry run, writes nothing
python import_old_sheets.py "../Old Apply sheets.xlsx" --commit   # apply it
```

It writes `jobs` and `applications` with **no batch**. The old sheets are not a
dispatch cycle and filing them as one would put months-old work into a cycle's
report and everybody's duplication figures. What it buys is the thing the sheets
are for: `applications` is the all-time record, and cover mode only dispatches a
job to a profile that has never applied to it, so loading the history is what
stops the team being handed a posting they already worked in July.

**Which profile a row goes to.** Every BD runs two identities — an Accounts
Receivable one and a Customer Service (VA) one — and the sheets record both in
one tab with a **VA jobs** column ticked on the VA rows. Ticked goes to the VA
profile, blank to the AR profile. Sidra's two tabs are both VA identities in
their own right, so each goes to its own profile whole.

That reading is checked rather than assumed: splitting each sheet on the column
and counting title words gives *patient / customer / service / care / access /
support* on the ticked side and *billing / revenue / cycle / accounts /
receivable / claims* on the blank side, in every sheet — which is exactly the
two headlines those profiles carry.

**Dates.** Excel decided for itself how to read what the team typed and on 842
rows read a day-first date month-first — "10/07/2026" was the 10th of July and
became the 7th of October. They are recognisable without guessing, because they
land in the future and these are sheets of work already done. Every one becomes
a real past date when the numbers change places, so the importer swaps them and
leaves alone anything that does not survive the swap.

**Running it twice is safe.** `applications` is UNIQUE(job_id, profile_id) and
jobs are looked up by fingerprint before being created, so a second run inserts
nothing. That is what makes the dry run worth trusting — the counts it prints
are what a real run would write.

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
4. Each BD signs in and picks the name they are applying under. The tabs:
   - **Own jobs** — what they went out and found themselves. Either *Add
     manually*, which gives a table where every **+ New entry** adds a row
     stamped with the current Eastern time, or *Upload a sheet* for anyone who
     already keeps a spreadsheet. Any column layout works; the mapper guesses
     and they can correct it.
   - **Others' jobs** — what a colleague found and this profile has never
     applied to, refreshed as the lists rebuild.
   - **All jobs** — everything ever applied for, searchable.
   - **Interviews** — replies that turned into conversations, and the outcomes.
   - **Assessments** — what clients set, and how far along each is.
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
7b. If the client sends an assessment, record it under **Assessments** with whatever
   deadline they gave — or none, if they gave none. The developer picks it up
   there, and anything still open past its deadline is called out on both
   screens.
8. **Close cycle** when the cycle is done. That stops the rebuilds and stops
   accepting sheets. Reopen it if you closed too early. Interviews are not
   attached to a cycle and are unaffected: a reply that arrives three weeks
   late belongs to the work that earned it.

### The cycle clock

**Clock on this cycle**, on the manager's screen, sets a countdown for the whole
team — *give this cycle 120 minutes*, or one of the presets. It starts the
moment you set it, and every BD working that cycle sees the same number ticking
down beside their cycle picker. **Add 15 min** and **Take 15 min** move the
window without restarting it, so a clock that has been running an hour has still
been running an hour when you give them twenty minutes more.

**Nothing happens when it reaches zero.** The cycle stays open, sheets still go
in, jobs are still marked, the lists still rebuild. The clock simply leaves the
BD's screen. That is deliberate: a clock that locked people out would cost the
team real work to make a point about timekeeping, and the point is only ever
worth *knowing*.

What it is for is the table underneath it — **what the window caught**, per
profile:

| Column | What it counts |
|---|---|
| Own jobs | Jobs that profile logged on its own sheet inside the window |
| Others' jobs applied for | Rows off a colleague's sheet marked applied inside the window |
| Others' jobs skipped | Rows skipped inside the window, with a reason |
| Left | Still untouched when the time ran out |
| Late | Marked after the whistle — counted, not hidden |
| Done | Applied + skipped, as a share of everything handed to that profile |

Every figure is dated by when somebody actually marked something, so it says
what was done *between* the clock starting and the time running out — not what
the cycle holds in total, which the report above it already says. **Late** is
counted separately because a profile that finished everything twenty minutes
over is a different story from one that stopped, and folding the two together
would tell you the wrong one.

The seconds left are counted on the server and sent to the browser, so a laptop
whose own clock is twenty minutes fast does not show its owner twenty minutes
less time than everybody else.

**Clear** takes the clock away, and the window it measured goes with it. Simply
running out of time does not: the cycle keeps its window so these figures still
have one to report on.

Sheets can be any of `.xlsx`, `.xls`, `.csv`, `.tsv`. The mapper reads job link,
job title, company, job description link, platform, applied on and optional
headline columns; everything else is ignored. Manual entry always shows a
Headline is shown automatically from the active profile and cannot be changed
per row. Each job is dispatched only to profiles with the same headline, so VA
work stays with VA profiles and Accounts Receivable work stays with Accounts
Receivable profiles.

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
not used", never fresh leads. Headline markets keep unrelated specialisms
separate; skills are used only to identify profiles that may join a cycle when
they have not handed in a sheet.

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

Version 2.6 added the reason a job was skipped, and the count of rows on a
sheet the matcher can actually use. The second is backfilled on first start
rather than left at zero, because a zero there reads as *handed in nothing* on
the manager's screen, which is worse than the mismatch it was fixing.

Version 2.7 added the link to the client's own email, on both `interviews` and
`assessments`. One nullable column each, empty on every row already recorded,
which is the truth: nobody was asked for it at the time.

It also **repairs blank platforms**, once. `build_lists` used to set a job's
platform only at the moment it created the row and never afterwards, so a
posting first built from a sheet whose Platform column had not been mapped yet
— or from the one colleague who left the cell blank — kept an empty platform for
good and read as a dash on every screen, with the board named on a sheet all
along. The build fills the gap on every pass now; the jobs already stranded are
repaired on first start from the sheets that named them. Only blanks are
touched, so a correction made by hand is never overwritten, and running it twice
does nothing the second time.

Version 2.8 added the client screen. One new table, `client_notes`, which
`create_all` makes on its own — nothing to migrate and nothing to backfill,
because the clients themselves are derived from the company names already on
`jobs` and were never stored.

Version 2.9 gave a cycle a clock. Two columns on `batches`, and a cycle that
predates them has `timer_minutes` 0 — which reads as *nobody set a clock on this
one*, and no screen shows anything.

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
- Keep the production connection string out of a working copy that runs the
  tests. `conftest.py` clears `DATABASE_URL` before pytest collects anything,
  so the suite always builds its own throwaway SQLite file — but a stray script
  that imports `app` and then writes is answerable to whatever `.env` names.

---

## Layout

```
backend/
  app/
    main.py       FastAPI app, auth, all routes
    models.py     Tables, and the constraints that carry the guarantees
    matching.py   Fingerprints, fuzzy merge, skills overlap, cover and split
    crm.py        The client account view — read-only, one pass over the lot
    dashboard.py  Progress figures — read-only queries, no writes anywhere
    interviews.py The diary, the ladder and the funnel — read-only too
    assessments.py Assessments and their deadlines — read-only too
    ingest.py     Spreadsheet reading and column auto-detection
    exports.py    Excel output — dispatched lists, the cycle report, the pipeline
    schema.py     The v1 -> v2 upgrade, and the columns added since
    __init__.py   Reads backend/.env, before anything else reads the environment
  .env            Your configuration. Not in git
  conftest.py     Clears DATABASE_URL so the tests never touch a real database
  schema.sql      The whole Postgres schema, for review or for Supabase
  seed.py         First accounts, profiles, developers and the sample data
  import_old_sheets.py  The team's pre-app spreadsheets, loaded as history
  test_matching.py, test_e2e.py, test_dashboard.py, test_developer.py,
  test_pipeline.py, test_crm.py     233 tests in all

frontend/
  src/
    App.jsx       Shell and role routing
    api.js        Fetch wrapper, token handling, downloads
    views/
      Login.jsx            Sign in
      Todo.jsx             The one action list every screen opens with, and
                           the BD's and the developer's versions of it
      PersonDashboard.jsx  One person's progress — the screen itself
      Dashboard.jsx        Fetches it for the person whose it is
      ManagerDashboard.jsx The workspace, each person, and the two switches
      ManagerCRM.jsx       Clients: the board, the table and one client whole
      ManagerSummary.jsx   The manager's plain-English half: what needs you,
                           the four numbers, effort spent twice, the team table
      BdHome.jsx           Logging jobs and working the list
      DevHome.jsx          A developer's day — the diary and their record
      DevProfiles.jsx      What a client is handed, kept by the developer
      Interviews.jsx       Scheduling and the diary — one component, three screens
      JobRecord.jsx        Every job ever applied for, searched, and the
                           interview started from a row
      Assessments.jsx      Assessments: set on one side, done on the other
      AdminHome.jsx        Running cycles
      People.jsx           People, profiles, developers, and who is on the board
      shell.jsx            Toasts, the command palette and the theme — the
                           parts that outlive whichever screen is mounted
      widgets.jsx          The shared pieces, and the glossary at the top of
                           it: tiles and big figures, the day strip, the flow
                           chart, the stage ladder, the stalled list, the
                           board, the assessments board and the
                           between-two-dates report
    styles.css             The design system: one neutral ramp, four semantic
                           families, and every component this app uses
```

`crm.py`, `dashboard.py` and `interviews.py` never write. A dashboard can be opened while
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
- `_APPLY_TAIL` and `_APPLY_LAST`, read by `posting_stem` — the tails an apply
  flow hangs off a listing. Add one when a board you use appends something new.
  Keep the split: the first list may swallow a sub-path, the second must be the
  very last segment. Putting `job` or `jobs` in the first list collapses every
  posting on a careers site into its hostname.

Change any of them, then run `pytest test_matching.py` to see what moved.
