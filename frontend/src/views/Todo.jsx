import React from "react";

/** The one list at the top of every screen: what will not fix itself.
 *
 * Every screen in this app had grown its own stack of coloured banners, in
 * whatever order the code happened to check them. A BD could have an interview
 * starting in forty minutes sitting underneath a note about a spreadsheet, and
 * a developer's one irreplaceable job — saying how the interview actually
 * went — was a tile in a row of six.
 *
 * So there is one list, hardest first, and every item obeys the same three
 * rules:
 *
 *   1. It says what is wrong in a sentence somebody would say out loud, with
 *      the number inside the sentence rather than floating beside it.
 *   2. It says why it matters, because "3 replies waiting" is a fact and
 *      "three clients are waiting on us" is a reason to move.
 *   3. It carries the button that fixes it. A screen that reports a problem
 *      without a route to it is a dead end.
 *
 * The urgency is a word as well as a colour — "Do this now", "Worth chasing" —
 * so the order survives a phone in sunlight and every common kind of colour
 * blindness.
 */

export const LEVELS = {
  now:   { label: "Do this now",     cls: "act-now" },
  chase: { label: "Worth chasing",   cls: "act-chase" },
  today: { label: "Happening today", cls: "act-today" },
  next:  { label: "When you can",    cls: "act-next" },
};

export const plural = (n, one, many) => (n === 1 ? one : many);

export function ActionList({ items, heading = "What needs you", lead = "", empty }) {
  if (!items.length) {
    return empty ? (
      <section className="card pad act-clear">
        <b style={{ fontFamily: "var(--display)", fontSize: 15 }}>{empty.title}</b>
        <p className="muted" style={{ marginTop: 4, maxWidth: 640 }}>{empty.body}</p>
      </section>
    ) : null;
  }

  return (
    <section className="stack" style={{ gap: 8 }}>
      <div>
        <h2>{heading}</h2>
        {lead && (
          <p className="hint" style={{ marginTop: 3, maxWidth: 680 }}>{lead}</p>
        )}
      </div>
      <div className="acts">
        {items.map((item) => (
          <div className={`act ${LEVELS[item.level].cls}`} key={item.key}>
            <span className="act-tag">{LEVELS[item.level].label}</span>
            <div className="act-body">
              <b>{item.title}</b>
              <p className="muted" style={{ marginTop: 3 }}>{item.body}</p>
            </div>
            {item.action && (
              <button className="ghost act-go" onClick={item.action.onClick}>
                {item.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── What a BD has to do ───────────────────────────────────────────────── */

/** The BD's list, in the order the damage happens.
 *
 * A client kept waiting is worse than a deadline missed is worse than a list
 * left unworked, and that is the order regardless of which of them the code
 * checks first. The sheet comes near the bottom deliberately: it is the thing
 * a BD is most often nagged about and the thing that costs the least when it
 * slips by an hour.
 */
export function bdTodo({ diary, tests, batch, toDo, handedIn, profile, go }) {
  const items = [];

  if (diary?.awaiting_time > 0) {
    const n = diary.awaiting_time;
    items.push({
      key: "awaiting-time",
      level: "now",
      title: `${n} ${plural(n, "client is", "clients are")} waiting on you for a time.`,
      body: "They replied and said yes. Nothing is booked until somebody puts a "
          + "time on it, and every day it sits there is a day they wonder.",
      action: { label: "Give them a time", onClick: () => go("interviews") },
    });
  }

  if (tests?.overdue > 0) {
    const n = tests.overdue;
    items.push({
      key: "overdue",
      level: "now",
      title: `${n} ${plural(n, "test is", "tests are")} past the deadline the client set.`,
      body: "This is the one thing here that goes wrong quietly. Nothing on any "
          + "screen changes when a deadline passes — the next you hear is the client.",
      action: { label: "Open the tests", onClick: () => go("assessments") },
    });
  }

  if (diary?.today > 0) {
    const n = diary.today;
    items.push({
      key: "today",
      level: "today",
      title: `${n} ${plural(n, "interview", "interviews")} today.`,
      body: "All times are Eastern. Check the developer knows before it starts.",
      action: { label: "Open the diary", onClick: () => go("interviews") },
    });
  }

  if (diary?.stalled > 0) {
    const n = diary.stalled;
    items.push({
      key: "stalled",
      level: "chase",
      title: `${n} ${plural(n, "conversation", "conversations")} went quiet after going well.`,
      body: "The client agreed to another round and nothing was ever booked, "
          + "usually because each side thought the other was arranging it. "
          + "Everywhere else these look like successes.",
      action: { label: "Pick them up", onClick: () => go("interviews") },
    });
  }

  if (diary?.awaiting_outcome > 0) {
    const n = diary.awaiting_outcome;
    items.push({
      key: "awaiting-outcome",
      level: "chase",
      title: `${n} ${plural(n, "interview has", "interviews have")} happened with no result recorded.`,
      body: "The developer was in the room, so the answer is theirs — but nobody "
          + "chases it but you. Until they say, your success rate reads lower "
          + "than it is.",
      action: { label: "Open the diary", onClick: () => go("interviews") },
    });
  }

  if (profile && !profile.developer) {
    items.push({
      key: "no-developer",
      level: "chase",
      title: `Nobody is attached to ${profile.name}.`,
      body: "An interview booked against this profile reaches no one, and there "
          + "is no one to do a test set against it. Your manager attaches a "
          + "developer under People.",
    });
  }

  if (profile && profile.developer && !profile.resume_url) {
    items.push({
      key: "no-resume",
      level: "chase",
      title: `${profile.name} has no resume link.`,
      body: `That is the document a client asks for first, and you have nothing `
          + `to send. ${profile.developer} adds it on their own screen.`,
    });
  }

  if (toDo > 0) {
    items.push({
      key: "todo",
      level: "next",
      title: `${toDo} ${plural(toDo, "job is", "jobs are")} waiting on your to-do list.`,
      body: "Jobs a colleague found that this profile has never applied to. "
          + "Anything you leave as to-do comes back next round.",
      action: { label: "Open the list", onClick: () => go("new") },
    });
  }

  if (batch?.status === "open" && !handedIn) {
    items.push({
      key: "sheet",
      level: "next",
      title: "You have not handed in the jobs you found this round.",
      body: "Until you do, the jobs you found are not shared out — and a "
          + "colleague can spend their morning finding them all over again.",
      action: { label: "Add them", onClick: () => go("applied") },
    });
  }

  return items;
}

/* ── What a developer has to do ────────────────────────────────────────── */

/** The developer's list.
 *
 * Shorter than the BD's, and led by the one thing on the whole screen that
 * nobody else in the company can do: say how the interview went. They were in
 * the room. Until they answer, every rate anybody reads about their work is
 * lower than the truth, and no amount of chasing by a manager can produce the
 * answer from anywhere else.
 */
export function devTodo({ counts, tests, go }) {
  const items = [];

  if (counts?.awaiting_outcome > 0) {
    const n = counts.awaiting_outcome;
    items.push({
      key: "awaiting-outcome",
      level: "now",
      title: `Say how ${n === 1 ? "an interview" : `${n} interviews`} went.`,
      body: "You were the one in the room, so nobody else can answer this. Set "
          + "the result on the row, and open notes to say what actually "
          + "happened — your BD reads both within the minute.",
      action: { label: "Open the diary", onClick: () => go("diary") },
    });
  }

  if (tests?.overdue > 0) {
    const n = tests.overdue;
    items.push({
      key: "overdue",
      level: "now",
      title: `${n} ${plural(n, "test is", "tests are")} past its deadline.`,
      body: "A client set these and is waiting. Nothing anywhere changes when a "
          + "deadline passes, so this is the only warning you get.",
      action: { label: "Open the tests", onClick: () => go("assessments") },
    });
  }

  if (counts?.today > 0) {
    const n = counts.today;
    items.push({
      key: "today",
      level: "today",
      title: `${n} ${plural(n, "interview", "interviews")} today.`,
      body: "All times are Eastern, not your local clock.",
      action: { label: "See the times", onClick: () => go("diary") },
    });
  }

  if (counts?.stalled > 0) {
    const n = counts.stalled;
    items.push({
      key: "stalled",
      level: "chase",
      title: `${n} ${plural(n, "conversation", "conversations")} went quiet after going well.`,
      body: "You cleared a round and nothing was booked after it. You heard them "
          + "say they wanted another, so you are the one who can start it.",
      action: { label: "Book the next round", onClick: () => go("diary") },
    });
  }

  if (tests?.open > 0 && !tests?.overdue) {
    const n = tests.open;
    items.push({
      key: "open-tests",
      level: "next",
      title: `${n} ${plural(n, "test", "tests")} still to do.`,
      body: "Set by a client against one of the names you are sold under. "
          + "Nothing is late yet.",
      action: { label: "Open the tests", onClick: () => go("assessments") },
    });
  }

  return items;
}
