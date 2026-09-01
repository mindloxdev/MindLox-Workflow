import React from "react";

/** The shape of what is coming, while it is still coming.
 *
 * A spinner says "wait"; this says "a headline, some figures and a table are
 * about to be here", which is the same wait spent usefully. It also holds the
 * height, so nothing under the pointer jumps when the data lands.
 */
export function Loading({ lines = 3, figures = false }) {
  return (
    <div className="stack enter-fade" style={{ gap: 12 }} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="skeleton" style={{ height: 22, width: 200 }} />
      {figures && (
        <div className="stats">
          {Array.from({ length: 4 }, (_, i) => (
            <div className="stat" key={i}>
              <div className="skeleton" style={{ height: 22, width: 54, marginBottom: 6 }} />
              <div className="skeleton" style={{ height: 10, width: 88 }} />
            </div>
          ))}
        </div>
      )}
      <div className="card pad stack" style={{ gap: 9 }}>
        {Array.from({ length: lines }, (_, i) => (
          <div className="skeleton" key={i}
               style={{ height: 12, width: `${94 - i * 13}%` }} />
        ))}
      </div>
    </div>
  );
}

/** "just now", "4 minutes ago", "2 hours ago" — enough to trust the numbers.
 *
 * Stored timestamps are UTC. SQLite hands them back with no marker at all, so
 * the Z goes on here or the browser reads them as local time and everything
 * looks hours old.
 */
export function sinceText(iso) {
  if (!iso) return "never";
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return then.toLocaleDateString();
}

/** The sub-tabs inside a screen, as one control rather than a row of buttons.
 *
 * Five loose buttons read as five unrelated actions; a segmented control reads
 * as one question with five answers, which is what it is. The count rides on
 * the tab it belongs to, so "Interviews (3 waiting)" needs no second line.
 *
 * `items` are `{ key, label, count, tone }`. A falsy entry is dropped, so a tab
 * that only exists in some states can be written inline.
 */
export function Segment({ items, value, onChange, label = "View" }) {
  const shown = items.filter(Boolean);
  if (shown.length < 2) return null;
  return (
    <div className="segment" role="tablist" aria-label={label}>
      {shown.map((item) => (
        <button key={item.key} role="tab" aria-pressed={value === item.key}
                aria-selected={value === item.key}
                onClick={() => onChange(item.key)}>
          {item.label}
          {item.count ? (
            <span className="count" style={item.tone ? { color: `var(--${item.tone})` } : undefined}>
              {item.count}
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function DateRange({ dateFrom, dateTo, onChange }) {
  const update = (key, value) => onChange({ dateFrom: key === "dateFrom" ? value : dateFrom,
                                             dateTo: key === "dateTo" ? value : dateTo });
  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
      <label className="row muted" style={{ gap: 5 }}>
        From
        <input type="date" value={dateFrom} onChange={(e) => update("dateFrom", e.target.value)} />
      </label>
      <label className="row muted" style={{ gap: 5 }}>
        To
        <input type="date" value={dateTo} onChange={(e) => update("dateTo", e.target.value)} />
      </label>
      {(dateFrom || dateTo) && (
        <button className="link" onClick={() => onChange({ dateFrom: "", dateTo: "" })}>
          Clear dates
        </button>
      )}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "1 Aug" from "2026-08-01", without constructing a Date.
 *
 * These strings are already the team's working day, decided on the server.
 * Handing one to `new Date()` would parse it as UTC midnight and print the
 * day before for anybody west of Greenwich — the one bug this whole app is
 * careful about, reintroduced for a label. */
function dayLabel(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}${y === new Date().getFullYear() ? "" : ` ${y}`}`;
}

/** What somebody did between two dates.
 *
 * The rest of this app answers "how is the current cycle going". This answers
 * the question people are actually asked at the end of a fortnight: what did
 * you do between these two dates. They are different questions — a cycle
 * opened on the 3rd is still being worked on the 20th — so this is its own
 * block rather than the usual figures with a filter on them.
 *
 * `show` is "all" for a BD, whose week is applications first, and "interviews"
 * for a developer, who did not send any.
 */
export function RangeReport({ report, show = "all", whose = "your" }) {
  if (!report) return null;
  const { applied, heard_back: heard, interviews: sat } = report;
  const span = [dayLabel(report.from), dayLabel(report.to)].filter(Boolean).join(" – ");
  const sendings = show === "all";

  return (
    <section className="card pad stack enter" style={{ gap: 16 }}>
      <div className="head">
        <h2>{span || "This range"}</h2>
        <span className="hint">
          {report.days} day{report.days === 1 ? "" : "s"} · everything below is
          {" "}this range only
        </span>
      </div>

      {sendings && (
        <div className="stack" style={{ gap: 10 }}>
          <Tiles items={[
            { label: "applications sent", value: applied.total },
            { label: "a day, on average", value: applied.per_day,
              foot: `${applied.active_days} day${applied.active_days === 1 ? "" : "s"} worked` },
            { label: `${whose === "your" ? "you" : whose} found`, value: applied.own_found,
              hint: "Postings off this profile's own sheet." },
            { label: "found by colleagues", value: applied.from_others,
              hint: "Postings the cycle handed over, then marked applied." },
            { label: "skipped", value: applied.skipped },
            applied.busiest ? {
              label: "busiest day", value: applied.busiest.count,
              foot: dayLabel(applied.busiest.day),
            } : null,
          ]} />

          {/* The split as one bar. Two numbers side by side are two numbers;
              a bar is the ratio, which is the thing being asked about. */}
          {applied.total > 0 && (
            <div>
              <div className="bar" title={`${applied.own_found} found here · `
                + `${applied.from_others} from colleagues`}>
                <i style={{ width: `${(applied.own_found / applied.total) * 100}%`,
                            background: "var(--a)" }} />
                <i style={{ width: `${(applied.from_others / applied.total) * 100}%`,
                            background: "var(--ok)" }} />
              </div>
              <p className="hint" style={{ marginTop: 5 }}>
                {Math.round((applied.own_found / applied.total) * 100)}% off
                {" "}{whose === "your" ? "your" : `${whose}'s`} own search,
                {" "}{100 - Math.round((applied.own_found / applied.total) * 100)}% off
                {" "}colleagues&apos;.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── What came back ─────────────────────────────────────────────── */}
      <div className="stack" style={{ gap: 10 }}>
        <div className="head">
          <h3>What came back</h3>
          <span className="hint">
            {sat.conversations} client{sat.conversations === 1 ? "" : "s"} talked,
            {" "}across {sat.sittings} interview{sat.sittings === 1 ? "" : "s"}
            {sendings && applied.total > 0 ? ` · ${heard.rate}% of what went out` : ""}
          </span>
        </div>

        {sat.sittings === 0 ? (
          <Empty>No interviews in this range.</Empty>
        ) : (
          <>
            <Tiles items={[
              { label: "interviews held", value: sat.completed,
                hint: "Been and gone, whatever the outcome." },
              { label: "still to come", value: sat.scheduled },
              { label: "one round only", value: sat.one_round,
                hint: "Clients who spoke once and went no further." },
              { label: "reached a 2nd round", value: sat.two_plus,
                tone: sat.two_plus ? "ok" : undefined },
              { label: "reached a 3rd", value: sat.three_plus,
                tone: sat.three_plus ? "ok" : undefined },
              { label: "furthest one got", value: sat.furthest
                ? `${sat.furthest} round${sat.furthest === 1 ? "" : "s"}` : "—" },
              sat.offers ? { label: "offers", value: sat.offers, tone: "ok" } : null,
              sat.rejected ? { label: "ended in a no", value: sat.rejected } : null,
            ]} />

            <StageLadder rows={sat.by_stage} />

            {heard.clients.length > 0 && (
              <div className="card scroll">
                <table className="board">
                  <thead>
                    <tr>
                      <th>Client</th>
                      <th>Role</th>
                      <th>Got to</th>
                      <th>How it ended</th>
                      <th>Last spoke</th>
                    </tr>
                  </thead>
                  <tbody>
                    {heard.clients.map((row, i) => (
                      <tr key={`${row.client}-${i}`}>
                        <td><b>{row.client}</b></td>
                        <td className="truncate" style={{ maxWidth: 240 }}>
                          {row.role || <span className="muted">—</span>}
                        </td>
                        <td>
                          {STAGE_LABELS[row.stage] || row.stage}
                          {row.rounds > 1 && (
                            <span className="hint"> · {row.rounds} rounds</span>
                          )}
                        </td>
                        <td>
                          <span className={row.outcome === "rejected" ? "pill off"
                            : ["offer", "hired", "passed"].includes(row.outcome) ? "pill on"
                              : "pill"}>
                            {row.outcome === "pending" ? "not said yet" : row.outcome}
                          </span>
                        </td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>
                          {row.when.label}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

/** Nothing here — said in a way that reads as finished rather than broken.
 *
 * A blank panel is indistinguishable from a failed request. A sentence and,
 * where there is one, a way out, is the difference.
 */
export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      {title && <b>{title}</b>}
      {children}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

/** A row of headline numbers. `tone` tints the figure, not the label. */
export function Tiles({ items }) {
  return (
    <div className="stats">
      {items.filter(Boolean).map((item) => (
        <div className="stat" key={item.label} title={item.hint || undefined}>
          <b style={item.tone ? { color: `var(--${item.tone})` } : undefined}>{item.value}</b>
          <span>{item.label}</span>
          {item.foot && <span className="foot">{item.foot}</span>}
        </div>
      ))}
    </div>
  );
}

/** Jobs logged per day, as bars.
 *
 * Bars rather than a line: these are counts of discrete days, and a line
 * between two of them implies a value at half past Tuesday that does not exist.
 * The server always sends a fixed number of days, zeros included, so a quiet
 * week keeps the shape instead of stretching two bars across the whole strip.
 */
export function Sparkline({ series, height = 46, label = "jobs logged" }) {
  if (!series?.length) return null;
  const peak = Math.max(1, ...series.map((d) => d.count));
  const step = 8;
  const width = series.length * step;
  const total = series.reduce((sum, d) => sum + d.count, 0);

  return (
    <div className="spark-wrap">
      <svg className="spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
           role="img" aria-label={`${total} ${label} over the last ${series.length} days`}>
        {series.map((day, i) => {
          const tall = day.count ? Math.max(2, (day.count / peak) * (height - 2)) : 1;
          return (
            <rect key={day.day} x={i * step + 1} y={height - tall}
                  width={step - 2} height={tall}
                  fill={day.count ? "var(--petrol)" : "var(--rule)"}>
              <title>{`${day.count} on ${day.day}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="spark-axis muted">
        <span>{series[0].day.slice(5)}</span>
        <span>peak {peak}/day</span>
        <span>today</span>
      </div>
    </div>
  );
}

/** How a list was worked: applied, skipped, still to do. */
export function Progress({ applied = 0, skipped = 0, pending = 0 }) {
  const total = applied + skipped + pending;
  if (!total) {
    return <div className="bar" title="Nothing on this list yet"><i style={{ width: "100%" }} /></div>;
  }
  const share = (n) => `${(n / total) * 100}%`;
  return (
    <div className="bar" title={`${applied} applied · ${skipped} skipped · ${pending} to do`}>
      <i style={{ width: share(applied), background: "var(--pine)" }} />
      <i style={{ width: share(skipped), background: "var(--slate)" }} />
      <i style={{ width: share(pending), background: "var(--rule)" }} />
    </div>
  );
}

export function CyclePicker({ batches, value, onChange, label = "Cycle" }) {
  if (!batches?.length) return null;
  return (
    <label>
      {label}&nbsp;
      <select value={value || ""} onChange={(e) => onChange(Number(e.target.value))}>
        {batches.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name} · {b.status === "open" ? "open" : "closed"}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Every profile side by side.
 *
 * `onOpen` is only ever passed for a manager: a BD may see the totals on this
 * board but not click through into a colleague's record, and the server refuses
 * that request too.
 */
export function TeamBoard({ rows, onOpen, highlight = [] }) {
  const mine = new Set(highlight);
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th style={{ width: 34 }}>#</th>
            <th>Profile</th>
            <th>Run by</th>
            <th className="num">Logged</th>
            <th className="num" title="Jobs this profile logged that a colleague had already found">
              Also found
            </th>
            <th className="num">List</th>
            <th className="num">Applied</th>
            <th style={{ width: 150 }}>Worked through</th>
            <th>Last logged</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.profile_id}
                className={mine.has(row.profile_id) ? "is-mine" : undefined}
                style={onOpen ? { cursor: "pointer" } : undefined}
                onClick={onOpen ? () => onOpen(row.profile_id) : undefined}>
              <td className="mono muted num">{row.rank ?? "—"}</td>
              <td>
                <b>{row.name}</b>
                {row.headline && <span className="muted"> · {row.headline}</span>}
                {row.shared === false && <span className="pill off" style={{ marginLeft: 6 }}>off the board</span>}
              </td>
              <td className="muted">{row.person || "nobody"}</td>
              <td className="mono num">{row.logged}</td>
              <td className="mono num" style={{ color: row.duplicates ? "var(--brick)" : undefined }}>
                {row.duplicates}
              </td>
              <td className="mono num">{row.assigned}</td>
              <td className="mono num"><b>{row.applied}</b></td>
              <td>
                <Progress applied={row.applied} skipped={row.skipped} pending={row.pending} />
                <span className="muted mono" style={{ fontSize: 11 }}>{row.done_pct}%</span>
              </td>
              <td className="muted">{sinceText(row.last_logged)}</td>
            </tr>
          ))}
          {!rows.length && (
            <tr><td colSpan={9} className="muted">No profiles to show yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** The strip of numbers behind one profile, used on both dashboards. */
export function ProfileCard({ row, children, onOpen }) {
  const left = row.pending;
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontFamily: "var(--display)", fontWeight: 600, fontSize: 15 }}>{row.name}</div>
          <div className="muted">{row.headline || "—"}{row.person ? ` · ${row.person}` : ""}</div>
        </div>
        {onOpen && <button className="ghost" onClick={onOpen}>Open</button>}
      </div>

      <div className="figures">
        <div><b className="mono">{row.logged}</b><span>logged</span></div>
        <div><b className="mono">{row.assigned}</b><span>on the list</span></div>
        <div><b className="mono">{row.applied}</b><span>applied</span></div>
        <div><b className="mono" style={{ color: left ? "var(--brick)" : "var(--pine)" }}>{left}</b>
             <span>left to do</span></div>
      </div>

      <Progress applied={row.applied} skipped={row.skipped} pending={row.pending} />
      <div className="row muted" style={{ justifyContent: "space-between", fontSize: 12 }}>
        <span>{row.done_pct}% worked through</span>
        <span>{row.all_time} applications all time</span>
      </div>
      {/* A card about how much this identity applied for is half the story if
          it says nothing about the test it owes a client. Only drawn when
          there is one — a permanent "0 take-homes" is noise. */}
      {row.assessments_open > 0 && (
        <div style={{ fontSize: 12,
                      color: row.assessments_overdue ? "var(--brick)" : undefined }}>
          {row.assessments_open} take-home{row.assessments_open === 1 ? "" : "s"} outstanding
          {row.assessments_overdue
            ? ` · ${row.assessments_overdue} past the deadline`
            : ""}
        </div>
      )}
      {children}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Developers, and what the applications turned into.

   Everything above this line counts effort. Everything below it counts what
   the effort produced, which is a different question and needs its own shapes.
   -------------------------------------------------------------------------- */

export const MODE_LABELS = {
  video: "video call",
  call: "phone call",
  onsite: "on site",
  async: "written",
};

export const AVAILABILITY_LABELS = {
  open: "taking work",
  limited: "limited",
  booked: "booked up",
};

/** Only ever put an http(s) link in an href.
 *
 * The same rule as api.safeUrl, kept here so a widget has no reason to reach
 * into the api module. Meeting links and resume links are typed by people and
 * land in an href on somebody else's screen.
 */
function safeLink(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}

/** Whether the developer behind a profile could actually start.
 *
 * A BD reads this before applying under a profile. Winning an interview for
 * somebody who cannot take the work costs the client goodwill as well as the
 * developer an afternoon.
 */
export function Availability({ value, small = false }) {
  const state = value || "open";
  const tone = state === "open" ? "on" : state === "booked" ? "off" : "";
  return (
    <span className={`pill ${tone}`} style={small ? { fontSize: 10 } : undefined}>
      {AVAILABILITY_LABELS[state] || state}
    </span>
  );
}

/** A comma-separated skills field, as something readable. */
export function Skills({ value, limit = 8 }) {
  const parts = (value || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return <span className="muted">no skills listed</span>;
  return (
    <span className="row" style={{ gap: 5 }}>
      {parts.slice(0, limit).map((skill) => (
        <span className="pill" key={skill}>{skill}</span>
      ))}
      {parts.length > limit && <span className="muted">+{parts.length - limit} more</span>}
    </span>
  );
}

/** Put a value on the clipboard.
 *
 * The clipboard API does not exist on plain http, so a failure is swallowed:
 * the value is on the screen either way, and an error about copying an email
 * address helps nobody.
 */
export function CopyButton({ value, label = "copy" }) {
  const [done, setDone] = React.useState(false);
  if (!value) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      setTimeout(() => setDone(false), 1400);
    } catch {
      /* clipboard blocked — nothing useful to say about it */
    }
  };
  return <button className="link" onClick={copy}>{done ? "copied" : label}</button>;
}

/** Applications in, interviews out, offers at the end of it.
 *
 * Drawn as steps rather than a funnel shape on purpose. A real funnel encodes
 * each ratio twice — once in the number, once in the width — and the width is
 * always the less accurate of the two. The rates are said in words underneath
 * instead, where they can be qualified.
 */
export function Funnel({ data, note = "", awaiting = 0 }) {
  if (!data) return null;
  const steps = [
    { label: "applications sent", value: data.applications,
      foot: data.scoped_to_cycle ? "this cycle" : "all time" },
    { label: "interviews", value: data.interviews,
      foot: data.applications ? `${data.interview_rate}% of applications` : "—" },
    { label: "offers", value: data.offers,
      foot: data.interviews ? `${data.offer_rate}% of interviews` : "—" },
    { label: "hired", value: data.hired, foot: data.hired ? "work won" : "—" },
  ];
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="funnel">
        {steps.map((step, i) => (
          <React.Fragment key={step.label}>
            {i > 0 && <span className="funnel-arrow" aria-hidden="true">→</span>}
            <div className="funnel-step">
              <b className="mono">{step.value}</b>
              <span>{step.label}</span>
              <span className="foot">{step.foot}</span>
            </div>
          </React.Fragment>
        ))}
      </div>
      {note && <p className="muted">{note}</p>}
      {awaiting > 0 && (
        <p className="muted">
          {awaiting} interview{awaiting === 1 ? " has" : "s have"} been and gone without
          anybody saying how it went, so these rates are understated until they do.
        </p>
      )}
    </div>
  );
}

/** The next interview still ahead, sized to be read before anything else. */
export function NextInterview({ row, onOpen, openLabel = "All interviews" }) {
  if (!row) return null;
  return (
    <section className="card pad row headline" style={{ justifyContent: "space-between" }}>
      <div>
        <div className="mono headline-figure" style={{ fontSize: 32 }}>{row.when.time}</div>
        <div>
          <b style={{ fontFamily: "var(--display)", fontSize: 15 }}>
            {row.is_today ? "Today" : row.when.label} · {row.client || "a client"}
          </b>
          <p className="muted" style={{ marginTop: 2 }}>
            {row.role || "role not recorded"} · applying as <b>{row.profile}</b> ·{" "}
            {MODE_LABELS[row.mode] || row.mode} · {row.duration_minutes} min · Eastern time
          </p>
        </div>
      </div>
      <div className="row">
        {safeLink(row.link) && (
          <a className="btn go" href={safeLink(row.link)} target="_blank" rel="noreferrer noopener">
            Join
          </a>
        )}
        {onOpen && <button className="ghost" onClick={onOpen}>{openLabel}</button>}
      </div>
    </section>
  );
}

/** The rungs, in order, as a person would say them.
 *
 * Ordered because the order is the product: a screening call and a final round
 * are not the same event, and a team that cannot tell them apart cannot see
 * where its conversations die. Kept here rather than in each screen so the
 * words are the same wherever a stage is shown.
 */
export const STAGE_LABELS = {
  screening: "screening call",
  technical: "technical round",
  assessment: "take-home",
  final: "final round",
  offer: "offer talks",
};

export const ASSESSMENT_LABELS = {
  sent: "sent",
  in_progress: "in progress",
  submitted: "submitted",
  passed: "passed",
  failed: "failed",
};

/** Which round of how many, and what it followed on from.
 *
 * A conversation is rarely one sitting, and a flat list of interviews makes a
 * client who ran four rounds before saying no look exactly like four clients
 * who each said no after one call. Those are opposite problems.
 */
export function Round({ row }) {
  if (!row || (row.rounds || 1) < 2) return null;
  return (
    <span className="muted" style={{ fontSize: 11 }} title={
      row.follows
        ? `Booked out of the ${STAGE_LABELS[row.follows.stage] || row.follows.stage}`
          + ` on ${row.follows.when.label}.`
        : undefined}>
      round {row.round} of {row.rounds}
      {row.follows ? ` · after the ${STAGE_LABELS[row.follows.stage] || row.follows.stage}` : ""}
    </span>
  );
}

/** The posting a conversation came out of.
 *
 * Six things, and a BD reading a client's reply three weeks later wants all of
 * them: the title, the client, where it was applied, where the posting is
 * written out, which board it came off, and the day it went. Going back to the
 * job record for the last two is exactly the retyping the record exists to
 * stop, so the whole row travels onto the interview rather than a useful-looking
 * subset of it.
 *
 * Both links, never one. They are usually the same on the day and rarely the
 * same three weeks later — an expired posting redirects to a board's home page
 * and takes the wording with it, and the wording is what the reply is about.
 */
export function JobDetail({ job, showTitle = false }) {
  if (!job) return null;
  const apply = safeLink(job.url);
  const spec = safeLink(job.description_url);
  const foot = [job.platform, job.applied_on ? `applied ${job.applied_on}` : ""]
    .filter(Boolean).join(" · ");

  return (
    <div style={{ fontSize: 11, lineHeight: 1.5 }}>
      {showTitle && job.title && (
        <div className="truncate" style={{ fontSize: 12 }}>{job.title}</div>
      )}
      {(apply || spec) && (
        <div>
          {spec && (
            <a href={spec} target="_blank" rel="noreferrer noopener"
               title={job.description_url}>the posting</a>
          )}
          {spec && apply && " · "}
          {apply && (
            <a href={apply} target="_blank" rel="noreferrer noopener" title={job.url}>
              where it was applied
            </a>
          )}
        </div>
      )}
      {foot && <div className="muted">{foot}</div>}
    </div>
  );
}

/** Attach the posting a client is replying about, without retyping it.
 *
 * The mirror of pressing *they replied* on the job record: same result, from
 * the other direction, for somebody who is already in the diary. Picking a row
 * carries the title, the client and both links onto the interview, so the two
 * ways into a conversation produce the same row rather than one good one and
 * one typed out of memory.
 *
 * `onSearch` is a prop rather than a call into the api module, because nothing
 * in this file talks to the server — the same reason safeLink is duplicated
 * here instead of imported.
 */
export function JobPicker({ value, onPick, onClear, onSearch, disabled = false }) {
  const [q, setQ] = React.useState("");
  const [rows, setRows] = React.useState([]);
  const [busy, setBusy] = React.useState(false);
  const typing = React.useRef(null);

  React.useEffect(() => {
    clearTimeout(typing.current);
    if (!q.trim() || disabled) {
      setRows([]);
      return undefined;
    }
    // A short pause is the signal somebody has finished pasting. One request
    // per keystroke would be slower and no more useful.
    typing.current = setTimeout(() => {
      setBusy(true);
      Promise.resolve(onSearch(q.trim()))
        .then((found) => setRows(found || []))
        .catch(() => setRows([]))
        .finally(() => setBusy(false));
    }, 250);
    return () => clearTimeout(typing.current);
  }, [q, disabled, onSearch]);

  if (value) {
    return (
      <div className="card pad stack" style={{ gap: 6 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <b style={{ fontSize: 13 }}>{value.title || "Untitled posting"}</b>
            <div className="muted" style={{ fontSize: 12 }}>
              {value.company || "no client recorded"}
            </div>
          </div>
          <button className="link" onClick={() => { setQ(""); onClear(); }}>
            not this one
          </button>
        </div>
        <JobDetail job={value} />
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <input style={{ width: "100%" }} value={q} disabled={disabled}
             placeholder={disabled
               ? "Pick which profile first"
               : "Paste the client, the job title, or the link"}
             onChange={(e) => setQ(e.target.value)} />
      <span className="muted" style={{ fontSize: 12 }}>
        {busy ? "Searching the record…"
          : q.trim() && !rows.length ? "Nothing in the record matches that."
            : "Optional. Attaching it carries the title, the client and both links across, "
              + "and keeps the posting readable once the apply link expires."}
      </span>
      {rows.length > 0 && (
        <div className="card scroll" style={{ maxHeight: 210 }}>
          <table className="board">
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.job_id}-${row.profile_id}`}>
                  <td className="truncate" style={{ maxWidth: 260 }}>
                    {row.title || <span className="muted">no title recorded</span>}
                    <div className="muted" style={{ fontSize: 11 }}>
                      {[row.company, row.platform,
                        row.applied_on ? `applied ${row.applied_on}` : ""]
                        .filter(Boolean).join(" · ") || "—"}
                    </div>
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="link" onClick={() => { setQ(""); onPick(row); }}>
                      this one
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** The take-homes that came out of one conversation, as chips on its row.
 *
 * On the interview rather than only in its own tab, because when a client has
 * sent a test the test *is* the state of that conversation, and a diary that
 * cannot say so sends people to a second screen to find out whether they are
 * waiting on the client or on their own developer.
 */
export function AssessmentChips({ rows }) {
  if (!rows?.length) return null;
  return (
    <span className="row" style={{ gap: 5 }}>
      {rows.map((row) => (
        <span key={row.id}
              className={row.overdue ? "pill off" : row.status === "passed" ? "pill on" : "pill"}
              title={`${row.title || "take-home"}${row.due ? ` · due ${row.due.label}` : ""}`}>
          {row.overdue ? "take-home overdue" : `take-home ${ASSESSMENT_LABELS[row.status] || row.status}`}
        </span>
      ))}
    </span>
  );
}


/** Interviews as a table.
 *
 * Two people read this and they can do different things to it. `canBook` is
 * the BD or the manager: they agreed the time with the client, so the status,
 * the outcome and the row itself are theirs to change. Without it — a
 * developer — the booking is read-only and the only thing they can write is
 * the half nobody else can answer: what happened on the call.
 *
 * Leave `onChange` off entirely for a screen that only reads.
 */
export function InterviewRows({ rows, showProfile = true, onChange, onRemove,
                               onNextRound, canBook = true,
                               empty = "Nothing scheduled." }) {
  const [open, setOpen] = React.useState(null);
  if (!rows?.length) return <div className="card pad muted">{empty}</div>;
  const columns = showProfile ? 8 : 7;
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th style={{ width: 128 }}>When · ET</th>
            {showProfile && <th>Applied as</th>}
            <th>Client</th>
            <th>Role</th>
            <th>How</th>
            <th style={{ width: 130 }}>Round</th>
            <th style={{ width: 200 }}>How it went</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <React.Fragment key={row.id}>
              <tr style={{ opacity: row.status === "cancelled" ? 0.5 : 1 }}>
                <td>
                  <b className="mono">{row.when.time}</b>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {row.when.label.split(" · ")[0]}
                  </div>
                </td>
                {showProfile && (
                  <td>
                    <b>{row.profile}</b>
                    {row.developer && (
                      <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                    )}
                  </td>
                )}
                <td>{row.client || <span className="muted">—</span>}</td>
                <td style={{ maxWidth: 280 }}>
                  <div className="truncate">
                    {row.role || <span className="muted">—</span>}
                  </div>
                  {/* The posting itself. A developer opening this an hour
                      before the call wants the wording that was applied to,
                      and the apply link is usually dead by then — which is
                      exactly why both are here rather than one. */}
                  <JobDetail job={row.job} />
                  <AssessmentChips rows={row.assessments} />
                </td>
                <td className="muted">
                  {MODE_LABELS[row.mode] || row.mode}
                  <div style={{ fontSize: 11 }}>{row.duration_minutes} min</div>
                </td>
                <td>
                  {onChange ? (
                    <select value={row.stage || "screening"}
                            onChange={(e) => onChange(row.id, { stage: e.target.value })}>
                      {Object.entries(STAGE_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>{label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="muted">
                      {STAGE_LABELS[row.stage] || row.stage || "—"}
                    </span>
                  )}
                  <div><Round row={row} /></div>
                </td>
                <td>
                  {onChange ? (
                    <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                      <select value={row.status}
                              onChange={(e) => onChange(row.id, { status: e.target.value })}>
                        <option value="scheduled">scheduled</option>
                        <option value="done">happened</option>
                        <option value="no_show">no show</option>
                        <option value="cancelled">cancelled</option>
                      </select>
                      {(row.is_past || row.status === "done") && row.status !== "cancelled" && (
                        <select value={row.outcome}
                                onChange={(e) => onChange(row.id, { outcome: e.target.value })}>
                          <option value="pending">not said yet</option>
                          <option value="passed">next round</option>
                          <option value="offer">offer</option>
                          <option value="hired">hired</option>
                          <option value="rejected">no</option>
                        </select>
                      )}
                    </div>
                  ) : (
                    <span className={row.outcome === "rejected" ? "pill off"
                      : ["offer", "hired", "passed"].includes(row.outcome) ? "pill on" : "pill"}>
                      {row.status === "scheduled" ? "scheduled" : row.outcome}
                    </span>
                  )}
                  {row.awaiting_outcome && (
                    <div style={{ fontSize: 11, color: "var(--brick)" }}>
                      it happened — nobody has said how it went
                    </div>
                  )}
                  {/* Cleared, and nothing booked after it. The quietest way
                      this product loses work: it reads as a success on every
                      screen while the client waits for somebody to arrange the
                      next round. */}
                  {row.cleared_nothing_next && onNextRound && (
                    <div style={{ fontSize: 11, color: "var(--brick)" }}>
                      cleared — nothing booked after it
                    </div>
                  )}
                  {row.reported_by && (
                    <div className="muted" style={{ fontSize: 11 }}>
                      {row.reported_by} reported it{row.reported_at ? ` · ${row.reported_at}` : ""}
                    </div>
                  )}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {safeLink(row.link) && (
                    <a href={safeLink(row.link)} target="_blank" rel="noreferrer noopener">open</a>
                  )}
                  {/* Offered on anything that has happened and was not a no,
                      not only on the stalled ones — the moment a developer
                      says "they want me to meet the team" is the moment this
                      should cost one press. */}
                  {onNextRound && row.status !== "draft" && row.status !== "cancelled"
                    && row.outcome !== "rejected" && row.outcome !== "hired"
                    && (row.is_past || row.status === "done") && (
                    <button className="link" onClick={() => onNextRound(row)}>
                      next round
                    </button>
                  )}
                  <button className="link"
                          onClick={() => setOpen(open === row.id ? null : row.id)}>
                    {open === row.id ? "close" : row.debrief ? "notes ✓" : "notes"}
                  </button>
                  {onRemove && <button className="link" onClick={() => onRemove(row)}>remove</button>}
                </td>
              </tr>
              {open === row.id && (
                <tr>
                  <td colSpan={columns}>
                    <InterviewNotes row={row} canBook={canBook} onChange={onChange}
                                    onClose={() => setOpen(null)} />
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The two halves of an interview that are prose rather than a dropdown.
 *
 * The brief is the BD's, written when they booked it. The debrief is the
 * developer's, written after the call. Separate fields on purpose: one typed
 * over the other loses what the client actually asked for, and there is no
 * second copy of that anywhere.
 *
 * Both sides may write the debrief — a BD who took it over the phone should
 * not have to wait for the developer to sign in — but only the BD may touch
 * the brief, because only they were on the thread with the client.
 */
function InterviewNotes({ row, canBook, onChange, onClose }) {
  const [draft, setDraft] = React.useState(row.debrief || "");
  const [saving, setSaving] = React.useState(false);
  const dirty = draft.trim() !== (row.debrief || "").trim();

  const save = async () => {
    setSaving(true);
    try {
      await onChange(row.id, { debrief: draft.trim() });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 10, padding: "10px 2px" }}>
      <div>
        <label>What the BD wrote when they booked it</label>
        <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
          {row.notes || "Nothing was written down."}
        </p>
      </div>

      <div>
        <label htmlFor={`debrief-${row.id}`}>How the call went</label>
        <p className="hint" style={{ margin: "3px 0 5px", maxWidth: 620 }}>
          {canBook
            ? "Whoever was in the room usually writes this."
            : "You were on the call — this is the part only you can answer."}
        </p>
        {onChange ? (
          <textarea id={`debrief-${row.id}`} rows={3} style={{ width: "100%" }}
                    placeholder="Went well. They are sending a take-home by Friday."
                    value={draft} onChange={(e) => setDraft(e.target.value)} />
        ) : (
          <p className="muted">{row.debrief || "Nothing recorded yet."}</p>
        )}
      </div>

      {onChange && (
        <div className="row" style={{ gap: 10 }}>
          <button onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving…" : "Save the note"}
          </button>
          <button className="ghost" onClick={onClose}>Close</button>
          <span className="muted">
            {row.reported_by
              ? `Last reported by ${row.reported_by}${row.reported_at ? ` · ${row.reported_at}` : ""}.`
              : "Nobody has reported on this one yet."}
          </span>
        </div>
      )}
    </div>
  );
}

/** Replies with no time on them yet.
 *
 * Its own table rather than a row in the diary, because these have no time to
 * be sorted by and nothing to turn up to. What they need is one field — the
 * time — and putting it in is what turns the row into a real booking. There is
 * deliberately no confirm step after it: agreeing the time *is* the
 * confirmation, and a second button is one somebody forgets, leaving a real
 * interview counted nowhere.
 */
export function WaitingOnTime({ rows, onChange, onRemove, suggested }) {
  const [draft, setDraft] = React.useState({});
  if (!rows?.length) return null;

  const put = async (row) => {
    const when = draft[row.id] || suggested;
    if (!when) return;
    await onChange(row.id, { scheduled_at: when });
    setDraft((all) => {
      const next = { ...all };
      delete next[row.id];
      return next;
    });
  };

  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th>Client</th>
            <th>Role</th>
            {/* Everything the record already knows about the posting they
                replied about. Without it this table is four words a colleague
                typed, and answering the client means going back to All jobs to
                find out which board it came off and when it went. */}
            <th style={{ minWidth: 200 }}>The posting</th>
            <th>Applied as</th>
            <th style={{ width: 130 }}>Round</th>
            <th style={{ width: 230 }}>Time · ET</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.client || <span className="muted">—</span>}</td>
              <td className="truncate" style={{ maxWidth: 260 }}>
                {row.role || <span className="muted">—</span>}
              </td>
              <td>
                {row.job
                  ? <JobDetail job={row.job} showTitle />
                  : <span className="muted" style={{ fontSize: 11 }}>
                      logged without a posting
                    </span>}
              </td>
              <td>
                <b>{row.profile}</b>
                {row.developer && (
                  <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                )}
              </td>
              <td>
                <select value={row.stage || "screening"}
                        onChange={(e) => onChange(row.id, { stage: e.target.value })}>
                  {Object.entries(STAGE_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </td>
              <td>
                <input type="datetime-local" style={{ width: "100%" }}
                       value={draft[row.id] ?? suggested ?? ""}
                       onChange={(e) => setDraft((all) => ({ ...all, [row.id]: e.target.value }))} />
              </td>
              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                <button onClick={() => put(row)}>Book it</button>
                {onRemove && <button className="link" onClick={() => onRemove(row)}>remove</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/** How many conversations reached each rung, and how many died there.
 *
 * The thing a single interviews-to-offers percentage cannot show. A team losing
 * everybody at the technical round has a tooling problem; one losing them at
 * the final round has a rate or an availability problem. Both look identical in
 * one number, and they call for opposite fixes.
 */
export function StageLadder({ rows }) {
  if (!rows?.length) return null;
  const widest = Math.max(...rows.map((row) => row.reached), 1);
  if (!rows.some((row) => row.reached)) return null;

  return (
    <section className="card pad stack" style={{ gap: 10 }}>
      <div>
        <h3>Where the conversations get to</h3>
        <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
          Reached each round, and what happened there. Cleared went on; lost ended there.
        </p>
      </div>
      <div className="stack" style={{ gap: 7 }}>
        {rows.map((row) => (
          <div key={row.stage} className="row" style={{ gap: 10, alignItems: "center" }}>
            <span style={{ minWidth: 110, fontSize: 12 }}>
              {STAGE_LABELS[row.stage] || row.stage}
            </span>
            <span className="mono" style={{ minWidth: 28, textAlign: "right" }}>
              {row.reached}
            </span>
            <span style={{ flex: 1, display: "flex", height: 12, gap: 2 }}>
              <span style={{
                width: `${(row.cleared / widest) * 100}%`,
                background: "var(--pine)", borderRadius: 2,
              }} title={`${row.cleared} went on`} />
              <span style={{
                width: `${(row.lost / widest) * 100}%`,
                background: "var(--brick)", borderRadius: 2,
              }} title={`${row.lost} ended here`} />
              <span style={{
                width: `${((row.reached - row.cleared - row.lost) / widest) * 100}%`,
                background: "var(--line, #d8d3c8)", borderRadius: 2,
              }} title={`${row.reached - row.cleared - row.lost} still open`} />
            </span>
            <span className="muted" style={{ minWidth: 96, fontSize: 11, textAlign: "right" }}>
              {row.reached ? `${row.rate}% went on` : "—"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}


/** Every developer, and whether they are free. The manager's version. */
/** Take-homes, read-only, for a dashboard rather than for working through.
 *
 * Its own widget because a deadline is the one thing in this product that goes
 * wrong silently. Every other figure understates itself when nobody touches it
 * — an unreported interview makes a good week look quiet. A missed assessment
 * does the opposite: nothing changes on any screen, the row sits there looking
 * exactly as it did yesterday, and the first anybody hears of it is the
 * client's next email. So the number that leads is `overdue`, and it is shown
 * even when it is zero on a screen that has any at all.
 *
 * `onOpen` points at the screen where they can actually be worked, because a
 * dashboard that reports a problem without a route to it is a dead end.
 */
export function AssessmentBoard({ data, onOpen, heading = "Take-homes and tests",
                                 note = "", limit = 8 }) {
  if (!data) return null;
  const counts = data.counts || {};
  if (!counts.total) return null;

  // Late first, then whatever is due soonest. The order is the priority — a
  // dashboard sorted by anything else makes somebody do the sorting.
  const open = [...(data.open || [])].sort((a, b) => {
    if (a.overdue !== b.overdue) return a.overdue ? -1 : 1;
    if (!a.due) return 1;
    if (!b.due) return -1;
    return a.due.iso.localeCompare(b.due.iso);
  });

  return (
    <section className="card pad stack" style={{ gap: 10 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3>{heading}</h3>
          <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
            {note || "The only work here with a deadline on it."}
          </p>
        </div>
        {onOpen && <button className="ghost" onClick={onOpen}>Open them</button>}
      </div>

      <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
        <Figure value={counts.overdue} label="past the deadline"
                tone={counts.overdue ? "var(--brick)" : undefined} />
        <Figure value={counts.due_soon} label="due within three days" />
        <Figure value={counts.open} label="still open" />
        <Figure value={counts.passed} label="cleared" tone={counts.passed ? "var(--pine)" : undefined} />
      </div>

      {open.length === 0 ? (
        <p className="muted">
          Nothing outstanding. {counts.total} recorded in all.
        </p>
      ) : (
        <div className="scroll">
          <table className="board">
            <thead>
              <tr>
                <th>What</th>
                <th>Client</th>
                <th>Applied as</th>
                <th style={{ width: 150 }}>Due · ET</th>
                <th style={{ width: 120 }}>How far along</th>
              </tr>
            </thead>
            <tbody>
              {open.slice(0, limit).map((row) => (
                <tr key={row.id}>
                  <td className="truncate" style={{ maxWidth: 280 }}>
                    {row.title || <span className="muted">untitled</span>}
                    {row.interview && (
                      <div className="muted" style={{ fontSize: 11 }}>
                        after the {STAGE_LABELS[row.interview.stage] || row.interview.stage}
                      </div>
                    )}
                  </td>
                  <td>{row.client || <span className="muted">—</span>}</td>
                  <td>
                    <b>{row.profile}</b>
                    {row.developer && (
                      <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                    )}
                  </td>
                  <td>
                    {row.due ? (
                      <span style={{
                        color: row.overdue ? "var(--brick)"
                          : row.due_soon ? "var(--petrol)" : undefined,
                      }}>
                        {row.due.label}
                        {row.overdue ? " · late" : row.due_soon ? " · soon" : ""}
                      </span>
                    ) : <span className="muted">none set</span>}
                  </td>
                  <td className={row.overdue ? "pill off" : "pill"}>
                    {ASSESSMENT_LABELS[row.status] || row.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open.length > limit && (
        <p className="muted">{open.length - limit} more not shown.</p>
      )}
    </section>
  );
}

/** One number and what it means. The unit a headline strip is built from. */
function Figure({ value, label, tone }) {
  return (
    <span>
      <span className="mono" style={{ fontSize: 22, color: tone }}>{value || 0}</span>
      <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>{label}</span>
    </span>
  );
}

/** Conversations that were cleared and then stopped.
 *
 * The single most valuable list in this product, and the only one nothing else
 * can produce. Every other warning here is about work not done; this is about
 * work that went *well* and was dropped anyway, because the client said yes and
 * both sides assumed the other was arranging what came next. On every other
 * screen these rows read as successes.
 */
export function Stalled({ rows, onNextRound, limit = 6 }) {
  if (!rows?.length) return null;
  return (
    <section className="card pad stack" style={{ gap: 10 }}>
      <div>
        <h3>Cleared, and nothing booked after</h3>
        <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
          {rows.length === 1 ? "This conversation" : `These ${rows.length} conversations`} cleared
          a round and stopped. Booking the next one carries everything across.
        </p>
      </div>
      <div className="scroll">
        <table className="board">
          <thead>
            <tr>
              <th style={{ width: 128 }}>Last round</th>
              <th>Client</th>
              <th>Role</th>
              <th>Applied as</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((row) => (
              <tr key={row.id}>
                <td>
                  <span style={{ fontSize: 12 }}>
                    {STAGE_LABELS[row.stage] || row.stage}
                  </span>
                  <div className="muted" style={{ fontSize: 11 }}>{row.when.label}</div>
                </td>
                <td>{row.client || <span className="muted">—</span>}</td>
                <td className="truncate" style={{ maxWidth: 240 }}>
                  {row.role || <span className="muted">—</span>}
                </td>
                <td>
                  <b>{row.profile}</b>
                  {row.developer && (
                    <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                  )}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {onNextRound && (
                    <button className="ghost" onClick={() => onNextRound(row)}>
                      Book the next round
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <p className="muted">{rows.length - limit} more not shown.</p>
      )}
    </section>
  );
}

export function DeveloperBoard({ rows, onOpen }) {
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th>Developer</th>
            <th>Applied as</th>
            <th>Availability</th>
            <th className="num">Today</th>
            <th className="num">This week</th>
            <th className="num" title="Interviews that have happened with no outcome recorded">
              Unreported
            </th>
            {/* A take-home is the other claim on this person's week and the one
                a calendar cannot show. "Free on Thursday" is not free when a
                test is due Friday. */}
            <th className="num" title="Take-homes still open against this developer">
              Take-homes
            </th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.user_id}>
              <td>
                <b>{row.name}</b>
                <div className="muted mono" style={{ fontSize: 11 }}>{row.email}</div>
              </td>
              <td>
                {row.profiles.length
                  ? (
                    <span className="row" style={{ gap: 5 }}>
                      {row.profiles.map((p) => <span className="pill on" key={p.id}>{p.name}</span>)}
                    </span>
                  )
                  : <span className="muted">no profile attached — they see an empty screen</span>}
              </td>
              <td>{row.runs ? <Availability value={row.availability} /> : <span className="muted">—</span>}</td>
              <td className="mono num" style={{ color: row.today ? "var(--petrol)" : undefined }}>
                {row.today}
              </td>
              <td className="mono num">{row.week}</td>
              <td className="mono num" style={{ color: row.awaiting_outcome ? "var(--brick)" : undefined }}>
                {row.awaiting_outcome}
              </td>
              <td className="mono num"
                  style={{ color: row.assessments_overdue ? "var(--brick)" : undefined }}
                  title={row.assessments_overdue
                    ? `${row.assessments_overdue} past the deadline` : undefined}>
                {row.assessments_open || 0}
                {row.assessments_overdue ? " !" : ""}
              </td>
              <td style={{ textAlign: "right" }}>
                {onOpen && (
                  <button className="ghost" style={{ padding: "5px 9px", fontSize: 12 }}
                          onClick={() => onOpen(row)}>Open</button>
                )}
              </td>
            </tr>
          ))}
          {!rows.length && (
            <tr><td colSpan={8} className="muted">
              No developers yet. Add one under People and profiles, then attach it to the
              profile it is sold under.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
