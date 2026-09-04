import React from "react";
import { ActionList, plural } from "./Todo.jsx";
import { BigFigures, sinceText } from "./widgets.jsx";

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
      title: `${n} ${plural(n, "test is", "tests are")} past the deadline a client set.`,
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
           + "not handed in a job sheet for this round.",
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
 * this round and two are all time and there is no way to guess which from the
 * words alone. Interviews and offers cannot be scoped to a round without
 * lying: a client who replies three weeks late is answering work from a round
 * that closed, and counting that reply against whichever round happened to be
 * open would credit the wrong fortnight. So they are all-time, and say so.
 */
export function Headline({ org, funnel }) {
  // Every application the team sent this round, whoever found the job. The
  // screen used to headline `applied` on its own, which is only the ones that
  // came off a colleague's list — on a team that finds most of its own work
  // that reads as barely half the week.
  const sent = (org.own_found || 0) + (org.from_others || 0);

  const cards = [
    {
      key: "sent",
      scope: "this round",
      value: num(sent),
      label: "applications sent",
      body: "Every job somebody applied for this round, whether they found it "
          + "themselves or a colleague found it for them.",
      tone: "good",
    },
    {
      key: "shared",
      scope: "this round",
      value: num(org.from_others),
      label: "of those, found by a teammate",
      body: sent
        ? `${Math.round((org.from_others / sent) * 100)}% of the round's work came off `
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

  return <BigFigures items={cards} />;
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
                this round. Splitting up who searches where is what brings this down.</>
            : <>Nobody found the same posting as anybody else this round. That is the
                best this number gets.</>}
          {direction !== null && (
            <> {direction < 0
              ? <>It is <b>{Math.abs(direction)} points lower</b> than the round before.</>
              : direction > 0
                ? <>It is <b>{direction} points higher</b> than the round before.</>
                : <>It is level with the round before.</>}</>
          )}
        </p>
      </div>

      {trend.length > 1 && (
        <div>
          <p className="hint" style={{ marginBottom: 8 }}>
            Share of the team's typing spent on a job somebody else had already found,
            round by round. Lower is better.
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
         title={`${applied} applied for · ${skipped} turned down · ${pending} still to do`}>
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
      <span><i style={{ background: "var(--n6)" }} />turned down, with a reason</span>
      <span><i style={{ background: "var(--n4)" }} />still to do</span>
    </div>
  );
}

/** Every person on the team, in the words a manager would use.
 *
 * The old column headings were the database's: Logged, Also found, List,
 * Worked through. Four of the nine needed a tooltip to be read at all, which
 * on a screen somebody skims once a morning means they were not read.
 *
 * The columns add up now, which they did not before. "Applications sent" used
 * to be `applied` — only the jobs that came off somebody else's sheet — while
 * the same words at the top of the page meant everything they applied for. A
 * manager comparing the two found a headline of 224 sitting over a column that
 * summed to 52. Here the split is drawn rather than hidden: what they found
 * themselves, plus what a teammate found for them, makes the total.
 */
export function PeopleTable({ people, onOpen, onToggle, busy }) {
  // A developer is on the payroll but does not hand in sheets, so a row of
  // zeros against their name says nothing except that they are a developer.
  // They have their own section further down. A *BD* with no profile is a
  // different thing entirely — somebody who cannot do their job — so they
  // stay on the table, and are named under it.
  const rows = people.filter((person) => person.runs > 0 || person.role !== "dev");
  const idle = rows.filter((person) => !person.runs && person.role === "bd");

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="card scroll">
        <table className="board">
          <thead>
            <tr>
              <th>Person</th>
              <th className="num" title="Job sheets handed in, out of the profiles they run">
                Sheets in
              </th>
              <th className="num">Applications sent</th>
              <th className="num">Found it themselves</th>
              <th className="num">Found by a teammate</th>
              <th className="num" title="Jobs they found that a colleague had already found">
                Found twice
              </th>
              <th style={{ width: 156 }}>Their list</th>
              <th>Last worked</th>
              <th>Own figures</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((person) => (
              <tr key={person.user_id} style={{ cursor: "pointer" }}
                  onClick={() => onOpen(person)}>
                <td>
                  <b>{person.name}</b>
                  {person.role === "admin" && (
                    <span className="pill" style={{ marginLeft: 6 }}>manager</span>
                  )}
                  <div className="muted" style={{ fontSize: 11 }}>
                    {person.runs
                      ? `${person.runs} ${plural(person.runs, "profile", "profiles")}`
                      : "no profile yet"}
                  </div>
                </td>
                <td className="mono num"
                    style={{ color: person.runs && person.handed_in < person.runs
                      ? "var(--bad-text)" : undefined }}>
                  {person.handed_in}/{person.runs}
                </td>
                <td className="mono num"><b>{num(person.logged + person.applied)}</b></td>
                <td className="mono num">{num(person.logged)}</td>
                <td className="mono num">{num(person.applied)}</td>
                <td className="mono num"
                    style={{ color: person.duplicates ? "var(--bad-text)" : undefined }}>
                  {num(person.duplicates)}
                </td>
                <td>
                  <ListBar applied={person.applied} skipped={person.skipped}
                           pending={person.pending} />
                  <span className="muted mono" style={{ fontSize: 11 }}>
                    {person.assigned ? `${person.done_pct}% done` : "nothing handed over"}
                  </span>
                </td>
                <td className="muted">{sinceText(person.last_logged)}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <label className="row" style={{ gap: 6 }}>
                    <input type="checkbox" checked={!!person.dashboard_visible}
                           disabled={busy || person.role === "admin"}
                           title={person.role === "admin"
                             ? "A manager always has their own figures."
                             : `Let ${person.name} see their own figures`}
                           onChange={(e) => onToggle(person, e.target.checked)} />
                    <span className={person.dashboard_visible ? "pill on" : "pill off"}>
                      {person.dashboard_visible ? "can see" : "hidden"}
                    </span>
                  </label>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={9} className="muted">Nobody on the team yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <ListLegend />
      <p className="hint" style={{ maxWidth: 760 }}>
        Reading a row: <b>applications sent</b> is everything they applied for, and the
        two columns after it are that same number split — what they went out and{" "}
        <b>found themselves</b>, plus what a colleague <b>found for them</b> and handed
        over. <b>Found twice</b> is how much of their own digging somebody else had
        already done, which is effort spent for nothing. <b>Their list</b> is how far
        through the handed-over work they have got. Click any row to open that
        person&apos;s own screen.
      </p>
      {idle.length > 0 && (
        <p className="hint" style={{ maxWidth: 760 }}>
          {idle.map((person) => person.name).join(", ")}{" "}
          {plural(idle.length, "has", "have")} no profile to apply under yet, so there is
          nothing for {plural(idle.length, "them", "them")} to hand in. Set one up
          under <b>People</b>.
        </p>
      )}
    </div>
  );
}
