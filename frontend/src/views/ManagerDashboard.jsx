import React, { useCallback, useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import {
  AssessmentBoard, Availability, CyclePicker, DateRange, DeveloperBoard, Funnel,
  InterviewRows, Loading, Progress, RangeReport, Skills, Sparkline, StageLadder,
  Stalled, TeamBoard, Tiles, sinceText,
} from "./widgets.jsx";
import PersonDashboard from "./PersonDashboard.jsx";

/** One developer, close up.
 *
 * The manager checking on the half of the operation that does not type: who is
 * free, what is in their diary, and which interviews nobody has reported back
 * on. Outcomes are editable from here on purpose — the person chasing them is
 * usually the one on this screen.
 */
function DeveloperView({ person, batchId, dateRange, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.developerDashboard(person.user_id, batchId, dateRange.dateFrom, dateRange.dateTo)
      .then(setData).catch((err) => setError(err.message));
  }, [person.user_id, batchId, dateRange]);

  useEffect(() => { setData(null); load(); }, [load]);

  const change = (id, patch) =>
    api.updateInterview(id, patch).then(load).catch((err) => setError(err.message));

  // A manager reading a developer's screen is the person most likely to spot a
  // conversation that stalled, because they are the one looking across all of
  // them. So it is actionable here rather than a read-only observation.
  const advance = (row) =>
    api.nextRound(row.id).then(load).catch((err) => setError(err.message));

  if (error) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={4} />;

  const { counts, funnel } = data;

  return (
    <section className="card pad stack detail" style={{ gap: 14 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2>{data.developer.name}</h2>
          <p className="muted" style={{ marginTop: 3 }}>
            {data.profiles.length
              ? <>Applied as {data.profiles.map((p) => p.name).join(", ")} · this is their own screen.</>
              : "Not behind any profile, so they sign in to an empty desk."}
          </p>
        </div>
        <button className="link" onClick={onClose}>Close</button>
      </div>

      <Tiles items={[
        { label: "today", value: counts.today, tone: counts.today ? "petrol" : undefined },
        { label: "next seven days", value: counts.week },
        { label: "no outcome recorded", value: counts.awaiting_outcome,
          tone: counts.awaiting_outcome ? "brick" : undefined },
        { label: "offers", value: funnel.offers, tone: funnel.offers ? "pine" : undefined },
        { label: "applications in their name", value: funnel.applications, foot: "all time" },
        { label: "reached an interview", value: `${funnel.interview_rate}%` },
        data.assessments?.counts.total ? {
          label: "take-homes outstanding", value: data.assessments.counts.open,
          tone: data.assessments.counts.overdue ? "brick" : undefined,
          foot: data.assessments.counts.overdue
            ? `${data.assessments.counts.overdue} past the deadline` : undefined,
          hint: "Work sitting on this developer's week that no calendar shows.",
        } : null,
      ]} />

      <Funnel data={funnel} awaiting={counts.awaiting_outcome} />
      <StageLadder rows={funnel?.by_stage} />

      <RangeReport report={data.report} show="interviews" />

      <Stalled rows={data.stalled} onNextRound={advance} />

      <AssessmentBoard
        data={data.assessments}
        heading={`Take-homes on ${data.developer.name}`}
        note="A diary says they are free Thursday; a test due Friday says otherwise."
      />

      {data.profiles.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
          {data.profiles.map((row) => (
            <div className="card pad stack" key={row.profile_id} style={{ gap: 8 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <b style={{ fontFamily: "var(--display)" }}>{row.name}</b>
                  <div className="muted">{row.headline || "—"}
                    {row.person ? ` · run by ${row.person}` : " · nobody runs it"}</div>
                </div>
                <Availability value={row.availability} small />
              </div>
              <Skills value={row.skills} limit={5} />
              <div className="row muted" style={{ gap: 10, fontSize: 12 }}>
                <span>{row.email || "no email"}</span>
                {safeUrl(row.resume_url)
                  ? <a href={safeUrl(row.resume_url)} target="_blank" rel="noreferrer noopener">resume</a>
                  : <span style={{ color: "var(--brick)" }}>no resume link</span>}
                {row.rate && <span>{row.rate}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {data.today.length > 0 && (
        <div>
          <h3>Today</h3>
          <div style={{ marginTop: 8 }}>
            <InterviewRows rows={data.today} showProfile onChange={change}
                           onNextRound={advance} />
          </div>
        </div>
      )}

      <div>
        <h3>Coming up</h3>
        <div style={{ marginTop: 8 }}>
          <InterviewRows rows={data.upcoming} showProfile onChange={change}
                         onNextRound={advance}
                         empty="Nothing booked in the next fortnight." />
        </div>
      </div>

      {data.recent.length > 0 && (
        <div>
          <h3>What happened</h3>
          <div style={{ marginTop: 8 }}>
            <InterviewRows rows={data.recent} showProfile onChange={change}
                           onNextRound={advance} />
          </div>
        </div>
      )}
    </section>
  );
}

/** One profile, close up. Opened by clicking a row on either table. */
function ProfileDetail({ profileId, batchId, dateRange, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api.profileDetail(profileId, batchId, dateRange.dateFrom, dateRange.dateTo)
      .then(setData).catch((err) => setError(err.message));
  }, [profileId, batchId, dateRange]);

  if (error) return <div className="notice">{error}</div>;
  if (!data) return <Loading lines={4} />;

  const { profile, stats } = data;

  return (
    <section className="card pad stack detail" style={{ gap: 14 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2>{profile.name}</h2>
          <p className="muted" style={{ marginTop: 3 }}>
            {profile.headline || "—"} · run by {profile.person || "nobody"}
            {profile.platform ? ` · ${profile.platform}` : ""}
            {!profile.shared && " · not on the team board"}
          </p>
        </div>
        <button className="link" onClick={onClose}>Close</button>
      </div>

      <Tiles items={[
        { label: "logged this cycle", value: stats.logged },
        { label: "a colleague also found", value: stats.duplicates,
          tone: stats.duplicates ? "brick" : undefined },
        { label: "handed to this profile", value: stats.assigned },
        { label: "applied", value: stats.applied, tone: "pine" },
        { label: "still to do", value: stats.pending },
        { label: "applications all time", value: stats.all_time },
      ]} />

      <RangeReport report={data.report} whose={profile.name} />

      <AssessmentBoard
        data={data.assessments}
        heading={`Take-homes under ${profile.name}`}
        note="Tests a client sent to this identity."
      />

      <div>
        <h3>Logged day by day</h3>
        <div className="card pad" style={{ marginTop: 8 }}>
          <Sparkline series={data.activity} />
        </div>
      </div>

      {data.cycles.length > 0 && (
        <div>
          <h3>Cycle by cycle</h3>
          <div className="card scroll" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr><th>Cycle</th><th className="num">Logged</th><th className="num">Given</th>
                    <th className="num">Applied</th></tr>
              </thead>
              <tbody>
                {data.cycles.map((cycle) => (
                  <tr key={cycle.id}>
                    <td>{cycle.name}</td>
                    <td className="mono num">{cycle.logged}</td>
                    <td className="mono num">{cycle.assigned}</td>
                    <td className="mono num">{cycle.applied}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <h3>The last {data.recent.length} jobs logged</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>
          Newest first, across every cycle this profile has taken part in.
        </p>
        <div className="card scroll">
          <table>
            <thead>
              <tr><th>Job</th><th>Client</th><th>Platform</th><th>Applied on</th></tr>
            </thead>
            <tbody>
              {data.recent.map((job, i) => (
                <tr key={i}>
                  <td className="truncate">
                    {safeUrl(job.url)
                      ? <a href={safeUrl(job.url)} target="_blank" rel="noreferrer noopener">{job.title || job.url}</a>
                      : (job.title || "—")}
                  </td>
                  <td>{job.company || "—"}</td>
                  <td className="muted">{job.platform || "—"}</td>
                  <td className="mono muted" style={{ fontSize: 12 }}>
                    {job.applied_on || sinceText(job.logged_at)}
                  </td>
                </tr>
              ))}
              {!data.recent.length && (
                <tr><td colSpan={4} className="muted">Nothing logged yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/** One person's dashboard, opened by the manager.
 *
 * The very screen that person gets — same component, same payload — with the
 * switch that decides whether they get it sitting on top of it. Checking what
 * you are about to show somebody and showing it are then the same act.
 */
function PersonView({ person, batchId, dateRange, onBatchChange, onClose, onToggle, busy }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api.personDashboard(person.user_id, batchId, dateRange.dateFrom, dateRange.dateTo)
      .then(setData).catch((err) => setError(err.message));
  }, [person.user_id, batchId, dateRange]);

  const open = person.dashboard_visible;

  return (
    <section className="stack detail card pad" style={{ gap: 14 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2>Looking at {person.name}&apos;s dashboard</h2>
          <p className="muted" style={{ marginTop: 3, maxWidth: 620 }}>
            {open
              ? `${person.name} can open this screen themselves. This is exactly what they see.`
              : `${person.name} cannot see this yet. Nothing here is hidden from you — the switch decides whether it is hidden from them.`}
          </p>
        </div>
        <div className="row">
          <label className="row" style={{ gap: 8 }}>
            <input type="checkbox" checked={open} disabled={busy}
                   onChange={(e) => onToggle(person, e.target.checked)} />
            <b style={{ fontFamily: "var(--display)", color: open ? "var(--pine)" : "var(--slate)" }}>
              {open ? `Open to ${person.name}` : "Manager only"}
            </b>
          </label>
          <button className="link" onClick={onClose}>Close</button>
        </div>
      </div>

      {error && <div className="notice">{error}</div>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && (
        <PersonDashboard data={data} batchId={batchId} onBatchChange={onBatchChange}
                         viewingAs={person.name} />
      )}
    </section>
  );
}

/** The duplicate rate over recent cycles.
 *
 * The number a manager should actually be steering: the share of the team's
 * typing that two profiles spent on the same posting. Drawn as bars rather
 * than a table because the only question is whether it is going down.
 */
function History({ rows }) {
  if (rows.length < 2) return null;
  const peak = Math.max(1, ...rows.map((r) => r.duplicate_pct));
  return (
    <section>
      <h3>Duplicated effort, cycle by cycle</h3>
      <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
            Rows handed in that a second profile had already found.
          </p>
      <div className="card pad scroll">
        <div className="history">
          {rows.map((row) => (
            <div className="history-col" key={row.id} title={`${row.duplicates} of ${row.rows_read} rows`}>
              <span className="mono history-value">{row.duplicate_pct}%</span>
              <div className="history-bar">
                <i style={{
                  height: `${Math.max(3, (row.duplicate_pct / peak) * 100)}%`,
                  background: row.duplicate_pct > 20 ? "var(--brick)" : "var(--pine)",
                }} />
              </div>
              <span className="muted history-label truncate">{row.name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function ManagerDashboard({ onOpenBatches }) {
  const [data, setData] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [dateRange, setDateRange] = useState({ dateFrom: "", dateTo: "" });
  const [openProfile, setOpenProfile] = useState(null);
  const [openPerson, setOpenPerson] = useState(null);
  const [openDev, setOpenDev] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [note, setNote] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (id) => {
    try {
      const next = await api.overview(id, dateRange.dateFrom, dateRange.dateTo);
      setData(next);
      if (!id && next.batch) setBatchId(next.batch.id);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  }, [dateRange]);

  useEffect(() => { load(batchId); }, [batchId, load]);

  // Cycles rebuild on a timer behind the manager's back, so the screen refreshes
  // itself rather than showing a figure that stopped being true.
  useEffect(() => {
    const tick = setInterval(() => load(batchId), 30000);
    return () => clearInterval(tick);
  }, [batchId, load]);

  const toggleBoard = async (visible) => {
    setSaving(true);
    try {
      const settings = await api.saveSettings({ team_board_visible: visible });
      setData((current) => (current ? { ...current, settings } : current));
      setNote({
        text: visible
          ? "The team board is open. Everyone can now see how every shared profile is doing."
          : "The team board is closed. People see only their own numbers again.",
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const togglePerson = async (person, open) => {
    setSaving(true);
    try {
      await api.updateUser(person.user_id, { dashboard_visible: open });
      await load(batchId);
      setNote({
        text: open
          ? `${person.name} can now see their own dashboard — their figures, their progress, nobody else's.`
          : `${person.name}'s dashboard is closed again. Their work is unaffected; only the screen is gone.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const shareProfile = async (profileId, share) => {
    try {
      await api.updateProfile(profileId, { share_progress: share });
      await load(batchId);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  if (!data) return <Loading lines={5} figures />;

  const { org, batch, people, profiles, missing, settings } = data;
  const diary = data.interviews;
  const boardOpen = !!settings?.team_board_visible;
  const closedCount = people.filter((p) => p.role !== "admin" && !p.dashboard_visible).length;

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Dashboard</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            {batch
              ? <>Cycle <b>{batch.name}</b> · {batch.status === "open" ? "running" : "closed"}
                  {batch.last_built_at && <> · lists rebuilt {sinceText(batch.last_built_at)}</>}</>
              : "No cycle has been opened yet."}
          </p>
        </div>
        <div className="row">
          <CyclePicker batches={data.batches} value={batchId || batch?.id} onChange={(id) => {
            setBatchId(id);
            setOpenProfile(null);
          }} />
          <DateRange {...dateRange} onChange={setDateRange} />
          {onOpenBatches && <button className="ghost" onClick={onOpenBatches}>Run the cycle</button>}
        </div>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      <Tiles items={[
        { label: "profiles handed in", value: `${org.handed_in}/${org.expected}`,
          tone: org.handed_in < 2 ? "brick" : undefined,
          hint: "Two sheets are the minimum before anything can be compared." },
        { label: "jobs found by their own profiles", value: org.own_found },
        { label: "jobs found by colleagues", value: org.from_others },
        { label: "postings found twice", value: org.duplicates,
          tone: org.duplicates ? "brick" : undefined,
          foot: `${org.wasted_rows} rows typed twice · ${org.duplicate_pct}%`,
          hint: "Postings more than one profile logged. Counted once each, however many people found them." },
        { label: "places on lists", value: org.assigned },
        { label: "applied from those lists", value: org.applied, tone: "pine" },
        { label: "skipped from those lists", value: org.skipped },
        { label: "of all lists worked through", value: `${org.done_pct}%` },
      ]} />

      {missing.length > 0 && (
        <div className="notice">
          <b>Waiting on {missing.length} profile{missing.length === 1 ? "" : "s"}.</b>{" "}
          {missing.map((row) => `${row.name}${row.person ? ` (${row.person})` : ""}`).join(", ")}
          {" "}{missing.length === 1 ? "has" : "have"} not handed in for this cycle. The lists
          rebuild without them until they do.
        </div>
      )}

      {diary && diary.counts.awaiting_time > 0 && (
        <div className="notice gate">
          <b>{diary.counts.awaiting_time} {diary.counts.awaiting_time === 1
            ? "reply" : "replies"} waiting on a time.</b> Nobody has anything to turn up to yet.
        </div>
      )}

      {diary && diary.counts.today > 0 && (
        <div className="notice gate">
          <b>{diary.counts.today} interview{diary.counts.today === 1 ? "" : "s"} today.</b>{" "}
          {diary.today.map((row) => `${row.when.time} ${row.profile}`
            + `${row.client ? ` · ${row.client}` : ""}`).join(" · ")} — Eastern time.
        </div>
      )}

      {diary && diary.counts.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{diary.counts.awaiting_outcome} interview
          {diary.counts.awaiting_outcome === 1 ? "" : "s"} with no outcome.</b> Every rate below
          reads low until somebody says.
        </div>
      )}

      {data.assessments?.counts.overdue > 0 && (
        <div className="notice">
          <b>{data.assessments.counts.overdue} take-home
          {data.assessments.counts.overdue === 1 ? "" : "s"} past the deadline.</b> Nothing else
          here shows this.
        </div>
      )}

      {diary?.counts.stalled > 0 && (
        <div className="notice">
          <b>{diary.counts.stalled} conversation{diary.counts.stalled === 1 ? "" : "s"} cleared
          a round, then stopped.</b> They read as successes everywhere else.
        </div>
      )}

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>What the applications produced</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Everything above counts effort. This is the part a client decides.
          </p>
        </div>
        <StageLadder rows={data.funnel?.by_stage} />
        <p className="muted">Round progression: {data.funnel?.rounds?.initial || 0} initial,
          {" "}{data.funnel?.rounds?.two_or_more || 0} reached round 2,
          {" "}{data.funnel?.rounds?.three_or_more || 0} reached round 3+.</p>
        <Funnel data={data.funnel} awaiting={diary?.counts.awaiting_outcome || 0}
                note="Applications are all-time across the workspace. Interviews are never
                      filtered to a cycle: a reply that lands three weeks late belongs to the
                      work that earned it, not to whichever cycle happened to be open." />

        {diary?.today.length > 0 && (
          <div>
            <h3>Interviews today</h3>
            <div style={{ marginTop: 8 }}>
              <InterviewRows rows={diary.today} showProfile />
            </div>
          </div>
        )}
        {diary?.upcoming.length > 0 && (
          <div>
            <h3>Coming up</h3>
            <div style={{ marginTop: 8 }}>
              <InterviewRows rows={diary.upcoming.slice(0, 12)} showProfile />
            </div>
          </div>
        )}

        {/* Read-only from the workspace view. Whoever runs that profile books
            the next round, and their screen is one click away under The
            developers — a manager quietly booking into somebody else's client
            relationship is how one reply becomes two conversations. */}
        <Stalled rows={diary?.stalled} />

        <AssessmentBoard
          data={data.assessments}
          heading="Take-homes across the workspace"
          note="Set by a BD, done by a developer. The only work here with a deadline."
          limit={12}
        />
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>The developers</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Who is behind each profile, and what is in their diary.
            {" "}<b>Open</b> shows their screen as they see it.
          </p>
        </div>
        <DeveloperBoard rows={data.developers || []} onOpen={(row) => {
          setOpenDev(row);
          setOpenPerson(null);
          setOpenProfile(null);
        }} />
      </section>

      {openDev && (
        <DeveloperView person={openDev} batchId={batchId || batch?.id}
                       dateRange={dateRange}
                       onClose={() => setOpenDev(null)} />
      )}

      <section className="card pad stack" style={{ gap: 12 }}>
        <div>
          <h2>Who can see what</h2>
          <p className="muted" style={{ marginTop: 3, maxWidth: 680 }}>
            Two separate questions. You can see all of it whatever these say.
          </p>
        </div>

        <div className="notice ok gate">
          <b>1. Can a person see their own figures?</b> Off until you open it, one person at a
          time, in the <b>Their dashboard</b> column below — or from the switch on their own
          dashboard, which <b>Open</b> puts you inside.
          {closedCount > 0
            ? ` ${closedCount} ${closedCount === 1 ? "person has" : "people have"} no dashboard yet.`
            : " Everyone on the team has theirs."}
          {" "}Closing it takes nothing away from their work: their list and the sheet they hand
          in are untouched, only the screen of figures goes.
        </div>

        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <b style={{ fontFamily: "var(--display)" }}>2. Can they see each other?</b>
            <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Every profile side by side, ranked. Only reaches people who already
            have a dashboard.
          </p>
          </div>
          <label className="row" style={{ gap: 8 }}>
            <input type="checkbox" checked={boardOpen} disabled={saving}
                   onChange={(e) => toggleBoard(e.target.checked)} />
            <b style={{ fontFamily: "var(--display)", color: boardOpen ? "var(--pine)" : "var(--slate)" }}>
              {boardOpen ? "Open to the team" : "Manager only"}
            </b>
          </label>
        </div>
        {boardOpen && (
          <p className="hint">
            Take one profile off it under <b>Every profile</b> below.
          </p>
        )}
      </section>

      <section>
        <h3>Jobs logged across the team</h3>
        <p className="muted" style={{ margin: "3px 0 9px" }}>
          Every profile, over the last thirty days, in Eastern time.
        </p>
        <div className="card pad"><Sparkline series={data.activity} /></div>
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Each person</h2>
          <p className="hint" style={{ marginTop: 3 }}>
            Profiles added up per person. Open a row to see them separately.
          </p>
        </div>
        <div className="card scroll">
          <table className="board">
            <thead>
              <tr>
                <th>Person</th>
                <th className="num">Profiles</th>
                <th className="num">Handed in</th>
                <th className="num">Logged</th>
                <th className="num" title="Jobs they logged that a colleague had already found">
                  Also found
                </th>
                <th className="num">List</th>
                <th className="num">Applied</th>
                <th style={{ width: 150 }}>Worked through</th>
                <th>Last logged</th>
                <th title="Whether this person may open their own dashboard">Their dashboard</th>
              </tr>
            </thead>
            <tbody>
              {people.map((person) => (
                <React.Fragment key={person.user_id}>
                  <tr style={{ cursor: "pointer" }}
                      onClick={() => setExpanded(expanded === person.user_id ? null : person.user_id)}>
                    <td>
                      <b>{person.name}</b>
                      {person.role === "admin" && <span className="pill" style={{ marginLeft: 6 }}>manager</span>}
                      <div className="muted mono" style={{ fontSize: 11 }}>{person.email}</div>
                    </td>
                    <td className="mono num">{person.runs}</td>
                    <td className="mono num"
                        style={{ color: person.runs && person.handed_in < person.runs ? "var(--brick)" : undefined }}>
                      {person.handed_in}/{person.runs}
                    </td>
                    <td className="mono num">{person.logged}</td>
                    <td className="mono num" style={{ color: person.duplicates ? "var(--brick)" : undefined }}>
                      {person.duplicates}
                    </td>
                    <td className="mono num">{person.assigned}</td>
                    <td className="mono num"><b>{person.applied}</b></td>
                    <td>
                      <Progress applied={person.applied} skipped={person.skipped} pending={person.pending} />
                      <span className="muted mono" style={{ fontSize: 11 }}>{person.done_pct}%</span>
                    </td>
                    <td className="muted">{sinceText(person.last_logged)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                        <label className="row" style={{ gap: 5 }}>
                          <input type="checkbox" checked={!!person.dashboard_visible}
                                 disabled={saving || person.role === "admin"}
                                 title={person.role === "admin"
                                   ? "Managers always have their dashboard."
                                   : `Let ${person.name} see their own figures`}
                                 onChange={(e) => togglePerson(person, e.target.checked)} />
                          <span className={person.dashboard_visible ? "pill on" : "pill off"}>
                            {person.dashboard_visible ? "open" : "closed"}
                          </span>
                        </label>
                        <button className="ghost" style={{ padding: "5px 9px", fontSize: 12 }}
                                onClick={() => { setOpenPerson(person); setOpenProfile(null); }}>
                          Open
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expanded === person.user_id && (
                    <tr>
                      <td colSpan={10} style={{ background: "var(--paper)" }}>
                        {person.profiles.length ? (
                          <div className="row" style={{ gap: 8 }}>
                            <span className="muted">Runs:</span>
                            {person.profiles.map((p) => (
                              <button key={p.id} className="ghost" onClick={() => setOpenProfile(p.id)}>
                                {p.name}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">
                            No profile assigned. They cannot hand anything in until one is.
                          </span>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {!people.length && (
                <tr><td colSpan={10} className="muted">Nobody on the team yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {openPerson && (
        <PersonView
          person={people.find((p) => p.user_id === openPerson.user_id) || openPerson}
          batchId={batchId || batch?.id}
          dateRange={dateRange}
          onBatchChange={setBatchId}
          onToggle={togglePerson}
          busy={saving}
          onClose={() => setOpenPerson(null)} />
      )}

      {openProfile && (
        <ProfileDetail profileId={openProfile} batchId={batchId || batch?.id}
                       dateRange={dateRange}
                       onClose={() => setOpenProfile(null)} />
      )}

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Every profile</h2>
          <p className="muted" style={{ marginTop: 3 }}>
            Click a row to open it. Ranked by jobs applied to this cycle.
          </p>
        </div>
        <TeamBoard rows={profiles} onOpen={setOpenProfile} />
        {boardOpen && (
          <div className="card pad">
            <h3>On the team board</h3>
            <p className="muted" style={{ margin: "3px 0 10px" }}>
              Uncheck a profile to keep it off the shared board. It stays on this screen.
            </p>
            <div className="row" style={{ gap: 14 }}>
              {profiles.map((row) => (
                <label key={row.profile_id} className="row" style={{ gap: 6 }}>
                  <input type="checkbox" checked={row.shared}
                         onChange={(e) => shareProfile(row.profile_id, e.target.checked)} />
                  {row.name}
                </label>
              ))}
            </div>
          </div>
        )}
      </section>

      <History rows={data.history} />
    </div>
  );
}
