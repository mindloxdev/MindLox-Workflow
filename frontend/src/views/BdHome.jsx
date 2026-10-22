import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import Assessments from "./Assessments.jsx";
import EntryTable from "./EntryTable.jsx";
import ImportHistory from "./ImportHistory.jsx";
import Interviews from "./Interviews.jsx";
import JobRecord from "./JobRecord.jsx";
import { ActionList, bdTodo } from "./Todo.jsx";
import {
  Availability, CopyButton, CycleClock, CyclePicker, Empty, References, Segment, Skills,
  useModalFocus,
} from "./widgets.jsx";

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

// The reasons that come up again and again, offered as one tap so the manager's
// report groups them under the same words. Anything else is still written out
// in the box, and a picked reason can have a detail added after it.
const SKIP_REASONS = [
  "Already Applied",
  "Job expired",
  "Website error",
  "Travel Required",
  "Onsite",
  "Hybrid",
  "Certification Required",
  "Life insurance",
  "Sales",
];

/** Which listed reason the text starts with, if any. */
const pickedReason = (text) => {
  const t = text.trim().toLowerCase();
  return SKIP_REASONS.find((r) => t.startsWith(r.toLowerCase())
    && !/[a-z0-9]/.test(t.charAt(r.length))) || null;
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
  const [how, setHow] = useState("type");      // type | upload | history
  // The workspace switches. Only one matters on this screen: whether a whole
  // selection may be marked in one press. Read rather than assumed, because
  // the server refuses the press when it is off and a button that throws is
  // worse than a button that is not there.
  const [switches, setSwitches] = useState({ bulk_actions_enabled: false });
  // Which of the others' jobs are ticked, by assignment id. A Set rather than
  // a flag on each row: the rows are replaced wholesale every time the lists
  // rebuild, and a selection kept on them would be wiped every sixty seconds.
  const [picked, setPicked] = useState(() => new Set());
  // True while a whole selection is being written. The press goes up in
  // slices, so this is what stops a second one starting on top of the first.
  const [busyBulk, setBusyBulk] = useState(false);
  // Narrows the new-jobs list. Client-side on purpose: the whole list is
  // already here, so filtering it is instant and a request per keystroke would
  // be slower and worse.
  const [filter, setFilter] = useState("");
  // The jobs waiting on a reason before they can be skipped. A skip retires the
  // posting from this profile for good and never comes back in a later cycle,
  // so it is the one status change that asks a question first — and that is as
  // true of two hundred at once as it is of one, which is why this holds a list
  // and the same dialog serves both.
  const [skipping, setSkipping] = useState(null);   // { ids, title, company }
  const [skipReason, setSkipReason] = useState("");
  // Skip it for every profile this person runs. Off each time on purpose:
  // it is a decision about this job, not a setting, and a sticky checkbox
  // would quietly retire postings from a market nobody meant to close.
  const [skipEverywhere, setSkipEverywhere] = useState(false);
  const fileInput = useRef(null);
  // The file that was just read, kept so a different tab of the same workbook
  // can be asked for without making the person find the file again.
  const lastFile = useRef(null);
  // The skip dialog asks a question that retires a job for good, so the
  // keyboard stays inside it until it is answered or dismissed.
  const skipBox = useRef(null);
  useModalFocus(!!skipping, skipBox);

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

  useEffect(() => {
    api.settings().then(setSwitches).catch(() => {});
  }, []);

  // A selection belongs to one profile's list in one cycle. Carrying it across
  // either would mean a press landing on rows nobody looked at.
  useEffect(() => { setPicked(new Set()); }, [profileId, batchId, tab]);

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

  const send = async (file, sheet = "") => {
    if (!file || !batchId || !profileId) return;
    lastFile.current = file;
    setBusy(true);
    setNote(null);
    try {
      const data = await api.upload(batchId, profileId, file, sheet);
      setUpload(data);
      setNote({ text: `${data.usable_count ?? data.row_count} of ${data.row_count} rows `
                    + `are usable for ${data.profile}`
                    + (data.sheet ? `, read from the “${data.sheet}” tab` : "")
                    + ". Check the columns below." });
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

  const mark = async (assignmentId, status, reason = "", everyProfile = false) => {
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
      const saved = await api.setStatus(assignmentId, status, reason, everyProfile);
      if (saved.also_skipped) {
        setNote({ text: `Skipped here and on ${saved.also_skipped} other `
                      + `profile${saved.also_skipped === 1 ? "" : "s"} you run. `
                      + "It will not come back to any of them." });
        loadSheets();
      }
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
      setSkipEverywhere(false);
      setSkipping({ ids: [job.id], title: job.title, company: job.company });
      return;
    }
    mark(job.id, status);
  };

  /** Tapping a reason swaps it in for the one already picked, keeping any
   *  detail written after it; tapping the picked one again takes it off. */
  const pickReason = (reason) => setSkipReason((now) => {
    const current = pickedReason(now);
    const rest = current
      ? now.trim().slice(current.length).replace(/^\s*[—:-]?\s*/, "")
      : now.trim();
    if (current === reason) return rest;
    return rest ? `${reason} — ${rest}` : reason;
  });

  const confirmSkip = async () => {
    const reason = skipReason.trim();
    if (!reason) return;
    const target = skipping;
    const everywhere = skipEverywhere;
    setSkipping(null);
    if (target.ids.length === 1) {
      await mark(target.ids[0], "skipped", reason, everywhere);
      return;
    }
    await markMany(target.ids, "skipped", reason, everywhere);
  };

  /* ── One decision over a whole selection ──────────────────────────────── */

  const toggleOne = (id) => setPicked((now) => {
    const next = new Set(now);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  /** Marking the lot.
   *
   * Sent in slices because the server caps one press at 500 rows, and pressed
   * through to the end rather than stopping at the first slice — a selection of
   * six hundred that half applied would be worse than one that failed outright,
   * because nobody could tell which half.
   */
  const markMany = async (ids, status, reason = "", everyProfile = false) => {
    if (!ids.length) return;
    setBusyBulk(true);
    setNote(null);
    try {
      let updated = 0;
      let elsewhere = 0;
      for (let at = 0; at < ids.length; at += 200) {
        const saved = await api.setStatusMany(ids.slice(at, at + 200), status,
                                              reason, everyProfile);
        updated += saved.updated;
        elsewhere += saved.also_skipped || 0;
      }
      setPicked(new Set());
      const what = status === "applied" ? "moved to All jobs" : status === "skipped"
        ? `skipped — gone from ${profile?.name} for good` : "put back on the list";
      setNote({
        text: `${updated} job${updated === 1 ? "" : "s"} ${what}.`
            + (elsewhere ? ` Also skipped on ${elsewhere} row${elsewhere === 1 ? "" : "s"} `
                         + "across your other profiles." : "")
            + (updated < ids.length
                ? ` ${ids.length - updated} were already off this list — the lists rebuild `
                  + "while you work."
                : ""),
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusyBulk(false);
      loadSheets();
    }
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

  // "All" means what is on screen, never what is behind the filter. Somebody
  // who has narrowed a list to one client and pressed select-all has said
  // something about that client; quietly including the four hundred rows they
  // filtered out would be the opposite of what they asked for.
  const selectable = visible.map((job) => job.id);
  const chosen = selectable.filter((id) => picked.has(id));
  const allPicked = selectable.length > 0 && chosen.length === selectable.length;
  const canBulk = !!switches.bulk_actions_enabled;

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
        <div className="card pad stack" ref={skipBox} role="alertdialog" aria-modal="true"
             style={{ gap: 10, borderLeft: "3px solid var(--brick)" }}>
          <div>
            <b style={{ fontFamily: "var(--display)" }}>
              {skipping.ids.length > 1
                ? `Why are you skipping these ${skipping.ids.length}?`
                : "Why are you skipping this one?"}
            </b>
            <p className="muted" style={{ marginTop: 3 }}>
              {skipping.ids.length > 1 ? (
                <>The same reason goes on all <b>{skipping.ids.length}</b> of them.</>
              ) : (
                <>
                  <b>{skipping.title || "This job"}</b>
                  {skipping.company ? <> at <b>{skipping.company}</b></> : null}.
                </>
              )}
            </p>
            <p className="hint" style={{ marginTop: 6, maxWidth: 620 }}>
              Skipping retires {skipping.ids.length > 1 ? "them" : "it"} from{" "}
              {profile?.name} for good — {skipping.ids.length > 1 ? "they" : "it"} will
              not come back in a later cycle. Your manager reads these to see whether
              the searches feeding this profile are landing, so pick a reason below
              or write your own in a few words.
            </p>
          </div>
          <div className="row" role="group" aria-label="Common reasons"
               style={{ gap: 6, flexWrap: "wrap" }}>
            {SKIP_REASONS.map((r) => {
              const on = pickedReason(skipReason) === r;
              return (
                <button key={r} type="button" className="pill" aria-pressed={on}
                        onClick={() => pickReason(r)}>
                  {r}
                </button>
              );
            })}
          </div>
          <textarea rows={3} autoFocus value={skipReason}
                    placeholder="Or write your own — wrong seniority, this one wants 10 years."
                    onChange={(e) => setSkipReason(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmSkip();
                      if (e.key === "Escape") setSkipping(null);
                    }} />
          {profiles.length > 1 && (
            <label className="row" style={{ gap: 8, alignItems: "flex-start" }}>
              <input type="checkbox" checked={skipEverywhere} style={{ marginTop: 3 }}
                     onChange={(e) => setSkipEverywhere(e.target.checked)} />
              <span>
                <b>
                  Skip {skipping.ids.length > 1 ? "them" : "it"} for all{" "}
                  {profiles.length} profiles I run
                </b>
                <p className="hint" style={{ marginTop: 2, maxWidth: 620 }}>
                  Leave this off when the {skipping.ids.length > 1 ? "jobs are" : "job is"}{" "}
                  simply wrong for <b>{profile?.name}</b> — {skipping.ids.length > 1
                    ? "they may suit" : "it may suit"} one of your other names.
                  Tick it when the reason is about the job itself: the rate, on-site
                  only, a client you are already working. Otherwise the same posting
                  comes round again under your other name next week.
                </p>
              </span>
            </label>
          )}

          <div className="row" style={{ gap: 10 }}>
            <button onClick={confirmSkip} disabled={!skipReason.trim()}>
              {skipping.ids.length > 1
                ? skipEverywhere && profiles.length > 1
                  ? `Skip all ${skipping.ids.length}, on all ${profiles.length} profiles`
                  : `Skip all ${skipping.ids.length}`
                : skipEverywhere && profiles.length > 1
                  ? `Skip it for all ${profiles.length}`
                  : "Skip it"}
            </button>
            <button className="ghost" onClick={() => setSkipping(null)}>
              {skipping.ids.length > 1 ? "Keep them on the list" : "Keep it on the list"}
            </button>
          </div>
        </div>
      )}

      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Your work</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Applying as <b>{profile?.name}</b>{profile?.headline ? ` · ${profile.headline}` : ""}.
          </p>
        </div>
        <div className="row" style={{ gap: 10 }}>
          {/* The manager's clock. Absent unless one is set, and gone the
              moment it runs out — nothing about the cycle changes then, so a
              spent clock sitting over the work would be a warning about
              nothing. */}
          <CycleClock batch={batch} />
          <CyclePicker batches={batches} value={batchId} onChange={setBatchId} />
        </div>
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
        heading="Updates on interview & Assessments"
        empty={{
          title: "You are straight.",
          body: "No client is waiting on a time, nothing is past a deadline, your "
              + "to-do list is clear and this cycle's jobs are handed in.",
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
                <h3>Developer</h3>
                {profile.developer
                  ? <p style={{ marginTop: 3, fontWeight: 500 }}>{profile.developer}</p>
                  : <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
                      Nobody is attached to <b>{profile.name}</b>, so an interview
                      booked against it reaches no one.
                    </p>}
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

            <References rows={profile.references} who={profile.developer || ""} />

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
          {/* "Own jobs" and "Others' jobs" — the same pair of words used on
              every other screen in the app. They used to be "Own jobs" and
              "New jobs", which named one by where it came from and the other
              by how recent it was, so nothing in the pair told you they were
              opposites. */}
          <Segment
            label="What you are working on"
            value={tab}
            onChange={setTab}
            items={[
              { key: "applied", label: "Own jobs", count: handedIn },
              { key: "new", label: "Others' jobs", count: newJobs.length },
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
              heading="Assessments from clients"
              intro="Assessments a client has set. You record it here; the developer behind the profile does it."
            />
          )}

          {tab === "interviews" && (
            <Interviews
              profiles={profiles}
              heading="Interviews"
            />
          )}

          {tab === "applied" && (
            <section className="stack" style={{ gap: 10 }}>
              <div>
                  <h2>Own jobs — what {profile?.name} found</h2>
              </div>

              <div className="row" style={{ gap: 8 }}>
                <button className={how === "type" ? "" : "ghost"} onClick={() => setHow("type")}>
                  Add manually
                </button>
                <button className={how === "upload" ? "" : "ghost"} onClick={() => setHow("upload")}>
                  Upload a sheet
                </button>
                {/* The third way in, and the only one that is not about this
                    week. A team that has been applying for months out of a
                    spreadsheet has nothing here to show for it, so the app
                    keeps handing them postings they worked in June. */}
                <button className={how === "history" ? "" : "ghost"} onClick={() => setHow("history")}>
                  Import past work
                </button>
                <span className="muted">
                  {how === "type"
                    ? "Add jobs one row at a time as you apply."
                    : how === "upload"
                      ? "Already keep a spreadsheet? Drop the whole thing in."
                      : "Months of applying done before this app, filed as your record."}
                </span>
              </div>

              {/* Past work is not this cycle's sheet, so a closed cycle does not
                  stop it. The other two are exactly this cycle's sheet, and do. */}
              {how === "history" ? (
                <ImportHistory
                  profileId={profileId}
                  profileName={profile?.name}
                  onWrote={loadSheets}
                />
              ) : batch.status !== "open" ? (
                <div className="notice">
                  This cycle is closed — your manager has already built the lists. Anything
                  new goes into the next one. <b>Import past work</b> still works: it is
                  your record, not this cycle's sheet.
                </div>
              ) : (
                <>
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

                  {/* Which tab was read. An old sheet is nearly always one
                      workbook with a tab per person, and reading the wrong one
                      files a colleague's work under this profile — so the guess
                      is said out loud and the others are one click away. */}
                  {how === "upload" && upload && (upload.sheets?.length > 1) && (
                    <div className="notice">
                      Read from the <b>{upload.sheet}</b> tab of {upload.sheets.length} in
                      that workbook.
                      <label style={{ display: "block", marginTop: 6 }}>
                        Wrong one?&nbsp;
                        <select value={(upload.sheet || "").trim()} disabled={busy}
                                onChange={(e) => send(lastFile.current, e.target.value)}>
                          {upload.sheets.map((name) => (
                            <option key={name} value={name.trim()}>{name.trim()}</option>
                          ))}
                        </select>
                      </label>
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
                  <h2>Others&apos; jobs for {profile?.name}{profile?.headline ? ` · ${profile.headline}` : ""}</h2>
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
                    download(`/batches/${batchId}/profiles/${profileId}/sheet.xlsx`, "others-jobs.xlsx")
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

                  {/* Select all, and the two things worth doing to a whole
                      selection. Absent — not merely disabled — when the manager
                      has turned it off, because a button that exists and always
                      refuses teaches people to distrust the screen. The server
                      refuses it too; this is the courtesy, not the control. */}
                  {canBulk && visible.length > 0 && (
                    <div className="card pad row" style={{ gap: 12, flexWrap: "wrap",
                                                           alignItems: "center" }}>
                      <label className="row" style={{ gap: 8 }}>
                        <input type="checkbox" checked={allPicked}
                               ref={(box) => {
                                 // Some of them, but not all: the third state a
                                 // checkbox has and the only honest answer here.
                                 if (box) box.indeterminate = chosen.length > 0 && !allPicked;
                               }}
                               onChange={() => setPicked(allPicked
                                 ? new Set()
                                 : new Set(selectable))} />
                        <b>
                          {allPicked ? "Clear the selection" : `Select all ${selectable.length}`}
                          {needle && !allPicked ? " shown" : ""}
                        </b>
                      </label>

                      <span className="muted" style={{ flex: 1, minWidth: 120 }}>
                        {chosen.length
                          ? `${chosen.length} selected`
                          : "Tick rows, or take the lot in one press."}
                      </span>

                      <div className="row" style={{ gap: 8 }}>
                        <button disabled={!chosen.length || busyBulk}
                                onClick={() => markMany(chosen, "applied")}>
                          {busyBulk ? "Working…" : `Mark ${chosen.length || ""} applied`}
                        </button>
                        <button className="ghost" disabled={!chosen.length || busyBulk}
                                onClick={() => {
                                  setSkipReason("");
                                  setSkipEverywhere(false);
                                  setSkipping({ ids: chosen, title: "", company: "" });
                                }}>
                          Skip {chosen.length || ""}…
                        </button>
                      </div>
                    </div>
                  )}

                  {needle && visible.length === 0 ? (
                    <div className="card pad muted">
                      Nothing on this list matches “{filter}”. Try a colleague's name, a client, or a platform.
                    </div>
                  ) : (
                  <div className="card scroll stacks">
                    <table>
                      <thead>
                        <tr>
                          {canBulk && (
                            <th style={{ width: 34 }}>
                              <input type="checkbox" checked={allPicked}
                                     aria-label={allPicked
                                       ? "Clear the selection"
                                       : `Select all ${selectable.length} jobs shown`}
                                     ref={(box) => {
                                       if (box) box.indeterminate = chosen.length > 0 && !allPicked;
                                     }}
                                     onChange={() => setPicked(allPicked
                                       ? new Set()
                                       : new Set(selectable))} />
                            </th>
                          )}
                          <th>Job</th><th>Company</th><th>Found by</th><th>Platform</th><th>Found on</th>
                          <th style={{ minWidth: 220 }}>Link</th><th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((job) => (
                          <tr key={job.id}>
                            {canBulk && (
                              <td data-label="">
                                <input type="checkbox" checked={picked.has(job.id)}
                                       aria-label={`Select ${job.title || "this job"}`}
                                       onChange={() => toggleOne(job.id)} />
                              </td>
                            )}
                            {/* The row's subject: on a phone this is the
                                card's heading rather than another labelled
                                field, which is why it carries no label. */}
                            <td className="truncate" data-label="">
                              {job.title || "—"}
                              {/* The answer to "I am sure I rejected this".
                                  They did — under a different name. */}
                              {job.turned_down_by?.length > 0 && (
                                <div style={{ fontSize: 11, color: "var(--warn-text)" }}
                                     title="A skip is per profile: two profiles are two candidates, and a job wrong for one market can be right for the other.">
                                  you skipped this under{" "}
                                  {job.turned_down_by.join(", ")}
                                </div>
                              )}
                            </td>
                            <td data-label="Company">{job.company || "—"}</td>
                            <td data-label="Found by">
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
                            <td className="muted" data-label="Platform">{job.platform || "—"}</td>
                            {/* When the posting was found, not when this
                                profile applied — it has not, which is why the
                                row is here. Reading a job as three days old or
                                three weeks old is what decides whether the
                                link is still worth opening. */}
                            <td className="mono muted" data-label="Found on"
                                style={{ whiteSpace: "nowrap", fontSize: 12 }}
                                title={job.found_by?.length
                                  ? `When ${job.found_by.join(", ")} applied to it`
                                  : "When this posting first came into the system"}>
                              {job.found_on || "—"}
                            </td>
                            <td data-label="Link">
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
                            <td data-label="">
                              <select value={job.status} aria-label={`Status of ${job.title || "this job"}`}
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
                    <b>To do</b> stays on this cycle until you get to it — it does not
                    follow you into the next one. <b>Applied</b> or <b>skipped</b>
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
