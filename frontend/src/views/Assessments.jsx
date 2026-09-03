import React, { useCallback, useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import { JobDetail, JobPicker, Loading, STAGE_LABELS } from "./widgets.jsx";
import { useToast } from "./shell.jsx";

/** Take-homes and tests: set by the BD, done by the developer.
 *
 * The same split as an interview and for the same reason. The BD has the
 * client's email, so the brief, the link and the deadline are theirs. The
 * developer has the work, so how far along it is, what went back and what the
 * BD should know are theirs. Both may write either — a BD told over the phone
 * that it went in should be able to say so — but the screen leads each side to
 * their own half.
 *
 * `canSet` decides which half gets the form. Everything is readable to both,
 * because a deadline nobody can see is a deadline nobody meets.
 */

const STATUS_LABELS = {
  sent: "not started",
  in_progress: "in progress",
  submitted: "submitted",
  passed: "passed",
  failed: "did not pass",
};

const BLANK = {
  profile_id: "",
  dev_user_id: "",
  title: "",
  client: "",
  brief: "",
  link: "",
  due_at: "",
  interview_id: "",
  // The posting the test came out of. Inherited from the interview when one is
  // named, and pickable directly for a client that screened with a take-home
  // before anybody spoke. `job` is the whole record row so the form can show
  // what was picked; only `job_id` goes to the server.
  job_id: null,
  job: null,
};

export default function Assessments({
  profiles = [],
  profileId = null,
  canSet = true,
  heading = "Assessments",
  intro = "",
}) {
  const [data, setData] = useState(null);
  const [diary, setDiary] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [developers, setDevelopers] = useState([]);
  const [devOverride, setDevOverride] = useState(false);
  const [adding, setAdding] = useState(false);
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.listDevelopers()
      .then(setDevelopers)
      .catch(() => setDevelopers([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const [next, calendar] = await Promise.all([
        api.assessments(profileId),
        // Only to offer "which call did this come out of" on the form. A
        // failure here must not take the list down with it.
        api.interviews(profileId).catch(() => null),
      ]);
      setData(next);
      setDiary(calendar);
      setForm((current) => (current.due_at
        ? current
        : { ...current, due_at: next.suggested_due }));
    } catch (err) {
      toast(err.message, "bad");
    }
  }, [profileId]);

  useEffect(() => { load(); }, [load]);

  // The other side may set one, or submit one, at any moment.
  useEffect(() => {
    const tick = setInterval(load, 60000);
    return () => clearInterval(tick);
  }, [load]);

  useEffect(() => {
    if (profiles.length && !form.profile_id) {
      const first = profiles[0];
      setForm((current) => ({
        ...current,
        profile_id: String(first.id),
        dev_user_id: first.dev_user_id ? String(first.dev_user_id) : "",
      }));
      setDevOverride(false);
    }
  }, [profiles, form.profile_id]);

  useEffect(() => {
    if (!form.profile_id) return;
    const selected = profiles.find((p) => String(p.id) === String(form.profile_id));
    if (!selected) return;
    if (!devOverride) {
      setForm((current) => ({
        ...current,
        dev_user_id: current.dev_user_id || (selected.dev_user_id ? String(selected.dev_user_id) : ""),
      }));
    }
  }, [form.profile_id, profiles, devOverride]);

  /* Search the record for the posting this test came out of.
   *
   * Scoped to the profile the form is on, for the same reason the diary's
   * picker is: a job the *other* identity applied to is not this
   * conversation. */
  const findJobs = useCallback(
    (q) => (form.profile_id
      ? api.jobRecord({ q, profileId: Number(form.profile_id), limit: 8 })
        .then((found) => found.rows)
      : Promise.resolve([])),
    [form.profile_id]
  );

  const create = async () => {
    setBusy(true);
    try {
      // `job` is only here so the form can show what was picked.
      const { job, ...payload } = form;
      const made = await api.createAssessment({
        ...payload,
        profile_id: Number(form.profile_id),
        dev_user_id: form.dev_user_id ? Number(form.dev_user_id) : null,
        interview_id: form.interview_id ? Number(form.interview_id) : null,
      });
      setForm({ ...BLANK, profile_id: form.profile_id, due_at: data?.suggested_due || "" });
      setAdding(false);
      await load();
      toast(`${made.title} is on ${made.developer || made.profile}'s screen`
        + `${made.due ? ` · due ${made.due.label} ET` : ""}.`);
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const change = async (id, patch) => {
    try {
      const saved = await api.updateAssessment(id, patch);
      await load();
      return saved;
    } catch (err) {
      toast(err.message, "bad");
      return null;
    }
  };

  const remove = async (row) => {
    if (!window.confirm(
      `Remove “${row.title}”? If the client withdrew it, mark it and leave it — `
      + "a test that was pulled is worth knowing about. This is for one that was never real."
    )) return;
    try {
      await api.deleteAssessment(row.id);
      await load();
    } catch (err) {
      toast(err.message, "bad");
    }
  };

  if (!data) return <Loading lines={4} />;

  const { counts } = data;
  // Only calls that have been and gone can have produced a take-home.
  const sittings = (diary?.recent || []).concat(diary?.today || []);

  return (
    <section className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h2>{heading}</h2>
          {intro && <p className="muted" style={{ marginTop: 3, maxWidth: 760 }}>{intro}</p>}
        </div>
        {canSet && profiles.length > 0 && (
          <button className={adding ? "ghost" : ""} onClick={() => setAdding((on) => !on)}>
            {adding ? "Never mind" : "Set an assessment"}
          </button>
        )}
      </div>

      {counts.overdue > 0 && (
        <div className="notice">
          <b>{counts.overdue} past the deadline.</b> Worth clearing before anything else here.
        </div>
      )}

      {canSet && adding && (
        <div className="card pad stack" style={{ gap: 12 }}>
          <div>
            <h3>A client has sent something to do</h3>
            <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
              Deadline is <b>Eastern</b>. Leave it empty if the client gave none.
            </p>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
            <div>
              <label htmlFor="as-profile">Applying as</label>
              {/* Changing the identity drops any posting already attached —
                  a job the other profile applied to is not this test. */}
              <select id="as-profile" style={{ width: "100%", marginTop: 4 }}
                      value={form.profile_id}
                      onChange={(e) => setForm({
                        ...form,
                        profile_id: e.target.value,
                        dev_user_id: profiles.find((p) => String(p.id) === e.target.value)?.dev_user_id
                          ? String(profiles.find((p) => String(p.id) === e.target.value).dev_user_id)
                          : "",
                        job: null,
                        job_id: null,
                      })}>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.headline ? ` · ${p.headline}` : ""}
                  </option>
                ))}
              </select>
            </div>
            {(() => {
              const selected = profiles.find((p) => String(p.id) === String(form.profile_id));
              const assignedDev = selected?.dev_user_id
                ? developers.find((person) => person.id === Number(selected.dev_user_id))
                : null;
              const showDevPicker = !selected?.dev_user_id || devOverride;

              if (showDevPicker) {
                return (
                  <div>
                    <label htmlFor="as-dev">Developer</label>
                    <select id="as-dev" style={{ width: "100%", marginTop: 4 }}
                            value={form.dev_user_id || (assignedDev ? String(assignedDev.id) : "")}
                            onChange={(e) => setForm({ ...form, dev_user_id: e.target.value })}>
                      <option value="">— nobody —</option>
                      {developers.map((person) => (
                        <option key={person.id} value={person.id}>{person.name}</option>
                      ))}
                    </select>
                  </div>
                );
              }

              return (
                <div>
                  <label>Developer</label>
                  <div style={{ marginTop: 4 }} className="row">
                    <span className="muted">Default: {assignedDev ? assignedDev.name : "nobody"}</span>
                    <button type="button" className="ghost" onClick={() => {
                      setDevOverride(true);
                      setForm((current) => ({ ...current, dev_user_id: assignedDev ? String(assignedDev.id) : "" }));
                    }}>
                      change
                    </button>
                  </div>
                </div>
              );
            })()}
            <div>
              <label htmlFor="as-title">What is it</label>
              <input id="as-title" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Take-home · RAG pipeline" value={form.title}
                     onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <label htmlFor="as-client">Company</label>
              <input id="as-client" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Copperline Media" value={form.client}
                     onChange={(e) => setForm({ ...form, client: e.target.value })} />
            </div>
            <div>
              <label htmlFor="as-due">Due · ET</label>
              <input id="as-due" type="datetime-local" style={{ width: "100%", marginTop: 4 }}
                     value={form.due_at}
                     onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="as-link">Where the task is</label>
              <input id="as-link" style={{ width: "100%", marginTop: 4 }}
                     placeholder="https://example.com/take-home" value={form.link}
                     onChange={(e) => setForm({ ...form, link: e.target.value })} />
            </div>
            {sittings.length > 0 && (
              <div style={{ gridColumn: "span 2" }}>
                <label htmlFor="as-interview">Came out of</label>
                {/* Naming a call means the posting comes across with it, so
                    a hand-picked one is dropped rather than left to win a
                    quiet argument with the interview's own. */}
                <select id="as-interview" style={{ width: "100%", marginTop: 4 }}
                        onChange={(e) => setForm({
                          ...form, interview_id: e.target.value,
                          ...(e.target.value ? { job: null, job_id: null } : {}),
                        })}
                        value={form.interview_id}>
                  <option value="">nothing — the client sent it cold</option>
                  {sittings.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.client || "a client"} · {STAGE_LABELS[row.stage] || row.stage}
                      {" · "}{row.when.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="as-brief">What they asked for</label>
              <textarea id="as-brief" rows={3} style={{ width: "100%", marginTop: 4 }}
                        placeholder="Build a small RAG pipeline over the sample docs. Python."
                        value={form.brief}
                        onChange={(e) => setForm({ ...form, brief: e.target.value })} />
            </div>
          </div>

          {/* Named a call above and the posting comes with it — the interview
              already knows which one. This is for the other case, and it is
              common: plenty of clients screen with a take-home before anybody
              speaks, and there is no call for that test to hang off. */}
          {!form.interview_id && (
            <div>
              <label>Which job is this test for?</label>
              <div style={{ marginTop: 4 }}>
                <JobPicker
                  value={form.job}
                  disabled={!form.profile_id}
                  onSearch={findJobs}
                  onPick={(row) => setForm((current) => ({
                    ...current,
                    job: row,
                    job_id: row.job_id,
                    // Only ever fills a blank. What was copied out of the
                    // client's email beats what the sheet recorded.
                    client: current.client || row.company || "",
                    title: current.title
                      || (row.title ? `Take-home · ${row.title}` : ""),
                  }))}
                  onClear={() => setForm((current) => ({
                    ...current, job: null, job_id: null,
                  }))}
                />
              </div>
            </div>
          )}

          <div className="row">
            <button onClick={create} disabled={busy || !form.profile_id}>
              {busy ? "Saving…" : "Put it on their screen"}
            </button>
            <span className="muted">
              Nothing is emailed. It appears on the developer&apos;s screen within the minute.
            </span>
          </div>
        </div>
      )}

      <Section title="Outstanding" rows={data.open} canSet={canSet}
               open={open} setOpen={setOpen} onChange={change} onRemove={remove}
               empty="Nothing outstanding." />
      <Section title="Finished with" rows={data.closed} canSet={canSet}
               open={open} setOpen={setOpen} onChange={change} onRemove={remove}
               empty="Nothing has been submitted yet."
               note="Kept next to the conversation it came from — a test that did not pass is
                     as worth seeing as one that did." />
    </section>
  );
}


function Section({ title, rows, canSet, open, setOpen, onChange, onRemove, empty, note }) {
  return (
    <div>
      <h3>{title}</h3>
      {note && <p className="muted" style={{ margin: "3px 0 8px", maxWidth: 720 }}>{note}</p>}
      {!rows.length ? (
        <div className="card pad muted" style={{ marginTop: 8 }}>{empty}</div>
      ) : (
        <div className="card scroll" style={{ marginTop: 8 }}>
          <table className="board">
            <thead>
              <tr>
                <th>What</th>
                <th>Company</th>
                <th>Applied as</th>
                <th style={{ width: 140 }}>Due · ET</th>
                <th style={{ width: 160 }}>How far along</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <React.Fragment key={row.id}>
                  <tr style={{ opacity: row.status === "failed" ? 0.6 : 1 }}>
                    <td style={{ maxWidth: 300 }}>
                      <div className="truncate">{row.title}</div>
                      {row.interview && (
                        <div className="muted" style={{ fontSize: 11 }}>
                          after the {STAGE_LABELS[row.interview.stage] || row.interview.stage}
                        </div>
                      )}
                      {/* The posting it is a test for. The same block the
                          diary shows, so the two screens describing one
                          conversation cannot describe it differently. */}
                      <JobDetail job={row.job} />
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
                        <>
                          <span className="mono">{row.due.time}</span>
                          <div style={{
                            fontSize: 11,
                            color: row.overdue ? "var(--brick)"
                              : row.due_soon ? "var(--petrol)" : undefined,
                          }}>
                            {row.due.label.split(" · ")[0]}
                            {row.overdue ? " · late" : row.due_soon ? " · soon" : ""}
                          </div>
                        </>
                      ) : <span className="muted">none set</span>}
                    </td>
                    <td>
                      <select value={row.status}
                              onChange={(e) => onChange(row.id, { status: e.target.value })}>
                        {Object.entries(STATUS_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>{label}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {safeUrl(row.link) && (
                        <a href={safeUrl(row.link)} target="_blank" rel="noreferrer noopener">
                          the task
                        </a>
                      )}
                      <button className="link"
                              onClick={() => setOpen(open === row.id ? null : row.id)}>
                        {open === row.id ? "close" : "details"}
                      </button>
                      {canSet && onRemove && (
                        <button className="link" onClick={() => onRemove(row)}>remove</button>
                      )}
                    </td>
                  </tr>
                  {open === row.id && (
                    <tr>
                      <td colSpan={6}>
                        <Detail row={row} canSet={canSet} onChange={onChange}
                                onClose={() => setOpen(null)} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


/** The two halves again: what was asked for, and what went back. */
function Detail({ row, canSet, onChange, onClose }) {
  const [submission, setSubmission] = useState(row.submission_url || "");
  const [notes, setNotes] = useState(row.notes || "");
  const [saving, setSaving] = useState(false);
  const dirty = submission.trim() !== (row.submission_url || "").trim()
    || notes.trim() !== (row.notes || "").trim();

  const save = async () => {
    setSaving(true);
    try {
      await onChange(row.id, { submission_url: submission.trim(), notes: notes.trim() });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 11, padding: "10px 2px" }}>
      <div>
        <label>What the client asked for</label>
        <p className="muted" style={{ marginTop: 3, maxWidth: 760 }}>
          {row.brief || "No brief was written down."}
        </p>
        {row.job && (
          <div style={{ marginTop: 6 }}>
            <span className="muted">For <b>{row.job.title || "a job"}</b>
              {row.job.company ? ` at ${row.job.company}` : ""}</span>
            <JobDetail job={row.job} />
          </div>
        )}
        {row.set_by && (
          <p className="muted" style={{ marginTop: 3, fontSize: 12 }}>Set by {row.set_by}.</p>
        )}
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
        <div>
          <label htmlFor={`sub-${row.id}`}>Where you put it</label>
          <input id={`sub-${row.id}`} style={{ width: "100%", marginTop: 4 }}
                 placeholder="https://github.com/…" value={submission}
                 onChange={(e) => setSubmission(e.target.value)} />
        </div>
        <div>
          <label htmlFor={`asn-${row.id}`}>
            {canSet ? "Anything worth recording" : "Anything your BD should know"}
          </label>
          <input id={`asn-${row.id}`} style={{ width: "100%", marginTop: 4 }}
                 placeholder="Took about four hours. Went with hybrid search."
                 value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>

      <div className="row" style={{ gap: 10 }}>
        <button onClick={save} disabled={saving || !dirty}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button className="ghost" onClick={onClose}>Close</button>
        <span className="muted">
          {row.submitted
            ? `Went back ${row.submitted.label}, Eastern.`
            : "Not submitted yet."}
          {row.updated_by ? ` Last touched by ${row.updated_by}.` : ""}
        </span>
      </div>
    </div>
  );
}
