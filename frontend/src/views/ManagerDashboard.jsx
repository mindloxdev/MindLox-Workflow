import React, { useCallback, useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import {
  AssessmentBoard, Availability, CyclePicker, DateRange, DayByDay, DeveloperBoard,
  Flow, Funnel, InterviewRows, Loading, RangeReport, Rounds, Skills,
  StageLadder, Stalled, TeamBoard, Tiles, sinceText,
} from "./widgets.jsx";
import { DoubledUp, Headline, NeedsYou, PeopleTable } from "./ManagerSummary.jsx";
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
        <h3>Jobs found, day by day</h3>
        <div style={{ marginTop: 8 }}>
          <DayByDay series={data.activity} />
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
              <tr><th>Job</th><th>Company</th><th>Platform</th><th>Applied on</th></tr>
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
function PersonView({ person, batchId, dateRange, onBatchChange, onDateRangeChange,
                      onClose, onToggle, busy }) {
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
          <DateRange {...dateRange} onChange={onDateRangeChange} />
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

export default function ManagerDashboard({ onOpenBatches }) {
  const [data, setData] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [dateRange, setDateRange] = useState({ dateFrom: "", dateTo: "" });
  const [openProfile, setOpenProfile] = useState(null);
  const [openPerson, setOpenPerson] = useState(null);
  const [openDev, setOpenDev] = useState(null);
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

  const openTheirScreen = (person) => { setOpenPerson(person); setOpenProfile(null); };

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>How the team is doing</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            {batch
              ? <>Round of work: <b>{batch.name}</b> · {batch.status === "open"
                  ? "still running, so these numbers are still moving"
                  : "finished"}
                  {batch.last_built_at && <> · lists last shared out {sinceText(batch.last_built_at)}</>}</>
              : "No round of work has been started yet."}
          </p>
        </div>
        <div className="row">
          <CyclePicker batches={data.batches} value={batchId || batch?.id}
                       label="Round" onChange={(id) => {
            setBatchId(id);
            setOpenProfile(null);
          }} />
          <DateRange {...dateRange} onChange={setDateRange} />
          {onOpenBatches && <button className="ghost" onClick={onOpenBatches}>Run the round</button>}
        </div>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {/* First, and on its own. Everything below is the picture; this is the
          list of things that will not fix themselves. */}
      <NeedsYou org={org} missing={missing} diary={diary} assessments={data.assessments} />

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>The four numbers</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Left to right is the order the work happens in: applications go out, some of
            them come off a colleague's sheet, a few clients want to talk, and a few of
            those say yes. The grey word on each card says what it counts over.
          </p>
        </div>
        <Headline org={org} funnel={data.funnel} />
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>What the applications turned into</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Everything else on this page counts effort, and effort goes up when people
            work harder. This is the part a client decides, and it only goes up when the
            work was worth sending.
          </p>
        </div>
        <Flow funnel={data.funnel} awaiting={diary?.counts.awaiting_outcome || 0} />
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>Effort spent twice</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            Two people going out and finding the same job. It is the one thing on this
            page that costs money rather than making it, and the whole reason everybody
            hands their sheet into one place.
          </p>
        </div>
        <DoubledUp org={org} history={data.history} />
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>How each person is doing</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            One row per person, busiest first, with everything they run added together.
          </p>
        </div>
        <PeopleTable people={people} onOpen={openTheirScreen}
                     onToggle={togglePerson} busy={saving} />
      </section>

      {openPerson && (
        <PersonView
          person={people.find((p) => p.user_id === openPerson.user_id) || openPerson}
          batchId={batchId || batch?.id}
          dateRange={dateRange}
          onBatchChange={setBatchId}
          onDateRangeChange={setDateRange}
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
          <h2>Jobs found, day by day</h2>
          <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
            The whole team over the last thirty days, on Eastern time. Weekends are
            drawn paler, so a quiet Saturday does not read as a team that stopped.
          </p>
        </div>
        <DayByDay series={data.activity} />
      </section>

      {/* Everything past here is detail. Folded away because a manager who
          opens this screen once a morning should be finished by now — and the
          things they came for stop being findable if six tables sit under
          them. Opening it is one click and the browser remembers nothing, so
          the screen is the same tomorrow. */}
      <details className="more">
        <summary>Show the detail — interviews, tests, developers, every profile</summary>

        <div className="stack" style={{ gap: 22 }}>
          <section className="stack" style={{ gap: 10 }}>
            <div>
              <h2>The conversations, round by round</h2>
              <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
                How far each client conversation got, and where they stop. Interviews are
                never counted against one round of work: a reply that lands three weeks
                late belongs to the applications that earned it.
              </p>
            </div>
            <StageLadder rows={data.funnel?.by_stage} />
            <Rounds rounds={data.funnel?.rounds} />

            {diary?.today.length > 0 && (
              <div>
                <h3>Today</h3>
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

            {/* Read-only from here. Whoever runs that profile books the next
                round, and their screen is one click away under the developers —
                a manager quietly booking into somebody else's client
                relationship is how one reply becomes two conversations. */}
            <Stalled rows={diary?.stalled} />

            <AssessmentBoard
              data={data.assessments}
              heading="Tests clients have set"
              note="Set by whoever runs the profile, done by the developer behind it. The only work here with a deadline on it."
              limit={12}
            />
          </section>

          <section className="stack" style={{ gap: 10 }}>
            <div>
              <h2>The developers</h2>
              <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
                Who is behind each profile, and whether they could take work this week.
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

          <section className="stack" style={{ gap: 10 }}>
            <div>
              <h2>Every profile separately</h2>
              <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
                One person can run several profiles. This is each of them on its own,
                best first. Click a row to open it.
              </p>
            </div>
            <TeamBoard rows={profiles} onOpen={setOpenProfile} />
          </section>

          <section className="card pad stack" style={{ gap: 12 }}>
            <div>
              <h2>Who can see what</h2>
              <p className="muted" style={{ marginTop: 3, maxWidth: 680 }}>
                Two separate questions. You can see all of it whatever these say.
              </p>
            </div>

            <div className="notice ok gate">
              <b>1. Can a person see their own figures?</b> Off until you turn it on, one
              person at a time, in the <b>Own figures</b> column further up this page.
              {closedCount > 0
                ? ` ${closedCount} ${closedCount === 1 ? "person cannot" : "people cannot"} see theirs yet.`
                : " Everybody on the team can see theirs."}
              {" "}Turning it off takes nothing away from their work — their list and the
              sheet they hand in are untouched, only the screen of figures goes.
            </div>

            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <b style={{ fontFamily: "var(--display)" }}>2. Can they see each other?</b>
                <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
                  Every profile side by side, ranked. Only reaches people who can already
                  see their own figures.
                </p>
              </div>
              <label className="row" style={{ gap: 8 }}>
                <input type="checkbox" checked={boardOpen} disabled={saving}
                       onChange={(e) => toggleBoard(e.target.checked)} />
                <b style={{ fontFamily: "var(--display)",
                            color: boardOpen ? "var(--ok-text)" : "var(--slate)" }}>
                  {boardOpen ? "The team can see it" : "Only you can see it"}
                </b>
              </label>
            </div>

            {boardOpen && (
              <div>
                <p className="hint" style={{ marginBottom: 8 }}>
                  Untick a profile to keep it off the shared board. It stays on this screen.
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
        </div>
      </details>
    </div>
  );
}
