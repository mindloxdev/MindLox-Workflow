import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, safeUrl } from "../api.js";
import {
  AssessmentBoard, Availability, CyclePicker, DateRange, DayByDay, DeveloperBoard,
  Disclosure, Flow, Funnel, InterviewRows, Loading, RangeReport, Rounds, Segment,
  Skills, StageLadder, Stalled, TeamBoard, Tiles, sinceText, workingToday,
} from "./widgets.jsx";
import {
  DoubledUp, Headline, HeadlineKey, NeedsYou, PeopleTable,
} from "./ManagerSummary.jsx";
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
    <div className="stack" style={{ gap: 14 }}>
      <button className="link back" onClick={onClose}>← Back to the team</button>
      <div>
        <h1>{data.developer.name}</h1>
        <p className="muted" style={{ marginTop: 3 }}>
          {data.profiles.length
            ? <>Applied as {data.profiles.map((p) => p.name).join(", ")} · this is their
                own screen, exactly as they see it.</>
            : "Not behind any profile, so they sign in to an empty desk."}
        </p>
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
    </div>
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
    <div className="stack" style={{ gap: 14 }}>
      <button className="link back" onClick={onClose}>← Back to the team</button>
      <div>
        <h1>{profile.name}</h1>
        <p className="muted" style={{ marginTop: 3 }}>
          {profile.headline || "—"} · run by {profile.person || "nobody"}
          {profile.platform ? ` · ${profile.platform}` : ""}
          {!profile.shared && " · not on the team board"}
        </p>
      </div>

      <Tiles items={[
        { label: "own jobs", value: stats.logged,
          hint: "Found on this profile's own sheet, and applied for." },
        { label: "found twice", value: stats.duplicates,
          tone: stats.duplicates ? "brick" : undefined,
          hint: "Of those, ones a colleague had already found." },
        { label: "others' jobs given", value: stats.assigned,
          hint: "Handed over off a colleague's sheet." },
        { label: "applied", value: stats.applied, tone: "pine" },
        { label: "still to do", value: stats.pending },
        { label: "applications sent, all time", value: stats.all_time },
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
                <tr><th>Cycle</th><th className="num">Own jobs</th>
                    <th className="num">Others&apos; jobs given</th>
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
        <h3>The last {data.recent.length} jobs applied for</h3>
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
                <tr><td colSpan={4} className="muted">Nothing applied for yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
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
    <div className="stack" style={{ gap: 14 }}>
      <button className="link back" onClick={onClose}>← Back to the team</button>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1>{person.name}</h1>
          <p className="muted" style={{ marginTop: 3, maxWidth: 620 }}>
            {open
              ? `This is ${person.name}'s own screen, exactly as they see it.`
              : `${person.name} cannot see this yet. Nothing here is hidden from you — the switch decides whether it is hidden from them.`}
          </p>
        </div>
        <div className="row">
          <DateRange {...dateRange} onChange={onDateRangeChange} />
          <label className="row" style={{ gap: 8 }}>
            <input type="checkbox" checked={open} disabled={busy}
                   onChange={(e) => onToggle(person, e.target.checked)} />
            <b style={{ fontFamily: "var(--display)",
                        color: open ? "var(--ok-text)" : "var(--slate)" }}>
              {open ? `Open to ${person.name}` : "Manager only"}
            </b>
          </label>
        </div>
      </div>

      {error && <div className="notice">{error}</div>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && (
        <PersonDashboard data={data} batchId={batchId} onBatchChange={onBatchChange}
                         viewingAs={person.name} />
      )}
    </div>
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
  // What window the per-person table counts over. Opens on today, because the
  // question a manager actually walks in with is "has the team started", and
  // a cycle-to-date total answers that identically on a busy Monday and a dead
  // one. The cycle is a click away, and setting dates takes over from both.
  const [when, setWhen] = useState("today");
  const [todayRows, setTodayRows] = useState(null);
  // Where the team screen was when somebody was opened, so closing them puts
  // the manager back on the row they pressed rather than at the top of a page
  // they have to scroll through again.
  const cameFrom = useRef(0);

  const load = useCallback(async (id) => {
    try {
      const next = await api.overview(id, dateRange.dateFrom, dateRange.dateTo);
      setData(next);
      if (!id && next.batch) setBatchId(next.batch.id);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  }, [dateRange]);

  // Today's slice, fetched alongside the cycle's. Its own request because the
  // rest of the screen is deliberately about the whole cycle — the four
  // numbers, the drop, the duplication — and narrowing all of that to one
  // morning would make every one of them read as a bad week.
  const loadToday = useCallback(async (id) => {
    try {
      const day = workingToday();
      setTodayRows((await api.overview(id, day, day)).people);
    } catch {
      setTodayRows(null);
    }
  }, []);

  useEffect(() => { load(batchId); loadToday(batchId); }, [batchId, load, loadToday]);

  // Cycles rebuild on a timer behind the manager's back, so the screen refreshes
  // itself rather than showing a figure that stopped being true.
  useEffect(() => {
    const tick = setInterval(() => { load(batchId); loadToday(batchId); }, 30000);
    return () => clearInterval(tick);
  }, [batchId, load, loadToday]);

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
      await Promise.all([load(batchId), loadToday(batchId)]);
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

  // Opening somebody replaces this screen with theirs. It used to be appended
  // underneath, which meant a manager pressed a row and nothing appeared to
  // happen — the thing they asked for was a screenful further down, past the
  // table they had just used, and they had to scroll to find out whether the
  // click had worked at all.
  //
  // Nothing is thrown away: this component stays mounted, so the cycle, the
  // dates and the Today/This cycle switch are all exactly as they left them
  // when they come back.
  if (openDev) {
    return (
      <DeveloperView person={openDev} batchId={batchId || data.batch?.id}
                     dateRange={dateRange}
                     onClose={() => closeDetail(() => setOpenDev(null))} />
    );
  }
  if (openProfile) {
    return (
      <ProfileDetail profileId={openProfile} batchId={batchId || data.batch?.id}
                     dateRange={dateRange}
                     onClose={() => closeDetail(() => setOpenProfile(null))} />
    );
  }
  if (openPerson) {
    return (
      <PersonView
        person={data.people.find((p) => p.user_id === openPerson.user_id) || openPerson}
        batchId={batchId || data.batch?.id}
        dateRange={dateRange}
        onBatchChange={setBatchId}
        onDateRangeChange={setDateRange}
        onToggle={togglePerson}
        busy={saving}
        onClose={() => closeDetail(() => setOpenPerson(null))} />
    );
  }

  const { org, batch, people, profiles, missing, settings } = data;
  const diary = data.interviews;
  const boardOpen = !!settings?.team_board_visible;
  const closedCount = people.filter((p) => p.role !== "admin" && !p.dashboard_visible).length;

  // Every route into somebody's screen goes through here, so there is one
  // place that remembers where to come back to and one that scrolls to the top
  // of what just opened — a new page that starts halfway down reads as broken.
  const openDetail = (apply) => {
    cameFrom.current = window.scrollY;
    apply();
    window.scrollTo({ top: 0 });
  };
  const closeDetail = (apply) => {
    apply();
    window.scrollTo({ top: cameFrom.current });
  };
  const openTheirScreen = (person) => openDetail(() => {
    setOpenPerson(person);
    setOpenProfile(null);
    setOpenDev(null);
  });

  // Dates typed into the box beat the switch: somebody who has just asked for
  // 1–15 September did not mean "today", and leaving the switch in charge
  // would silently ignore what they typed.
  const datesSet = !!(dateRange.dateFrom || dateRange.dateTo);
  const showingToday = !datesSet && when === "today";
  const peopleRows = showingToday ? todayRows : people;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>How the team is doing</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            {batch
              ? <>Cycle <b>{batch.name}</b> · {batch.status === "open"
                  ? "still running" : "finished"}
                  {batch.last_built_at && <> · lists last shared out {sinceText(batch.last_built_at)}</>}</>
              : "No cycle of work has been started yet."}
          </p>
        </div>
        <div className="row">
          <CyclePicker batches={data.batches} value={batchId || batch?.id}
                       onChange={(id) => {
            setBatchId(id);
            setOpenProfile(null);
          }} />
          <DateRange {...dateRange} onChange={setDateRange} />
          {onOpenBatches && <button className="ghost" onClick={onOpenBatches}>Run the cycle</button>}
        </div>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {/* First, and one line each. The title says what is wrong and how many;
          why it matters opens on request. Six of these with a paragraph apiece
          was the screenful that pushed everything else below the fold. */}
      <NeedsYou org={org} missing={missing} diary={diary} assessments={data.assessments} />

      {/* Then four numbers, and nothing else above the fold. Everything below
          this point starts closed: it is worth reading, and not worth reading
          every morning before the thing you came for. */}
      <section className="stack" style={{ gap: 8 }}>
        <Headline org={org} funnel={data.funnel} />
        <Disclosure title="What these four numbers mean"
                    hint="the windows they count over">
          <HeadlineKey org={org} funnel={data.funnel} />
        </Disclosure>
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2>How each person is doing</h2>
            <p className="hint" style={{ marginTop: 3, maxWidth: 660 }}>
              {datesSet
                ? <>Counting <b>only the dates you picked</b> above.</>
                : showingToday
                  ? <>Counting <b>today so far</b>, on Eastern time — a row of zeros at
                      nine in the morning is a team that has not started yet.</>
                  : <>Counting the <b>whole cycle</b>.</>}
            </p>
          </div>
          {!datesSet && (
            <Segment
              label="Counting"
              value={when}
              onChange={setWhen}
              items={[{ key: "today", label: "Today" },
                      { key: "round", label: "This cycle" }]} />
          )}
        </div>
        {peopleRows
          ? <PeopleTable people={peopleRows} onOpen={openTheirScreen}
                         onToggle={togglePerson} busy={saving} />
          : <Loading lines={3} />}
      </section>

      {/* ── Everything below opens on request ─────────────────────────────
          Each one carries the number it is worth opening for, so a closed
          section says "there are two things in here" rather than "there might
          be something in here" — which is the difference between progressive
          disclosure and hidden information. */}

      <Disclosure title="What the applications turned into"
                  badge={data.funnel?.offers
                    ? `${data.funnel.offers} offer${data.funnel.offers === 1 ? "" : "s"}`
                    : null}
                  tone={data.funnel?.offers ? "on" : ""}
                  hint="applications, interviews, offers, hires">
        <div className="stack" style={{ gap: 10 }}>
          <p className="hint" style={{ maxWidth: 680 }}>
            Everything above counts effort, and effort goes up when people work
            harder. This is the part a client decides.
          </p>
          <Flow funnel={data.funnel} awaiting={diary?.counts.awaiting_outcome || 0} />
          <Rounds rounds={data.funnel?.rounds} />
          <StageLadder rows={data.funnel?.by_stage} />
        </div>
      </Disclosure>

      <Disclosure title="Effort spent twice"
                  badge={org.duplicates || null}
                  tone={org.duplicates ? "off" : ""}
                  hint="the same job found by two people">
        <DoubledUp org={org} history={data.history} />
      </Disclosure>

      <Disclosure title="Jobs found, day by day"
                  hint="the whole team, last thirty days">
        <div className="stack" style={{ gap: 10 }}>
          <p className="hint" style={{ maxWidth: 680 }}>
            Eastern time. Weekends are drawn paler, so a quiet Saturday does not
            read as a team that stopped.
          </p>
          <DayByDay series={data.activity} />
        </div>
      </Disclosure>

      <Disclosure title="Interviews and tests"
                  badge={diary?.counts.scheduled || null}
                  hint="today, the coming fortnight, and what clients set">
        <div className="stack" style={{ gap: 14 }}>
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
              round — a manager quietly booking into somebody else's client
              relationship is how one reply becomes two conversations. */}
          <Stalled rows={diary?.stalled} />

          <AssessmentBoard
            data={data.assessments}
            heading="Tests clients have set"
            note="Set by whoever runs the profile, done by the developer behind it. The only work here with a deadline on it."
            limit={12}
          />
        </div>
      </Disclosure>

      <Disclosure title="The developers"
                  badge={(data.developers || []).length || null}
                  hint="who is behind each profile, and who could start on Monday">
        <div className="stack" style={{ gap: 10 }}>
          <p className="hint" style={{ maxWidth: 680 }}>
            <b>Open</b> shows their screen as they see it.
          </p>
          <DeveloperBoard rows={data.developers || []} onOpen={(row) => openDetail(() => {
            setOpenDev(row);
            setOpenPerson(null);
            setOpenProfile(null);
          })} />
        </div>
      </Disclosure>

      <Disclosure title="Every profile separately"
                  badge={profiles.length || null}
                  hint="one person can run several">
        <div className="stack" style={{ gap: 10 }}>
          <p className="hint" style={{ maxWidth: 680 }}>
            Best first. Press a row to open it.
          </p>
          <TeamBoard rows={profiles}
                     onOpen={(id) => openDetail(() => setOpenProfile(id))} />
        </div>
      </Disclosure>

      <Disclosure title="Who can see what"
                  badge={closedCount || null}
                  tone={closedCount ? "warn" : ""}
                  hint={closedCount
                    ? `${closedCount} cannot see their own figures yet`
                    : "everybody can see their own figures"}>
        <div className="stack" style={{ gap: 12 }}>
          <div className="notice ok gate">
            <b>1. Can a person see their own figures?</b> Off until you turn it on,
            one person at a time — press the chevron on their row above.
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
        </div>
      </Disclosure>
    </div>
  );
}
