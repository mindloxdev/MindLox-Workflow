import React from "react";
import {
  AssessmentBoard, BigFigures, CyclePicker, DateRange, DayByDay, Flow,
  InterviewRows, NextInterview, ProfileCard, RangeReport, StageLadder, Stalled,
  TeamBoard, Tiles, sinceText,
} from "./widgets.jsx";

/** One person's progress.
 *
 * Rendered for the person themselves, and by a manager looking at them — the
 * same component either way, fed the same payload, so what a manager checks
 * before opening somebody's dashboard is exactly what that person will get.
 *
 * `viewingAs` is the person's name when a manager is the one looking. It only
 * changes the wording: "your list" becomes "Ali's list", and the buttons that
 * would put you into somebody else's work are not drawn at all.
 */
export default function PersonDashboard({
  data, batchId, onBatchChange, onOpenWork,
  board, showBoard, onToggleBoard, dateRange, onDateRangeChange,
  viewingAs = null, error = "",
}) {
  const { totals, profiles, batch } = data;
  const left = totals.pending;
  const mine = viewingAs ? [] : profiles.map((p) => p.profile_id);

  // An interview this afternoon outranks an unworked list every time, so when
  // there is one it goes above the headline rather than below it.
  const diary = data.interviews;
  const next = diary?.today.find((row) => !row.is_past && row.status === "scheduled") || null;
  const tests = data.assessments;
  const rangeActive = !!(dateRange?.dateFrom || dateRange?.dateTo);

  // Every label that names an owner, in one place. `whose` reads as "your" or
  // "Ali's"; `did` as "you found" or "Ali found".
  const whose = viewingAs ? `${viewingAs}'s` : "your";
  const did = (verb) => (viewingAs ? `${viewingAs} ${verb}` : `you ${verb}`);

  if (!profiles.length) {
    return (
      <div className="stack">
        <h1>{viewingAs ? `${viewingAs}'s dashboard` : "Your dashboard"}</h1>
        <div className="notice">
          {viewingAs
            ? `${viewingAs} runs no profile yet, so there is nothing to measure. Give them one under People and profiles.`
            : "No profile has been assigned to you yet. Your manager creates one under People and profiles — it is the name and resume your applications go out under."}
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          {/* A manager arrives here from a page that has already named them
              in a heading, so a second one directly under it is furniture. */}
          {!viewingAs && <h1>Your dashboard</h1>}
          <p className="muted" style={{ marginTop: viewingAs ? 0 : 3 }}>
            {batch
              ? <>Round <b>{batch.name}</b> · {batch.status === "open"
                  ? "still running, so these numbers are still moving" : "finished"}
                  {batch.last_built_at && <> · lists last shared out {sinceText(batch.last_built_at)}</>}</>
              : "No round of work has been started yet."}
          </p>
        </div>
        <div className="stack" style={{ alignItems: "flex-end", gap: 8 }}>
          <CyclePicker batches={data.batches} value={batchId || batch?.id}
                     label="Round" onChange={onBatchChange} />
          {onDateRangeChange && <DateRange {...dateRange} onChange={onDateRangeChange} />}
        </div>
      </div>

      {error && <div className="notice">{error}</div>}

      {/* Only when a range was asked for. The server returns null otherwise,
          so there is no default window inventing a figure. */}
      <RangeReport report={data.report} whose={viewingAs || "your"} />

      {next && (
        <NextInterview row={next} onOpen={onOpenWork}
                       openLabel={onOpenWork ? "Open the diary" : undefined} />
      )}

      {/* The one number worth acting on, and the way to act on it. */}
      <section className="card pad row headline" style={{ justifyContent: "space-between" }}>
        <div>
          <div className="mono headline-figure" style={{ color: left ? "var(--brick)" : "var(--pine)" }}>
            {left}
          </div>
          <div>
            <b style={{ fontFamily: "var(--display)", fontSize: 15 }}>
              {left === 0
                ? `${viewingAs ? `${viewingAs}'s` : "Your"} list is clear`
                : `others' job${left === 1 ? "" : "s"} still waiting on ${whose} list`}
            </b>
            <p className="muted" style={{ marginTop: 2 }}>
              {left === 0
                ? "Nothing left to do. More land here as colleagues hand in what they found."
                : `A colleague found these and nobody here has applied to them yet. Marking each one applied — or turned down, with a reason — is what stops it coming back next round.`}
            </p>
          </div>
        </div>
        {onOpenWork && (
          <button className="go" onClick={onOpenWork}>{left ? "Work the list" : "Log a job"}</button>
        )}
      </section>

      {/* Four figures, not the ten that were here — four of which needed a
          tooltip to be read at all, which on a screen somebody skims once a
          morning means they were not read. The rest are still below, in one
          quiet row, because none of them is worth a headline on their own. */}
      <BigFigures items={[
        { key: "sent", scope: "this round",
          value: totals.own_found + totals.from_others,
          label: "applications sent",
          body: `Everything ${viewingAs || "you"} applied for this round, whether `
              + "it was found here or handed over by a colleague.",
          tone: "good" },
        { key: "shared", scope: "this round", value: totals.from_others,
          label: "of those, others' jobs",
          body: "Work that came off somebody else's sheet. This is the part that "
              + "would not have happened without everybody handing in to one place." },
        { key: "wasted", scope: "this round", value: totals.duplicates,
          label: "also found by somebody else",
          body: "A posting two people both went out and found. The search that "
              + "turned it up the second time was time spent for nothing.",
          tone: totals.duplicates ? "bad" : undefined },
        { key: "talking", scope: "all time",
          value: data.funnel?.interviews || 0,
          label: "clients who wanted to talk",
          body: "Interviews off every application ever sent under these names. A "
              + "reply often lands weeks after the application that earned it.",
          tone: data.funnel?.interviews ? "good" : undefined },
      ]} />

      <Tiles items={[
        { label: `others' jobs given to ${viewingAs || "you"}`, value: totals.assigned,
          hint: "Found by a colleague and handed over this round." },
        { label: "turned down, with a reason", value: totals.skipped },
        { label: "of that list worked through", value: `${totals.done_pct}%` },
        { label: `day${data.streak === 1 ? "" : "s"} in a row with jobs added`,
          value: data.streak,
          hint: "Working days in a row with at least one job added. Today does not "
              + "break it until tomorrow." },
        diary && !rangeActive && { label: "interviews today", value: diary.counts.today,
          tone: diary.counts.today ? "petrol" : undefined,
          foot: diary.counts.week ? `${diary.counts.week} in the next seven days` : undefined },
        tests?.counts.total ? {
          label: "tests still to do", value: tests.counts.open,
          tone: tests.counts.overdue ? "brick" : undefined,
          foot: tests.counts.overdue
            ? `${tests.counts.overdue} past the deadline` : undefined,
        } : null,
      ]} />

      {diary && (diary.counts.total > 0 || data.funnel.applications > 0) && (
        <section className="stack" style={{ gap: 10 }}>
          <div>
            <h2>What {whose} applications turned into</h2>
            <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
              Everything above counts effort, and effort goes up when people work
              harder. This is the part a client decides.
            </p>
          </div>
          <Flow funnel={data.funnel} awaiting={diary.counts.awaiting_outcome} />
          {!rangeActive && <StageLadder rows={data.funnel.by_stage} />}

          {diary.today.length > 0 && (
            <div>
              <h3>Today</h3>
              <div style={{ marginTop: 8 }}>
                <InterviewRows rows={diary.today} showProfile />
              </div>
            </div>
          )}
          {diary.upcoming.length > 0 && (
            <div>
              <h3>Coming up</h3>
              <div style={{ marginTop: 8 }}>
                <InterviewRows rows={diary.upcoming.slice(0, 8)} showProfile />
              </div>
            </div>
          )}
          {dateRange && (dateRange.dateFrom || dateRange.dateTo) && diary.recent.length > 0 && (
            <div>
              <h3>Interviews in this range</h3>
              <div style={{ marginTop: 8 }}>
                <InterviewRows rows={diary.recent} showProfile />
              </div>
            </div>
          )}
          {diary.counts.awaiting_outcome > 0 && (
            <div className="notice">
              <b>{diary.counts.awaiting_outcome} interview
              {diary.counts.awaiting_outcome === 1 ? "" : "s"} with no outcome.</b>{" "}
              {onOpenWork ? "Record them under My work → Interviews."
                : `${viewingAs} can record them under My work → Interviews.`}
            </div>
          )}

          {/* Read-only here. Booking the next round is done where the diary
              is, so this points at it rather than growing a second button
              that does the same thing from a screen about figures. */}
          <Stalled rows={diary.stalled} />
          {diary.stalled?.length > 0 && (
            <p className="muted">
              {onOpenWork
                ? "Book the next round under My work → Interviews."
                : `${viewingAs} can book the next round under My work → Interviews.`}
            </p>
          )}
        </section>
      )}

      <AssessmentBoard
        data={tests}
        onOpen={onOpenWork}
        heading={`Tests clients set for ${whose} profiles`}
        note="A missed deadline changes nothing on screen until the client writes again."
      />

      <section>
        <h3>Jobs {viewingAs || "you"} found, day by day</h3>
        <p className="hint" style={{ margin: "3px 0 9px", maxWidth: 640 }}>
          The last fortnight, Eastern time. Weekends are drawn paler, so a quiet
          Saturday does not read as a week that stopped.
        </p>
        <DayByDay series={data.activity} />
        <div className="card scroll" style={{ marginTop: 8 }}>
          <table>
            <thead><tr><th>Day</th><th className="num">Own jobs found</th></tr></thead>
            <tbody>
              {data.activity.map((day) => (
                <tr key={day.day}>
                  <td>{day.day}</td>
                  <td className="mono num"><b>{day.count}</b></td>
                </tr>
              ))}
              {!data.activity.length && (
                <tr><td colSpan={2} className="muted">No jobs found in this range.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {totals.duplicates > 0 && (
        <div className="notice">
          <b>{totals.duplicates} of {totals.logged} own jobs {did("found")}</b> were already on a
          colleague's sheet — the two searches are covering the same ground.
        </div>
      )}

      {/* Everything above is the person; this is the same person split by the
          name they applied under. Folded, because most mornings the total is
          the answer and a row of cards between the figures and the diary is
          just distance. */}
      <details className="more">
        <summary>
          {viewingAs ? `Break it down by profile — ${viewingAs} runs ${profiles.length}`
                     : `Break it down by profile — you run ${profiles.length}`}
        </summary>
        <section className="stack" style={{ gap: 10 }}>
          <p className="hint" style={{ maxWidth: 660 }}>
            Each is a separate candidate to a client, with its own developer, resume
            and history — so the same four words mean the same things here as they do
            on the totals above.
          </p>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
            {profiles.map((row) => (
              <ProfileCard key={row.profile_id} row={row}>
                {row.duplicates > 0 && (
                  <div className="muted" style={{ fontSize: 12 }}>
                    {row.duplicates} of {row.name}&apos;s own jobs were also found by
                    another profile.
                  </div>
                )}
              </ProfileCard>
            ))}
          </div>
        </section>
      </details>

      {/* Only on your own dashboard. A manager comparing people has a better
          screen for it than one person's view of the board. */}
      {!viewingAs && (
        <section className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h2>How the team is doing</h2>
              <p className="muted" style={{ marginTop: 3 }}>
                {data.team_visible
                  ? "Every profile your manager has put on the board, side by side."
                  : "Your manager has not opened the team board."}
              </p>
            </div>
            {data.team_visible && (
              <button className="ghost" onClick={onToggleBoard}>
                {showBoard ? "Hide the board" : "Show the board"}
              </button>
            )}
          </div>

          {!data.team_visible ? (
            <div className="notice gate">
              The team board is off. Your own figures are always yours to see.
            </div>
          ) : showBoard && board ? (
            <>
              <TeamBoard rows={board.rows} highlight={mine} />
              <p className="muted">
                Your own rows are marked. <b>Found twice</b> counts postings two profiles both
                logged — the number this whole tool exists to bring down.
                {board.hidden > 0 && ` ${board.hidden} profile${board.hidden === 1 ? " is" : "s are"} not on the board.`}
              </p>
            </>
          ) : showBoard ? (
            <p className="muted">Loading the board…</p>
          ) : null}
        </section>
      )}
    </div>
  );
}
