import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, safeUrl } from "../api.js";
import { DateRange, Loading, STAGE_LABELS } from "./widgets.jsx";
import { useToast } from "./shell.jsx";

/** Every job ever applied for, searchable, with an interview one click away.
 *
 * The screen you open with a client's reply still on the other monitor. Paste
 * in whatever you copied out of it — the company, the job title, the link —
 * find the row, and start the conversation from it. That is what carries the
 * title, the client and both links onto the interview instead of them being
 * typed again, differently, out of an email.
 *
 * Not scoped to a cycle, on purpose. A reply arrives three weeks after the
 * application that earned it, by which time that cycle is closed and gone from
 * every other screen in the app. This one goes back to the beginning.
 */

const PAGE = 50;

export default function JobRecord({ profiles = [], onOpenInterviews }) {
  const [q, setQ] = useState("");
  const [profileId, setProfileId] = useState("");
  const [dateRange, setDateRange] = useState({ dateFrom: "", dateTo: "" });
  const [data, setData] = useState(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const [starting, setStarting] = useState(null);   // the row being turned into one
  // Something was started this session, so offer the way to it.
  const [started, setStarted] = useState(false);
  const [stage, setStage] = useState("screening");
  // The row being corrected, and the draft of it. A posting is one shared row,
  // so this edit reaches every profile holding it — which is why the server
  // only allows it to whoever first logged the job.
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState(null);
  const typing = useRef(null);

  const load = useCallback(async (search, who, at, range) => {
    setBusy(true);
    try {
      setData(await api.jobRecord({
        q: search, profileId: who || null, limit: PAGE, offset: at * PAGE,
        dateFrom: range.dateFrom, dateTo: range.dateTo,
      }));
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  }, []);

  // Typing in a search box should not be one request per keystroke. A short
  // pause is the signal that somebody has finished pasting.
  useEffect(() => {
    clearTimeout(typing.current);
    typing.current = setTimeout(() => load(q, profileId, page, dateRange), q ? 250 : 0);
    return () => clearTimeout(typing.current);
  }, [q, profileId, page, dateRange, load]);

  // A new search starts at the beginning. Without this, searching from page
  // four shows an empty result and reads as "nothing found".
  useEffect(() => { setPage(0); }, [q, profileId, dateRange]);

  const showToday = () => {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York",
      year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const value = `${parts.find((p) => p.type === "year")?.value}-${parts.find((p) => p.type === "month")?.value}-${parts.find((p) => p.type === "day")?.value}`;
    setDateRange({ dateFrom: value, dateTo: value });
  };

  const start = async (row) => {
    setBusy(true);
    try {
      const made = await api.createInterview({
        profile_id: row.profile_id,
        job_id: row.job_id,
        stage,
        // No time yet — the client has replied, nothing has been agreed. It
        // lands in "waiting on a time" until somebody puts one on it.
        scheduled_at: "",
      });
      setStarting(null);
      // The toast says what happened; the route to it is the button below,
      // which is where somebody would look for it anyway.
      toast(`${made.client || "That job"} is waiting on a time under ${made.profile}.`);
      setStarted(true);
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const rowKey = (row) => `${row.job_id}-${row.profile_id}`;

  const openEditor = (row) => {
    if (editing === rowKey(row)) { setEditing(null); setDraft(null); return; }
    setStarting(null);
    setEditing(rowKey(row));
    setDraft({
      title: row.title || "", company: row.company || "",
      platform: row.platform || "", url: row.url || "",
      description_url: row.description_url || "",
    });
  };

  const saveEdit = async (row) => {
    setBusy(true);
    try {
      const saved = await api.editJob(row.job_id, draft);
      // Patch the row in place rather than refetching. The correction is
      // already the truth on the server, and a reload would throw away the
      // page and the search that got somebody here.
      setData((current) => current && {
        ...current,
        rows: current.rows.map((r) => (r.job_id === row.job_id
          ? { ...r, title: saved.title, company: saved.company,
              platform: saved.platform, url: saved.url,
              description_url: saved.description_url }
          : r)),
      });
      setEditing(null);
      setDraft(null);
      toast("Corrected. Everyone holding this posting sees the new wording.");
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const withdraw = async (row) => {
    const label = row.title || row.company || "this job";
    const ok = window.confirm(
      "Withdraw " + row.profile + "'s application to " + label + "?\n\n"
      + "The posting itself stays, so colleagues who applied to it keep their "
      + "record. Only this profile's entry goes, and the job becomes one this "
      + "profile can be offered again.");
    if (!ok) return;
    setBusy(true);
    try {
      await api.deleteEntry(row.job_id, row.profile_id);
      setData((current) => current && {
        ...current,
        rows: current.rows.filter(
          (r) => !(r.job_id === row.job_id && r.profile_id === row.profile_id)),
        total: Math.max(0, (current.total || 1) - 1),
      });
      toast(row.profile + "'s entry was withdrawn.");
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const total = data?.total || 0;
  const pages = Math.ceil(total / PAGE);

  return (
    <section className="stack" style={{ gap: 12 }}>
      <div>
        <h2>Every job applied for</h2>
        <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
          Everything ever applied for, all the way back. Search what the client
          mentioned, then start the interview from the row.
        </p>
      </div>

      <div className="card pad row" style={{ gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px" }}>
          <label htmlFor="rec-q">Search</label>
          <input id="rec-q" style={{ width: "100%", marginTop: 4 }} value={q}
                 placeholder="Paste the client, the job title, or the link"
                 onChange={(e) => setQ(e.target.value)} />
        </div>
        {profiles.length > 1 && (
          <div style={{ flex: "0 1 220px" }}>
            <label htmlFor="rec-profile">Applied as</label>
            <select id="rec-profile" style={{ width: "100%", marginTop: 4 }} value={profileId}
                    onChange={(e) => setProfileId(e.target.value)}>
              <option value="">every profile</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}
        <div style={{ flex: "0 1 auto" }}>
          <label>Applied date</label>
          <div className="row" style={{ marginTop: 4, gap: 8 }}>
            <button className={!dateRange.dateFrom && !dateRange.dateTo ? "ghost" : ""}
                    onClick={showToday}>Today</button>
            <DateRange {...dateRange} onChange={setDateRange} />
          </div>
        </div>
        <div className="row" style={{ alignItems: "flex-end", gap: 8 }}>
          <span className="muted">
            {busy ? "Searching…"
              : q ? `${total} match${total === 1 ? "" : "es"}`
                : `${total} logged`}
          </span>
        </div>
      </div>

      {started && onOpenInterviews && (
        <div className="notice gate">
          Waiting on a time.{" "}
          <button className="link" onClick={onOpenInterviews}>Open interviews</button>
        </div>
      )}

      {!data ? (
        <Loading lines={4} />
      ) : data.rows.length === 0 ? (
        <div className="card pad muted">
          {q ? `Nothing in the record matches “${q}”. Try the client name on its own — a job `
             + "logged without a link is only findable by what was typed."
             : "Nothing logged yet. Jobs appear here once a cycle has been built."}
        </div>
      ) : (
        <>
          <div className="card scroll">
            <table className="board">
              <thead>
                <tr>
                  <th style={{ width: 34 }}>#</th>
                  <th>Job</th>
                  <th>Company</th>
                  <th>Applied as</th>
                  <th>Platform</th>
                  <th>When</th>
                  <th>Links</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, index) => (
                  <React.Fragment key={`${row.job_id}-${row.profile_id}`}>
                    <tr>
                      <td className="mono muted" style={{ textAlign: "right" }}>
                        {page * PAGE + index + 1}
                      </td>
                      <td className="truncate" style={{ maxWidth: 320 }}>
                        {row.title || <span className="muted">no title recorded</span>}
                      </td>
                      <td>{row.company || <span className="muted">—</span>}</td>
                      <td><b>{row.profile}</b></td>
                      <td className="muted">{row.platform || "—"}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>
                        {row.applied_on || row.logged || "—"}
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        {safeUrl(row.url)
                          ? <a href={safeUrl(row.url)} target="_blank" rel="noreferrer noopener"
                               title={row.url}>apply</a>
                          : <span className="muted">—</span>}
                        {safeUrl(row.description_url) && (
                          <> · <a href={safeUrl(row.description_url)} target="_blank"
                                  rel="noreferrer noopener" title={row.description_url}>
                            description
                          </a></>
                        )}
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="link"
                                onClick={() => setStarting(
                                  starting === rowKey(row) ? null : rowKey(row))}>
                          {starting === rowKey(row) ? "never mind" : "they replied"}
                        </button>
                        {row.can_edit && (
                          <> · <button className="link" onClick={() => openEditor(row)}
                                  title="Correct the posting. There is one row per job, so this reaches everyone holding it.">
                            {editing === rowKey(row) ? "cancel" : "edit"}
                          </button></>
                        )}
                        {row.can_delete && (
                          <> · <button className="link" disabled={busy}
                                  onClick={() => withdraw(row)}
                                  title={"Withdraw " + row.profile + "'s entry. The posting stays."}>
                            withdraw
                          </button></>
                        )}
                      </td>
                    </tr>
                    {editing === rowKey(row) && draft && (
                      <tr>
                        <td colSpan={8}>
                          <div className="stack" style={{ gap: 9, padding: "10px 2px" }}>
                            <div>
                              <b style={{ fontFamily: "var(--display)" }}>
                                Correct this posting
                              </b>
                              <p className="hint" style={{ marginTop: 3, maxWidth: 620 }}>
                                There is one row per posting, so this correction reaches
                                every profile holding it — the new-jobs lists included,
                                straight away. Changing the link re-identifies the job,
                                which is usually the point: a link typed wrongly is what
                                splits one posting into two.
                              </p>
                            </div>
                            <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                              {[["title", "Job title"], ["company", "Company"],
                                ["platform", "Platform"], ["url", "Job link"],
                                ["description_url", "Description link"]].map(([key, label]) => (
                                <label key={key} style={{ flex: "1 1 220px" }}>
                                  {label}
                                  <input style={{ width: "100%", marginTop: 4 }}
                                         value={draft[key]}
                                         onChange={(e) => setDraft(
                                           (d) => ({ ...d, [key]: e.target.value }))} />
                                </label>
                              ))}
                            </div>
                            <div className="row" style={{ gap: 10 }}>
                              <button onClick={() => saveEdit(row)} disabled={busy}>
                                {busy ? "Saving…" : "Save for everyone"}
                              </button>
                              <button className="ghost"
                                      onClick={() => { setEditing(null); setDraft(null); }}>
                                Cancel
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                    {starting === rowKey(row) && (
                      <tr>
                        <td colSpan={8}>
                          <div className="stack" style={{ gap: 9, padding: "10px 2px" }}>
                            <div>
                              <b style={{ fontFamily: "var(--display)" }}>
                                Start a conversation on this one
                              </b>
                              <p className="hint" style={{ marginTop: 3, maxWidth: 620 }}>
                                The posting comes across as it is. No time is set —
                                it waits under <b>Interviews</b> until you agree one.
                              </p>
                            </div>
                            <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                              <label>
                                Which round&nbsp;
                                <select value={stage} onChange={(e) => setStage(e.target.value)}>
                                  {Object.entries(STAGE_LABELS).map(([key, label]) => (
                                    <option key={key} value={key}>{label}</option>
                                  ))}
                                </select>
                              </label>
                              <button onClick={() => start(row)} disabled={busy}>
                                {busy ? "Saving…" : "Add it to the diary"}
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="row" style={{ gap: 10 }}>
              <button className="ghost" disabled={page === 0 || busy}
                      onClick={() => setPage((n) => Math.max(0, n - 1))}>
                Back
              </button>
              <span className="muted">Page {page + 1} of {pages}</span>
              <button className="ghost" disabled={page + 1 >= pages || busy}
                      onClick={() => setPage((n) => n + 1)}>
                More
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
