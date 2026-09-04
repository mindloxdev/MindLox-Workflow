import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import Assessments from "./Assessments.jsx";
import EntryTable from "./EntryTable.jsx";
import Interviews from "./Interviews.jsx";
import JobRecord from "./JobRecord.jsx";
import { ActionList, bdTodo } from "./Todo.jsx";
import { Availability, CopyButton, CyclePicker, Empty, Segment, Skills } from "./widgets.jsx";

const FIELD_LABELS = {
  url: "Job link",
  title: "Job title",
  company: "Company",
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
  // The job waiting on a reason before it can be skipped. A skip retires the
  // posting from this profile for good and never comes back in a later cycle,
  // so it is the one status change that asks a question first.
  const [skipping, setSkipping] = useState(null);   // { id, title, company }
  const [skipReason, setSkipReason] = useState("");
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
      setNote({ text: `${data.usable_count ?? data.row_count} of ${data.row_count} rows `
                    + `are usable for ${data.profile}. Check the columns below.` });
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

  const mark = async (assignmentId, status, reason = "") => {
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
      const saved = await api.setStatus(assignmentId, status, reason);
      setSheets((all) => ({
        ...all,
        [profileId]: (all[profileId] || []).map((r) => (
          r.id === assignmentId
            ? { ...r, applied_on: saved.applied_on || r.applied_on || "" }
            : r
        )),
      }));
    } catch (err) {
      setNote({ bad: true, text: err.message });
      loadSheets();                 // put the row back; the change did not take
    }
  };

  /** Skipping goes through the prompt; everything else is immediate. */
  const chooseStatus = (job, status) => {
    if (status === "skipped") {
      setSkipReason("");
      setSkipping({ id: job.id, title: job.title, company: job.company });
      return;
    }
    mark(job.id, status);
  };

  const confirmSkip = async () => {
    const reason = skipReason.trim();
    if (!reason) return;
    const target = skipping;
    setSkipping(null);
    await mark(target.id, "skipped", reason);
  };

  const headers = upload?.headers || [];
  const done = sheet.filter((j) => j.status === "applied").length;
  // What the matcher can actually read, not how many lines the file had. The
  // two differ on an uploaded sheet with blank rows or an unmapped link column,
  // and showing the larger one here put "handed in 40" next to a cycle that
  // logged 36 with nothing to explain the gap.
  const handedIn = upload?.usable_count ?? upload?.row_count ?? 0;
  const newJobs = sheet.filter((j) => j.status !== "applied");

  // What the filter box matches. `found_by` is in here because it is the whole
  // reason the tag exists: a BD who has learned that a colleague's searches
  // land well for this profile — or badly — wants that run of jobs together,
  // and a tag you can read but not filter on cannot answer that.
  const needle = filter.trim().toLowerCase();
  // Newest posting first. Sorted on `found_on` — when the colleague who put
  // this job into the pool applied to it. It used to sort on `applied_on`,
  // which is this profile's own date and is empty on every row of this list by
  // definition, so the sort silently did nothing but fall through to the title.
  const orderedSheet = [...newJobs].sort((left, right) => {
    if (left.found_on && right.found_on) {
      return right.found_on.localeCompare(left.found_on);
    }
    if (left.found_on) return -1;
    if (right.found_on) return 1;
    return (left.title || "").localeCompare(right.title || "");
  });
  const visible = needle
    ? orderedSheet.filter((job) => [job.title, job.company, job.platform, job.url,
                             (job.found_by || []).join(" ")]
        .some((field) => (field || "").toLowerCase().includes(needle)))
    : orderedSheet;

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
      {skipping && (
        <div className="card pad stack" role="alertdialog" aria-modal="true"
             style={{ gap: 10, borderLeft: "3px solid var(--brick)" }}>
          <div>
            <b style={{ fontFamily: "var(--display)" }}>Why are you skipping this one?</b>
            <p className="muted" style={{ marginTop: 3 }}>
              <b>{skipping.title || "This job"}</b>
              {skipping.company ? <> at <b>{skipping.company}</b></> : null}.
            </p>
            <p className="hint" style={{ marginTop: 6, maxWidth: 620 }}>
              Skipping retires it from {profile?.name} for good — it will not come
              back in a later cycle. Your manager reads these to see whether the
              searches feeding this profile are landing, so a few words is enough:
              wrong seniority, on-site only, rate too low, client already approached.
            </p>
          </div>
          <textarea rows={3} autoFocus value={skipReason}
                    placeholder="Wrong seniority — this one wants 10 years."
                    onChange={(e) => setSkipReason(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmSkip();
                      if (e.key === "Escape") setSkipping(null);
                    }} />
          <div className="row" style={{ gap: 10 }}>
            <button onClick={confirmSkip} disabled={!skipReason.trim()}>
              Skip this job
            </button>
            <button className="ghost" onClick={() => setSkipping(null)}>Keep it on the list</button>
          </div>
        </div>
      )}

      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Your work</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Applying as <b>{profile?.name}</b>{profile?.headline ? ` · ${profile.headline}` : ""}
            {batch && <> · round <b>{batch.name}</b>, {batch.status === "open"
              ? "still taking jobs"
              : "closed — anything new goes into the next one"}</>}.
          </p>
        </div>
        <CyclePicker batches={batches} value={batchId} label="Round"
                     onChange={setBatchId} />
      </div>

      {profiles.length > 1 && (
        <div className="card pad">
          <h3>Which name are you applying under?</h3>
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
            Each one is a separate candidate to a client, with its own developer,
            resume and history. Everything on this screen follows whichever you pick.
          </p>
        </div>
      )}

      {/* Before anything else: the short list of things that will not fix
          themselves, hardest first, each carrying the button that fixes it.
          These were five separate coloured banners stacked in whatever order
          the code checked them, so an interview starting in forty minutes
          could sit below a note about a spreadsheet. */}
      <ActionList
        items={bdTodo({
          diary, tests, batch, toDo: newJobs.length,
          handedIn: handedIn > 0, profile, go: setTab,
        })}
        lead="Hardest first. Each one has the button that deals with it."
        empty={{
          title: "You are straight.",
          body: "No client is waiting on a time, nothing is past a deadline, your "
              + "to-do list is clear and this round's jobs are handed in.",
        }} />

      {/* What the client is actually being handed. Below the list, because it
          is reference rather than work — but never further down than this: the
          resume link is the thing a BD reaches for three seconds before they
          reach for anything else on the page. */}
      {profile && (
        <details className="more sheetcard">
          <summary>
            Who you are applying as — {profile.name}
            {profile.developer ? ` · ${profile.developer}` : " · nobody attached"}
          </summary>
          <section className="card pad stack" style={{ gap: 10 }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h3>Who the client meets</h3>
                <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
                  {profile.developer
                    ? <>A client who says yes to <b>{profile.name}</b> is
                        meeting <b>{profile.developer}</b>. You book the time; they say
                        afterwards how it went, and it comes back to your diary.</>
                    : <>Nobody is attached to <b>{profile.name}</b>, so an interview
                        booked against it reaches no one.</>}
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
                  <span style={{ color: "var(--bad-text)", fontSize: 12 }}>
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
                  <span className="muted">hours they work</span>
                  <span style={{ fontSize: 12 }}>{profile.timezone}</span>
                </span>
              )}
            </div>

            {profile.skills && <Skills value={profile.skills} />}
            {profile.bio && <p className="muted" style={{ maxWidth: 760 }}>{profile.bio}</p>}

            {profile.availability === "booked" && (
              <div className="notice">
                <b>{profile.developer || profile.name} is booked up.</b> Worth knowing
                before you send more — a client who says yes this week may be told to wait.
              </div>
            )}
          </section>
        </details>
      )}

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}
      {!batches.length && <div className="notice">No cycle is open yet. Your manager needs to start one.</div>}

      {batch && (
        <>
          {/* Named for what is behind them, not for what the database calls
              it. "Own jobs" and "New jobs" sat side by side meaning "the ones
              you found" and "the ones found for you", which is a distinction
              nobody gets from those two words. */}
          <Segment
            label="What you are working on"
            value={tab}
            onChange={setTab}
            items={[
              { key: "applied", label: "Jobs I found", count: handedIn },
              { key: "new", label: "To apply for", count: newJobs.length },
              { key: "record", label: "All jobs" },
              { key: "interviews", label: "Interviews",
                count: diary?.awaiting_time || diary?.today || diary?.scheduled,
                tone: diary?.awaiting_time ? "bad" : undefined },
              { key: "assessments", label: "Tests",
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
              heading="Tests from clients"
              intro="Tests a client has set. You record it here; the developer behind the profile does it."
            />
          )}

          {tab === "interviews" && (
            <Interviews
              profiles={profiles}
              heading="Interviews"
              intro="Every reply that turned into a conversation. You book the time; the developer says afterwards how it went."
              showFunnel
            />
          )}

          {tab === "applied" && (
            <section className="stack" style={{ gap: 10 }}>
              <div>
                  <h2>Jobs {profile?.name} found</h2>
                <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
                  The jobs you went out and applied for yourself this round. Handing
                  them in is what stops a colleague spending their morning finding the
                  same ones — and what puts them on other people&apos;s lists.
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
                      profileHeadline={profile?.headline}
                      onSaved={(result) => setUpload((current) => (
                        current
                          ? { ...current, row_count: result.row_count,
                              usable_count: result.usable_count }
                          : { row_count: result.row_count,
                              usable_count: result.usable_count, mapping: {}, headers: [] }
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
                        <span className="pill on">
                          {upload.usable_count ?? upload.row_count} rows handed in
                        </span>
                        {upload.usable_count != null
                          && upload.row_count > upload.usable_count && (
                          <span className="muted" style={{ fontSize: 12 }}>
                            {upload.row_count - upload.usable_count} of the{" "}
                            {upload.row_count} rows in the file carry no job link and
                            no client, so they are not counted.
                          </span>
                        )}
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
                  <h2>New jobs for {profile?.name}{profile?.headline ? ` · ${profile.headline}` : ""}</h2>
                  <p className="muted" style={{ marginTop: 3 }}>
                    {newJobs.length
                      ? `${newJobs.length} jobs ${profile?.name} has never applied to, ${done} moved to All jobs.`
                      : done
                        ? `${done} job${done === 1 ? "" : "s"} moved to All jobs.`
                        : "Nothing yet — your manager builds the lists once everyone has handed in."}
                  </p>
                </div>
                {newJobs.length > 0 && (
                  <button className="go" onClick={() =>
                    download(`/batches/${batchId}/profiles/${profileId}/sheet.xlsx`, "new-jobs.xlsx")
                      .catch((err) => setNote({ bad: true, text: err.message }))}>
                    Download as Excel
                  </button>
                )}
              </div>

              {newJobs.length === 0 ? (
                <div className="notice">
                  {done
                    ? "All jobs from this list have been moved to All jobs."
                    : batch.status !== "open"
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
                          ? `${visible.length} of ${newJobs.length} shown`
                          : `${newJobs.length} on the list`}
                      </span>
                      {needle && (
                        <button className="link" onClick={() => setFilter("")}>clear</button>
                      )}
                    </div>
                  </div>

                  {needle && visible.length === 0 ? (
                    <div className="card pad muted">
                      Nothing on this list matches “{filter}”. Try a colleague's name, a client, or a platform.
                    </div>
                  ) : (
                  <div className="card scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Job</th><th>Company</th><th>Found by</th><th>Platform</th><th>Found on</th>
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
                            {/* When the posting was found, not when this
                                profile applied — it has not, which is why the
                                row is here. Reading a job as three days old or
                                three weeks old is what decides whether the
                                link is still worth opening. */}
                            <td className="mono muted" style={{ whiteSpace: "nowrap", fontSize: 12 }}
                                title={job.found_by?.length
                                  ? `When ${job.found_by.join(", ")} applied to it`
                                  : "When this posting first came into the system"}>
                              {job.found_on || "—"}
                            </td>
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
                              <select value={job.status}
                                      onChange={(e) => chooseStatus(job, e.target.value)}>
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
