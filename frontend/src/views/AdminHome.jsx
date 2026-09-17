import React, { useCallback, useEffect, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import Skipped from "./Skipped.jsx";
import { CycleClock, sinceText } from "./widgets.jsx";

function Matrix({ names, rows }) {
  const offDiagonal = rows.flatMap((row, i) => row.filter((_, j) => i !== j));
  const peak = Math.max(1, ...offDiagonal);

  return (
    <div className="card scroll">
      <table className="matrix">
        <thead>
          <tr>
            <th />
            {names.map((n) => <th key={n}>{n}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={names[i]}>
              <td style={{ fontWeight: 500, whiteSpace: "nowrap" }}>{names[i]}</td>
              {row.map((value, j) => {
                const self = i === j;
                const heat = self ? 0 : Math.min(0.88, value / peak);
                return (
                  <td key={j} style={{
                    background: self ? "var(--paper)" : `rgba(158,59,44,${heat * 0.85})`,
                    color: self ? "var(--slate)" : heat > 0.5 ? "#fff" : "var(--ink)",
                    fontWeight: self ? 400 : 500,
                  }}>{value}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminHome() {
  const [batches, setBatches] = useState([]);
  const [current, setCurrent] = useState(null);
  const [detail, setDetail] = useState(null);
  const [report, setReport] = useState(null);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    name: "", quota: 40, mode: "cover", one_per_client: false, auto_build_minutes: 10,
  });
  // The clock. `timerDraft` is only the number in the box before it is set;
  // once a clock is running the cycle itself carries it.
  const [timerDraft, setTimerDraft] = useState(120);
  // The running cycle's own settings, as they are being edited. Seeded from
  // the cycle when a different one is picked and left alone after that — the
  // screen re-reads the cycle every thirty seconds, and re-seeding on every
  // read would wipe a half-typed cap out from under whoever is typing it.
  const [settings, setSettings] = useState(null);
  const [figures, setFigures] = useState(null);
  // The workspace switches, which belong to no cycle. Separate state from
  // `settings` above, which is this cycle's cap and mode: these outlive every
  // cycle and are saved the moment they are pressed rather than on a button.
  const [switches, setSwitches] = useState(null);
  // Which profile's skips are open underneath the figures. One at a time: the
  // reasons are read against a profile, and two tables open at once is a
  // screenful of somebody else's rows between you and the row you pressed.
  const [openSkips, setOpenSkips] = useState(null);

  // Rebuilds happen on the server whether or not anyone is looking, so the
  // screen refreshes itself to stay honest about what the lists contain.
  useEffect(() => {
    if (!current) return undefined;
    const tick = setInterval(() => {
      api.report(current).then(setReport).catch(() => {});
      api.getBatch(current).then(setDetail).catch(() => {});
      api.timerReport(current).then(setFigures).catch(() => setFigures(null));
    }, 30000);
    return () => clearInterval(tick);
  }, [current]);

  useEffect(() => {
    api.settings().then(setSwitches).catch(() => {});
  }, []);

  const flip = async (key, value) => {
    const was = switches;
    setSwitches({ ...switches, [key]: value });      // it reads as instant
    try {
      setSwitches(await api.saveSettings({ [key]: value }));
    } catch (err) {
      setSwitches(was);                              // it did not take
      setNote({ bad: true, text: err.message });
    }
  };

  const refresh = useCallback(async (selectId) => {
    const rows = await api.listBatches();
    setBatches(rows);
    const pick = selectId || current || (rows[0] && rows[0].id);
    if (pick) setCurrent(pick);
  }, [current]);

  useEffect(() => { refresh().catch((e) => setNote({ bad: true, text: e.message })); }, []);

  useEffect(() => {
    if (!current) return;
    setReport(null);
    setFigures(null);
    api.getBatch(current).then(setDetail).catch(() => setDetail(null));
    api.report(current).then(setReport).catch(() => setReport(null));
    // 404 here is the ordinary case — most cycles never have a clock set.
    api.timerReport(current).then(setFigures).catch(() => setFigures(null));
  }, [current]);

  useEffect(() => {
    if (!detail) { setSettings(null); return; }
    setSettings({
      name: detail.name || "",
      quota: detail.quota,
      mode: detail.mode,
      one_per_client: !!detail.one_per_client,
      auto_build_minutes: detail.auto_build_minutes || 0,
    });
  }, [detail?.id]);

  const create = async () => {
    setBusy(true);
    setNote(null);
    try {
      const batch = await api.createBatch({
        name: draft.name.trim() || `Cycle ${new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}`,
        quota: Number(draft.quota) || 40,
        mode: draft.mode,
        one_per_client: draft.one_per_client,
        auto_build_minutes: Number(draft.auto_build_minutes),
      });
      setDraft({ ...draft, name: "", quota: 40, one_per_client: false });
      await refresh(batch.id);
      setNote({
        text: batch.auto_build_minutes
          ? `${batch.name} is open. Lists rebuild every ${batch.auto_build_minutes} minutes on their own — you do not need to come back.`
          : `${batch.name} is open. You will need to build the lists yourself.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const compute = async () => {
    setBusy(true);
    setNote(null);
    try {
      const data = await api.compute(current);
      setReport(data);
      await refresh(current);
      const detailData = await api.getBatch(current);
      setDetail(detailData);
      const full = await api.report(current).catch(() => data);
      setReport(full);
      setNote({ text: `Lists built. ${data.report["Jobs put on a list"]} jobs went out across ${data.participants.length} profiles.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!window.confirm(
      "Close this cycle? No more sheets are accepted and the lists stop rebuilding. " +
      "Everyone keeps what they already have.")) return;
    setBusy(true);
    try {
      await api.closeBatch(current);
      await refresh(current);
      setDetail(await api.getBatch(current));
      setNote({ text: "Cycle closed. Open a new one when the next cycle starts." });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const reopen = async () => {
    setBusy(true);
    try {
      await api.reopenBatch(current);
      await refresh(current);
      setDetail(await api.getBatch(current));
      setNote({ text: "Cycle reopened. Sheets are accepted again and rebuilding resumes." });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  /** Save the cycle's settings.
   *
   * Nothing is retracted by this. A rebuild only ever replaces the jobs still
   * sitting untouched, so lowering the cap trims what nobody has started and
   * raising it hands out more — what somebody has already marked applied or
   * skipped is their record of this cycle and stays on their list.
   */
  const saveSettings = async () => {
    setBusy(true);
    setNote(null);
    try {
      const saved = await api.updateBatch(current, {
        name: settings.name.trim(),
        quota: Math.max(1, Number(settings.quota) || 1),
        mode: settings.mode,
        one_per_client: settings.one_per_client,
        auto_build_minutes: Number(settings.auto_build_minutes),
      });
      await refresh(current);
      setDetail(await api.getBatch(current));
      setNote({
        text: saved.auto_build_minutes
          ? `Saved. The next rebuild uses these — within ${saved.auto_build_minutes} minutes, or press Build now.`
          : "Saved. Press Build now to put these to work.",
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  /** Set, move or clear the clock. `payload` is passed straight through. */
  const setTimer = async (payload, said) => {
    setBusy(true);
    setNote(null);
    try {
      const saved = await api.setCycleTimer(current, payload);
      setDetail(await api.getBatch(current));
      await refresh(current);
      setFigures(await api.timerReport(current).catch(() => null));
      setNote({ text: said(saved) });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const startClock = () => {
    const minutes = Math.max(1, Math.min(7 * 24 * 60, Number(timerDraft) || 0));
    return setTimer({ minutes }, () =>
      `The clock is running: ${minutes} minutes. Everyone working this cycle sees `
      + "the same countdown, and nothing stops when it ends.");
  };

  const moveClock = (delta) => setTimer({ add_minutes: delta }, (saved) =>
    saved.timer_minutes
      ? `${delta > 0 ? "Added" : "Took back"} ${Math.abs(delta)} minutes — `
        + `the window is now ${saved.timer_minutes} minutes from when it started.`
      : "That took the whole clock away.");

  const clearClock = () => setTimer({ minutes: 0 }, () =>
    "Clock cleared. Nobody sees a countdown, and the figures for the window go with it.");

  const handedIn = detail?.uploads?.length || 0;
  const settingsChanged = !!settings && !!detail && (
    settings.name.trim() !== (detail.name || "")
    || Number(settings.quota) !== detail.quota
    || settings.mode !== detail.mode
    || settings.one_per_client !== !!detail.one_per_client
    || Number(settings.auto_build_minutes) !== (detail.auto_build_minutes || 0)
  );

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Cycles</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Open a cycle, wait for everyone's sheet, then build the lists.
          </p>
        </div>
        {batches.length > 0 && (
          <label>
            Viewing&nbsp;
            <select value={current || ""} onChange={(e) => setCurrent(Number(e.target.value))}>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>{b.name} · {b.status}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {/* Switches that belong to the workspace rather than to any one cycle,
          so they sit above the cycle that happens to be open. Both are about
          what a BD's screen offers, and both are held on the server: turning
          one off is a rule the API keeps, not a button the browser hides. */}
      {switches && (
        <section className="card pad stack" style={{ gap: 12 }}>
          <h2>What your team's screens offer</h2>

          <label className="row" style={{ gap: 10, alignItems: "flex-start" }}>
            <input type="checkbox" style={{ marginTop: 3 }}
                   checked={!!switches.bulk_actions_enabled}
                   onChange={(e) => flip("bulk_actions_enabled", e.target.checked)} />
            <span>
              <b>Let a BD select a whole list and mark it in one press</b>
              <p className="hint" style={{ marginTop: 2, maxWidth: 680 }}>
                Puts <b>Select all</b> on others&apos; jobs, with one press to mark
                the selection applied or skipped. A skip still has to say why, and
                the one reason goes on every row. Turn it off for a team you want
                reading each posting before it is turned down — nothing already
                marked changes, and the server refuses the press as well as the
                screen hiding it.
              </p>
            </span>
          </label>

          <label className="row" style={{ gap: 10, alignItems: "flex-start" }}>
            <input type="checkbox" style={{ marginTop: 3 }}
                   checked={!!switches.team_board_visible}
                   onChange={(e) => flip("team_board_visible", e.target.checked)} />
            <span>
              <b>Let a BD see the team board</b>
              <p className="hint" style={{ marginTop: 2, maxWidth: 680 }}>
                Every profile&apos;s progress side by side. Off by default, because a
                board that appears without anybody deciding to show it is a
                performance ranking nobody agreed to.
              </p>
            </span>
          </label>
        </section>
      )}

      <section className="card pad">
        <h2>Start a new cycle</h2>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="Name, e.g. Week 33" value={draft.name} style={{ minWidth: 200 }}
                 onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <label>
            Cap per profile
            <input type="number" min="1" max="1000" value={draft.quota} style={{ width: 80 }}
                   onChange={(e) => setDraft({ ...draft, quota: e.target.value })} />
          </label>
          <label>
            <input type="checkbox" checked={draft.one_per_client}
                   onChange={(e) => setDraft({ ...draft, one_per_client: e.target.checked })} />
            One job per client, per profile
          </label>
          <label>
            Rebuild lists
            <select value={draft.auto_build_minutes} style={{ marginLeft: 6 }}
                    onChange={(e) => setDraft({ ...draft, auto_build_minutes: e.target.value })}>
              <option value={5}>every 5 minutes</option>
              <option value={10}>every 10 minutes</option>
              <option value={15}>every 15 minutes</option>
              <option value={30}>every 30 minutes</option>
              <option value={0}>only when I ask</option>
            </select>
          </label>
          <button onClick={create} disabled={busy}>Open cycle</button>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", marginTop: 14 }}>
          {[
            { key: "cover", title: "Give every profile what it has not tried",
              blurb: "The sheets are pooled, then each profile gets back everything it has never applied to. Two profiles are two candidates, so both may go for the same job." },
            { key: "split", title: "Split the pool, no two profiles share",
              blurb: "Every job goes to exactly one profile. Use this when the profiles are really one identity and a second application would look like a repeat." },
          ].map((option) => (
            <label key={option.key} className="card pad" style={{
              display: "block", cursor: "pointer",
              borderColor: draft.mode === option.key ? "var(--petrol)" : "var(--rule)",
              borderWidth: draft.mode === option.key ? 2 : 1,
            }}>
              <span className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                <input type="radio" name="mode" value={option.key} checked={draft.mode === option.key}
                       onChange={() => setDraft({ ...draft, mode: option.key })} />
                <span>
                  <b style={{ fontFamily: "var(--display)" }}>{option.title}</b>
                  <span className="muted" style={{ display: "block", marginTop: 4 }}>{option.blurb}</span>
                </span>
              </span>
            </label>
          ))}
        </div>

        <p className="hint">
              Stops one profile bidding on four jobs from the same buyer.
            </p>
      </section>

      {detail && (
        <section className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Sheets handed in · {detail.name}</h2>
            <div className="row" style={{ gap: 8 }}>
              <span className="pill">
                {detail.mode === "split" ? "split the pool" : "cover every profile"}
              </span>
              <span className={detail.status === "open" ? "pill" : "pill on"}>
                {detail.status === "open" ? "open" : "closed"}
              </span>
              <button className="ghost" onClick={compute} disabled={busy || handedIn < 2}>
                {busy ? "Working…" : "Build now"}
              </button>
              {detail.status === "open"
                ? <button onClick={finish} disabled={busy}>Close cycle</button>
                : <button className="ghost" onClick={reopen} disabled={busy}>Reopen</button>}
            </div>
          </div>

          {detail.status === "open" && detail.auto_build_minutes > 0 && (
            <div className="notice ok">
              <b>Building itself.</b> The lists rebuild every {detail.auto_build_minutes} minutes
              while this cycle is open, so whatever your team has added is already counted.
              {detail.last_built_at
                ? ` Last built ${sinceText(detail.last_built_at)}.`
                : handedIn < 2
                  ? " Nothing built yet — it starts once two profiles have handed in."
                  : " First build is due within a minute."}
              {" "}Close the cycle when the week is done.
            </div>
          )}

          {detail.status === "open" && !detail.auto_build_minutes && (
            <div className="notice">
              This cycle only builds when you press <b>Build now</b>.
              {detail.last_built_at && ` Last built ${sinceText(detail.last_built_at)}.`}
            </div>
          )}

          {handedIn < 2 && (
            <div className="notice">
              {handedIn} profile{handedIn === 1 ? " has" : "s have"} handed in. At least two sheets
              are needed before anything can be compared.
            </div>
          )}

          {/* The cycle's own settings, while it is running.
              These used to be answerable only at the moment the cycle was
              opened — the moment a manager knows least, because not one sheet
              is in yet. A cap that turns out to be starving half the team meant
              closing the cycle and starting another, which threw away the work
              already logged against it. */}
          {settings && detail.status === "open" && (
            <div className="card pad stack" style={{ gap: 10 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <b style={{ fontFamily: "var(--display)" }}>Settings for this cycle</b>
                  <p className="muted" style={{ marginTop: 3, maxWidth: 620 }}>
                    Change these while it runs. The next build uses them, and nobody loses
                    anything: only jobs still sitting untouched are re-dealt, so a job somebody
                    has already marked applied or skipped stays on their list whatever the cap
                    now says.
                  </p>
                </div>
                <div className="row" style={{ gap: 8 }}>
                  {settingsChanged && (
                    <button className="ghost" disabled={busy} onClick={() => setSettings({
                      name: detail.name || "",
                      quota: detail.quota,
                      mode: detail.mode,
                      one_per_client: !!detail.one_per_client,
                      auto_build_minutes: detail.auto_build_minutes || 0,
                    })}>Undo</button>
                  )}
                  <button onClick={saveSettings} disabled={busy || !settingsChanged}>
                    {settingsChanged ? "Save settings" : "Saved"}
                  </button>
                </div>
              </div>

              <div className="row">
                <label>
                  Name
                  <input value={settings.name} style={{ minWidth: 180, marginLeft: 6 }}
                         onChange={(e) => setSettings({ ...settings, name: e.target.value })} />
                </label>
                <label>
                  Cap per profile
                  <input type="number" min="1" max="1000" value={settings.quota}
                         style={{ width: 80, marginLeft: 6 }}
                         onChange={(e) => setSettings({ ...settings, quota: e.target.value })} />
                </label>
                <label>
                  <input type="checkbox" checked={settings.one_per_client}
                         onChange={(e) => setSettings({ ...settings, one_per_client: e.target.checked })} />
                  One job per client, per profile
                </label>
                <label>
                  Rebuild lists
                  <select value={settings.auto_build_minutes} style={{ marginLeft: 6 }}
                          onChange={(e) => setSettings({ ...settings, auto_build_minutes: e.target.value })}>
                    <option value={5}>every 5 minutes</option>
                    <option value={10}>every 10 minutes</option>
                    <option value={15}>every 15 minutes</option>
                    <option value={30}>every 30 minutes</option>
                    <option value={0}>only when I ask</option>
                  </select>
                </label>
                <label>
                  Dealing
                  <select value={settings.mode} style={{ marginLeft: 6 }}
                          onChange={(e) => setSettings({ ...settings, mode: e.target.value })}>
                    <option value="cover">cover every profile</option>
                    <option value="split">split the pool</option>
                  </select>
                </label>
              </div>

              {settingsChanged && settings.mode !== detail.mode && (
                <p className="hint">
                  Changing how the pool is dealt only moves jobs nobody has started.
                  {settings.mode === "split"
                    ? " From the next build each job goes to one profile."
                    : " From the next build every profile gets back everything it has not tried."}
                </p>
              )}
            </div>
          )}

          {/* The clock. One for the whole cycle, not one per person: it is the
              window this cycle is meant to be worked in, so everybody sees the
              same number and "two hours" means the same thing to all of them.
              It changes nothing when it runs out — that is the point of the
              figures underneath, which are worth knowing rather than
              enforcing. */}
          <div className="card pad stack" style={{ gap: 10 }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <b style={{ fontFamily: "var(--display)" }}>Clock on this cycle</b>
                <p className="muted" style={{ marginTop: 3, maxWidth: 620 }}>
                  A countdown on every BD&apos;s screen for this cycle. Nothing stops when
                  it reaches zero — sheets still come in and jobs are still marked. The
                  clock simply leaves their screen, and what each profile did inside the
                  window shows up here.
                </p>
              </div>
              {detail.timer_minutes > 0 && detail.timer_running && <CycleClock batch={detail} />}
            </div>

            {detail.timer_minutes > 0 ? (
              <>
                <div className="row" style={{ gap: 8 }}>
                  <span className={detail.timer_running ? "pill on" : "pill"}>
                    {detail.timer_minutes} minute window
                  </span>
                  <span className="muted">
                    {/* No second copy of the countdown here. The pill above
                        ticks every second and this only re-reads on the poll,
                        so the two would sit side by side disagreeing. */}
                    {detail.timer_running
                      ? <>started {sinceText(detail.timer_started_at)}</>
                      : <>time was up {sinceText(detail.timer_ends_at)}</>}
                  </span>
                  <span style={{ flex: 1 }} />
                  <button className="ghost" onClick={() => moveClock(15)} disabled={busy}>
                    Add 15 min
                  </button>
                  <button className="ghost" onClick={() => moveClock(-15)} disabled={busy}>
                    Take 15 min
                  </button>
                  <button className="ghost" onClick={clearClock} disabled={busy}>
                    Clear
                  </button>
                </div>
                {!detail.timer_running && (
                  <p className="hint" style={{ margin: 0 }}>
                    Adding time to a clock that has already run out restarts the countdown
                    on everyone&apos;s screen from wherever the new window ends.
                  </p>
                )}
              </>
            ) : (
              <div className="row" style={{ gap: 8 }}>
                <label>
                  Give this cycle
                  <input type="number" min="1" max="10080" value={timerDraft} style={{ width: 90 }}
                         onChange={(e) => setTimerDraft(e.target.value)} />
                  minutes
                </label>
                {[[30, "30 min"], [60, "1 hour"], [120, "2 hours"], [240, "4 hours"]].map(
                  ([mins, label]) => (
                    <button key={mins} className="pill" type="button"
                            onClick={() => setTimerDraft(mins)}>{label}</button>
                  ))}
                <button onClick={startClock} disabled={busy}>Start the clock</button>
              </div>
            )}

            {figures?.profiles?.length > 0 && (
              <div className="stack" style={{ gap: 6 }}>
                <b>{figures.timer_running ? "So far, inside the window" : "What the window caught"}</b>
                <p className="hint" style={{ margin: 0, maxWidth: 660 }}>
                  Dated by when somebody actually marked something, so this is the work
                  done between the clock starting and the time running out — not what the
                  cycle holds in total. <b>Late</b> is the same work finished after the
                  whistle, counted rather than hidden: a profile that got everything done
                  twenty minutes over is a different story from one that stopped.
                </p>
                <div className="card scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Profile</th><th>Run by</th>
                        <th className="num">Own jobs</th>
                        <th className="num">Others&apos; jobs applied for</th>
                        <th className="num">Others&apos; jobs skipped</th>
                        <th className="num">Left</th>
                        <th className="num">Late</th>
                        <th className="num">Done</th>
                      </tr>
                    </thead>
                    <tbody>
                      {figures.profiles.map((row) => (
                        <React.Fragment key={row.id}>
                          <tr>
                            <td style={{ fontWeight: 500 }}>{row.name}</td>
                            <td className="muted">{row.person || "—"}</td>
                            <td className="num mono">{row.own_jobs}</td>
                            <td className="num mono">{row.applied}</td>
                            {/* The one figure on this table with a reason
                                behind it. A manager reading "12 skipped" is
                                being asked to judge somebody's week on a
                                number; the words are one press away. */}
                            <td className="num mono">
                              {row.skipped ? (
                                <button type="button" className="link"
                                        aria-expanded={openSkips === row.id}
                                        onClick={() => setOpenSkips(
                                          (now) => (now === row.id ? null : row.id))}>
                                  {row.skipped}
                                </button>
                              ) : row.skipped}
                            </td>
                            <td className="num mono">{row.left}</td>
                            <td className="num mono"
                                style={{ color: row.late ? "var(--bad-text)" : undefined }}>
                              {row.late}
                            </td>
                            <td className="num mono">{row.done_pct}%</td>
                          </tr>
                          {openSkips === row.id && (
                            <tr>
                              <td colSpan={8} style={{ padding: "6px 10px 12px" }}>
                                {/* The clock's own window, to the second.
                                    The figure above counts what happened
                                    inside it, and a list rounded out to whole
                                    days would not add up to the number that
                                    was pressed. */}
                                <Skipped batchId={current} profileId={row.id}
                                         since={figures.started_at}
                                         until={figures.ends_at} />
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          <div className="card scroll">
            <table>
              <thead>
                <tr><th>Profile</th><th>Headline</th><th>Run by</th><th>File</th>
                    <th title="Rows the matcher can read a job from. A file row with no link and no client is not one.">Usable rows</th>
                    <th>Link column</th></tr>
              </thead>
              <tbody>
                {detail.uploads.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 500 }}>{u.profile}</td>
                    <td className="muted">{u.headline || "—"}</td>
                    <td>{u.person}</td>
                    <td className="mono truncate" style={{ fontSize: 12 }}>{u.filename}</td>
                    <td className="mono">
                      {u.usable_count ?? u.row_count}
                      {u.usable_count != null && u.row_count > u.usable_count && (
                        <span className="muted" style={{ fontSize: 11 }}>
                          {" "}of {u.row_count}
                        </span>
                      )}
                    </td>
                    <td>
                      {u.mapping?.url
                        ? <span className="pill on">{u.mapping.url}</span>
                        : <span className="pill off">falling back to client + title</span>}
                    </td>
                  </tr>
                ))}
                {!detail.uploads.length && (
                  <tr><td colSpan={6} className="muted">Nobody has handed in yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {report?.report && Object.keys(report.report).length > 0 && (
        <section className="stack" style={{ gap: 14 }}>
          <h2>What the comparison found</h2>
          <div className="stats">
            {Object.entries(report.report).map(([label, value]) => (
              <div className="stat" key={label}>
                <b style={{ color: /Duplicate|2 or more/.test(label) ? "var(--brick)" : "var(--ink)" }}>{value}</b>
                <span>{label}</span>
              </div>
            ))}
          </div>

          {report.matrix?.names?.length > 1 && (
            <div>
              <h3>Which profiles are stepping on each other</h3>
              <p className="hint" style={{ marginTop: 3 }}>
            Jobs both profiles applied to. Dark means near-identical searches.
          </p>
              <Matrix names={report.matrix.names} rows={report.matrix.rows} />
            </div>
          )}

          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3>Lists going out</h3>
            <button className="go" onClick={() =>
              download(`/batches/${current}/report.xlsx`, "dispatch.xlsx")
                .catch((err) => setNote({ bad: true, text: err.message }))}>
              Download everything as one workbook
            </button>
          </div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))" }}>
            {report.participants.map((p) => (
              <div className="card pad" key={p.id} style={{ borderTop: `3px solid ${p.assigned ? "var(--pine)" : "var(--rule)"}` }}>
                <div style={{ fontFamily: "var(--display)", fontWeight: 600 }}>{p.name}</div>
                <div className="muted" style={{ marginTop: 2 }}>{p.headline || "—"}</div>
                <div className="mono" style={{ fontSize: 25, fontWeight: 500, marginTop: 6 }}>{p.pending}</div>
                <div className="muted">
                  others&apos; jobs · {p.assigned} handed over in all{p.person ? ` · ${p.person}` : ""}
                </div>
              </div>
            ))}
          </div>

          {report.collisions?.length > 0 && (
            <div>
              <h3>Jobs more than one profile already applied to</h3>
              <p className="muted" style={{ margin: "3px 0 9px" }}>
                Two of your profiles reached the same client this cycle. Showing the
                {" "}{Math.min(report.collisions.length, 50)} worst.
              </p>
              <div className="card scroll">
                <table>
                  <thead>
                    <tr><th>Job</th><th>Company</th><th>Applied by</th></tr>
                  </thead>
                  <tbody>
                    {report.collisions.slice(0, 50).map((c, i) => (
                      <tr key={i}>
                        <td className="truncate">
                          {safeUrl(c.url)
                            ? <a href={safeUrl(c.url)} target="_blank" rel="noreferrer noopener">{c.title || c.url}</a>
                            : (c.title || "—")}
                        </td>
                        <td>{c.company || "—"}</td>
                        <td style={{ color: "var(--brick)", fontWeight: 500 }}>{c.applied_by.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {report.turned_down?.length > 0 && (
            <div>
              <h3>Skipped, and why</h3>
              <p className="muted" style={{ margin: "3px 0 9px" }}>
                A skip retires the posting from that profile for good — no later
                cycle offers it again — so this is the only place the reasoning
                is visible. Read together rather than one at a time: a run of
                "wrong seniority" against one profile is usually something about
                the searches feeding it, not about the postings.
              </p>
              <div className="card scroll">
                <table>
                  <thead>
                    <tr><th>Job</th><th>Company</th><th>Profile</th><th>Reason</th><th>When</th></tr>
                  </thead>
                  <tbody>
                    {report.turned_down.slice(0, 100).map((t, i) => (
                      <tr key={i}>
                        <td className="truncate" style={{ maxWidth: 260 }}>
                          {safeUrl(t.url)
                            ? <a href={safeUrl(t.url)} target="_blank" rel="noreferrer noopener">{t.title || t.url}</a>
                            : (t.title || "—")}
                        </td>
                        <td>{t.company || "—"}</td>
                        <td><b>{t.profile}</b></td>
                        <td style={{ maxWidth: 320 }}>{t.reason || <span className="muted">no reason recorded</span>}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{t.when || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {report.turned_down.length > 100 && (
                <p className="hint">Showing 100 of {report.turned_down.length}.</p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
