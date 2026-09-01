import React from "react";
import {
  AssessmentBoard, CyclePicker, DateRange, Funnel, InterviewRows, NextInterview,
  ProfileCard, RangeReport, Sparkline, StageLadder, Stalled, TeamBoard, Tiles,
  sinceText,
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
  // "Ali's"; `did` as "you logged" or "Ali logged".
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
          <h1>{viewingAs ? `${viewingAs}'s dashboard` : "Your dashboard"}</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            {batch
              ? <>Cycle <b>{batch.name}</b> · {batch.status === "open" ? "running" : "closed"}
                  {batch.last_built_at && <> · lists rebuilt {sinceText(batch.last_built_at)}</>}</>
              : "No cycle has been opened yet."}
          </p>
        </div>
        <div className="stack" style={{ alignItems: "flex-end", gap: 8 }}>
          <CyclePicker batches={data.batches} value={batchId || batch?.id} onChange={onBatchChange} />
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
                : `job${left === 1 ? "" : "s"} still waiting on ${whose} list`}
            </b>
            <p className="muted" style={{ marginTop: 2 }}>
              {left === 0
                ? "Nothing left to work. New jobs land here as colleagues log theirs."
                : `Nobody running ${whose} profiles has applied to these. Marking them applied or skipped is what keeps the next cycle accurate.`}
            </p>
          </div>
        </div>
        {onOpenWork && (
          <button className="go" onClick={onOpenWork}>{left ? "Work the list" : "Log a job"}</button>
        )}
      </section>

      <Tiles items={[
        { label: `jobs ${did("found")} this cycle`, value: totals.own_found },
        { label: "jobs found by colleagues", value: totals.from_others },
        { label: "a colleague also found", value: totals.duplicates,
          tone: totals.duplicates ? "brick" : undefined,
          hint: "Postings this profile and somebody else both typed in. Time spent twice on one search." },
        { label: `handed to ${viewingAs || "you"} this cycle`, value: totals.assigned },
        { label: `${did("marked")} applied`, value: totals.applied, tone: "pine" },
        { label: `${did("marked")} skipped`, value: totals.skipped },
        { label: `of ${whose} list worked through`, value: `${totals.done_pct}%` },
        { label: `day${data.streak === 1 ? "" : "s"} logging in a row`, value: data.streak,
          hint: "Consecutive working days with at least one job logged. Today does not break it until tomorrow." },
        diary && !rangeActive && { label: "interviews today", value: diary.counts.today,
          tone: diary.counts.today ? "petrol" : undefined,
          foot: diary.counts.week ? `${diary.counts.week} in seven days` : undefined,
          hint: "Against the profiles these figures cover. Eastern time." },
        // Only shown once there is one. A tile reading zero take-homes on a
        // team that has never been sent one is a column of noise.
        tests?.counts.total ? {
          label: "take-homes outstanding", value: tests.counts.open,
          tone: tests.counts.overdue ? "brick" : undefined,
          foot: tests.counts.overdue
            ? `${tests.counts.overdue} past the deadline` : undefined,
          hint: "A test a client sent. The only work here with a deadline, and the only kind "
                + "that is lost by nobody doing anything.",
        } : null,
      ]} />

      {diary && (diary.counts.total > 0 || data.funnel.applications > 0) && (
        <section className="stack" style={{ gap: 10 }}>
          <div>
            <h2>What {whose} applications turned into</h2>
            <p className="hint" style={{ marginTop: 3, maxWidth: 640 }}>
              These only move when the work was worth sending.
            </p>
          </div>
          <Funnel data={data.funnel} awaiting={diary.counts.awaiting_outcome} />
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
        heading={`Take-homes against ${whose} profiles`}
        note="A missed deadline changes nothing on screen until the client writes again."
      />

      <section>
        <h3>What {viewingAs || "you"} logged, day by day</h3>
        <p className="hint" style={{ margin: "3px 0 9px" }}>
          The last fortnight, Eastern time.
        </p>
        <div className="card pad"><Sparkline series={data.activity} /></div>
      </section>

      {totals.duplicates > 0 && (
        <div className="notice">
          <b>{totals.duplicates} of {totals.logged} jobs {did("logged")}</b> were already on a
          colleague's sheet — the two searches are covering the same ground.
        </div>
      )}

      <section className="stack" style={{ gap: 10 }}>
        <div>
          <h2>{viewingAs ? `Profiles ${viewingAs} runs` : "Your profiles"}</h2>
          <p className="hint" style={{ marginTop: 3 }}>
            Each keeps its own history.
          </p>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
          {profiles.map((row) => (
            <ProfileCard key={row.profile_id} row={row}>
              {row.duplicates > 0 && (
                <div className="muted" style={{ fontSize: 12 }}>
                  {row.duplicates} of {row.name}'s logged jobs were also found by another profile.
                </div>
              )}
            </ProfileCard>
          ))}
        </div>
      </section>

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
                Your own rows are marked. <b>Also found</b> counts postings two profiles both
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
