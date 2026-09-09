import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, download } from "../api.js";
import { useToast } from "./shell.jsx";
import {
  Flow, InterviewRows, JobPicker, Loading, Rounds, STAGE_LABELS, StageLadder, Stalled,
  WaitingOnTime,
} from "./widgets.jsx";

/** Scheduling, and the list of what is scheduled.
 *
 * One component for three screens. A BD opens it for the profiles they run, a
 * developer for the identities they are sold under, a manager for everything —
 * and the server decides which of those it is from the token, so the only
 * difference here is which profiles the picker offers.
 *
 * Who may do what is one prop. `canSchedule` is the BD and the manager: the
 * client replied to the account the applications went out from, so booking it,
 * moving it and briefing the developer are all theirs. A developer opens the
 * same screen read-only over the booking and writes the one part nobody else
 * can answer — what happened on the call. The server holds both halves of that
 * whatever this file passes down; the prop only saves somebody a dead end.
 *
 * `profileId` narrows the whole screen to one identity. A developer sold under
 * three profiles usually wants "what has Khuram got today", not the union.
 *
 * Every time on this screen is Eastern, said out loud in the form and again on
 * every row, because the one thing worse than a missed interview is two people
 * confidently reading the same row as two different hours.
 */

const BLANK = {
  profile_id: "",
  dev_user_id: "",
  scheduled_at: "",
  client: "",
  role: "",
  mode: "video",
  duration_minutes: 30,
  link: "",
  // The client's own email thread. Optional, and deliberately not the same
  // field as the meeting link: one is where to be at two o'clock, the other is
  // what they actually asked for.
  email_url: "",
  notes: "",
  stage: "screening",
  // The posting they replied about, when there is one. `job` is the whole row
  // so the form can show what was picked; only `job_id` goes to the server.
  job_id: null,
  job: null,
};

/* The picker starts on `suggested_time` from the server — an hour from now on
   the team's clock. It is not worked out here on purpose: the field means
   Eastern, and a machine in Karachi prefilling its own clock would suggest a
   time nine hours away from the one it appears to say. Nothing in this file
   does date arithmetic. */

export default function Interviews({
  profiles = [],
  heading = "Interviews",
  intro = "",
  canSchedule = true,
  showProfile = true,
  showFunnel = false,
  profileId = null,
}) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [developers, setDevelopers] = useState([]);
  const [devOverride, setDevOverride] = useState(false);
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    api.listDevelopers()
      .then(setDevelopers)
      .catch(() => setDevelopers([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const next = await api.interviews(profileId);
      setData(next);
      // Only ever fills an empty field, so a refresh in the background cannot
      // move a time somebody is halfway through typing.
      setForm((current) => (current.scheduled_at
        ? current
        : { ...current, scheduled_at: next.suggested_time }));
    } catch (err) {
      toast(err.message, "bad");
    }
  }, [profileId]);

  useEffect(() => { load(); }, [load]);

  // Somebody else may be booking into the same calendar, so this screen does
  // not get to assume it is the only writer.
  useEffect(() => {
    const tick = setInterval(load, 60000);
    return () => clearInterval(tick);
  }, [load]);

  // One profile is the overwhelmingly common case; picking it for them saves a
  // click on every single interview.
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

  const byId = useMemo(
    () => Object.fromEntries(profiles.map((p) => [String(p.id), p])),
    [profiles]
  );

  /* Search the record for the posting a client is replying about.
   *
   * Scoped to the profile the form is on, because a job the *other* profile
   * applied to is not this conversation — attaching it would put a stranger's
   * application behind this interview. Re-made when that profile changes so a
   * stale closure cannot search the wrong one. */
  const findJobs = useCallback(
    (q) => (form.profile_id
      ? api.jobRecord({ q, profileId: Number(form.profile_id), limit: 8 })
        .then((found) => found.rows)
      : Promise.resolve([])),
    [form.profile_id]
  );

  const schedule = async () => {
    setBusy(true);
    try {
      // `job` is the whole record row and is only here so the form can show
      // what was picked. The server wants the id.
      const { job, ...payload } = form;
      const made = await api.createInterview({
        ...payload,
        profile_id: Number(form.profile_id),
        dev_user_id: form.dev_user_id ? Number(form.dev_user_id) : null,
        duration_minutes: Number(form.duration_minutes) || 30,
      });
      setForm({ ...BLANK, scheduled_at: data?.suggested_time || "",
                profile_id: form.profile_id });
      setAdding(false);
      await load();
      if (made.clash) {
        toast(`${made.clash.profile} already has ${made.clash.client || "an interview"} at `
          + `${made.clash.when.label} — the same person twice over.`, "bad");
      } else {
        toast(`${made.client || "Booked"} · ${made.when.label} ET`);
      }
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const change = async (id, patch) => {
    try {
      const saved = await api.updateInterview(id, patch);
      await load();
      if (saved.clash) {
        toast(`That now overlaps ${saved.clash.client || "another interview"} at `
          + `${saved.clash.when.label}.`, "bad");
      }
      return saved;
    } catch (err) {
      // Shown rather than thrown: the notes panel awaits this to decide whether
      // to close, and a rejection there would close on a save that never landed.
      toast(err.message, "bad");
      return null;
    }
  };

  /* Book the round after one that was cleared.
   *
   * No form. The whole value of it is that a second round costs one press and
   * no retyping — the client, the role and the posting come across from the
   * round that earned it, and it lands in "waiting on a time" like any other
   * reply with no hour agreed yet. Putting a time on it there is what books
   * it, which is the same single step as every other draft in this app. */
  const advance = async (row) => {
    setBusy(true);
    try {
      const made = await api.nextRound(row.id);
      await load();
      toast(`${STAGE_LABELS[made.stage] || made.stage} added for `
        + `${made.client || made.profile} — waiting on a time.`);
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(
      `Remove the ${row.client || "interview"} on ${row.when.label}? `
      + "If it was real and fell through, mark it cancelled instead — a client who "
      + "pulled out is worth knowing about.")) return;
    try {
      await api.deleteInterview(row.id);
      await load();
    } catch (err) {
      toast(err.message, "bad");
    }
  };

  if (!data) return <Loading lines={5} />;

  const ready = form.profile_id && form.scheduled_at;
  const chosen = byId[form.profile_id];

  return (
    <section className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h2>{heading}</h2>
          {intro && <p className="muted" style={{ marginTop: 3 }}>{intro}</p>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          {/* Everything above counts what went out and has had an export for
              a long time. This is the half that says what came back, and it
              is the half somebody is asked about at the end of a quarter. */}
          {(data?.counts.total > 0 || data?.counts.awaiting_time > 0) && (
            <button className="ghost" onClick={() =>
              download(api.pipelinePath(profileId), "pipeline.xlsx")
                .catch((err) => toast(err.message, "bad"))}>
              Download as Excel
            </button>
          )}
          {canSchedule && profiles.length > 0 && (
            <button className={adding ? "ghost" : ""} onClick={() => setAdding((on) => !on)}>
              {adding ? "Never mind" : "Log an interview"}
            </button>
          )}
        </div>
      </div>

      {!canSchedule && (
        <p className="hint" style={{ maxWidth: 640 }}>
          Your BD books these. Saying how a call went is yours.
        </p>
      )}

      {canSchedule && adding && (
        <div className="card pad stack" style={{ gap: 12 }}>
          <div>
            <h3>A client wants to talk</h3>
            <p className="hint" style={{ marginTop: 3 }}>
              Times are <b>Eastern</b> — type what you agreed with the client.
            </p>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
            <div>
              <label htmlFor="iv-profile">Applying as</label>
              {/* Changing the identity drops any posting already attached.
                  A job the *other* profile applied to is not this
                  conversation, and carrying it over would put a stranger's
                  application behind this interview. */}
              <select id="iv-profile" style={{ width: "100%", marginTop: 4 }}
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
                    <label htmlFor="iv-dev">Developer</label>
                    <select id="iv-dev" style={{ width: "100%", marginTop: 4 }}
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
                  <div style={{ marginTop: 4 }} className="row" >
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
              <label htmlFor="iv-when">Date and time · ET</label>
              <input id="iv-when" type="datetime-local" style={{ width: "100%", marginTop: 4 }}
                     value={form.scheduled_at}
                     onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })} />
            </div>
            <div>
                    <label htmlFor="iv-client">Company</label>
              <input id="iv-client" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Northwind Digital" value={form.client}
                     onChange={(e) => setForm({ ...form, client: e.target.value })} />
            </div>
            <div>
              <label htmlFor="iv-role">Role</label>
              <input id="iv-role" style={{ width: "100%", marginTop: 4 }}
                     placeholder="RAG Pipeline Developer" value={form.role}
                     onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </div>
            <div>
              <label htmlFor="iv-stage">Which round</label>
              <select id="iv-stage" style={{ width: "100%", marginTop: 4 }} value={form.stage}
                      onChange={(e) => setForm({ ...form, stage: e.target.value })}>
                <option value="screening">screening call</option>
                <option value="technical">technical round</option>
                <option value="assessment">assessment</option>
                <option value="final">final round</option>
                <option value="offer">offer talks</option>
              </select>
            </div>
            <div>
              <label htmlFor="iv-mode">How</label>
              <select id="iv-mode" style={{ width: "100%", marginTop: 4 }} value={form.mode}
                      onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                <option value="video">video call</option>
                <option value="call">phone call</option>
                <option value="onsite">on site</option>
                <option value="async">written / assessment</option>
              </select>
            </div>
            <div>
              <label htmlFor="iv-mins">Minutes</label>
              <input id="iv-mins" type="number" min="5" max="600" step="5"
                     style={{ width: "100%", marginTop: 4 }} value={form.duration_minutes}
                     onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="iv-link">Meeting link</label>
              <input id="iv-link" style={{ width: "100%", marginTop: 4 }}
                     placeholder="https://meet.example.com/…" value={form.link}
                     onChange={(e) => setForm({ ...form, link: e.target.value })} />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="iv-email">
                Link to the client&apos;s email <span className="opt">optional</span>
              </label>
              <input id="iv-email" style={{ width: "100%", marginTop: 4 }}
                     placeholder="https://mail.google.com/mail/u/0/#inbox/…"
                     value={form.email_url}
                     onChange={(e) => setForm({ ...form, email_url: e.target.value })} />
              <p className="hint" style={{ marginTop: 4, maxWidth: 640 }}>
                Optional. Paste the client&apos;s email straight out of your inbox — in Gmail or Outlook, open the message and copy the address bar. Three weeks later it is the only place their actual words still exist.
              </p>
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="iv-notes">Anything they should know</label>
              <input id="iv-notes" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Wants to see the RAG project" value={form.notes}
                     onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>

          {/* The same thing pressing *they replied* on the job record does,
              from the other direction. Both ways in should produce the same
              row, rather than one that carries the posting and one typed out
              of memory a fortnight later. */}
          <div>
            <label>Which job did they reply about?</label>
            <div style={{ marginTop: 4 }}>
              <JobPicker
                value={form.job}
                disabled={!form.profile_id}
                onSearch={findJobs}
                onPick={(row) => setForm((current) => ({
                  ...current,
                  job: row,
                  job_id: row.job_id,
                  // Only ever fills a blank. What somebody typed out of the
                  // client's email is theirs and may well be better than what
                  // the sheet recorded.
                  client: current.client || row.company || "",
                  role: current.role || row.title || "",
                }))}
                onClear={() => setForm((current) => ({
                  ...current, job: null, job_id: null,
                }))}
              />
            </div>
          </div>

          {chosen?.developer && (
            <p className="hint">
              Lands in <b>{chosen.developer}</b>&apos;s diary. Nothing is emailed.
            </p>
          )}
          {chosen && !chosen.developer && (
            <div className="notice">
              Nobody is attached to {chosen.name}, so this reaches no one.
            </div>
          )}

          <div className="row">
            <button onClick={schedule} disabled={busy || !ready}>
              {busy ? "Saving…" : "Put it in the diary"}
            </button>
            <span className="muted">
              Nothing is emailed. It appears on their screen the next time it refreshes.
            </span>
          </div>
        </div>
      )}

      {showFunnel && (
        <>
          <Flow funnel={data.funnel} awaiting={data.counts.awaiting_outcome} />
          <p className="hint" style={{ maxWidth: 700 }}>
            Applications are all-time. Interviews are never counted against one round
            of work — a reply that lands three weeks late belongs to the applications
            that earned it, not to whichever round happened to be open.
          </p>
          <Rounds rounds={data.funnel.rounds} />
          <StageLadder rows={data.funnel.by_stage} />
        </>
      )}

      {data.awaiting_time?.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <div>
            <h3>Waiting on a time</h3>
            <p className="hint" style={{ margin: "3px 0 0" }}>
              Clients who answered and are waiting. Adding a time books it.
            </p>
          </div>
          <WaitingOnTime rows={data.awaiting_time} onChange={change}
                         onRemove={canSchedule ? remove : undefined}
                         suggested={data.suggested_time} />
        </div>
      )}

      {data.counts.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{data.counts.awaiting_outcome} interview
          {data.counts.awaiting_outcome === 1 ? "" : "s"} with no outcome.</b> Every rate here
          reads low until somebody says.
        </div>
      )}

      <Stalled rows={data.stalled} onNextRound={advance} />

      <div>
        <h3>Today</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>
          {data.today.length
            ? `${data.today.length} today, Eastern time.`
            : "Nothing today."}
        </p>
        {data.today.length > 0 && (
          <InterviewRows rows={data.today} showProfile={showProfile} canBook={canSchedule}
                         onChange={change} onRemove={canSchedule ? remove : undefined}
                         onNextRound={advance} />
        )}
      </div>

      <div>
        <h3>Coming up</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>The next fortnight.</p>
        <InterviewRows rows={data.upcoming} showProfile={showProfile} canBook={canSchedule}
                       onChange={change} onRemove={canSchedule ? remove : undefined}
                       onNextRound={advance}
                       empty="Nothing booked in the next fortnight." />
      </div>

      <div>
        <h3>What happened</h3>
        <p className="hint" style={{ margin: "3px 0 8px" }}>
          Been and gone. Recording the outcome is what makes the rates true.
        </p>
        <InterviewRows rows={data.recent} showProfile={showProfile} canBook={canSchedule}
                       onChange={change} onRemove={canSchedule ? remove : undefined}
                       onNextRound={advance}
                       empty="Nothing has happened yet." />
      </div>
    </section>
  );
}
