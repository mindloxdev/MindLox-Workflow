# Build prompt: the manager's client screen (Clients)

Paste this whole file as the task. Read `README.md` first, then build.

---

## Context

This is **Dispatch**. FastAPI + SQLAlchemy backend in `backend/app`, React + Vite
frontend in `frontend/src`, plain CSS design system in `frontend/src/styles.css`.
Roles are manager, BD and developer. Everything already built is described in
`README.md` and that document is the source of truth for vocabulary, permissions
and time handling. Read it before writing code.

## The gap this fills

Every screen in the app is organised by **profile**, by **person**, or by
**cycle**. Nothing is organised by the **client**.

That means a manager cannot answer the questions a manager actually gets asked:

- Have we approached Northwind before, and how did it go?
- Which clients are live right now, and who is sitting on them?
- Which clients replied and then went quiet?
- Are three of our profiles all applying into the same company this month?

The data to answer all four is already in the database. It is just never grouped
by company. Build the screen that groups it.

## What to build

One new manager screen, **Clients**, plus the read model behind it. A client
account view of everything the team has already recorded: postings applied to,
conversations, tests, outcomes, and who is on it.

Nothing on this screen invents a new source of truth. It is a different cut of
`jobs`, `applications`, `interviews` and `assessments`, with one small additive
table for the manager's own annotations.

---

## Rules that are not negotiable

Copy these from the existing app rather than reinventing them.

1. **The vocabulary is fixed.** Own jobs, others' jobs, applications sent,
   applied, skipped, still to do, found twice, round. The glossary at the top of
   `frontend/src/views/widgets.jsx` is the mapping. Nothing on screen is named
   after the column it is stored in.
2. **Read modules never write.** `dashboard.py`, `interviews.py` and
   `assessments.py` contain no writes, so a dashboard can be opened while a
   rebuild is running. `crm.py` follows the same rule. The one write in this
   feature (the annotation) is a route in `main.py`, not a function in `crm.py`.
3. **Time is Eastern, formatted once on the server.** Reuse
   `models.working_label`. The browser does no date arithmetic, ever.
4. **Permission is a server check, not a hidden tab.** Manager only. A BD or a
   developer hitting any of these endpoints gets a `403`. The tab is hidden as a
   courtesy, not as the control.
5. **A cancellation is never a rejection**, and an interview with no outcome
   recorded is not a loss. Both rules already exist in the funnel code. Do not
   write a second, slightly different version of them here.
6. **This screen does not book anything.** Read-only on conversations, for the
   same reason the manager's stalled list is read-only: whoever runs the profile
   books the next round. Link across to their screen instead.

---

## The client key

There is no clients table and you are not creating one for identity.

Derive the key at read time from the company name on `jobs`, using the same
noise-word stripping that `matching.py` already does with `_SUFFIX`. Lowercase,
strip punctuation, strip the suffix words, collapse whitespace. Put the helper in
`matching.py` next to the existing one and import it, so there is one definition
of what "the same company" means and the unit tests can reach it without a
database.

Two things this must handle, and both need a test:

- `Northwind Health, Inc.` and `northwind health` are one client.
- Two genuinely different companies with similar names are two clients. Do not
  fuzzy match company names here. The fuzzy tier in `matching.py` requires client
  **and** title to match before it merges anything, and loosening that on this
  screen would silently fuse two clients' histories.

Display name is the most recently recorded spelling of the company, not the key.

---

## The screen

### Top: what needs you, client-side

Same three rules as every other list in this app. Says what is wrong in a
sentence, says why it matters, carries the button that deals with it. Hardest
first:

- Clients who replied and have no time agreed.
- Clients with a test past its deadline.
- Clients who cleared a round with nothing booked after.
- Clients with an interview today.
- Clients who have gone quiet: last activity older than 14 days while the status
  is still live.

Each row links to that client's drawer, and to the screen of whoever runs the
profile involved.

### The board

Client accounts grouped by status, each column showing a count and the clients
in it, most recent activity first. Status is **derived**, never typed:

| Status | How it is derived |
|---|---|
| Approached | Applications exist, no reply recorded |
| Replied, no time agreed | An interview row with no time on it |
| In conversation | An interview booked or held, not settled |
| Test out | An open assessment, whatever the interview says |
| Offer | Outcome is offer, no hire recorded |
| Hired | Outcome is hired |
| Stalled | Cleared a round, nothing booked after it, not a hire |
| Closed | Last recorded outcome is no |

A client sits in exactly one column. When more than one applies, take the
furthest up the ladder, except that **Stalled** and **Test out** win over
**In conversation**, because those are the two that need somebody to move.

Board or table is a switch, and the table is the default. A board is easier to
show a client; a table is easier to read on a Monday.

### The table

One row per client. Columns:

- Client
- Status
- Applications sent (all-time, and the count inside the date window when one is set)
- Profiles that applied, named
- Who runs those profiles
- Developers involved
- Furthest rung reached on the ladder
- Open tests
- Next thing in the diary, with the Eastern label
- Last activity, as a date

Sortable on every column. One search box filtering on client, profile, BD,
developer or title, because somebody pasting out of an email does not know which
field the thing they copied lives in.

The **From / To** pair works exactly as it does on the other dashboards: setting
it replaces the default view rather than sitting beside it, and rows are dated by
when the work happened, not by which cycle it belonged to.

### The drawer: one client, whole

Opening a row opens the client's record. Not appended underneath. Scroll to the
top on the way in, back to the row on the way out, filters preserved. Match what
`ManagerDashboard.jsx` already does when a manager opens a person.

Inside, in this order:

1. **The header.** Client name, status, first approached, last activity, and the
   annotation card (below).
2. **Conversations.** One block per chain, not one row per sitting. A client who
   ran four rounds reads as one story: `round 2 of 3 · after the screening call`.
   Each shows the profile it was under, the developer, the rung, the outcome,
   who reported it and when, the meeting link and **their email** as two clearly
   separate links. Brief and debrief shown side by side, never merged.
3. **Tests.** Deadline, state, which conversation produced it, and an overdue
   marker.
4. **Every posting we applied to at this client.** Title, profile, who found it,
   applied on for that profile, platform, both links, and whether it was applied
   or skipped with the reason. This is the answer to "have we been here before".
5. **Found twice at this client.** Postings two profiles both went out and found.
   A run of these at one company is a search problem, not a dispatch problem.

### The annotation card

The one writable thing on this screen, and it is the manager's own note, not a
change to anybody's work:

- **Priority** flag.
- **Already being worked** flag, with a line saying who and since when.
- A free-text note, with who last wrote it and when.

**Advisory only.** It does not filter the pool, does not skip anything, and does
not touch dispatch. A flag that quietly stopped jobs going out would be a rule
nobody could see the effect of, and the reason for a missing job would be
invisible on the BD's screen. Surface it instead: when a BD logs a job whose
client carries the **already being worked** flag, show it in the same dialog that
already fires for a duplicate link, with the same **Ignore, keep this row**
escape.

---

## Data model

One additive table. Nullable everywhere, empty on every existing row, created by
`create_all` and noted in `schema.py` as restart-only, in the style of the 2.2
through 2.7 upgrades already documented in the README.

```
client_notes
  id
  client_key        unique, the derived key
  display_name      the spelling last seen, for a note on a client
                    whose jobs were later deleted
  priority          bool, default false
  being_worked      bool, default false
  note              text, nullable
  updated_by        person id
  updated_at        utc
```

No foreign key to `jobs`. The key is derived, and a note must survive the last
posting at that client being withdrawn.

---

## API

New module `backend/app/crm.py`, read-only. Routes wired in `main.py`, all behind
the manager check.

```
GET  /api/crm/clients?from=&to=&status=&q=&sort=&page=&per_page=
     -> { clients: [...], totals: {...}, page: {...} }

GET  /api/crm/clients/{client_key}
     -> { client, status, conversations: [...], tests: [...],
          postings: [...], found_twice: [...], note }

PUT  /api/crm/clients/{client_key}/note        manager only, in main.py
     -> the saved note

GET  /api/crm/export.xlsx
```

Paginate the list endpoint. A team a year in has thousands of clients and a
screen that loads all of them will be the slowest page in the app.

Every timestamp in every response is preformatted by `models.working_label`.

The export goes in `exports.py` alongside the others and carries three sheets:
the client list as shown, every conversation with its round and what it followed,
and every test with its deadline. Include the **Client email** column, since the
pipeline export already does.

---

## Files

Add:

- `backend/app/crm.py`
- `backend/test_crm.py`
- `frontend/src/views/ManagerCRM.jsx`

Change:

- `backend/app/matching.py` - the client key helper, no framework imports
- `backend/app/models.py` - `client_notes`
- `backend/app/schema.py` - the additive step, and a line in the README's
  upgrade section
- `backend/app/main.py` - routes and the manager check
- `backend/app/exports.py` - the export
- `frontend/src/App.jsx` - routing and the tab
- `frontend/src/views/widgets.jsx` - only if a genuinely shared piece comes out
  of this, and add any new word to the glossary at the top
- `frontend/src/views/BdHome.jsx` - the being-worked notice in the existing
  duplicate dialog
- `frontend/src/styles.css` - only if no existing class fits

---

## Tests

`backend/test_crm.py`, run with `pytest test_crm.py -v`. Assert the things that
would be wrong quietly:

1. `Northwind Health, Inc.` and `northwind health` group as one client.
2. Two similarly named but distinct companies stay two clients.
3. A client with applications and no reply is **Approached**.
4. A client with an untimed interview is **Replied, no time agreed**, and is in
   no funnel rate and no count of what is coming.
5. A client that cleared a round with nothing after is **Stalled**, and a hire
   never lands there.
6. An open test outranks the interview status.
7. A cancelled interview does not put a client in **Closed**.
8. The date window filters by when work happened, not by cycle.
9. Applications sent for a client equals own jobs plus others' jobs at that
   client, and the columns add up.
10. A BD token and a developer token each get `403` on all four endpoints.
11. A note survives every posting at that client being deleted.
12. Two profiles that both found the same posting at one client show up once
    under found twice, not twice.

Run the full suite afterwards. The 215 existing tests all still pass; if any
break, the change is wrong, not the test.

---

## Do not

- Do not add a clients table as an identity, or fuzzy match company names.
- Do not let this screen book, reschedule or settle a conversation.
- Do not let the annotation flags change what dispatch hands out.
- Do not put a second copy of the funnel maths in `crm.py`. Call what
  `interviews.py` already computes.
- Do not do date arithmetic in the browser.
- Do not show a database column name anywhere on screen.
- Do not fabricate figures for empty states. A client with no conversations shows
  nothing there, and says so in a sentence.

## Verify it by hand

Sign in as `admin@example.com`. Open **Clients**. Every company on the seeded
sheets appears, the two interviews seeded for today put their clients under
**In conversation** with today's date in the diary column, and the one seeded
interview from yesterday with no outcome recorded appears at the top under
results nobody recorded. Sign in as `ali@example.com` and confirm the tab is
absent and the endpoint returns `403`.
