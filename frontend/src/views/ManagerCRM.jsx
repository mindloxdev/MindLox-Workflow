import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import { ActionList, plural } from "./Todo.jsx";
import { DateRange, Loading, Segment, STAGE_LABELS } from "./widgets.jsx";

/** Clients.
 *
 * Every other screen in this app is organised by profile, by person or by
 * round. None of them can answer the question a manager is actually asked on
 * the phone: have we been to Northwind before, and how did it go.
 *
 * Nothing here is a new source of truth. It is the same postings, the same
 * conversations and the same tests, grouped by the company instead of by the
 * person who typed them. The only writable thing is the manager's own note, and
 * that changes nobody's work: it does not filter the pool, does not skip
 * anything and does not touch dispatch.
 *
 * Read-only on conversations, for the same reason the manager's stalled list
 * is: whoever runs the profile books the next round. A manager quietly booking
 * into somebody else's client relationship is how one reply becomes two.
 */

const SORTS = [
  { key: "last_activity", label: "Last activity" },
  { key: "client", label: "Client" },
  { key: "status", label: "Status" },
  { key: "applications", label: "Applications sent" },
  { key: "found_twice", label: "Found twice" },
  { key: "open_tests", label: "Open tests" },
  { key: "next_up", label: "Next in the diary" },
];

/** A status is derived, never typed, so it gets the tone its state deserves
 *  rather than one somebody chose. */
const TONE = {
  hired: "on", offer: "on", test_out: "warn", stalled: "warn",
  in_conversation: "", replied: "warn", closed: "off", approached: "",
};

function Pill({ status, label }) {
  const tone = TONE[status] || "";
  return <span className={`pill ${tone}`.trim()}>{label}</span>;
}

function dayLabel(iso) {
  if (!iso) return "—";
  const date = new Date(`${iso}T12:00:00Z`);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric",
                                            year: "numeric", timeZone: "UTC" });
}

/* ── The note ──────────────────────────────────────────────────────────── */

/** The manager's own annotation, and the only thing on this screen that writes.
 *
 * Said plainly on the card that it changes nothing about dispatch. A flag that
 * quietly held jobs back would be a rule whose effect nobody could see, and the
 * reason for a missing job would be invisible on the screen it went missing
 * from. **Already being worked** is surfaced instead, in the dialog a BD
 * already gets as they type a link.
 */
function NoteCard({ clientKey, note, onSaved }) {
  const [draft, setDraft] = useState(note.note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setDraft(note.note || ""); }, [clientKey, note.note]);

  const save = async (patch) => {
    setBusy(true);
    setError("");
    try {
      onSaved(await api.saveClientNote(clientKey, patch));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const dirty = draft.trim() !== (note.note || "").trim();

  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
        <label className="row" style={{ gap: 7 }}>
          <input type="checkbox" checked={!!note.priority} disabled={busy}
                 onChange={(e) => save({ priority: e.target.checked })} />
          <b style={{ fontFamily: "var(--display)" }}>Priority</b>
        </label>
        <label className="row" style={{ gap: 7 }}>
          <input type="checkbox" checked={!!note.being_worked} disabled={busy}
                 onChange={(e) => save({ being_worked: e.target.checked })} />
          <b style={{ fontFamily: "var(--display)" }}>Already being worked</b>
        </label>
        {note.updated_by && (
          <span className="hint">
            Last touched by {note.updated_by}
            {note.updated_at ? ` · ${note.updated_at}` : ""}
          </span>
        )}
      </div>

      <p className="hint" style={{ maxWidth: 700 }}>
        Yours, and advisory. Neither flag filters the pool, skips anything or
        changes what dispatch hands out. <b>Already being worked</b> shows up for
        a BD in the dialog they already get as they type a link, with the same
        way past it — a flag that quietly held jobs back would be a rule nobody
        could see the effect of.
      </p>

      <textarea rows={3} value={draft} disabled={busy}
                placeholder="Approached in March through the CFO. Went quiet after the second round."
                onChange={(e) => setDraft(e.target.value)} />
      <div className="row" style={{ gap: 10 }}>
        <button onClick={() => save({ note: draft.trim() })} disabled={busy || !dirty}>
          {busy ? "Saving…" : "Save the note"}
        </button>
        {error && <span style={{ color: "var(--bad-text)" }}>{error}</span>}
      </div>
    </div>
  );
}

/* ── One client, whole ─────────────────────────────────────────────────── */

function Drawer({ clientKey, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api.client(clientKey).then(setData).catch((err) => setError(err.message));
  }, [clientKey]);

  if (error) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={4} />;

  const { client, conversations, tests, postings, found_twice: twice } = data;

  return (
    <div className="stack" style={{ gap: 14 }}>
      <button className="link back" onClick={onClose}>← Back to the clients</button>

      <div>
        <h1>{client.client}</h1>
        <p className="muted" style={{ marginTop: 3 }}>
          <Pill status={client.status} label={client.status_label} />{" "}
          First approached {dayLabel(client.first_seen)} · last activity{" "}
          {dayLabel(client.last_activity)} ·{" "}
          <b>{client.applications}</b> {plural(client.applications,
            "application sent", "applications sent")}
          {client.applications > 0 && <> ({client.own_jobs} own jobs,{" "}
            {client.others_jobs} others&apos; jobs)</>}
        </p>
        {client.profiles.length > 0 && (
          <p className="hint" style={{ marginTop: 4 }}>
            Applied as {client.profiles.join(", ")}
            {client.bds.length ? ` · run by ${client.bds.join(", ")}` : ""}
            {client.developers.length ? ` · ${client.developers.join(", ")} behind them` : ""}
          </p>
        )}
      </div>

      <NoteCard clientKey={clientKey} note={data.note}
                onSaved={(note) => setData((now) => ({ ...now, note }))} />

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Conversations</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>
            One block per conversation, not one row per sitting. A client who ran
            four rounds is one story; four rows look like four clients who each
            said no once. Read-only here — whoever runs the profile books the
            next round.
          </p>
        </div>
        {conversations.length === 0 ? (
          <div className="card pad muted">Nobody here has spoken to them yet.</div>
        ) : conversations.map((block) => (
          <div className="card pad stack" key={block.rounds[0].id} style={{ gap: 10 }}>
            {block.rounds.map((row) => (
              <div key={row.id} className="stack" style={{ gap: 6 }}>
                <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                  <b className="mono">{row.when.label}</b>
                  <span>
                    {row.rounds > 1 ? `round ${row.round} of ${row.rounds} · ` : ""}
                    {STAGE_LABELS[row.stage] || row.stage}
                  </span>
                  {row.follows && (
                    <span className="hint">
                      after the {STAGE_LABELS[row.follows.stage] || row.follows.stage}
                    </span>
                  )}
                  <span className={row.outcome === "rejected" ? "pill off"
                    : ["offer", "hired", "passed"].includes(row.outcome) ? "pill on" : "pill"}>
                    {row.status === "scheduled" ? "scheduled" : row.outcome}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  as <b>{row.profile}</b>
                  {row.developer ? ` · ${row.developer}` : ""}
                  {row.bd ? ` · booked by ${row.bd}` : ""}
                  {row.reported_by
                    ? ` · ${row.reported_by} reported it${row.reported_at ? ` · ${row.reported_at}` : ""}`
                    : ""}
                </div>
                {/* Two links, named. They go to completely different places and
                    picking the wrong one at two o'clock costs a meeting. */}
                <div className="row" style={{ gap: 12, fontSize: 12 }}>
                  {safeUrl(row.link)
                    ? <a href={safeUrl(row.link)} target="_blank" rel="noreferrer noopener">the meeting</a>
                    : <span className="hint">no meeting link</span>}
                  {safeUrl(row.email_url)
                    ? <a href={safeUrl(row.email_url)} target="_blank" rel="noreferrer noopener">their email</a>
                    : <span className="hint">no email linked</span>}
                </div>
                {(row.notes || row.debrief) && (
                  <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
                    <div>
                      <label>What the BD wrote when they booked it</label>
                      <p className="muted" style={{ marginTop: 2 }}>{row.notes || "Nothing."}</p>
                    </div>
                    <div>
                      <label>How the call went</label>
                      <p className="muted" style={{ marginTop: 2 }}>{row.debrief || "Not reported yet."}</p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Tests</h2>
          <p className="hint" style={{ marginTop: 3 }}>
            What this client set, and where each one stands.
          </p>
        </div>
        {tests.length === 0 ? (
          <div className="card pad muted">They have not set one.</div>
        ) : (
          <div className="card scroll">
            <table className="board">
              <thead>
                <tr><th>What</th><th>Applied as</th><th>Came out of</th>
                    <th>Due · ET</th><th>How far along</th></tr>
              </thead>
              <tbody>
                {tests.map((row) => (
                  <tr key={row.id}>
                    <td>{row.title}</td>
                    <td>{row.profile}</td>
                    <td className="muted">
                      {row.interview
                        ? `after the ${STAGE_LABELS[row.interview.stage] || row.interview.stage}`
                        : "sent cold"}
                    </td>
                    <td className={row.overdue ? "mono" : "mono muted"}
                        style={row.overdue ? { color: "var(--bad-text)" } : undefined}>
                      {row.due ? row.due.label : "none set"}
                      {row.overdue ? " · late" : ""}
                    </td>
                    <td><span className="pill">{row.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Everything we applied to here</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>
            The answer to &ldquo;have we been here before&rdquo;. Newest first.
          </p>
        </div>
        <div className="card scroll">
          <table className="board">
            <thead>
              <tr><th>Job</th><th>Applied as</th><th>Found by</th><th>Platform</th>
                  <th>Applied on</th><th>Links</th></tr>
            </thead>
            <tbody>
              {postings.map((row, i) => (
                <tr key={`${row.job_id}-${row.profile_id}-${i}`}>
                  <td className="truncate">{row.title || "—"}</td>
                  <td>{row.profile}</td>
                  <td className="muted">
                    {row.found_here ? "own job" : "others' job"}
                    {row.bd ? ` · ${row.bd}` : ""}
                  </td>
                  <td className="muted">{row.platform || "—"}</td>
                  <td className="mono muted" style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                    {row.applied_on || "—"}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {safeUrl(row.url)
                      ? <a href={safeUrl(row.url)} target="_blank" rel="noreferrer noopener">apply</a>
                      : <span className="muted">—</span>}
                    {safeUrl(row.description_url) && (
                      <> · <a href={safeUrl(row.description_url)} target="_blank"
                              rel="noreferrer noopener">description</a></>
                    )}
                  </td>
                </tr>
              ))}
              {!postings.length && (
                <tr><td colSpan={6} className="muted">Nothing applied for here yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {twice.length > 0 && (
        <section className="stack" style={{ gap: 10 }}>
          <div>
            <h2>Found twice at this client</h2>
            <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>
              Postings two profiles both went out and found. A run of these at one
              company is a search problem rather than a dispatch problem — two
              people are covering the same ground here.
            </p>
          </div>
          <div className="card scroll">
            <table className="board">
              <thead><tr><th>Job</th><th>Found by</th></tr></thead>
              <tbody>
                {twice.map((row) => (
                  <tr key={row.job_id}>
                    <td className="truncate">{row.title || "—"}</td>
                    <td className="muted">{row.profiles.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── The list ──────────────────────────────────────────────────────────── */

export default function ManagerCRM() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [dateRange, setDateRange] = useState({ dateFrom: "", dateTo: "" });
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("last_activity");
  const [page, setPage] = useState(1);
  const [view, setView] = useState("table");
  const cameFrom = useRef(0);
  const typing = useRef(null);

  const load = useCallback(async () => {
    try {
      setData(await api.clients({
        dateFrom: dateRange.dateFrom, dateTo: dateRange.dateTo,
        status, q, sort, page,
      }));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, [dateRange, status, q, sort, page]);

  // A pause is the signal somebody has finished pasting; one request per
  // keystroke across a workspace of clients would be slower and worse.
  useEffect(() => {
    clearTimeout(typing.current);
    typing.current = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(typing.current);
  }, [load, q]);

  useEffect(() => { setPage(1); }, [dateRange, status, q, sort]);

  const enter = (key) => {
    cameFrom.current = window.scrollY;
    setOpen(key);
    window.scrollTo({ top: 0 });
  };
  const leave = () => {
    setOpen(null);
    window.scrollTo({ top: cameFrom.current });
    load();
  };

  if (open) return <Drawer clientKey={open} onClose={leave} />;
  if (error && !data) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={5} figures />;

  const { clients, totals, page: paging, statuses } = data;

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Clients</h1>
          <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
            Everything already recorded, grouped by the company instead of by the
            person who typed it. <b>{totals.clients}</b>{" "}
            {plural(totals.clients, "client", "clients")},{" "}
            <b>{totals.applications}</b> applications sent between them. Nothing
            here books, reschedules or settles anything.
          </p>
        </div>
        <div className="row">
          <DateRange {...dateRange} onChange={setDateRange} />
          <button className="ghost" onClick={() =>
            download(api.clientsExportPath({
              dateFrom: dateRange.dateFrom, dateTo: dateRange.dateTo, status, q,
            }), "clients.xlsx").catch((err) => setError(err.message))}>
            Download as Excel
          </button>
        </div>
      </div>

      {error && <div className="notice">{error}</div>}

      <ActionList
        items={(data.needs_you || []).map((item) => ({
          key: item.key,
          level: item.level,
          title: `${item.count} ${plural(item.count, "client has", "clients have")} ${item.title}.`,
          body: `${item.body} ${item.clients.map((c) => c.client).join(", ")}`
              + (item.count > item.clients.length
                 ? ` and ${item.count - item.clients.length} more.` : "."),
          action: { label: "Open the first", onClick: () => enter(item.clients[0].client_key) },
        }))}
        lead="Hardest first. Each one has the button that opens the client it is about."
        empty={{
          title: "No client is waiting on you.",
          body: "Nobody is waiting on a time, no test is past its deadline, "
              + "nothing has gone quiet and nothing cleared a round without a "
              + "next one booked.",
        }} />

      <section className="stack" style={{ gap: 10 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2>Every client</h2>
            <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>
              Status is worked out from what is already recorded, never typed —
              a status somebody sets by hand is one somebody forgets to change.
            </p>
          </div>
          {/* A board is easier to show a client; a table is easier to read on a
              Monday, which is what this screen is mostly for. */}
          <Segment label="Shown as" value={view} onChange={setView}
                   items={[{ key: "table", label: "Table" },
                           { key: "board", label: "Board" }]} />
        </div>

        <div className="card pad row" style={{ gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 300px" }}>
            <label htmlFor="crm-q">Narrow this list</label>
            <input id="crm-q" style={{ width: "100%", marginTop: 4 }} value={q}
                   placeholder="A client, a profile, a BD or a developer"
                   onChange={(e) => setQ(e.target.value)} />
          </div>
          <label>
            Status&nbsp;
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">any</option>
              {statuses.map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label} ({totals.by_status[row.key] || 0})
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort by&nbsp;
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map((row) => (
                <option key={row.key} value={row.key}>{row.label}</option>
              ))}
            </select>
          </label>
        </div>

        {clients.length === 0 ? (
          <div className="card pad muted">
            Nothing matches that. Clear the search, or widen the dates.
          </div>
        ) : view === "board" ? (
          <div className="board-cols">
            {statuses.filter((s) => totals.by_status[s.key]).map((column) => (
              <div className="board-col" key={column.key}>
                <div className="board-col-head">
                  <b>{column.label}</b>
                  <span className="mono">{totals.by_status[column.key]}</span>
                </div>
                {clients.filter((row) => row.status === column.key).map((row) => (
                  <button className="board-card" key={row.client_key}
                          onClick={() => enter(row.client_key)}>
                    <b>{row.client}</b>
                    <span className="muted">
                      {row.applications} sent · {dayLabel(row.last_activity)}
                    </span>
                    {row.note.priority && <span className="pill warn">priority</span>}
                  </button>
                ))}
                {!clients.some((row) => row.status === column.key) && (
                  <p className="hint">None on this page.</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="card scroll">
            <table className="board">
              <thead>
                <tr>
                  <th>Client</th><th>Status</th>
                  <th className="num">Applications sent</th>
                  <th className="num">Own jobs</th>
                  <th className="num">Others&apos; jobs</th>
                  <th className="num">Found twice</th>
                  <th>Applied as</th><th>Run by</th><th>Developers</th>
                  <th>Furthest round</th>
                  <th className="num">Open tests</th>
                  <th>Next in the diary</th><th>Last activity</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((row) => (
                  <tr key={row.client_key} style={{ cursor: "pointer" }}
                      onClick={() => enter(row.client_key)}>
                    <td>
                      <b>{row.client}</b>
                      {row.note.priority && (
                        <span className="pill warn" style={{ marginLeft: 6 }}>priority</span>
                      )}
                      {row.note.being_worked && (
                        <span className="pill" style={{ marginLeft: 6 }}>being worked</span>
                      )}
                    </td>
                    <td><Pill status={row.status} label={row.status_label} /></td>
                    <td className="mono num"><b>{row.applications}</b></td>
                    <td className="mono num">{row.own_jobs}</td>
                    <td className="mono num">{row.others_jobs}</td>
                    <td className="mono num"
                        style={{ color: row.found_twice ? "var(--bad-text)" : undefined }}>
                      {row.found_twice}
                    </td>
                    <td className="muted truncate">{row.profiles.join(", ") || "—"}</td>
                    <td className="muted truncate">{row.bds.join(", ") || "—"}</td>
                    <td className="muted truncate">{row.developers.join(", ") || "—"}</td>
                    <td className="muted">
                      {row.furthest ? (STAGE_LABELS[row.furthest] || row.furthest) : "—"}
                    </td>
                    <td className="mono num"
                        style={{ color: row.overdue_tests ? "var(--bad-text)" : undefined }}>
                      {row.open_tests}
                    </td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>
                      {row.next_up ? row.next_up.when.label : "—"}
                    </td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>
                      {dayLabel(row.last_activity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="hint" style={{ maxWidth: 760 }}>
          <b>Applications sent</b> is everything applied for at this client, and
          the two columns after it are that same number split — <b>own jobs</b> are
          the ones somebody went out and found, <b>others&apos; jobs</b> are the ones
          a colleague found and handed over. <b>Found twice</b> counts postings,
          not people: two profiles finding one job is one piece of duplicated
          effort. Click any row to open that client.
        </p>

        {paging.pages > 1 && (
          <div className="row" style={{ gap: 10 }}>
            <button className="ghost" disabled={paging.page <= 1}
                    onClick={() => setPage((n) => Math.max(1, n - 1))}>Back</button>
            <span className="muted">Page {paging.page} of {paging.pages}</span>
            <button className="ghost" disabled={paging.page >= paging.pages}
                    onClick={() => setPage((n) => n + 1)}>More</button>
          </div>
        )}
      </section>
    </div>
  );
}
