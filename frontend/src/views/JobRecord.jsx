import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, safeUrl } from "../api.js";
import { Loading, STAGE_LABELS } from "./widgets.jsx";
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
  const [data, setData] = useState(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const [starting, setStarting] = useState(null);   // the row being turned into one
  // Something was started this session, so offer the way to it.
  const [started, setStarted] = useState(false);
  const [stage, setStage] = useState("screening");
  const typing = useRef(null);

  const load = useCallback(async (search, who, at) => {
    setBusy(true);
    try {
      setData(await api.jobRecord({
        q: search, profileId: who || null, limit: PAGE, offset: at * PAGE,
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
    typing.current = setTimeout(() => load(q, profileId, page), q ? 250 : 0);
    return () => clearTimeout(typing.current);
  }, [q, profileId, page, load]);

  // A new search starts at the beginning. Without this, searching from page
  // four shows an empty result and reads as "nothing found".
  useEffect(() => { setPage(0); }, [q, profileId]);

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
                  <th>Job</th>
                  <th>Client</th>
                  <th>Applied as</th>
                  <th>Platform</th>
                  <th>When</th>
                  <th>Links</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <React.Fragment key={`${row.job_id}-${row.profile_id}`}>
                    <tr>
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
                                  starting === `${row.job_id}-${row.profile_id}`
                                    ? null : `${row.job_id}-${row.profile_id}`)}>
                          {starting === `${row.job_id}-${row.profile_id}`
                            ? "never mind" : "they replied"}
                        </button>
                      </td>
                    </tr>
                    {starting === `${row.job_id}-${row.profile_id}` && (
                      <tr>
                        <td colSpan={7}>
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
