import React from "react";
import { ActionList, plural } from "./Todo.jsx";
import { Figures, sinceText } from "./widgets.jsx";

/** The plain-English half of the manager's screen.
 *
 * Everything here answers a question somebody would actually say out loud.
 * The rest of this app is written for the people who do the work, and they
 * have the vocabulary for it — a cycle, a sheet, a posting, a fingerprint. The
 * manager does not, and should not have to. So nothing on this screen is named
 * after the thing it is stored as:
 *
 *   logged      → jobs the team found
 *   assigned    → jobs handed to them
 *   duplicates  → the same job found twice
 *   done_pct    → how much of their list they have got through
 *   funnel      → what the applications turned into
 *
 * Every number is followed by the sentence that says what to think about it,
 * because a figure with no sentence is a figure everybody reads differently.
 */

const nf = new Intl.NumberFormat("en-US");
const num = (value) => nf.format(value || 0);

/* ── What needs you ────────────────────────────────────────────────────── */

/** The screen's first and most important section: the short list of things
 * that will not fix themselves.
 *
 * These used to be six separate coloured banners stacked down the page in the
 * order the code happened to check them, which meant an interview happening in
 * an hour could sit below a note about last week's typing. They are one list
 * now, sorted hardest-first, and each one says who is waiting and what to do
 * rather than only how many there are.
 *
 * `level` is a word as well as a colour. A manager reading this on a phone in
 * sunlight, or with any of the common kinds of colour blindness, gets the same
 * ordering either way.
 */
function needsYou({ org, missing, diary, assessments }) {
  const items = [];

  if (diary?.counts.awaiting_time > 0) {
    const n = diary.counts.awaiting_time;
    items.push({
      key: "awaiting-time",
      level: "now",
      title: `${n} ${plural(n, "client is", "clients are")} waiting on us to agree a time.`,
      body: "They have replied and said yes. Nobody has anything to turn up to "
          + "until a time is put on it, and this is the only place it shows.",
    });
  }

  if (assessments?.counts.overdue > 0) {
    const n = assessments.counts.overdue;
    items.push({
      key: "overdue-tests",
      level: "now",
      title: `${n} ${plural(n, "assessment is", "assessments are")} past the deadline a client set.`,
      body: "A missed deadline is the one thing here that goes wrong silently — "
          + "nothing on any other screen changes, and the next you hear is the client.",
    });
  }

  if (missing?.length > 0) {
    const names = missing.map((row) => row.name).join(", ");
    items.push({
      key: "missing",
      level: org.handed_in < 2 ? "now" : "chase",
      title: `${missing.length} ${plural(missing.length, "person has", "people have")} `
           + "not handed in a job sheet for this cycle.",
      body: org.handed_in < 2
        ? "Nothing can be worked out until at least two sheets are in — with fewer "
          + "than that there is nothing to compare. Waiting on: " + names + "."
        : "The lists are being built without them, so they get handed work but "
          + "none of what they found is shared out. Waiting on: " + names + ".",
    });
  }

  if (diary?.counts.today > 0) {
    const n = diary.counts.today;
    items.push({
      key: "today",
      level: "today",
      title: `${n} ${plural(n, "interview", "interviews")} today.`,
      body: diary.today
        .map((row) => `${row.when.time} ${row.profile}${row.client ? ` with ${row.client}` : ""}`)
        .join(" · ") + " — Eastern time.",
    });
  }

  if (diary?.counts.stalled > 0) {
    const n = diary.counts.stalled;
    items.push({
      key: "stalled",
      level: "chase",
      title: `${n} ${plural(n, "conversation", "conversations")} went quiet after going well.`,
      body: "The client said yes to another round and then nothing was booked, "
          + "usually because each side thought the other was arranging it. "
          + "Everywhere else on this screen these count as successes.",
    });
  }

  if (diary?.counts.awaiting_outcome > 0) {
    const n = diary.counts.awaiting_outcome;
    items.push({
      key: "awaiting-outcome",
      level: "chase",
      title: `${n} ${plural(n, "interview has", "interviews have")} happened with nobody `
           + "saying how it went.",
      body: "Until somebody does, every success rate further down this page is "
          + "lower than the truth.",
    });
  }

  return items;
}

export function NeedsYou(data) {
  return (
    <ActionList
      items={needsYou(data)}
      heading="Updates on interview & Assessments"
      empty={{
        title: "Nothing needs you right now.",
        body: "Every sheet is in, no client is waiting on a time, no deadline has "
            + "been missed and every interview that has happened has been reported on.",
      }} />
  );
}

/* ── The four numbers ──────────────────────────────────────────────────── */

/** The headline, in the order the work actually happens.
 *
 * Four, not the nine that were here before. Nine numbers side by side is a
 * wall somebody's eye slides off, and the four that mattered were in the
 * middle of it.
 *
 * Every card says which window it is counting over, because two of these are
 * this cycle and two are all time and there is no way to guess which from the
 * words alone. Interviews and offers cannot be scoped to a cycle without
 * lying: a client who replies three weeks late is answering work from a cycle
 * that closed, and counting that reply against whichever cycle happened to be
 * open would credit the wrong fortnight. So they are all-time, and say so.
 */
export function Headline({ org, funnel }) {
  // Every application the team sent this cycle, whoever found the job. The
  // screen used to headline `applied` on its own, which is only the ones that
  // came off a colleague's list — on a team that finds most of its own work
  // that reads as barely half the week.
  const sent = (org.own_found || 0) + (org.from_others || 0);

  const cards = [
    {
      key: "sent",
      scope: "all time",
      value: num(sent),
      label: "applied",
      body: "Every job somebody applied for this cycle, whether they found it "
          + "themselves or a colleague found it for them.",
      tone: "good",
    },
    {
      key: "shared",
      scope: "all time",
      value: num(org.from_others),
      label: "others' jobs",
      body: sent
        ? `${Math.round((org.from_others / sent) * 100)}% of the cycle's work came off `
          + "somebody else's sheet. This is the part that would not have happened "
          + "without everybody handing in to one place."
        : "Work that came off somebody else's sheet rather than their own.",
    },
    {
      key: "interviews",
      scope: "all time",
      value: num(funnel?.interviews || 0),
      label: "companies who want to talk",
      body: "Interviews booked off every application ever sent. A reply often "
          + "lands weeks after the application that earned it.",
    },
    {
      key: "offers",
      scope: "all time",
      value: num(funnel?.offers || 0),
      label: "offers of work",
      body: "The only number on this page that pays for anything.",
      tone: funnel?.offers ? "good" : undefined,
    },
  ];

  return <Figures items={cards} />;
}

/* ── Each person ───────────────────────────────────────────────────────── */

/** How much of a handed-out list somebody has got through.
 *
 * Three states, and they are states rather than a series, so they wear the
 * status colours and carry a written legend above the table. The 2px gaps are
 * what stop two touching segments reading as one longer one.
 */
function ListBar({ applied, skipped, pending }) {
  const total = (applied || 0) + (skipped || 0) + (pending || 0);
  if (!total) return <div className="listbar is-empty" title="Nothing handed to them yet" />;
  const share = (n) => `${(n / total) * 100}%`;
  return (
    <div className="listbar"
         title={`${applied} applied for · ${skipped} skipped · ${pending} still to do`}>
      <i style={{ width: share(applied), background: "var(--ok)" }} />
      <i style={{ width: share(skipped), background: "var(--n6)" }} />
      <i style={{ width: share(pending), background: "var(--n4)" }} />
    </div>
  );
}

export function ListLegend() {
  return (
    <div className="row legend" style={{ gap: 14 }}>
      <span><i style={{ background: "var(--ok)" }} />applied for</span>
      <span><i style={{ background: "var(--n6)" }} />skipped, with a reason</span>
      <span><i style={{ background: "var(--n4)" }} />still to do</span>
    </div>
  );
}

/** Every person on the team, in the words a manager would use.
 *
 * Nine columns fitted on nobody's laptop and half of them were read once a
 * month. Five stay — who, how much went out, how far through their handed-over
 * work they are, and when they last did any — and the rest open per row.
 *
 * Two targets on a row, never one doing two jobs: the name opens that person's
 * screen, the chevron opens the numbers underneath. A row that did both would
 * navigate away from somebody trying to read it.
 *
 * The columns still add up. "Applied this cycle" is everything they applied
 * for; own jobs and others' jobs are that same number split.
 */
function PersonRow({ person, onOpen, onToggle, busy }) {
  const [open, setOpen] = React.useState(false);
  const id = React.useId();
  const sent = person.logged + person.applied;
  const behind = person.runs && person.handed_in < person.runs;

  return (
    <>
      <tr>
        <td data-label="">
          <button className="link" onClick={() => onOpen(person)}
                  title={`Open ${person.name}'s screen`}>
            <b>{person.name}</b>
          </button>
          {person.role === "admin" && (
            <span className="pill" style={{ marginLeft: 6 }}>manager</span>
          )}
          <div className="muted" style={{ fontSize: 11 }}>
            {person.runs
              ? `${person.runs} ${plural(person.runs, "profile", "profiles")}`
              : "no profile yet"}
            {behind && (
              <span style={{ color: "var(--bad-text)" }}>
                {" "}· {person.runs - person.handed_in} sheet
                {person.runs - person.handed_in === 1 ? "" : "s"} not in
              </span>
            )}
          </div>
        </td>
        <td className="mono num" data-label="Applied this cycle"><b>{num(sent)}</b></td>
        <td data-label="Their list">
          <ListBar applied={person.applied} skipped={person.skipped}
                   pending={person.pending} />
          <span className="muted mono" style={{ fontSize: 11 }}>
            {person.assigned ? `${person.done_pct}% done` : "nothing handed over"}
          </span>
        </td>
        <td className="muted" data-label="Last worked">{sinceText(person.last_logged)}</td>
        <td data-label="" style={{ textAlign: "right" }}>
          <button type="button" className="row-more" aria-expanded={open}
                  aria-controls={id}
                  aria-label={`${open ? "Hide" : "Show"} the rest of ${person.name}'s figures`}
                  onClick={() => setOpen((now) => !now)}>
            <svg className={open ? "chev is-open" : "chev"} viewBox="0 0 16 16"
                 width="14" height="14" aria-hidden="true" focusable="false">
              <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor"
                    strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </td>
      </tr>
      <tr className="row-detail" id={id} hidden={!open}>
        <td colSpan={5}>
          <div className="stack" style={{ gap: 10, padding: "4px 0 10px" }}>
            <div className="figures">
              <div title="Found on their own sheets, and applied for">
                <b className="mono">{num(person.logged)}</b><span>own jobs</span>
              </div>
              <div title="A colleague found these and handed them over">
                <b className="mono">{num(person.applied)}</b><span>others&apos; jobs</span>
              </div>
              <div title="Of their own digging, what somebody else had already found">
                <b className="mono" style={{ color: person.duplicates ? "var(--bad-text)" : undefined }}>
                  {num(person.duplicates)}
                </b><span>found twice</span>
              </div>
              <div title="Job sheets handed in, out of the profiles they run">
                <b className="mono" style={{ color: behind ? "var(--bad-text)" : undefined }}>
                  {person.handed_in}/{person.runs}
                </b><span>sheets in</span>
              </div>
            </div>
            <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
              <label className="row" style={{ gap: 6 }}>
                <input type="checkbox" checked={!!person.dashboard_visible}
                       disabled={busy || person.role === "admin"}
                       onChange={(e) => onToggle(person, e.target.checked)} />
                <span>
                  {person.role === "admin"
                    ? "A manager always has their own figures."
                    : `${person.name} can see their own figures`}
                </span>
              </label>
              <button className="ghost" onClick={() => onOpen(person)}>
                Open {person.name}&apos;s screen
              </button>
            </div>
          </div>
        </td>
      </tr>
    </>
  );
}

export function PeopleTable({ people, onOpen, onToggle, busy }) {
  // A developer is on the payroll but hands in no sheets, so a row of zeros
  // against their name says nothing except that they are a developer. They
  // have their own section. A *BD* with no profile stays regardless — that is
  // somebody who cannot do their job.
  const rows = people.filter((person) => person.runs > 0 || person.role !== "dev");

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="card scroll stacks">
        <table className="board">
          <thead>
            <tr>
              <th>Person</th>
              <th className="num">Applied this cycle</th>
              <th style={{ width: 168 }}>Their list</th>
              <th>Last worked</th>
              <th style={{ width: 44 }}><span className="sr-only">More</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((person) => (
              <PersonRow key={person.user_id} person={person} onOpen={onOpen}
                         onToggle={onToggle} busy={busy} />
            ))}
            {!rows.length && (
              <tr><td colSpan={5} className="muted">Nobody on the team yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <ListLegend />
    </div>
  );
}

