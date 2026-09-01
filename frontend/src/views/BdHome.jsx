import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import Assessments from "./Assessments.jsx";
import EntryTable from "./EntryTable.jsx";
import Interviews from "./Interviews.jsx";
import JobRecord from "./JobRecord.jsx";
import { Availability, CopyButton, Empty, Segment, Skills } from "./widgets.jsx";

const FIELD_LABELS = {
  url: "Job link",
  title: "Job title",
  company: "Client or company",
  platform: "Platform",
  date: "Applied on",
  // Where the posting is written out, when that is not the apply link. The
  // server guesses this from the column headings and is usually right, but a
  // sheet calling it something unexpected has to be correctable here — a
  // column that can only ever be guessed is a column that is sometimes wrong
  // with no way to fix it.
  description_url: "Job description link",
};

export default function BdHome({ pane = null, onPaneSeen }) {
  const [batches, setBatches] = useState([]);
  const [batchId, setBatchId] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [profileId, setProfileId] = useState(null);
  const [upload, setUpload] = useState(null);
  const [sheets, setSheets] = useState({});
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hot, setHot] = useState(false);
  // applied | new | record | interviews | assessments
  const [tab, setTab] = useState("applied");
  const [diary, setDiary] = useState(null);   // interview counts, for the badge
  const [tests, setTests] = useState(null);   // assessment counts, for the badge
  const [how, setHow] = useState("type");      // type | upload
  // Narrows the new-jobs list. Client-side on purpose: the whole list is
  // already here, so filtering it is instant and a request per keystroke would
  // be slower and worse.
  const [filter, setFilter] = useState("");
  const fileInput = useRef(null);

  const batch = useMemo(
    () => batches.find((b) => b.id === batchId) || null,
    [batches, batchId]
  );
  const profile = useMemo(
    () => profiles.find((p) => p.id === profileId) || null,
    [profiles, profileId]
  );
  const sheet = sheets[profileId] || [];

  useEffect(() => {
    Promise.all([api.listBatches(), api.listProfiles()])
      .then(([rows, mine]) => {
        setBatches(rows);
        setProfiles(mine);
        if (rows.length) setBatchId(rows[0].id);
        if (mine.length) setProfileId(mine[0].id);
      })
      .catch((err) => setNote({ bad: true, text: err.message }));
  }, []);

  // Once a cycle is computed there is nothing left to hand in, so open on the
  // half of the screen that still has something to do.
  useEffect(() => {
    if (batch) setTab(batch.status === "computed" ? "new" : "applied");
  }, [batch?.id, batch?.status]);

  // The command palette can land straight on a sub-tab. Honoured after the
  // rule above so a deliberate jump is not overwritten by the default.
  useEffect(() => {
    if (!pane) return;
    setTab(pane);
    onPaneSeen?.();
  }, [pane, onPaneSeen]);

  useEffect(() => {
    if (!batchId) return;
    setUpload(null);
    api.getBatch(batchId)
      .then((data) => {
        const mine = (data.uploads || []).find((u) => u.profile_id === profileId);
        if (mine) setUpload({ ...mine, fields: null });
      })
      .catch(() => {});
  }, [batchId, profileId]);

  const loadSheets = useCallback(() => {
    if (!batchId) return;
    api.mySheets(batchId)
      .then((data) => {
        const next = {};
        for (const p of data.profiles) next[p.id] = p.jobs;
        setSheets(next);
      })
      .catch(() => setSheets({}));
  }, [batchId]);

  useEffect(() => { loadSheets(); }, [loadSheets]);

  // Somebody else may put an interview in this diary at any moment — the
  // developer themselves, or a colleague who took the call. The badge is the
  // only thing on this screen that has to be right within the hour.
  useEffect(() => {
    const pull = () => {
      api.interviews().then((d) => setDiary(d.counts)).catch(() => {});
      api.assessments().then((d) => setTests(d.counts)).catch(() => {});
    };
    pull();
    const tick = setInterval(pull, 60000);
    return () => clearInterval(tick);
  }, []);

  // The server rebuilds these lists on a timer, so what is on screen goes stale
  // on its own. Pick up the new one rather than waiting for a reload.
  useEffect(() => {
    if (!batchId) return undefined;
    const tick = setInterval(() => {
      loadSheets();
      api.listBatches().then(setBatches).catch(() => {});
    }, 60000);
    return () => clearInterval(tick);
  }, [batchId, loadSheets]);

  const send = async (file) => {
    if (!file || !batchId || !profileId) return;
    setBusy(true);
    setNote(null);
    try {
      const data = await api.upload(batchId, profileId, file);
      setUpload(data);
      setNote({ text: `${data.row_count} rows read for ${data.profile}. Check the columns below.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const remap = async (key, value) => {
    const mapping = { ...upload.mapping, [key]: value };
    setUpload({ ...upload, mapping });
    try {
      await api.setMapping(upload.id, mapping);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const mark = async (assignmentId, status) => {
    setSheets((all) => ({
      ...all,
      // Skipping retires the job from this profile for good, so the row leaves
      // the list at once. Leaving it sitting there greyed out until the next
      // poll reads as a change that did not save.
      [profileId]: (all[profileId] || [])
        .filter((r) => !(r.id === assignmentId && status === "skipped"))
        .map((r) => (r.id === assignmentId ? { ...r, status } : r)),
    }));
    try {
      await api.setStatus(assignmentId, status);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const headers = upload?.headers || [];
  const done = sheet.filter((j) => j.status === "applied").length;
  const handedIn = upload?.row_count || 0;

  // What the filter box matches. `found_by` is in here because it is the whole
  // reason the tag exists: a BD who has learned that a colleague's searches
  // land well for this profile — or badly — wants that run of jobs together,
  // and a tag you can read but not filter on cannot answer that.
  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? sheet.filter((job) => [job.title, job.company, job.platform, job.url,
                             (job.found_by || []).join(" ")]
        .some((field) => (field || "").toLowerCase().includes(needle)))
    : sheet;

  if (!profiles.length) {
    return (
      <div className="stack">
        <h1>Your work</h1>
        <Empty title="No profile yet">
          A profile is the name and resume your applications go out under. Your manager
          creates one under <b>People and profiles</b>.
        </Empty>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Your work</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Working as <b>{profile?.name}</b>{profile?.headline ? ` · ${profile.headline}` : ""}.
          </p>
        </div>
        <label>
          Cycle&nbsp;
          <select value={batchId || ""} onChange={(e) => setBatchId(Number(e.target.value))}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>{b.name} · {b.status}</option>
            ))}
          </select>
        </label>
      </div>

      {profiles.length > 1 && (
        <div className="card pad">
          <h3>Which profile are you working as?</h3>
          <div className="row" style={{ marginTop: 10 }}>
            {profiles.map((p) => (
              <button key={p.id} className={p.id === profileId ? "" : "ghost"}
                      onClick={() => setProfileId(p.id)}>
                {p.name}
                <span style={{ opacity: 0.7, fontWeight: 400 }}>
                  {p.headline ? ` · ${p.headline}` : ""}
                </span>
                {sheets[p.id]?.length ? ` (${sheets[p.id].length})` : ""}
              </button>
            ))}
          </div>
          <p className="hint" style={{ marginTop: 8 }}>
            Each profile keeps its own history.
          </p>
        </div>
      )}

      {/* What the client is actually being handed. The resume link is the thing
          a BD needs three seconds before they need anything else on this page. */}
      {profile && (
        <section className="card pad stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h3>Who you are applying as</h3>
              <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
                {profile.developer
                  ? <>Behind <b>{profile.name}</b> is <b>{profile.developer}</b>. Booking
                      a reply is yours; their debrief comes back here.</>
                  : <>Nobody is attached to <b>{profile.name}</b>, so an interview booked
                      against it reaches no one.</>}
              </p>
            </div>
            {profile.developer && <Availability value={profile.availability} />}
          </div>

          <div className="row" style={{ gap: 20 }}>
            <span className="row" style={{ gap: 7 }}>
              <span className="muted">email</span>
              <span className="mono" style={{ fontSize: 12 }}>{profile.email || "—"}</span>
              <CopyButton value={profile.email} />
            </span>
            <span className="row" style={{ gap: 7 }}>
              <span className="muted">resume</span>
              {safeUrl(profile.resume_url) ? (
                <>
                  <a href={safeUrl(profile.resume_url)} target="_blank" rel="noreferrer noopener">open</a>
                  <CopyButton value={profile.resume_url} label="copy link" />
                </>
              ) : (
                <span style={{ color: "var(--brick)", fontSize: 12 }}>
                  not set{profile.developer ? ` — ${profile.developer} adds it on their own screen` : ""}
                </span>
              )}
            </span>
            {profile.rate && (
              <span className="row" style={{ gap: 7 }}>
                <span className="muted">rate</span>
                <span style={{ fontSize: 12 }}>{profile.rate}</span>
              </span>
            )}
            {profile.timezone && (
              <span className="row" style={{ gap: 7 }}>
                <span className="muted">hours</span>
                <span style={{ fontSize: 12 }}>{profile.timezone}</span>
              </span>
            )}
          </div>

          {profile.skills && <Skills value={profile.skills} />}
          {profile.bio && <p className="muted" style={{ maxWidth: 760 }}>{profile.bio}</p>}

          {profile.availability === "booked" && (
            <div className="notice">
              <b>{profile.developer || profile.name} is booked up.</b> Worth checking before
              you send more.
            </div>
          )}
        </section>
      )}

      {diary?.awaiting_time > 0 && (
        <div className="notice gate">
          <b>{diary.awaiting_time} {diary.awaiting_time === 1 ? "reply" : "replies"} waiting
          on a time.</b>{" "}
          <button className="link" onClick={() => setTab("interviews")}>Give them one</button>
        </div>
      )}

      {tests?.overdue > 0 && (
        <div className="notice">
          <b>{tests.overdue} take-home{tests.overdue === 1 ? "" : "s"} past the deadline.</b>{" "}
          <button className="link" onClick={() => setTab("assessments")}>Open them</button>
        </div>
      )}

      {diary?.today > 0 && (
        <div className="notice gate">
          <b>{diary.today} interview{diary.today === 1 ? "" : "s"} today.</b>{" "}
          <button className="link" onClick={() => setTab("interviews")}>Open the diary</button>
        </div>
      )}

      {diary?.stalled > 0 && (
        <div className="notice">
          <b>{diary.stalled} conversation{diary.stalled === 1 ? "" : "s"} cleared a round, then
          stopped.</b>{" "}
          <button className="link" onClick={() => setTab("interviews")}>Pick them up</button>
        </div>
      )}

      {diary?.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{diary.awaiting_outcome} interview
          {diary.awaiting_outcome === 1 ? "" : "s"} with no outcome.</b>{" "}
          Every rate reads low until somebody says.{" "}
          <button className="link" onClick={() => setTab("interviews")}>Open the diary</button>
        </div>
      )}

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}
      {!batches.length && <div className="notice">No cycle is open yet. Your manager needs to start one.</div>}

      {batch && (
        <>
          <Segment
            label="What you are working on"
            value={tab}
            onChange={setTab}
            items={[
              { key: "applied", label: "Applied", count: handedIn },
              { key: "new", label: "New jobs", count: sheet.length },
              { key: "record", label: "All jobs" },
              { key: "interviews", label: "Interviews",
                count: diary?.awaiting_time || diary?.today || diary?.scheduled,
                tone: diary?.awaiting_time ? "bad" : undefined },
              { key: "assessments", label: "Assessments",
                count: tests?.open,
                tone: tests?.overdue ? "bad" : undefined },
            ]}
          />

          {tab === "record" && (
            <JobRecord profiles={profiles} onOpenInterviews={() => setTab("interviews")} />
          )}

          {tab === "assessments" && (
            <Assessments
              profiles={profiles}
              heading="Assessments"
              intro="Take-homes across every profile you run. You set them, the developer does them."
            />
          )}

          {tab === "interviews" && (
            <Interviews
              profiles={profiles}
              heading="Interviews"
              intro="Every reply that became a conversation. Booking is yours; the debrief comes back here."
              showFunnel
            />
          )}

          {tab === "applied" && (
            <section className="stack" style={{ gap: 10 }}>
              <div>
                <h2>Jobs {profile?.name} applied to</h2>
                <p className="hint" style={{ marginTop: 3 }}>
                  Hand these in so nobody is sent what this profile already used.
                </p>
              </div>

              {batch.status !== "open" ? (
                <div className="notice">
                  This cycle is closed — your manager has already built the lists. Anything
                  new goes into the next one.
                </div>
              ) : (
                <>
                  <div className="row" style={{ gap: 8 }}>
                    <button className={how === "type" ? "" : "ghost"} onClick={() => setHow("type")}>
                      Add manually
                    </button>
                    <button className={how === "upload" ? "" : "ghost"} onClick={() => setHow("upload")}>
                      Upload a sheet
                    </button>
                    <span className="muted">
                      {how === "type"
                        ? "Add jobs one row at a time as you apply."
                        : "Already keep a spreadsheet? Drop the whole thing in."}
                    </span>
                  </div>

                  {how === "type" && (
                    <EntryTable
                      batchId={batchId}
                      profileId={profileId}
                      profileName={profile?.name}
                      onSaved={(result) => setUpload((current) => (
                        current
                          ? { ...current, row_count: result.row_count }
                          : { row_count: result.row_count, mapping: {}, headers: [] }
                      ))}
                    />
                  )}

                  {how === "upload" && (
                    <div
                      className={hot ? "drop hot" : "drop"}
                      onClick={() => fileInput.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); setHot(true); }}
                      onDragLeave={() => setHot(false)}
                      onDrop={(e) => { e.preventDefault(); setHot(false); send(e.dataTransfer.files[0]); }}
                    >
                      <div style={{ fontFamily: "var(--display)", fontWeight: 500, fontSize: 15 }}>
                        {busy ? "Reading the sheet…" : `Drop ${profile?.name}'s sheet here, or click to choose`}
                      </div>
                      <div className="muted" style={{ marginTop: 5 }}>
                        .xlsx, .xls or .csv — re-uploading replaces what you sent for this profile.
                      </div>
                      <input ref={fileInput} type="file" accept=".xlsx,.xls,.csv,.tsv" hidden
                             onChange={(e) => send(e.target.files[0])} />
                    </div>
                  )}

                  {how === "upload" && upload && headers.length > 0 && (
                    <div className="card pad stack" style={{ gap: 12 }}>
                      <div>
                        <h3>Columns we found</h3>
                        <p className="hint" style={{ marginTop: 3 }}>
                          The job link matters most. No links? Set the title and client.
                        </p>
                      </div>
                      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
                        {Object.keys(FIELD_LABELS).map((key) => (
                          <div key={key}>
                            <label htmlFor={`map-${key}`}>{FIELD_LABELS[key]}</label>
                            <select id={`map-${key}`} value={upload.mapping?.[key] || ""}
                                    style={{ width: "100%", marginTop: 4,
                                             borderColor: key === "url" && !upload.mapping?.url ? "var(--brick)" : undefined }}
                                    onChange={(e) => remap(key, e.target.value)}>
                              <option value="">— not in my sheet —</option>
                              {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                            </select>
                          </div>
                        ))}
                      </div>
                      {!upload.mapping?.url && (
                        <div className="notice">
                          No job link column is set. Matching will fall back to client plus title,
                          which is less exact.
                        </div>
                      )}
                      <div className="row">
                        <span className="pill on">{upload.row_count} rows handed in</span>
                        <button className="link" onClick={async () => {
                          await api.deleteUpload(upload.id);
                          setUpload(null);
                          setNote({ text: "That sheet was removed. Upload a different one when ready." });
                        }}>Remove this sheet</button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {tab === "new" && (
            <section className="stack" style={{ gap: 10 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <h2>New jobs for {profile?.name}</h2>
                  <p className="muted" style={{ marginTop: 3 }}>
                    {sheet.length
                      ? `${sheet.length} jobs ${profile?.name} has never applied to, ${done} marked applied.`
                      : "Nothing yet — your manager builds the lists once everyone has handed in."}
                  </p>
                </div>
                {sheet.length > 0 && (
                  <button className="go" onClick={() =>
                    download(`/batches/${batchId}/profiles/${profileId}/sheet.xlsx`, "new-jobs.xlsx")
                      .catch((err) => setNote({ bad: true, text: err.message }))}>
                    Download as Excel
                  </button>
                )}
              </div>

              {sheet.length === 0 ? (
                <div className="notice">
                  {batch.status !== "open"
                    ? "Nothing was dispatched to this profile in this cycle."
                    : batch.auto_build_minutes
                      ? `This cycle is still open. The lists rebuild every ${batch.auto_build_minutes} minutes once at least two profiles have handed in — yours will appear here on its own.`
                      : "This cycle is still open. Your jobs appear here once your manager builds the lists."}
                </div>
              ) : (
                <>
                  <div className="card pad row" style={{ gap: 12, flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 320px" }}>
                      <label htmlFor="new-filter">Narrow this list</label>
                      <input id="new-filter" style={{ width: "100%", marginTop: 4 }}
                             value={filter}
                             placeholder="A client, a job title, a platform, or who found it"
                             onChange={(e) => setFilter(e.target.value)} />
                    </div>
                    <div className="row" style={{ alignItems: "flex-end", gap: 8 }}>
                      <span className="muted">
                        {needle
                          ? `${visible.length} of ${sheet.length} shown`
                          : `${sheet.length} on the list`}
                      </span>
                      {needle && (
                        <button className="link" onClick={() => setFilter("")}>clear</button>
                      )}
                    </div>
                  </div>

                  {needle && visible.length === 0 ? (
                    <div className="card pad muted">
                      Nothing on this list matches “{filter}”. The names under <b>Found by</b> are
                      profiles, not people — try the profile name a colleague applies under.
                    </div>
                  ) : (
                  <div className="card scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Job</th><th>Client</th><th>Found by</th><th>Platform</th>
                          <th style={{ minWidth: 220 }}>Link</th><th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((job) => (
                          <tr key={job.id}>
                            <td className="truncate">{job.title || "—"}</td>
                            <td>{job.company || "—"}</td>
                            <td>
                              {/* Each name filters the list to that sourcer.
                                  Reading "found by Faizan" on one row is
                                  useful; seeing the whole run of them together
                                  is what tells you whether their searches suit
                                  this profile. */}
                              {job.found_by?.length ? (
                                <span className="row" style={{ gap: 4 }}>
                                  {job.found_by.map((name) => (
                                    <button key={name} className="pill"
                                            style={{ cursor: "pointer", border: 0 }}
                                            onClick={() => setFilter(
                                              filter.trim().toLowerCase() === name.toLowerCase()
                                                ? "" : name)}
                                            title={`Already applied to by ${name}. That is why `
                                              + "it is on this list. Click to see everything "
                                              + "they found."}>
                                      {name}
                                    </button>
                                  ))}
                                </span>
                              ) : <span className="muted">—</span>}
                            </td>
                            <td className="muted">{job.platform || "—"}</td>
                            <td>
                              {/* The link itself, not the word "open" over the top of it.
                                  A BD decides whether a posting is worth their time from
                                  the host and the slug as often as from the title. */}
                              {safeUrl(job.url) ? (
                                <a className="truncate" style={{ display: "block", maxWidth: 300 }}
                                   href={safeUrl(job.url)} title={job.url}
                                   target="_blank" rel="noreferrer noopener">
                                  {job.url.replace(/^https?:\/\/(www\.)?/i, "")}
                                </a>
                              ) : <span className="muted">no link</span>}
                              {safeUrl(job.description_url) && (
                                <a href={safeUrl(job.description_url)} title={job.description_url}
                                   style={{ fontSize: 11 }}
                                   target="_blank" rel="noreferrer noopener">
                                  the full description
                                </a>
                              )}
                            </td>
                            <td>
                              <select value={job.status} onChange={(e) => mark(job.id, e.target.value)}>
                                <option value="pending">to do</option>
                                <option value="applied">applied</option>
                                <option value="skipped">skipped</option>
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  )}
                  <p className="hint">
                    <b>To do</b> comes back next cycle. <b>Applied</b> or <b>skipped</b>
                    {" "}retires it from {profile?.name} for good.
                  </p>
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
