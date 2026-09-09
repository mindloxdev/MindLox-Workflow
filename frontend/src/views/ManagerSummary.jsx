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
      lead="Hardest first. Everything below this section is the picture; this is the list."
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
      scope: "this cycle",
      value: num(sent),
      label: "applied this cycle",
      body: "Every job somebody applied for this cycle, whether they found it "
          + "themselves or a colleague found it for them.",
      tone: "good",
    },
    {
      key: "shared",
      scope: "this cycle",
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
      label: "clients who wanted to talk",
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

/** What the four numbers mean, for whoever has not read it before.
 *
 * Under the row rather than inside each card: a sentence per figure is most of
 * a screen, and it is read once and scrolled past every morning after.
 */
export function HeadlineKey({ org, funnel }) {
  const sent = (org.own_found || 0) + (org.from_others || 0);
  return (
    <div className="stack" style={{ gap: 8, maxWidth: 720 }}>
      <p className="muted">
        <b>Applied this cycle</b> — every job somebody applied for this cycle,
        whether they found it themselves or a colleague found it for them.
      </p>
      <p className="muted">
        <b>Others&apos; jobs</b> — work that came off somebody else&apos;s
        sheet{sent ? `, ${Math.round((org.from_others / sent) * 100)}% of the cycle` : ""}.
        This is the part that would not have happened without everybody handing
        in to one place.
      </p>
      <p className="muted">
        <b>Clients who wanted to talk</b> and <b>offers of work</b> are all-time,
        and cannot honestly be anything else: a client who replies three weeks
        late is answering work from a cycle that closed, and counting that reply
        against whichever cycle happens to be open would credit the wrong
        fortnight.
      </p>
      {!funnel?.offers && (
        <p className="hint">
          No offers recorded yet. That figure only moves when the work was worth
          sending, which is why it is the one worth steering by.
        </p>
      )}
    </div>
  );
}

/* ── Doubled-up effort ─────────────────────────────────────────────────── */

/** The same job, found by two people.
 *
 * The one figure on this screen that is a cost rather than an achievement, and
 * the reason the product exists. Said as typing rather than as a percentage,
 * because "18%" is a statistic and "94 jobs were typed in twice" is a morning
 * somebody spent twice.
 */
export function DoubledUp({ org, history }) {
  const trend = (history || []).filter((row) => row.rows_read > 0);
  const peak = Math.max(1, ...trend.map((row) => row.duplicate_pct), 1);
  const previous = trend.length > 1 ? trend[trend.length - 2] : null;
  const direction = previous ? org.duplicate_pct - previous.duplicate_pct : null;

  return (
    <div className="card pad stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 26, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <b className={org.duplicates ? "dup-figure is-bad" : "dup-figure"}>
            {num(org.duplicates)}
          </b>
          <span className="head-label">
            {plural(org.duplicates, "job found twice", "jobs found twice")}
          </span>
        </div>
        <p style={{ flex: "1 1 340px", maxWidth: 620, fontSize: "var(--t-sm)", lineHeight: 1.6 }}>
          {org.duplicates
            ? <>Two people went out and found the same posting, so it was typed
                in <b>{num(org.wasted_rows)}</b> {plural(org.wasted_rows, "time", "times")} more
                than it needed to be — <b>{org.duplicate_pct}%</b> of everything typed
                this cycle. Splitting up who searches where is what brings this down.</>
            : <>Nobody found the same posting as anybody else this cycle. That is the
                best this number gets.</>}
          {direction !== null && (
            <> {direction < 0
              ? <>It is <b>{Math.abs(direction)} points lower</b> than the cycle before.</>
              : direction > 0
                ? <>It is <b>{direction} points higher</b> than the cycle before.</>
                : <>It is level with the cycle before.</>}</>
          )}
        </p>
      </div>

      {trend.length > 1 && (
        <div>
          <p className="hint" style={{ marginBottom: 8 }}>
            Share of the team's typing spent on a job somebody else had already found,
            cycle by cycle. Lower is better.
          </p>
          <div className="history">
            {trend.map((row) => {
              return (
                <div className="history-col" key={row.id}
                     title={`${row.name}: ${row.duplicates} of ${row.rows_read} rows were a repeat`}>
                  <span className="mono history-value">{row.duplicate_pct}%</span>
                  <div className="history-bar">
                    <i style={{
                      height: `${Math.max(3, (row.duplicate_pct / peak) * 100)}%`,
                      background: row.duplicate_pct > 20 ? "var(--bad)" : "var(--a)",
                    }} />
                  </div>
                  <span className="muted history-label truncate">{row.name}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
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
        <td>
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
        <td className="mono num"><b>{num(sent)}</b></td>
        <td>
          <ListBar applied={person.applied} skipped={person.skipped}
                   pending={person.pending} />
          <span className="muted mono" style={{ fontSize: 11 }}>
            {person.assigned ? `${person.done_pct}% done` : "nothing handed over"}
          </span>
        </td>
        <td className="muted">{sinceText(person.last_logged)}</td>
        <td style={{ textAlign: "right" }}>
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
  // have their own section. A *BD* with no profile stays, and is named under
  // the table — that is somebody who cannot do their job.
  const rows = people.filter((person) => person.runs > 0 || person.role !== "dev");
  const idle = rows.filter((person) => !person.runs && person.role === "bd");

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="card scroll">
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
      <p className="hint" style={{ maxWidth: 760 }}>
        <b>Applied this cycle</b> is everything they applied for. <b>Their list</b> is
        how far through the work a colleague handed them they have got. Press a
        name to open their screen, or the chevron for the rest of their figures.
      </p>
      {idle.length > 0 && (
        <p className="hint" style={{ maxWidth: 760 }}>
          {idle.map((person) => person.name).join(", ")}{" "}
          {plural(idle.length, "has", "have")} no profile to apply under yet, so there is
          nothing for them to hand in. Set one up under <b>People</b>.
        </p>
      )}
    </div>
  );
}

